# src/proxy_handler.py
import asyncio
import logging
import re
import random
import time
import json
import os
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from aiohttp import ClientSession, ClientConnectorError, ClientProxyConnectionError, TCPConnector
from bs4 import BeautifulSoup
from colorama import Fore, Style

# Configure logging
logger = logging.getLogger(__name__)

# User agents are a fixed local list: importing the package must not make a
# network request, and a fake-useragent download is one more thing to fail.
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0",
]


class _LocalAgents:
    @property
    def random(self) -> str:
        return random.choice(USER_AGENTS)


ua = _LocalAgents()

# Configuration
PROXY_SOURCES = [
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
    "https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc"
]

TEST_URLS = [
    "http://httpbin.org/ip",
    "http://example.com",
    "http://icanhazip.com"
]

# Performance tuning
TIMEOUT = 10
MAX_CONCURRENT_TASKS = 50  # Per process
MIN_DELAY = 0.1
MAX_DELAY = 0.5
MAX_VALIDATION_PROXIES = 200  # Check more to find working ones
MAX_RETRIES = 2
CPU_CORES = max(1, multiprocessing.cpu_count() - 1)  # Leave one core free

def get_random_headers():
    """Generate random headers with proper UserAgent handling."""
    return {
        'User-Agent': ua.random,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive'
    }

async def fetch_with_retry(session, url, max_retries=MAX_RETRIES):
    """Fetch content with retries and random delays."""
    last_error = RuntimeError("No fetch attempts made")
    for attempt in range(max_retries):
        try:
            await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
            async with session.get(
                url,
                headers=get_random_headers(),
                timeout=TIMEOUT
            ) as response:
                if response.status == 200:
                    return await response.text()
                last_error = RuntimeError(f"Unexpected HTTP {response.status}")
        except Exception as e:
            last_error = e
            logger.debug(f"Attempt {attempt+1} failed for {url}: {str(e)}")
        if attempt + 1 < max_retries:
            await asyncio.sleep(random.uniform(0.5, 1.5))
    logger.warning("Proxy source fetch failed for %s after %d attempts: %s: %s",
                   url, max_retries, type(last_error).__name__, last_error)
    return None

async def fetch_proxies_from_source(session, url):
    """Fetch proxies from a single source URL."""
    content = await fetch_with_retry(session, url)
    if not content:
        return set()
    
    try:
        if "geonode" in url:
            data = json.loads(content)
            return {f"{p['ip']}:{p['port']}" for p in data['data']}
        elif "raw.githubusercontent" in url:
            return set(line.strip() for line in content.split('\n') if re.match(r'\d+\.\d+\.\d+\.\d+:\d+', line))
        else:
            return parse_proxies(content)
    except Exception as e:
        logger.error(f"Error processing {url}: {str(e)}")
        return set()

def parse_proxies(html):
    """Parse HTML content to extract proxies."""
    proxies = set()
    try:
        soup = BeautifulSoup(html, 'html.parser')
        for row in soup.find_all('tr'):
            cols = [col.text.strip() for col in row.find_all('td')]
            if len(cols) >= 2 and re.match(r'\d+\.\d+\.\d+\.\d+', cols[0]):
                proxies.add(f"{cols[0]}:{cols[1]}")
    except Exception as e:
        logger.error(f"Error parsing HTML: {str(e)}")
    return proxies

async def validate_proxy_batch(proxy_batch):
    """Validate a batch of proxies (async for single process)."""
    connector = TCPConnector(limit=MAX_CONCURRENT_TASKS)
    async with ClientSession(connector=connector) as session:
        valid_proxies = []
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
        
        async def validate(proxy):
            async with semaphore:
                for attempt in range(MAX_RETRIES):
                    try:
                        await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
                        test_url = random.choice(TEST_URLS)
                        async with session.get(
                            test_url,
                            proxy=f"http://{proxy}",
                            headers=get_random_headers(),
                            timeout=TIMEOUT
                        ) as response:
                            if response.status == 200:
                                content = await response.text()
                                if proxy.split(':')[0] in content:
                                    valid_proxies.append(proxy)
                                    logger.info(f"{Fore.GREEN}Valid proxy: {proxy}{Style.RESET_ALL}")
                                    return True
                    except Exception:
                        continue
            return False
        
        await asyncio.gather(*[validate(proxy) for proxy in proxy_batch])
        return valid_proxies

def validate_proxy_wrapper(proxy_batch):
    """Wrapper for multiprocessing."""
    return asyncio.run(validate_proxy_batch(proxy_batch))

async def scrape_proxies(output: str | os.PathLike = "config/valid_proxies.txt",
                         validate: bool = True, limit: int | None = None):
    """Harvest proxies, optionally validate them, and save the pool.

    Nothing calls this unless the user asks for proxies: a fresh install must
    search without downloading a third-party list first.
    """
    logger.info(f"{Fore.CYAN}Starting proxy scraping with {CPU_CORES} processes...{Style.RESET_ALL}")
    
    # Step 1: Fetch all proxies
    connector = TCPConnector(limit=20)
    async with ClientSession(connector=connector) as session:
        tasks = [fetch_proxies_from_source(session, url) for url in PROXY_SOURCES]
        results = await asyncio.gather(*tasks)
        all_proxies = set().union(*results)
        logger.info(f"Found {len(all_proxies)} raw proxies")
        
        if not all_proxies:
            return []

        proxy_list = list(all_proxies)
        random.shuffle(proxy_list)
        if limit is not None:
            proxy_list = proxy_list[:max(1, int(limit))]

        if not validate:
            valid_proxies = proxy_list
        else:
            # Step 2: Prepare for multiprocessing validation
            validation_proxies = proxy_list[:MAX_VALIDATION_PROXIES]

            # Split proxies into batches for each process
            batch_size = max(1, len(validation_proxies) // CPU_CORES)
            batches = [validation_proxies[i:i + batch_size] for i in range(0, len(validation_proxies), batch_size)]

            logger.info(f"Validating {len(validation_proxies)} proxies across {CPU_CORES} processes...")

            # Step 3: Parallel processing
            with ProcessPoolExecutor(max_workers=CPU_CORES) as executor:
                results = list(executor.map(validate_proxy_wrapper, batches))

            # Combine results
            valid_proxies = []
            for batch_result in results:
                valid_proxies.extend(batch_result)

        logger.info(f"{Fore.GREEN}Found {len(valid_proxies)} valid proxies{Style.RESET_ALL}")

        # Save valid proxies
        target = os.fspath(output)
        parent = os.path.dirname(os.path.abspath(target))
        os.makedirs(parent, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write("\n".join(valid_proxies))

        return valid_proxies
