import asyncio
import logging
import aiohttp
import fake_useragent
import time
from bs4 import BeautifulSoup
from multiprocessing import Pool

# Initialize logging
logging.basicConfig(level=logging.WARNING)  # Only show warnings and errors
logger = logging.getLogger(__name__)

async def fetch_proxies_from_site(proxy_url):
    proxies = []

    async with aiohttp.ClientSession() as session:
        try:
            logger.info(f"Scraping proxies from {proxy_url}")
            async with session.get(proxy_url) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    tbody = soup.find('tbody')
                    if tbody:
                        for tr in tbody.find_all('tr')[:13]:  # Limiting to first 13 for example
                            tds = tr.find_all('td', limit=2)
                            if len(tds) == 2:
                                ip_address = tds[0].get_text(strip=True)
                                port = tds[1].get_text(strip=True)
                                proxy = f"{ip_address}:{port}"
                                proxies.append(proxy)
                    else:
                        logger.error(f"Proxy list not found in the response from {proxy_url}.")
                else:
                    logger.error(f"Failed to retrieve proxy list from {proxy_url}. Status code: {response.status}")
        except Exception as e:
            logger.error(f"Error scraping proxies from {proxy_url}: {e}")

    return proxies

async def scrape_proxies():
    proxy_urls = [
        "https://www.us-proxy.org/",
        "https://www.sslproxies.org/"
    ]
    tasks = [fetch_proxies_from_site(url) for url in proxy_urls]
    results = await asyncio.gather(*tasks)
    
    # Flatten the results list
    proxies = [proxy for sublist in results for proxy in sublist]
    
    if not proxies:
        logger.error("No proxies scraped.")
        
    return proxies

async def validate_single_proxy(proxy, validation_url="https://www.example.com/", timeout=10):
    ua = fake_useragent.UserAgent()
    proxy_with_scheme = proxy if proxy.startswith("http") else f"http://{proxy}"
    try:
        headers = {"User-Agent": ua.random}
        async with aiohttp.ClientSession() as client:
            async with client.get(validation_url, proxy=proxy_with_scheme, headers=headers, timeout=timeout) as response:
                if response.status == 200:
                    return proxy_with_scheme
    except (asyncio.TimeoutError, aiohttp.ClientError):
        return None

def validate_proxies_in_batch(proxies_batch):
    # This function runs in a separate process for each batch of proxies
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Validate the proxies in the batch concurrently
    valid_proxies = loop.run_until_complete(asyncio.gather(
        *[validate_single_proxy(proxy) for proxy in proxies_batch]
    ))
    
    # Filter out None values and return the valid proxies
    return [proxy for proxy in valid_proxies if proxy is not None]

async def validate_proxies(proxies, batch_size=10, validation_url="https://www.example.com/", timeout=10):
    # Split the proxies into smaller batches for multiprocessing
    batches = [proxies[i:i + batch_size] for i in range(0, len(proxies), batch_size)]
    
    # Initialize the multiprocessing pool to validate proxies in parallel batches
    with Pool() as pool:
        start_time = time.time()
        results = pool.map(validate_proxies_in_batch, batches)
        valid_proxies = [proxy for batch in results for proxy in batch]
        end_time = time.time()
        
        # Speed and time statistics
        elapsed_time = end_time - start_time
        logger.info(f"Validation completed in {elapsed_time:.2f} seconds.")
        logger.info(f"Total valid proxies found: {len(valid_proxies)}")
        
    return valid_proxies

async def main():
    proxies = await scrape_proxies()
    valid_proxies = await validate_proxies(proxies)
    print(f"\nTotal valid proxies found: {len(valid_proxies)}")

if __name__ == "__main__":
    asyncio.run(main())
