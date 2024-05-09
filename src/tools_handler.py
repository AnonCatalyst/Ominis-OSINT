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
from requests.exceptions import RequestException, HTTPError
from urllib.parse import urlencode, quote_plus
import urllib3


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Set up error logger for tool errors
error_logger = logging.getLogger('gfetcherror')
error_logger.setLevel(logging.ERROR)
error_handler = logging.FileHandler('src/gfetcherror.log')
error_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
error_logger.addHandler(error_handler)

# Disable httpx INFO logging
logging.getLogger('httpx').setLevel(logging.WARNING)
# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# Configure logging to save to a file

init(autoreset=True)  # Initialize colorama for colored output

# Set to store visited URLs
visited_urls = set()

# Load social platform patterns from a JSON file
with open("src/social_platforms.json", "r") as json_file:
    social_platforms = json.load(json_file)

counter_emojis = ['💥', '🌀', '💣', '🔥', '💢', '💀', '⚡', '💫', '💥', '💢']
emoji = random.choice(counter_emojis)  # Select a random emoji for the counter

MAX_RETRY_COUNT = 20  # Define the maximum number of retry attempts
#MAX_REDIRECTS = 5

async def make_request_async(url, proxies=None):
    retry_count = 0
    while retry_count < MAX_RETRY_COUNT:
        try:
            async with httpx.AsyncClient() as client:
                if proxies:
                    proxy = random.choice(proxies)
                    print(f"  {Fore.LIGHTBLACK_EX}Rotated to Proxy: {proxy} Avoiding detection! {Style.RESET_ALL}")
                    client.proxies = {"http://": proxy}

                client.headers = {"User-Agent": UserAgent().random.strip()}  # Strip extra spaces
                response = await client.get(url, timeout=7)

                if response.status_code == 302:
                    redirect_location = response.headers.get('location')
                    logger.info(f" ? Redirecting to: {redirect_location}")
                    if redirect_location:
                        if retry_count < MAX_REDIRECTS:
                            return await make_request_async(redirect_location, proxies)
                        else:
                            raise RuntimeError("Exceeded maximum number of redirects.")

                response.raise_for_status()
                return response.text

        except httpx.RequestError as e:
            logger.error(f"Failed to make connection: {e}")
            retry_count += 1
            logger.info(f"Retrying request {retry_count}/{MAX_RETRY_COUNT}...")
            await asyncio.sleep(7 * retry_count)  # Exponential backoff for retries
            if retry_count < MAX_RETRY_COUNT:
                await asyncio.sleep(6 * retry_count)  # Exponential backoff for retries
            else:
                raise RuntimeError(f"Failed to make connection after {MAX_RETRY_COUNT} retries: {e}")

    logger.info("Final retry using DuckDuckGo...")
    return await fetch_ddg_results(url)


async def fetch_ddg_results(query):
    ddg_search_url = f"https://html.duckduckgo.com/html/?q={query}"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(ddg_search_url)
            response.raise_for_status()
            if response.is_redirect:
                redirected_url = response.headers['location']
                logger.info(f"Redirecting to: {redirected_url}")
                # Follow redirects until a final response is obtained
                return await follow_redirects_async(redirected_url)
            return response.text
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error occurred during DuckDuckGo search: {e}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error occurred during DuckDuckGo search: {e}")
            raise

async def follow_redirects_async(url):
    MAX_REDIRECTS = 4  # Define the maximum number of redirects to prevent infinite loops
    redirect_count = 0
    while redirect_count < MAX_REDIRECTS:
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url)
                response.raise_for_status()
                if not response.is_redirect:
                    return response.text
                redirected_url = response.headers['location']
                logger.info(f"Redirecting to: {redirected_url}")
                url = redirected_url
                redirect_count += 1
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error occurred during redirect: {e}")
                raise
            except httpx.RequestError as e:
                logger.error(f"Request error occurred during redirect: {e}")
                raise
    logger.error("Exceeded maximum number of redirects.")
    return None


async def fetch_google_results(query, language=None, country=None, date_range=None, proxies=None):
    all_mention_links = []
    all_unique_social_profiles = set()
    processed_urls = set()  # Keep track of processed URLs
    total_results = 0
    retries = 0
    consistent_duplicates_count = 0
    previous_unique_count = 0
    max_retries = 10  # Define maximum retry attempts
    retry_interval = 10  # Initial retry interval in seconds

    # Encode the query
    encoded_query = quote_plus(query)

    # Construct the Google search URL with filtering options if provided
    params = {'q': encoded_query, 'start': total_results}
    if language:
        params['lr'] = language  # Language parameter (e.g., 'lang_en' for English)
    if country:
        params['cr'] = country   # Country parameter (e.g., 'countryUS' for United States)
    if date_range:
        params['tbs'] = f'cdr:1,cd_min:{date_range[0]},cd_max:{date_range[1]}'  # Date range parameter (e.g., 'cdr:1,cd_min:01/01/2023,cd_max:12/31/2023')

    output_file = f"Results/{query}_built-in-search_results.txt"
    with open(output_file, 'w') as file:  # Open file for writing
        print(f"Search Query: {query}")
        if language:
            print(f"Chosen Language: {language}")
        if country:
            print(f"Chosen Country: {country}")
        if date_range:
            print(f"Chosen Date Range: {date_range[0]} - {date_range[1]}")
        #print("_" * 80)

        while True:  # Infinite loop for continuous search
            try:
                # Construct the Google search URL with pagination
                params['start'] = total_results  # Update the 'start' parameter for pagination
                google_search_url = f"https://www.google.com/search?{urlencode(params)}"

                response_text = await make_request_async(google_search_url, proxies)
                if response_text is None:
                    retries += 1
                    if retries >= max_retries:
                        print(Fore.RED + "Exceeded maximum retry attempts. Stopping search." + Style.RESET_ALL)
                        break
                    print(Fore.RED + f"No response received from Google. Retrying ({retries})..." + Style.RESET_ALL)
                    await asyncio.sleep(retry_interval * retries)  # Exponential backoff
                    continue

                soup = BeautifulSoup(response_text, "html.parser")
                search_results = soup.find_all("div", class_="tF2Cxc")

                if not search_results:
                    if len(processed_urls) == previous_unique_count:
                        consistent_duplicates_count += 1
                        if consistent_duplicates_count >= 3:
                            print(Fore.YELLOW + "Consistent duplicates detected. Stopping search." + Style.RESET_ALL)
                            break
                    else:
                        consistent_duplicates_count = 0
                    previous_unique_count = len(processed_urls)
                    continue

                for result in search_results:
                    title = result.find("h3")
                    url = result.find("a", href=True)["href"] if result.find("a", href=True) else None

                    if not url or url.startswith('/'):
                        continue

                    if url in processed_urls:
                        continue

                    processed_urls.add(url)  # Mark URL as processed

                    if title and url:
                        # Write result to file
                        file.write(f"Title: {title.text.strip()}\n")
                        file.write(f"URL: {url}\n")

                        print('_' * 80)
                        print(random.choice(counter_emojis), Fore.BLUE + f"Title: {title.text.strip()}" + Style.RESET_ALL)
                        print(random.choice(counter_emojis), Fore.LIGHTBLACK_EX + f"URL: {url}" + Style.RESET_ALL)

                        text_to_check = title.text + ' ' + url
                        mention_count = extract_mentions(text_to_check, query)

                        for q, count in mention_count.items():
                            if count > 0:
                                print(random.choice(counter_emojis), Fore.YELLOW + f"'{q}' Detected in Title/Url: {url}" + Style.RESET_ALL)
                                all_mention_links.append({"url": url, "count": count})

                        social_profiles = find_social_profiles(url)
                        if social_profiles:
                            for profile in social_profiles:
                                print(random.choice(counter_emojis), Fore.GREEN + f"{profile['platform']}: {profile['profile_url']}" + Style.RESET_ALL)
                                all_unique_social_profiles.add(profile['profile_url'])

                        total_results += 1

                        await asyncio.sleep(2)

            except RequestException as e:
                print(random.choice(counter_emojis), Fore.RED + f"Request error occurred during search: {e}" + Style.RESET_ALL)
                # Retry for connection errors or other transient issues
                retries += 1
                if retries >= max_retries:
                    print(random.choice(counter_emojis), Fore.RED + "Exceeded maximum retry attempts. Stopping search." + Style.RESET_ALL)
                    break
                print(random.choice(counter_emojis), Fore.RED + f"Retrying request after error ({retries})..." + Style.RESET_ALL)
                await asyncio.sleep(retry_interval * retries)  # Exponential backoff
            except HTTPError as e:
                # Retry for certain HTTP status codes
                if e.response.status_code in [500, 502, 503, 504, 429]:
                    retries += 1
                    if retries >= max_retries:
                        print(random.choice(counter_emojis), Fore.RED + "Exceeded maximum retry attempts. Stopping search." + Style.RESET_ALL)
                        break
                    print(random.choice(counter_emojis), Fore.RED + f"Retrying request after HTTP error ({e.response.status_code}) ({retries})..." + Style.RESET_ALL)
                    await asyncio.sleep(retry_interval * retries)  # Exponential backoff
                else:
                    print(random.choice(counter_emojis), Fore.RED + f"HTTP error occurred during search: {e}" + Style.RESET_ALL)
            except Exception as e:
                print(random.choice(counter_emojis), Fore.RED + f"An error occurred during search: {e}" + Style.RESET_ALL)
                # Retry for generic errors
                retries += 1
                if retries >= max_retries:
                    print(random.choice(counter_emojis), Fore.RED + "Exceeded maximum retry attempts. Stopping search." + Style.RESET_ALL)
                    break
                print(random.choice(counter_emojis), Fore.RED + f"Retrying request after error ({retries})..." + Style.RESET_ALL)
                await asyncio.sleep(retry_interval * retries)

    if total_results == 0 and consistent_duplicates_count < 3:
        print(random.choice(counter_emojis), Fore.YELLOW + f"No more results found for the query '{query}'." + Style.RESET_ALL)
    elif total_results == 0 and consistent_duplicates_count >= 3:
        print(random.choice(counter_emojis), Fore.YELLOW + "No more new results found after consistent duplicates." + Style.RESET_ALL)
        print(random.choice(counter_emojis), Fore.YELLOW + "Stopping search." + Style.RESET_ALL)

    return total_results, all_mention_links, all_unique_social_profiles





# Define the find_social_profiles function
def find_social_profiles(url):
    if not isinstance(url, str):
        raise ValueError("URL must be a string")

    profiles = []

    # Check if URL has been visited before
    if url in visited_urls:
        return profiles

    for platform, pattern in social_platforms.items():
        match = re.search(pattern, url)
        if match:
            profile_url = match.group(0)
            profiles.append({"platform": platform, "profile_url": profile_url})

    if is_potential_forum(url):
        profiles.append({"platform": "Forum", "profile_url": url})

    # Add URL to visited set
    visited_urls.add(url)

    return profiles

# Define the is_potential_forum function
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

# Define the extract_mentions function
def extract_mentions(text, query):
    if not isinstance(text, str) or not text:
        raise ValueError("Input 'text' must be a non-empty string.")

    if isinstance(query, str):
        query = [query]
    elif not isinstance(query, list) or not all(isinstance(q, str) for q in query):
        raise ValueError("Input 'query' must be a string or a list of strings.")

    mention_count = {q: len(re.findall(re.escape(q), text, re.IGNORECASE)) for q in query}
    return mention_count
