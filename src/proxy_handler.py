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
from fake_useragent import UserAgent
from colorama import Fore, Style

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Suppress fake_useragent warnings
logging.getLogger('fake_useragent').setLevel(logging.ERROR)

# Initialize UserAgent
try:
    ua = UserAgent()
    ua.random  # Test generation
except:
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
    ]
    ua = type('', (), {'random': lambda: random.choice(USER_AGENTS)})()

# Configuration
PROXY_SOURCES = [
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
    "https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc",
    "https://proxik.cloud/proxy_list?type=http"
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
    for attempt in range(max_retries):
        try:
            await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
            async with session.get(
                url,
                headers=get_random_headers(),
                timeout=TIMEOUT,
                ssl=False
            ) as response:
                if response.status == 200:
                    return await response.text()
        except Exception as e:
            logger.debug(f"Attempt {attempt+1} failed for {url}: {str(e)}")
            await asyncio.sleep(random.uniform(0.5, 1.5))
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
    connector = TCPConnector(limit=MAX_CONCURRENT_TASKS, ssl=False)
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
                            timeout=TIMEOUT,
                            ssl=False
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

async def scrape_proxies():
    """Main function to scrape and validate proxies with multiprocessing."""
    logger.info(f"{Fore.CYAN}Starting proxy scraping with {CPU_CORES} processes...{Style.RESET_ALL}")
    
    # Step 1: Fetch all proxies
    connector = TCPConnector(limit=20, ssl=False)
    async with ClientSession(connector=connector) as session:
        tasks = [fetch_proxies_from_source(session, url) for url in PROXY_SOURCES]
        results = await asyncio.gather(*tasks)
        all_proxies = set().union(*results)
        logger.info(f"Found {len(all_proxies)} raw proxies")
        
        if not all_proxies:
            return []
        
        # Step 2: Prepare for multiprocessing validation
        proxy_list = list(all_proxies)
        random.shuffle(proxy_list)
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
        os.makedirs("config", exist_ok=True)
        with open("config/valid_proxies.txt", "w") as f:
            f.write("\n".join(valid_proxies))
        
        return valid_proxies
