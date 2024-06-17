import asyncio
import logging
import httpx
import time
from bs4 import BeautifulSoup
from colorama import Fore, Style, init
from tqdm import tqdm

# Initialize colorama
init(autoreset=True)

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# List of proxy source URLs
proxy_sources = [
    "https://www.proxy-list.download/HTTP",
    "https://free-proxy-list.net/",
    "https://www.sslproxies.org/",
    "https://www.us-proxy.org/",
    "https://www.socks-proxy.net/"
]
async def scrape_proxies_from_url(url):
    proxies = []
    async with httpx.AsyncClient() as session:
        try:
            response = await session.get(url)
            if response.status_code == 200:
                html = response.text
                soup = BeautifulSoup(html, 'html.parser')
                tbody = soup.find('tbody')
                if tbody:
                    for tr in tbody.find_all('tr'):
                        tds = tr.find_all('td', limit=2)
                        if len(tds) == 2:
                            ip_address = tds[0].get_text(strip=True)
                            port = tds[1].get_text(strip=True)
                            proxy = f"{ip_address}:{port}"
                            proxies.append(proxy)
                    logger.info(f"🎃 Proxies scraped successfully from {url}. Total: {len(proxies)}")
                else:
                    logger.error(f"👻 Proxy list not found in the response from {url}.")
            else:
                logger.error(f"🧟 Failed to retrieve proxy list from {url}. Status code: {response.status_code}")
        except Exception as e:
            logger.error(f"👻 Error scraping proxies from {url}: {e}")
    return proxies

async def scrape_proxies():
    all_proxies = []
    tasks = [scrape_proxies_from_url(url) for url in proxy_sources]
    results = await asyncio.gather(*tasks)
    for proxies in results:
        all_proxies.extend(proxies)
    if not all_proxies:
        logger.error("👻 No proxies scraped from any source.")
    return all_proxies

async def validate_proxy(proxy, timeout=30):
    proxy_with_scheme = proxy if proxy.startswith("http") else f"http://{proxy}"
    try:
        async with httpx.AsyncClient(proxies={"http://": proxy_with_scheme}, timeout=timeout) as client:
            response = await client.get("https://www.google.com", timeout=timeout)
            if response.status_code == 200:
                return proxy_with_scheme
    except httpx.RequestError as e:
        logger.error(f"👻 Request error with proxy {proxy}: {e}")
    except httpx.TimeoutException:
        logger.error(f"👻 Timeout with proxy {proxy}")
    except Exception as e:
        logger.error(f"👻 Error validating proxy {proxy}: {e}")
    return None

async def check_proxy_stability(proxy, timeout=30):
    proxy_with_scheme = proxy if proxy.startswith("http") else f"http://{proxy}"
    try:
        async with httpx.AsyncClient(proxies={"http://": proxy_with_scheme}, timeout=timeout) as client:
            start_time = time.time()
            response = await client.get("https://www.google.com", timeout=timeout)
            end_time = time.time()
            ping_time = (end_time - start_time) * 1000  # Convert to milliseconds
            if response.status_code == 200 and ping_time < 1000:
                return proxy_with_scheme
    except httpx.RequestError as e:
        logger.error(f"👻 Request error with proxy {proxy}: {e}")
    except httpx.TimeoutException:
        logger.error(f"👻 Timeout with proxy {proxy}")
    except Exception as e:
        logger.error(f"👻 Error checking stability of proxy {proxy}: {e}")
    return None

async def validate_proxies_concurrently(proxies, limit=50, timeout=10):
    valid_proxies = []
    semaphore = asyncio.Semaphore(limit)

    async def process_proxy(proxy):
        async with semaphore:
            result = await validate_proxy(proxy, timeout)
            if result:
                valid_proxies.append(result)

    tasks = [process_proxy(proxy) for proxy in proxies]
    await asyncio.gather(*tasks)

    return valid_proxies

async def check_proxies_stability(proxies, limit=50, timeout=10):
    stable_proxies = []
    semaphore = asyncio.Semaphore(limit)

    async def process_proxy(proxy):
        async with semaphore:
            result = await check_proxy_stability(proxy, timeout)
            if result:
                stable_proxies.append(result)

    tasks = [process_proxy(proxy) for proxy in proxies]
    with tqdm(total=len(proxies), desc="Checking proxy stability") as pbar:
        for task in asyncio.as_completed(tasks):
            await task
            pbar.update(1)

    return stable_proxies

async def main():
    proxies = await scrape_proxies()
    valid_proxies = await validate_proxies_concurrently(proxies)
    stable_proxies = await check_proxies_stability(valid_proxies)

if __name__ == "__main__":
    asyncio.run(main())
