import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from colorama import Fore, Style, init
import fake_useragent

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

init()  # Initialize colorama

async def fetch_proxies_from_site(proxy_url):
    proxies = []

    async with httpx.AsyncClient() as session:
        try:
            logger.info(f"🕸️ Scraping proxies from {Fore.RED}{proxy_url}{Style.RESET_ALL}")
            response = await session.get(proxy_url)
            if response.status_code == 200:
                html = response.text
                soup = BeautifulSoup(html, 'html.parser')
                tbody = soup.find('tbody')
                if tbody:
                    for tr in tbody.find_all('tr')[:13]:  # Limiting to first 10 for example
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
                logger.error(f"🧟 {Fore.RED}Failed to retrieve proxy list from {proxy_url}. Status code: {Fore.YELLOW}{response.status_code}{Style.RESET_ALL}")
        except Exception as e:
            logger.error(f"👻 {Fore.RED}Error scraping proxies from {proxy_url}: {Style.RESET_ALL}{e}")

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
        logger.error(f"👻 {Fore.RED}No proxies scraped.{Style.RESET_ALL}")
        
    return proxies

async def validate_proxies(proxies, validation_url="https://www.example.com/", timeout=10):
    valid_proxies = []
    ua = fake_useragent.UserAgent()

    for proxy in proxies:
        proxy_with_scheme = proxy if proxy.startswith("http") else f"http://{proxy}"
        try:
            logger.info(f"🔍 Validating proxy: {Fore.LIGHTBLACK_EX}{proxy_with_scheme}{Style.RESET_ALL}")
            headers = {"User-Agent": ua.random}
            async with httpx.AsyncClient(proxies={proxy_with_scheme: None}, timeout=timeout) as client:
                response = await client.get(validation_url, headers=headers, timeout=timeout)
                if response.status_code == 200:
                    valid_proxies.append(proxy_with_scheme)
                    logger.info(f"✅ Proxy: {Fore.CYAN}{proxy_with_scheme} {Fore.GREEN}is valid.{Style.RESET_ALL}")
                else:
                    logger.error(f"❌ Proxy {Fore.CYAN}{proxy_with_scheme} returned status code {Fore.YELLOW}{response.status_code}.{Style.RESET_ALL}")
        except (httpx.TimeoutException, httpx.RequestError) as e:
            logger.error(f"👻 {Fore.RED}Error occurred while testing proxy {Fore.CYAN}{proxy_with_scheme}: {Style.RESET_ALL}{e}")
            
    return valid_proxies

async def main():
    proxies = await scrape_proxies()
    valid_proxies = await validate_proxies(proxies)
    logger.info(f"Total valid proxies found: {Fore.GREEN}{len(valid_proxies)}{Style.RESET_ALL}")

if __name__ == "__main__":
    asyncio.run(main())