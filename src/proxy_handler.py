import asyncio
import logging
import httpx
from bs4 import BeautifulSoup

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def scrape_proxies(proxy_url="https://www.proxy-list.download/HTTP"):
    proxies = []

    async with httpx.AsyncClient() as session:
        try:
            logger.info("🕸️ Scraping proxies...")
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
                    logger.info(f"🎃 Proxies scraped successfully. Total: {len(proxies)}")
                else:
                    logger.error("👻 Proxy list not found in the response.")
            else:
                logger.error(f"🧟 Failed to retrieve proxy list. Status code: {response.status_code}")
        except Exception as e:
            logger.error(f"👻 Error scraping proxies: {e}")

    return proxies

def validate_proxies(proxies, timeout=10):
    valid_proxies = []

    async def validate_proxy(proxy):
        proxy_with_scheme = proxy if proxy.startswith("http") else f"http://{proxy}"
        try:
            logger.info(f"🔍 Validating proxy: {proxy_with_scheme}")
            async with httpx.AsyncClient(proxies={proxy_with_scheme: None}, timeout=timeout) as client:
                response = await client.get("https://www.google.com", timeout=timeout)
                if response.status_code == 200:
                    return proxy_with_scheme
                    logger.info(f"✅ Proxy {proxy_with_scheme} is valid.")
                else:
                    logger.error(f"❌ Proxy {proxy_with_scheme} returned status code {response.status_code}.")
        except (httpx.TimeoutException, httpx.RequestError) as e:
            logger.error(f"👻 Error occurred while testing proxy {proxy_with_scheme}: {e}")

    loop = asyncio.get_event_loop()
    valid_proxies = loop.run_until_complete([validate_proxy(proxy) for proxy in proxies])
    valid_proxies = [proxy for proxy in valid_proxies if proxy is not None]

    return valid_proxies

if __name__ == "__main__":
    proxies = asyncio.run(scrape_proxies())
    valid_proxies = validate_proxies(proxies)
    print(valid_proxies)
