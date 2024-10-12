import asyncio
import logging
import os
import random
import subprocess

import httpx
from colorama import Fore, Style, init
from fake_useragent import UserAgent
from bs4 import BeautifulSoup

from src.proxy_handler import scrape_proxies, validate_proxies
from src.tools_handler import fetch_google_results
from src.utils import find_social_profiles, is_potential_forum, extract_mentions

# Suppress InsecureRequestWarning
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

init(autoreset=True)  # Initialize colorama for colored output

DEFAULT_NUM_RESULTS = 500
MAX_RETRY_COUNT = 5

counter_emojis = ['🍻', '📑', '📌', '🌐', '🔰', '💀', '🔍', '📮', 'ℹ️', '📂', '📜', '📋', '📨', '🌟', '💫', '✨', '🔥', '🆔', '🎲']
emoji = random.choice(counter_emojis)  # Select a random emoji for the counter

# Keep track of user inputs
user_inputs = {}

def display_banner():
    print(
        f"""
{Fore.YELLOW} {Fore.WHITE}🇴‌🇲‌🇮‌🇳‌🇮‌🇸‌-🇴‌🇸‌🇮‌🇳‌🇹‌ {Fore.YELLOW}- {Fore.RED}[{Fore.WHITE}Secure Web-Hunter{Fore.RED}]
{Fore.RED} ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    {Fore.YELLOW}~ {Fore.CYAN}Developer{Fore.YELLOW}: {Fore.WHITE} AnonCatalyst {Fore.MAGENTA}<{Fore.RED}
    {Fore.RED}------------------------------------------
    {Fore.YELLOW}~ {Fore.CYAN}Github{Fore.YELLOW}:{Fore.BLUE} https://github.com/AnonCatalyst/{Fore.RED}
    {Fore.RED}------------------------------------------
    {Fore.YELLOW}~ {Fore.CYAN}Instagram{Fore.YELLOW}:{Fore.BLUE} https://www.instagram.com/istoleyourbutter/{Fore.RED}
    """)

async def get_user_input(prompt, options=None):
    clear_screen()
    
    # Display the banner
    display_banner()
    
    # Display current input statistics
    print(f'{Fore.RED}_' * 80)
    print(f"{Fore.RED}Input Statistics:{Fore.WHITE}")
    for key, value in user_inputs.items():
        # Display current input statistics
        print(f"{Fore.YELLOW}{key}: {Fore.WHITE}{value}")

    if options:
        print(f"\n{Fore.RED}Options (examples):{Fore.WHITE}")
        for option in options:
            print(f" - {option}")

    user_input = input(f"\n{Fore.RED}[{Fore.YELLOW}!{Fore.RED}]{Fore.WHITE} {prompt}: {Fore.WHITE}")
    
    # Save input
    user_inputs[prompt] = user_input
    
    print(f"{Fore.RED}You entered: {Fore.WHITE}{user_input}\n")
    await asyncio.sleep(1)  # Short delay to let user see the prompt

    return user_input

async def main():
    clear_screen()
    display_banner()
    await asyncio.sleep(2)  # Delay to let user read the information

    query = await get_user_input("Enter the query to search")
    language = await get_user_input("Enter language code (e.g., lang_en)", ["e.g., lang_en (English)", "e.g., lang_es (Spanish)", "e.g., lang_fr (French)", "e.g., lang_de (German)"])
    country = await get_user_input("Enter country code (e.g., US)", ["e.g., US (United States)", "e.g., CA (Canada)", "e.g., GB (United Kingdom)", "e.g., AU (Australia)"])
    start_date = await get_user_input("Enter start date (YYYY-MM-DD)")
    end_date = await get_user_input("Enter end date (YYYY-MM-DD)")

    # Validate and format date_range
    date_range = (start_date, end_date)

    # Proceed with scraping and validation
    proxies = await scrape_proxies()
    if not proxies:
        logger.error(f" {Fore.RED}No proxies scraped. Exiting...{Style.RESET_ALL}")
        return
    else:
        print(f'{Fore.RED}_' * 80)
        print(f" {Fore.RED}[{Fore.GREEN}+{Fore.RED}]{Fore.WHITE} Beginning proxy validation for proxy rotation{Fore.RED}.{Fore.WHITE}\n")

    valid_proxies = await validate_proxies(proxies)
    if not valid_proxies:
        logger.error(f" {Fore.RED}No valid proxies found. Exiting...{Fore.WHITE}")
        return
    else:
        logger.info(f" >| {Fore.GREEN}Proxies validated successfully{Fore.RED}.{Fore.WHITE}\n")

    await fetch_google_results(query, language, country, date_range, valid_proxies)
    await asyncio.sleep(3)  # Introduce delay between requests

    subprocess.run(["python3", "-m", "src.usr", query])

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

if __name__ == "__main__":
    asyncio.run(main())

