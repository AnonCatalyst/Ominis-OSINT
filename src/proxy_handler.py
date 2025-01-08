import asyncio
import logging
import ssl
import aiohttp
from bs4 import BeautifulSoup
from colorama import Fore, Style, init
import fake_useragent
from multiprocessing import Pool, cpu_count
import math

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

init()  # Initialize colorama

# Function to fetch proxies from a URL using aiohttp
async def fetch_proxies_from_site(session, proxy_url):
    proxies = []

    try:
        logger.info(f"🕸️ Scraping proxies from {Fore.RED}{proxy_url}{Style.RESET_ALL}")
        async with session.get(proxy_url) as response:
            if response.status == 200:
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                tbody = soup.find('tbody')
                if tbody:
                    for tr in tbody.find_all('tr')[:30]:  # Limiting to first 13 proxies for example
                        tds = tr.find_all('td', limit=2)
                        if len(tds) == 2:
                            ip_address = tds[0].get_text(strip=True)
                            port = tds[1].get_text(strip=True)
                            proxy = f"{ip_address}:{port}"
                            proxies.append(proxy)
                    logger.info(f"🎃 Proxies scraped successfully from {Fore.RED}{proxy_url}{Style.RESET_ALL}. Total: {Fore.GREEN}{len(proxies)}{Style.RESET_ALL}")
                else:
                    logger.error(f"👻 {Fore.RED}Proxy list not found in the response from {proxy_url}.{Style.RESET_ALL}")
            else:
                logger.error(f"🧟 {Fore.RED}Failed to retrieve proxy list from {proxy_url}. Status code: {Fore.YELLOW}{response.status}{Style.RESET_ALL}")
    except Exception as e:
        logger.error(f"👻 {Fore.RED}Error scraping proxies from {proxy_url}: {Style.RESET_ALL}{e}")

    return proxies

# Function to scrape proxies from multiple sources concurrently
async def scrape_proxies():
    proxy_urls = [
        "https://www.us-proxy.org/",
        "https://www.sslproxies.org/"
    ]
    
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_proxies_from_site(session, url) for url in proxy_urls]
        results = await asyncio.gather(*tasks)

    # Flatten the results list
    proxies = [proxy for sublist in results for proxy in sublist]

    if not proxies:
        logger.error(f"👻 {Fore.RED}No proxies scraped.{Style.RESET_ALL}")

    return proxies

# Function to validate proxies with SSL verification disabled
async def validate_proxies(proxies, validation_url="https://www.example.com/", timeout=10):
    valid_proxies = []
    ua = fake_useragent.UserAgent()

    # SSL context creation (no certificate validation)
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:  # Fixed SSL context usage
        tasks = []
        for proxy in proxies:
            proxy_with_scheme = proxy if proxy.startswith("http") else f"http://{proxy}"
            task = asyncio.create_task(validate_single_proxy(session, proxy_with_scheme, validation_url, ua, timeout))
            tasks.append(task)

        results = await asyncio.gather(*tasks)

    valid_proxies = [proxy for proxy, is_valid in results if is_valid]
    return valid_proxies

# Function to validate a single proxy with SSL verification disabled
async def validate_single_proxy(session, proxy, validation_url, ua, timeout):
    try:
        headers = {"User-Agent": ua.random}

        async with session.get(validation_url, headers=headers, proxy=proxy, timeout=timeout) as response:
            if response.status == 200:
                logger.info(f"✅ Proxy {Fore.CYAN}{proxy}{Fore.GREEN} is valid.{Style.RESET_ALL}")
                return proxy, True
            else:
                return proxy, False  # Do not log this error
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        return proxy, False  # Do not log this error

# Batch processing function
def process_in_batches(proxies, batch_size=10):
    num_batches = math.ceil(len(proxies) / batch_size)
    batches = [proxies[i * batch_size:(i + 1) * batch_size] for i in range(num_batches)]

    # Using multiprocessing Pool to validate each batch concurrently
    with Pool(cpu_count()) as pool:
        results = pool.map(validate_proxy_batch, batches)

    # Flatten the list of results and return all valid proxies
    return [proxy for sublist in results for proxy in sublist]

# Function to validate a batch of proxies
def validate_proxy_batch(proxy_batch):
    return asyncio.run(validate_proxies(proxy_batch))  # Ensure event loop is created

# Main function to run the program
async def main():
    proxies = await scrape_proxies()
    if proxies:
        logger.info(f"Total proxies scraped: {len(proxies)}")
        
        # Using batch processing to validate proxies
        valid_proxies = process_in_batches(proxies)
        logger.info(f"Total valid proxies found: {Fore.GREEN}{len(valid_proxies)}{Style.RESET_ALL}")
    else:
        logger.error(f"👻 {Fore.RED}No proxies found to validate.{Style.RESET_ALL}")

# Entry point of the script
if __name__ == "__main__":
    asyncio.run(main())
