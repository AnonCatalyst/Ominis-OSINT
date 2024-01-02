import os
import re
import json
import httpx
import urllib3
import urllib.parse
import asyncio
import time
from colorama import Fore
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

# Disable urllib3 warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Get a random user agent
user_agent = UserAgent().random
header = {"User-Agent": user_agent}

# Load social platform patterns from a JSON file
with open("src/social_platforms.json", "r") as json_file:
    social_platforms = json.load(json_file)

unique_social_profiles = set()
mention_links = []
mention_counts = {}


def delay(seconds=3):
    time.sleep(seconds)  # Adjust the delay time as needed


# Function to clear the screen
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


# Function to handle user input for the number of results
def get_num_results():
    num_results = input(
        f" {Fore.RED}[{Fore.GREEN}+{Fore.RED}] {Fore.YELLOW}~ {Fore.WHITE}Enter the number of results (default is 10){Fore.YELLOW}:{Fore.WHITE} ")
    return int(num_results) if num_results.isdigit() else 10


async def make_request_async(url):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
    except httpx.RequestError as e:
        print(f"Error making request to {url}: {e}")
        return None


def find_social_profiles(url):
    profiles = []
    for platform, pattern in social_platforms.items():
        match = re.search(pattern, url)
        if match:
            profile_url = match.group(0)
            profiles.append({"platform": platform, "profile_url": profile_url})

    # Check if the URL contains forum keywords
    if is_potential_forum(url):
        profiles.append({"platform": "Forum", "profile_url": url})

    return profiles


def extract_mentions(text, query):
    mention_pattern = rf"\b{re.escape(query)}\b"
    mentions = re.findall(mention_pattern, text, re.IGNORECASE)
    return len(mentions)


def is_potential_forum(url):
    potential_forum_keywords = ["forum", "community", "discussion", "board", "chat", "hub"]
    url_parts = urllib.parse.urlparse(url)
    path = url_parts.path.lower()
    return any(keyword in path for keyword in potential_forum_keywords)



async def main_async():
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
⠀⠀⠀⣸⡿⣷⣞⠋⠉⢹⠁⢈⠀⠀⠀⠀⡏⠉⠙⣲⣾⢿⣇⠀⠀⠀{Fore.YELLOW}~ {Fore.WHITE}Ominis Osint {Fore.YELLOW}- {Fore.RED}[{Fore.WHITE}Query to web search{Fore.RED}]
⠀⠀⠀⣿⡇⣿⣿⢿⣆⠈⠻⣆⢣⡴⢱⠟⠁⣰⡶⣿⣿⠘⣿⠀⠀⠀{Fore.RED}---------------------------------------
⠀⠀⠀⠹⣆⢈⡿⢸⣿⣻⠦⣼⣦⣴⣯⠴⣞⣿⡇⢻⡇⢸⠏⠀⠀⠀{Fore.YELLOW}~ {Fore.CYAN}Developer{Fore.YELLOW}: {Fore.WHITE} AnonCatalyst {Fore.MAGENTA}<{Fore.RED}
⠀⠀⠀⠀⠘⣞⣠⢾⣿⣿⣶⣿⣼⣧⣼⣶⣿⣿⡷⢌⢻⡋⠀⠀⠀ {Fore.RED}--------------------------------------- 
⠀⠀⠀⠀⠘⠉⢿⡀⣹⣿⣿⣿⣿⣿⣿⣿⣿⢏⢁⡼⠋⠃⠀⠀⠀⠀{Fore.YELLOW}~ {Fore.CYAN}Github{Fore.YELLOW}:{Fore.BLUE} https://github.com/AnonCatalyst{Fore.RED}
⠀⠀⠀⠀⠀⠀⠈⢻⡟⢿⣿⣿⣿⣿⣿⣿⡿⢸⡟⠁⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⢿⡈⢿⣿⣿⣿⣽⡿⠁⣿⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠘⠳⢦⣬⠿⠿⣡⣤⠾⠃⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠳⠦⠴⠞⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀""")
    print("\n" + f"{Fore.RED}_" * 80 + "\n")

    global query
    query = input(f" {Fore.RED}[{Fore.GREEN}+{Fore.RED}] {Fore.YELLOW}~ {Fore.WHITE}Enter your query{Fore.YELLOW}:{Fore.WHITE} ")
    num_results = get_num_results()

    retry_count = 0
    all_results = []
    all_mention_links = []
    all_unique_social_profiles = set()

    async with httpx.AsyncClient(verify=True) as client:
        total_results_to_fetch = min(300, num_results)  # Limit to 100 results to avoid Google limitations

        # Loop to fetch multiple pages
        for start_index in range(0, total_results_to_fetch, 10):
            google_search_url = f"https://www.google.com/search?q={query}&start={start_index}"

            try:
                response = await client.get(google_search_url, headers=header)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                search_results = soup.find_all("div", class_="tF2Cxc")

                if not search_results:
                    print(f"\n{Fore.RED}[{Fore.YELLOW}!{Fore.RED}] {Fore.YELLOW}~ {Fore.RED}No more results found for the query '{query}'{Fore.YELLOW}")
                    break

                for index, result in enumerate(search_results, start=start_index + 1):
                    title = result.find("h3")
                    url = result.find("a")["href"] if result.find("a") else None

                    if title and url:
                        print(f"{Fore.RED}_" * 80)
                        print(f"{Fore.WHITE}{index}. {Fore.BLUE}Title{Fore.YELLOW}:{Fore.WHITE} {title.text.strip()}")
                        print(f"{Fore.YELLOW}~ {Fore.WHITE}URL{Fore.YELLOW}:{Fore.WHITE} {url}")

                        text_to_check = title.text + ' ' + url
                        mention_count = extract_mentions(text_to_check, query)

                        if mention_count > 0:
                            print(
                                f"{Fore.YELLOW}~ {Fore.CYAN}'{query}' {Fore.WHITE}Detected in Title{Fore.YELLOW}/{Fore.WHITE}Url{Fore.YELLOW}: {Fore.MAGENTA}{url}")
                            all_mention_links.append({"url": url, "count": mention_count})

                        social_profiles = find_social_profiles(url)
                        if social_profiles:
                            for profile in social_profiles:
                                if profile['profile_url'] not in all_unique_social_profiles:
                                    if profile['platform'] == 'Forum':
                                        print(
                                            f"{Fore.YELLOW}~ {Fore.CYAN}{profile['platform']}{Fore.YELLOW}:{Fore.MAGENTA} {profile['profile_url']}")
                                    else:
                                        print(
                                            f"{Fore.YELLOW}~ {Fore.BLUE}{profile['platform']}{Fore.YELLOW}:{Fore.GREEN} {profile['profile_url']}")
                                    all_unique_social_profiles.add(profile['profile_url'])

                        # Introduce a delay
                        await asyncio.sleep(3)

            except httpx.RequestError as google_error:
                if google_error.response.status_code == 429:
                    retry_count += 1
                    print(
                        f"\n{Fore.RED}[{Fore.YELLOW}!{Fore.RED}] {Fore.YELLOW}~ {Fore.RED}Google Search rate limit reached (Retry: {retry_count}/3). Retrying in 30 seconds...{Fore.YELLOW}")
                    await asyncio.sleep(30)
                else:
                    print(
                        f"\n{Fore.RED}[{Fore.YELLOW}!{Fore.RED}] {Fore.YELLOW}~ {Fore.RED}Error making request to Google: {google_error}. Retrying in 30 seconds...{Fore.YELLOW}")
                    await asyncio.sleep(30)

        # If Google search still fails after retries, tell the user and wait
        if retry_count >= 3:
            print(
                f"\n{Fore.RED}[{Fore.YELLOW}!{Fore.RED}] {Fore.YELLOW}~ {Fore.RED}Google Search failed after multiple retries. Please try again later.{Fore.YELLOW}")
            await asyncio.sleep(60)

    # Print all social profiles found during the Google search
    if all_unique_social_profiles:
        print(f"\n{Fore.RED}[{Fore.GREEN}+{Fore.RED}] {Fore.YELLOW}~ {Fore.WHITE}All Social Profiles Found{Fore.YELLOW}:")
        for idx, profile_url in enumerate(all_unique_social_profiles, start=1):
            print(f"{Fore.YELLOW}~ {Fore.WHITE}{idx}. {profile_url}")


if __name__ == "__main__":
    asyncio.run(main_async())

os.system(f"python3 serp.py {query}")  # serp apii
os.system(f"python3 usr.py {query}")  # username search
