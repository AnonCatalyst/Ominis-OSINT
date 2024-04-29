import random
import asyncio
import os
import re
import json
import logging
import urllib.parse
import httpx
from colorama import Fore, Style, init
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from httpx import TimeoutException, RequestError
from tenacity import Retrying, stop_after_attempt, wait_exponential, retry_if_exception_type

init(autoreset=True)  # Initialize colorama for colored output

# Set up error logger for tool errors
error_logger = logging.getLogger('gfetcherror')
error_logger.setLevel(logging.ERROR)
error_handler = logging.FileHandler('src/gfetcherror.log')
error_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
error_logger.addHandler(error_handler)

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set to store visited URLs
visited_urls = set()

# Load social platform patterns from a JSON file
with open("src/social_platforms.json", "r") as json_file:
    social_platforms = json.load(json_file)

counter_emojis = ['💥', '🌀', '💣', '🔥', '💢', '💀', '⚡', '💫', '💥', '💢']
emoji = random.choice(counter_emojis)  # Select a random emoji for the counter

MAX_RETRY_COUNT = 5  # Define the maximum number of retry attempts

@retry_if_exception_type(RequestError, TimeoutException)
@wait_exponential(multiplier=1, min=1, max=5)
@stop_after_attempt(MAX_RETRY_COUNT)
async def make_request_async(url, proxies=None):
    async with httpx.AsyncClient() as client:
        if proxies:
            proxy = random.choice(proxies)
            logger.info(f"Using proxy: {proxy}")
            client.proxies = {"http://": proxy}

        client.headers = {"User-Agent": UserAgent().random.strip()}  # Strip extra spaces
        response = await client.get(url)

        if response.status_code == 302:
            redirect_location = response.headers.get('location')
            logger.info(f"Redirecting to: {redirect_location}")
            if redirect_location:
                return await make_request_async(redirect_location, proxies)

        response.raise_for_status()
        return response.text


async def fetch_google_results(query, proxies=None):
    all_mention_links = []
    all_unique_social_profiles = set()
    processed_urls = set()  # Keep track of processed URLs
    total_results = 0
    retries = 0
    consistent_duplicates_count = 0
    previous_unique_count = 0
    max_retries = 5  # Define maximum retry attempts
    retry_interval = 5  # Initial retry interval in seconds

    output_file = f"Results/{query}_built-in-search_results.txt"
    with open(output_file, 'w') as file:  # Open file for writing
        while True:  # Infinite loop for continuous search
            google_search_url = f"https://www.google.com/search?q={query}&start={total_results}"

            try:
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
                await asyncio.sleep(retry_interval * retries)  # Exponential backoff

    if total_results == 0 and consistent_duplicates_count < 3:
        print(random.choice(counter_emojis), Fore.YELLOW + f"No more results found for the query '{query}'." + Style.RESET_ALL)
    elif total_results == 0 and consistent_duplicates_count >= 3:
        print(random.choice(counter_emojis), Fore.YELLOW + "No more new results found after consistent duplicates." + Style.RESET_ALL)
        print(random.choice(counter_emojis), Fore.YELLOW + "Stopping search." + Style.RESET_ALL)

    return total_results, all_mention_links, all_unique_social_profiles

# ... (rest of the code remains the same)


pip install tenacity
