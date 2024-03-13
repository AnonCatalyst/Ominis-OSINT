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

# Load social platform patterns from a JSON file
with open("src/social_platforms.json", "r") as json_file:
    social_platforms = json.load(json_file)

counter_emojis = ['💥', '🌀', '💣', '🔥', '💢', '💀', '⚡', '💫', '💥', '💢']
emoji = random.choice(counter_emojis)  # Select a random emoji for the counter

MAX_RETRY_COUNT = 3  # Define the maximum number of retry attempts

async def make_request_async(url, proxies=None):
    retry_count = 0
    while retry_count < MAX_RETRY_COUNT:
        try:
            async with httpx.AsyncClient() as client:
                if proxies:
                    proxy = random.choice(proxies)
                    logger.info(f"Using proxy: {proxy}")
                    client.proxies = {"http://": proxy}
                client.headers = {"User-Agent": UserAgent().random.strip()}  # Strip extra spaces
                response = await client.get(url, timeout=5)
                
                if response.status_code == 302:
                    redirect_location = response.headers.get('location')
                    if redirect_location:
                        logger.info(f"Redirecting to: {redirect_location}")
                        # Limit maximum number of redirects to prevent stack overflow
                        if retry_count < MAX_REDIRECTS:
                            return await make_request_async(redirect_location, proxies)
                        else:
                            logger.error("Exceeded maximum number of redirects.")
                            return None
                
                response.raise_for_status()
                return response.text
            
        except httpx.RequestError as e:
            logger.error(f"Failed to make connection: {e}")
            retry_count += 1
            logger.info(f"Retrying request {retry_count}/{MAX_RETRY_COUNT}...")
            await asyncio.sleep(5 * retry_count)  # Exponential backoff for retries

    logger.info("Final retry using DuckDuckGo...")
    return await fetch_ddg_results(url)


async def fetch_ddg_results(query):
    ddg_search_url = f"https://duckduckgo.com/html/?q={query}"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(ddg_search_url)
            response.raise_for_status()
            if response.is_redirect:
                redirected_url = response.headers['location']
                response = await client.get(redirected_url)
                response.raise_for_status()
            return response.text
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error occurred during DuckDuckGo search: {e}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error occurred during DuckDuckGo search: {e}")
            raise


async def fetch_google_results(query, proxies=None):
    all_mention_links = []
    all_unique_social_profiles = set()
    unique_urls = set()  
    total_results = 0
    max_unique_results = 500  
    consecutive_failures = 0
    last_successful_page = 0
    page_number = 1
    start_index = 0

    while len(unique_urls) < max_unique_results:  # Remove the condition page_number <= 500
        google_search_url = f"https://www.google.com/search?q={query}&start={start_index}"

        try:
            response_text = await make_request_async(google_search_url, proxies)
            if response_text is None:
                consecutive_failures += 1
                if consecutive_failures >= MAX_RETRY_COUNT:
                    logger.error(f"{Fore.RED}Exceeded maximum consecutive failures. Changing proxy.{Style.RESET_ALL}")
                    if proxies:
                        proxies.pop(0)  
                    consecutive_failures = 0  
                    last_successful_page = page_number - 1  
                continue
            else:
                consecutive_failures = 0  

            soup = BeautifulSoup(response_text, "html.parser")
            search_results = soup.find_all("div", class_="tF2Cxc")

            if not search_results:
                logger.info(f"{Fore.RED}No more results found for the query '{query}'.{Style.RESET_ALL}")
                logger.info(f"{Fore.RED}Launching Username Search! Warning: This can take time depending on your network speed.   {Fore.WHITE}please wait...{Style.RESET_ALL}")
                break

            for result in search_results:
                title = result.find("h3")
                url = result.find("a", href=True)["href"] if result.find("a", href=True) else None

                if not url or url.startswith('/'):
                    continue  

                if url in unique_urls:  
                    continue  

                unique_urls.add(url)  

                if title and url:
                    logger.info(Style.BRIGHT + f"{Fore.WHITE}{'_' * 80}")
                    logger.info(f"{random.choice(counter_emojis)} {Fore.BLUE}Title{Fore.YELLOW}:{Fore.WHITE} {title.text.strip()}")
                    logger.info(f"{random.choice(counter_emojis)} {Fore.BLUE}URL{Fore.YELLOW}:{Fore.LIGHTBLACK_EX} {url}{Style.RESET_ALL}")

                    text_to_check = title.text + ' ' + url
                    mention_count = extract_mentions(text_to_check, query)

                    for q, count in mention_count.items():
                        if count > 0:
                            logger.info(f"{random.choice(counter_emojis)} {Fore.YELLOW}'{q}' {Fore.CYAN}Detected in {Fore.MAGENTA}Title{Fore.RED}/{Fore.MAGENTA}Url{Fore.YELLOW}:{Fore.GREEN} {url}")
                            all_mention_links.append({"url": url, "count": count})

                    social_profiles = find_social_profiles(url)
                    if social_profiles:
                        for profile in social_profiles:
                            logger.info(f"{Fore.BLUE}{profile['platform']}{Fore.YELLOW}:{Fore.GREEN} {profile['profile_url']}{Style.RESET_ALL}")
                            all_unique_social_profiles.add(profile['profile_url'])

                    total_results += 1  

                    await asyncio.sleep(2)  

            start_index += 10
            page_number += 1

        except Exception as e:
            logger.error(f"An error occurred during search: {e}")
            # Handle the error gracefully, e.g., retry with a different proxy or log the error for investigation
            consecutive_failures += 1
            if consecutive_failures >= MAX_RETRY_COUNT:
                logger.error(f"{Fore.RED}Exceeded maximum consecutive failures. Changing proxy.")
                if proxies:
                    proxies.pop(0)  
                consecutive_failures = 0  
                last_successful_page = page_number - 1  

    if total_results == 0:
        logger.info(f"No results found on Google. Trying DuckDuckGo as a fallback...")
        return await fetch_ddg_results(query)

    return total_results, start_index, page_number, consecutive_failures, last_successful_page

      

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

def is_potential_forum(url):
    forum_keywords = [
        r"forum[s]?", 
        r"community",
        r"discussion[s]?",
        r"board[s]?",
        r"chat",
        r"hub"
    ]
    url_parts = urllib.parse.urlparse(url)
    path = url_parts.path.lower()
    subdomain = url_parts.hostname.split('.')[0].lower()  # Extract subdomain
    path_keywords = any(re.search(keyword, path) for keyword in forum_keywords)
    subdomain_keywords = any(re.search(keyword, subdomain) for keyword in forum_keywords)
    return path_keywords or subdomain_keywords
