import asyncio
import logging
import httpx
from bs4 import BeautifulSoup
from colorama import Fore, Style, init

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def scrape_proxies():
    proxies = []
    proxy_url = "https://www.proxy-list.download/HTTP"

    async with httpx.AsyncClient() as session:
        try:
            logger.info(f" 🕸️ Scraping proxies{Fore.RED}...{Style.RESET_ALL}")
            response = await session.get(proxy_url)
            if response.status_code == 200:
                html = response.text
                soup = BeautifulSoup(html, 'html.parser')
                tbody = soup.find('tbody', id='tabli')
                if tbody:
                    for tr in tbody.find_all('tr'):
                        tds = tr.find_all('td', limit=2)
                        if len(tds) == 2:
                            ip_address = tds[0].get_text(strip=True)
                            port = tds[1].get_text(strip=True)
                            proxy = f"{ip_address}:{port}"
                            proxies.append(proxy)
                    logger.info(f"🎃 Proxies scraped successfully{Fore.RED}. {Fore.BLUE}Total{Style.RESET_ALL}{Fore.RED}: {Fore.GREEN}{len(proxies)}{Style.RESET_ALL}")
                else:
                    logger.error(f"👻 {Fore.RED}Proxy list not found in the response.{Style.RESET_ALL}")
            else:
                logger.error(f"🧟 {Fore.RED}Failed to retrieve proxy list. Status code: {Fore.YELLOW}{response.status_code}{Style.RESET_ALL}")
        except Exception as e:
            logger.error(f"👻 {Fore.RED}Error scraping proxies: {Style.RESET_ALL}{e}")
            
    if not proxies:
        logger.error(f"👻 {Fore.RED}No proxies scraped.{Style.RESET_ALL}")
        
    return proxies

async def validate_proxies(proxies, timeout=10):
    valid_proxies = []

    for proxy in proxies:
        proxy_with_scheme = proxy if proxy.startswith("http") else f"http://{proxy}"
        try:
            logger.info(f"🔍 Validating proxy{Fore.RED}: {Fore.LIGHTBLACK_EX}{proxy_with_scheme}{Style.RESET_ALL}")
            async with httpx.AsyncClient(proxies={proxy_with_scheme: None}, timeout=timeout) as client:
                response = await client.get("https://www.google.com", timeout=timeout)
                if response.status_code == 200:
                    valid_proxies.append(proxy_with_scheme)
                    logger.info(f"✅ Proxy{Fore.RED}: {Fore.CYAN}{proxy_with_scheme} {Fore.GREEN}is valid{Fore.RED}.{Style.RESET_ALL}")
                else:
                    logger.error(f"❌ Proxy {Fore.CYAN}{proxy_with_scheme} returned status code {Fore.YELLOW}{response.status_code}{Fore.RED}.{Style.RESET_ALL}")
        except (httpx.TimeoutException, httpx.RequestError) as e:
            logger.error(f"👻 {Fore.RED}Error occurred while testing proxy {Fore.CYAN}{proxy_with_scheme}{Fore.RED}: {Style.RESET_ALL}{e}")
            
    return valid_proxies
