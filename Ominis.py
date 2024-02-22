import random
import asyncio
import os
import re
import json
import logging
import urllib.parse
import httpx
import aiohttp
from colorama import Fore, Style, init
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from httpx import TimeoutException, RequestError
from tenacity import Retrying, stop_after_attempt, wait_exponential, retry_if_exception_type

# Suppress InsecureRequestWarning
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

init(autoreset=True)  # Initialize colorama for colored output

DEFAULT_NUM_RESULTS = 300
MAX_RETRY_COUNT = 3

# Load social platform patterns from a JSON file
with open("src/social_platforms.json", "r") as json_file:
    social_platforms = json.load(json_file)


counter_emojis = ['💥', '🌀', '💣', '🔥', '💢', '💀', '⚡', '💫', '💥', '💢']
emoji = random.choice(counter_emojis)  # Select a random emoji for the counter


async def scrape_proxies():
    proxies = []
    proxy_url = "https://www.proxy-list.download/HTTP"

    async with aiohttp.ClientSession() as session:
        try:
            response = await session.get(proxy_url)
            if response.status == 200:
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                tbody = soup.find('tbody', id='tabli')
                if tbody:
                    for tr in tbody.find_all('tr'):
                        tds = tr.find_all('td', limit=2)  # Limit the number of TDs to 2
                        if len(tds) == 2:  # Ensure IP address and port are present
                            ip_address = tds[0].get_text(strip=True)
                            port = tds[1].get_text(strip=True)
                            proxy = f"{ip_address}:{port}"
                            proxies.append(proxy)
                    logger.info(f"{Fore.RED} [{Fore.GREEN}+{Fore.RED}]{Fore.WHITE} Proxies scraped successfully{Fore.RED}. {Fore.BLUE}Total{Fore.YELLOW}:{Fore.GREEN} {len(proxies)}")
                else:
                    logger.error(f" Proxy list not found in the response.")
            else:
                logger.error(f" Failed to retrieve proxy list. Status code: {response.status}")

        except Exception as e:
            logger.error(f" Error scraping proxies: {e}")
    if not proxies:
        logger.error(f" No proxies scraped. Exiting...")


    # Filter out invalid characters from the proxy list
    valid_proxies = []
    for proxy in proxies:
        try:
            url = urllib.parse.urlparse(f"http://{proxy}")
            valid_proxies.append(proxy)
        except ValueError:
            logger.warning(f" Invalid proxy: {proxy}")
    return valid_proxies


async def make_request_async(url, proxies=None):
    retry_count = 0
    while retry_count < MAX_RETRY_COUNT:
        try:
            async with httpx.AsyncClient() as client:
                if proxies:
                    proxy = random.choice(proxies)
                    logger.info(f" {Fore.RED}[{Fore.YELLOW}!{Fore.RED}]{Fore.WHITE} Using proxy{Fore.YELLOW}:{Fore.CYAN} {proxy}{Fore.WHITE}")
                    client.proxies = {"http://": proxy}
                client.headers = {"User-Agent": UserAgent().random}
                response = await client.get(url, timeout=5)
                
                # Handle redirect
                if response.status_code == 302:
                    redirect_location = response.headers.get('location')
                    if redirect_location:
                        logger.info(f" Redirecting to: {redirect_location}")
                        return await make_request_async(redirect_location, proxies)
                
                response.raise_for_status()
                return response.text
            
        except httpx.RequestError as e:
            logger.error(f" Failed to make connection: {e}")
                
            retry_count += 1
            logger.info(f" Retrying request {retry_count}/{MAX_RETRY_COUNT}...")
            await asyncio.sleep(5 * retry_count)  # Increase delay with each retry

    logger.info(f" Final retry using DuckDuckGo...")
    return await fetch_ddg_results(url)


async def fetch_ddg_results(query):
    ddg_url = f"https://duckduckgo.com/html/?q={query}"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(ddg_url, timeout=10)
            response.raise_for_status()
            return response.text
    except httpx.RequestError as e:
        logger.error(f" Failed to make connection using DuckDuckGo: {e}")
        return None


async def fetch_google_results(query, proxies=None):
    all_mention_links = []
    all_unique_social_profiles = set()

    for start_index in range(0, DEFAULT_NUM_RESULTS):
        google_search_url = f"https://www.google.com/search?q={query}&start={start_index}"

        response_text = await make_request_async(google_search_url, proxies)
        if response_text is None:
            logger.error(f" Google search failed.")
            continue

        # Check if Google detected too many requests (status code 429)
        if "www.google.com/sorry/index?continue=" in response_text:
            logger.warning(" Google detected too many requests. Retrying with DuckDuckGo...")
            response_text = await fetch_ddg_results(query)
            if response_text is None:
                logger.error(" DuckDuckGo search failed.")
                continue

        soup = BeautifulSoup(response_text, "html.parser")
        search_results = soup.find_all("div", class_="tF2Cxc")

        if not search_results:
            logger.info(f" {Fore.RED}x No more results found for the query {Fore.BLUE}'{query}'{Fore.WHITE}")
            break

        for index, result in enumerate(search_results, start=start_index + 1):
            title = result.find("h3")
            url = result.find("a")["href"] if result.find("a") else None

            if title and url:
                emoji = random.choice(counter_emojis)  # Select a random emoji for the counter
                logger.info(Style.BRIGHT + f"{Fore.WHITE}_" * 80)
                logger.info(f" {emoji} {Fore.BLUE}Title{Fore.YELLOW}:{Fore.WHITE} {title.text.strip()}{Fore.WHITE}")
                logger.info(f" {emoji} {Fore.BLUE}URL{Fore.YELLOW}:{Fore.LIGHTBLACK_EX} {url}{Fore.WHITE}")

                text_to_check = title.text + ' ' + url
                mention_count = extract_mentions(text_to_check, query)

                for q, count in mention_count.items():
                    if count > 0:
                        logger.info(f" {emoji} {Fore.YELLOW}'{q}' {Fore.CYAN}Detected in {Fore.MAGENTA}Title{Fore.RED}/{Fore.MAGENTA}Url{Fore.YELLOW}:{Fore.GREEN} {url}{Fore.WHITE}")
                        all_mention_links.append({"url": url, "count": count})

                social_profiles = find_social_profiles(url)
                if social_profiles:
                    for profile in social_profiles:
                        logger.info(f" {Fore.BLUE}{profile['platform']}{Fore.YELLOW}:{Fore.GREEN} {profile['profile_url']}")
                        all_unique_social_profiles.add(profile['profile_url'])

                await asyncio.sleep(2)  # Introduce delay between requests

    if not all_mention_links:
        logger.info(f" {Fore.RED}Google search failed to find any mentions of {Fore.BLUE}'{query}'{Fore.RED}.{Fore.WHITE}")
    else:
        logger.info(f"\n >| {Fore.RED}- {Fore.WHITE}Mentions{Fore.YELLOW}:{Fore.GREEN} {mention['count']}{Fore.WHITE}")
        logger.info(f" >| {Fore.WHITE}All mentions found for{Fore.BLUE} '{query}'{Fore.YELLOW}:{Fore.GREEN}")
        for mention in all_mention_links:
            logger.info(f"\n >| {Fore.RED}-{Fore.GREEN} {mention['url']}{Fore.WHITE}")

    if all_unique_social_profiles:
        logger.info(f" >| {Fore.WHITE}Unique Social Profiles found{Fore.YELLOW}:{Fore.WHITE}")
        for profile_url in all_unique_social_profiles:
            logger.info(f" {Fore.GREEN}{profile_url}{Fore.WHITE}")

    logger.info(f" \n{Fore.RED}/{Fore.GREEN} Process completed successfully.")

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def find_social_profiles(url):
    if not isinstance(url, str):
        raise ValueError(" URL must be a string")

    profiles = []

    for platform, pattern in social_platforms.items():
        match = re.search(pattern, url)
        if match:
            profile_url = match.group(0)
            profiles.append({"platform": platform, "profile_url": profile_url})

    if is_potential_forum(url):
        profiles.append({"platform": "Forum", "profile_url": url})

    return profiles
def extract_mentions(text, query):
    if not isinstance(text, str) or not text:
        raise ValueError(" Input 'text' must be a non-empty string.")
    
    if isinstance(query, str):
        query = [query]
    elif not isinstance(query, list) or not all(isinstance(q, str) for q in query):
        raise ValueError(" Input 'query' must be a string or a list of strings.")

    mention_count = {q: len(re.findall(re.escape(q), text, re.IGNORECASE)) for q in query}
    return mention_count

async def main():
    clear_screen()
    print(f"""{Fore.RED}
⠀⢰⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣦⠀
⢀⣿⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣿⡄
⣜⢸⣧⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣸⡏⢣
⡿⡀⢿⣆⠀⠀⠀⠀⠀⠀⣀⣀⣀⣀⣀⣀⠀⠀⠀⠀⠀⠀⣰⣿⠀⣿
⣇⠁⠘⡌⢷⣀⣠⣴⣾⣟⠉⠉⠉⠉⠉⠉⣻⣷⣦⣄⣀⡴⢫⠃⠈⣸
⢻⡆⠀⠀⠀⠙⠻⣶⢝⢻⣧⡀⠀⠀⢀⣴⡿⡫⣶⠞⠛⠁⠀⠀⣰⡿
⠀⠳⡀⠢⡀⠀⠀⠸⡇⢢⠹⡌⠀⠀⢉⠏⡰⢱⡏⠀⠀⢀⡰⢀⡞⠁
⠀⢀⠟⢦⣈⠲⢌⣲⣿⠀⠀⢱⠀⠀⠜⠀⠁⣾⢒⣡⠔⢉⡴⠻⡄⠀
⠀⢸⠀⠀⣈⣻⣞⡛⠛⢤⡀⠀⠀⠀⠀⢀⡠⠟⢛⣓⣟⣉⠀⠀⣧⠀
⠀⢸⣶⢸⣍⡉⠉⠣⡀⠀⠈⢳⣠⣄⡜⠁⠀⢀⡴⠋⠉⠉⡏⢸⡿⠀
⠀⠈⡏⢸⡜⣿⠑⢤⡘⠲⠤⠤⣿⣿⠤⠤⠔⠋⡠⠊⣿⣃⡆⢸⠁⠀
⠀⢀⡿⠋⠙⠿⢷⣤⣹⣦⣀⣠⣼⣧⣄⣀⣠⣎⣤⡾⠿⠋⠙⢺⡄⠀
⠀⠘⣷⠀⠀⢠⠆⠈⢙⡛⢯⣤⠀⠐⣤⡽⠛⠋⠁⠐⡄⠀⢀⣾⠇⠀
⠀⠀⠘⣷⣀⡇⠀⢀⡀⣈⡆⢠⠀⠀⠀⢰⣇⡀⠀⠀⢸⣀⣼⠏⠀⠀
⠀⠀⠀⣸⡿⣷⣞⠋⠉⢹⠁⢈⠀⠀⠀⠀⡏⠉⠙⣲⣾⢿⣇⠀⠀⠀{Fore.YELLOW}~ {Fore.WHITE}Ominis Osint {Fore.YELLOW}- {Fore.RED}[{Fore.WHITE}Secure Web-history Search{Fore.RED}]
⠀⠀⠀⣿⡇⣿⣿⢿⣆⠈⠻⣆⢣⡴⢱⠟⠁⣰⡶⣿⣿⠘⣿⠀⠀⠀{Fore.RED}---------------------------------------
⠀⠀⠀⠹⣆⢈⡿⢸⣿⣻⠦⣼⣦⣴⣯⠴⣞⣿⡇⢻⡇⢸⠏⠀⠀⠀{Fore.YELLOW}~ {Fore.CYAN}Developer{Fore.YELLOW}: {Fore.WHITE} AnonCatalyst {Fore.MAGENTA}<{Fore.RED}
⠀⠀⠀⠀⠘⣞⣠⢾⣿⣿⣶⣿⣼⣧⣼⣶⣿⣿⡷⢌⢻⡋⠀⠀⠀ {Fore.RED}--------------------------------------- 
⠀⠀⠀⠀⠘⠉⢿⡀⣹⣿⣿⣿⣿⣿⣿⣿⣿⢏⢁⡼⠋⠃⠀⠀⠀⠀{Fore.YELLOW}~ {Fore.CYAN}Github{Fore.YELLOW}:{Fore.BLUE} https://github.com/AnonCatalyst/{Fore.RED}
⠀⠀⠀⠀⠀⠀⠈⢻⡟⢿⣿⣿⣿⣿⣿⣿⡿⢸⡟⠁⠀⠀⠀⠀⠀⠀{Fore.RED}--------------------------------------- 
⠀⠀⠀⠀⠀⠀⠀⠀⢿⡈⢿⣿⣿⣿⣽⡿⠁⣿⠀⠀⠀⠀⠀⠀⠀⠀{Fore.YELLOW}~ {Fore.CYAN}Instagram{Fore.YELLOW}:{Fore.BLUE} https://www.instagram.com/istoleyourbutter/{Fore.RED}
⠀⠀⠀⠀⠀⠀⠀⠀⠘⠳⢦⣬⠿⠿⣡⣤⠾⠃⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠳⠦⠴⠞⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀""")
    print("\n" + f"{Fore.RED}_" * 80 + "\n")
    
    proxies = await scrape_proxies()
    if not proxies:
        logger.error(f" {Fore.RED}No proxies scraped. Exiting...")
        return
    else:
        logger.info(f" {Fore.RED}[{Fore.GREEN}+{Fore.RED}]{Fore.WHITE} Beginning proxy validation for proxy rotation{Fore.RED}.{Fore.WHITE}\n")
    
    valid_proxies = await validate_proxies(proxies)
    if not valid_proxies:
        logger.error(f" {Fore.RED}No valid proxies found. Exiting...{Fore.WHITE}")
        return
    else:
        logger.info(f" >| {Fore.GREEN}Proxies validated successfully{Fore.RED}.{Fore.WHITE}\n")
    
    query = input(f" {Fore.RED}[{Fore.YELLOW}!{Fore.RED}]{Fore.WHITE}  Enter the query to search{Fore.YELLOW}: {Fore.WHITE}")
    await fetch_google_results(query, valid_proxies)
    
    count = 0  # Initialize count
    count = await fetch_google_results(query, valid_proxies, count=count)
    await asyncio.sleep(3)  # Introduce delay between requests

def is_potential_forum(url):
    potential_forum_keywords = ["forum", "community", "discussion", "board", "chat", "hub"]
    url_parts = urllib.parse.urlparse(url)
    path = url_parts.path.lower()
    return any(keyword in path for keyword in potential_forum_keywords)

async def validate_proxies(proxies, timeout=10, retry_attempts=3, retry_statuses={429, 500, 502, 503, 504}, 
                           backoff_factor=2, max_backoff=60, jitter=0.5):
    valid_proxies = []
    logger = logging.getLogger(__name__)
    
    def retry_predicate(exception):
        return isinstance(exception, (TimeoutException, RequestError))
    
    retry_policy = Retrying(
        stop=stop_after_attempt(retry_attempts),
        wait=wait_exponential(multiplier=backoff_factor, max=max_backoff),
        retry=retry_if_exception_type(retry_predicate)
    )
    
    for proxy in proxies:
        proxy_with_scheme = proxy if proxy.startswith("http") else f"http://{proxy}"
        try:
            logger.info(f" {Fore.WHITE}Validating proxy{Fore.YELLOW}: {Fore.CYAN}{proxy_with_scheme}{Fore.WHITE}")  # Add color to the log message
            async with httpx.AsyncClient(proxies={proxy_with_scheme: None}, timeout=timeout) as client:
                response = await client.get("https://www.google.com", timeout=timeout)
                if response.status_code == 200:
                    valid_proxies.append(proxy_with_scheme)
                    logger.info(f" {Fore.RED}[{Fore.GREEN}+{Fore.RED}]{Fore.GREEN} Proxy {Fore.CYAN}{proxy_with_scheme} {Fore.GREEN}is valid{Fore.RED}.{Fore.WHITE}")
                else:
                    logger.error(f" {Fore.RED}Proxy {proxy_with_scheme} returned status code {response.status_code}.")
        except (TimeoutException, RequestError) as e:
            logger.error(f" {Fore.RED}Error occurred while testing proxy {proxy_with_scheme}: {e}")
        finally:
            # Introduce a random delay before the next request to avoid overwhelming the server
            await asyncio.sleep(random.uniform(1, 3))  # Adjust the range as needed
    
    return valid_proxies

if __name__ == "__main__":
    asyncio.run(main())

os.system(f"python3 serp.py {query}")  # serp apii
os.system(f"python3 usr.py {query}")  # username search
