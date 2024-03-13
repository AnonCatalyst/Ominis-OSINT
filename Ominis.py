import asyncio
import logging
import os
import random
import urllib.parse
import subprocess
import httpx
from colorama import Fore, Style, init
from fake_useragent import UserAgent
from bs4 import BeautifulSoup

from src.proxy_handler import scrape_proxies, validate_proxies
from src.tools_handler import fetch_google_results

# Suppress InsecureRequestWarning
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

init(autoreset=True)  # Initialize colorama for colored output

DEFAULT_NUM_RESULTS = 500
MAX_RETRY_COUNT = 5

counter_emojis = ['💥', '🌀', '💣', '🔥', '💢', '💀', '⚡', '💫', '💥', '💢']
emoji = random.choice(counter_emojis)  # Select a random emoji for the counter

query = None

async def run_command(command):
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)

    # Wait for the subprocess to complete.
    stdout, stderr = await process.communicate()

    # Handle output or errors if needed.
    if stdout:
        print(f'[stdout]\n{stdout.decode()}')
    if stderr:
        print(f'[stderr]\n{stderr.decode()}')


async def main():
    clear_screen()
    print(
        f"""{Fore.RED}
    ⠀⢰⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣦⠀
    ⢀⣿⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣿⡄
    ⣜⢸⣧⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣸⡏⢣
    ⡿⡀⢿⣆⠀⠀⠀⠀⠀⠀⣀⣀⣀⣀⣀⣀⠀⠀⠀⠀⠀⠀⣰⣿⠀⣿
    ⣇⠁⠘⡌⢷⣀⣠⣴⣾⣟⠉⠉⠉⠉⠉⠉⣻⣷⣦⣄⣀⡴⢫⠃⠈⣸
    ⢻⡆⠀⠀⠀⠙⠻⣶⢝⢻⣧⡀⠀⠀⢀⣴⡿⡫⣶⠞⠛⠁⠀⠀⣰⡿
    ⠀⠳⡀⠢⡀⠀⠀⠸⡇⢢⠹⡌⠀⠀⢉⠏⡰⢱⡏⠀⠀⢀⡰⢀⡞⠁
    ⢀⠟⢦⣈⠲⢌⣲⣿⠀⠀⢱⠀⠀⠜⠀⠁⣾⢒⣡⠔⢉⡴⠻⡄⠀
    ⢻⠀⠀⣈⣻⣞⡛⠛⢤⡀⠉⠉⠉⠉⠉⠉⣷⣯⠏⠀⠀⠉⠉⡏⢸⡿⠀
    ⠈⡏⢸⡜⣿⠑⢤⡘⠲⠤⠤⣿⣿⠤⠤⠔⠋⡠⠊⣿⣃⡆⢸⠁⠀
    ⢀⡿⠋⠙⠿⢷⣤⣹⣦⣀⣠⣼⣧⣄⣀⣠⣎⣤⡾⠿⠋⠙⢺⡄⠀
    ⠘⣷⠀⠀⢠⠆⠈⢙⡛⢯⣤⠀⠐⣤⡽⠛⠋⠁⠐⡄⠀⢀⣾⠇⠀
    ⠀⠘⣷⣀⡇⠀⢀⡀⣈⡆⢠⠀⠀⠀⢰⣇⡀⠀⠀⢸⣀⣼⠏⠀⠀
    ⠀⠀⣸⡿⣷⣞⠋⠉⢹⠁⢈⠀⠀⠀⠀⡏⠉⠙⣲⣾⢿⣇⠀⠀⠀{Fore.YELLOW}~ {Fore.WHITE}Ominis Osint {Fore.YELLOW}- {Fore.RED}[{Fore.WHITE}Secure Web-history Search{Fore.RED}]
    ⠀⠀⣿⡇⣿⣿⢿⣆⠈⠻⣆⢣⡴⢱⠟⠁⣰⡶⣿⣿⠘⣿⠀⠀⠀{Fore.RED}---------------------------------------
    ⠀⠀⠹⣆⢈⡿⢸⣿⣻⠦⣼⣦⣴⣯⠴⣞⣿⡇⢻⡇⢸⠏⠀⠀⠀{Fore.YELLOW}~ {Fore.CYAN}Developer{Fore.YELLOW}: {Fore.WHITE} AnonCatalyst {Fore.MAGENTA}<{Fore.RED}
    ⠀⠀⠀⠈⠞⣠⢾⣿⣿⣶⣿⣼⣧⣼⣶⣿⣿⡷⢌⢻⡋⠀⠀⠀ {Fore.RED}--------------------------------------- 
    ⠀⠀⠀⠀⠈⢞⡛⠛⢤⡀⠉⠉⠉⠉⠉⠉⣷⣯⠏⠀⠀⠀⠀{Fore.YELLOW}~ {Fore.CYAN}Github{Fore.YELLOW}:{Fore.BLUE} https://github.com/AnonCatalyst/{Fore.RED}
    ⠀⠀⠀⠀⠀⠈⠳⢦⣬⠿⠿⣡⣤⠤⠤⠔⠋⡠⠊⢀⡞⠁⠀⠀⠀⠀{Fore.RED}--------------------------------------- 
    ⠀⠀⠀⠀⠀⠀⠀⢿⡈⢿⣿⣿⣿⣽⡿⠁⣿⠀⠀⠀⠀⠀⠀⠀⠀{Fore.YELLOW}~ {Fore.CYAN}Instagram{Fore.YELLOW}:{Fore.BLUE} https://www.instagram.com/istoleyourbutter/{Fore.RED}
    ⠀⠀⠀⠀⠀⠀⠀⠘⠳⠦⠴⠞⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀"""
    )
    print("\n" + f"{Fore.RED}_" * 80 + "\n")

    proxies = await scrape_proxies()
    if not proxies:
        logger.error(f" {Fore.RED}No proxies scraped. Exiting...{Style.RESET_ALL}")
        return
    else:
        logger.info(
            f" {Fore.RED}[{Fore.GREEN}+{Fore.RED}]{Fore.WHITE} Beginning proxy validation for proxy rotation{Fore.RED}.{Fore.WHITE}\n")

    valid_proxies = await validate_proxies(proxies)
    if not valid_proxies:
        logger.error(f" {Fore.RED}No valid proxies found. Exiting...{Fore.WHITE}")
        return
    else:
        logger.info(f" >| {Fore.GREEN}Proxies validated successfully{Fore.RED}.{Fore.WHITE}\n")

    query = input(f" {Fore.RED}[{Fore.YELLOW}!{Fore.RED}]{Fore.WHITE}  Enter the query to search{Fore.YELLOW}: {Fore.WHITE}")
    await fetch_google_results(query, valid_proxies)
    await asyncio.sleep(3)  # Introduce delay between requests
    await run_command(f"python3 usr.py {query}")


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


if __name__ == "__main__":
    asyncio.run(main())


