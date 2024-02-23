import sys
import threading
import time
import urllib.parse
import requests
from colorama import Fore, init
from fake_useragent import UserAgent

# Initialize UserAgent object
user_agent = UserAgent()

# Define headers with a fake user agent
headers = {
    'User-Agent': user_agent.random,
    'Accept-Language': 'en-US,en;q=0.5',
    # Add any other headers you may need
}

# Set up the 'header' variable
header = headers

# Check if the correct number of command-line arguments is provided
if len(sys.argv) != 2:
    print("Usage: python3 search.py <username>")
    sys.exit(1)

# Get the username from the command-line argument
username = sys.argv[1]

# Initialize colorama
init()

# Username Search
print(f" {Fore.RED}〘{Fore.WHITE} Username Search{Fore.YELLOW}: {Fore.CYAN}{username}{Fore.RED} 〙\n")

with open("src/urls.txt", "r") as f:
    url_list = [x.strip() for x in f.readlines()]


def username_search(username: str, url: str):
    try:
        s = requests.Session()
        s.headers.update(header)
        response = s.get(urllib.parse.urljoin(url, username), allow_redirects=False, timeout=5)

        if response.status_code == 200 and username.lower() in response.text.lower():
            print(
                f"{Fore.CYAN}• {Fore.BLUE}{username} {Fore.RED}| {Fore.YELLOW}[{Fore.GREEN}✓{Fore.YELLOW}]{Fore.WHITE} URL{Fore.YELLOW}: {Fore.GREEN}{url}{Fore.WHITE} {response.status_code}"
            )
    except (requests.exceptions.ConnectionError, requests.exceptions.TooManyRedirects, requests.exceptions.RequestException, requests.exceptions.SSLError, requests.exceptions.Timeout):
        # Ignore these specific exceptions
        pass


# Threading
def main(username):
    threads = []
    for url in url_list:
        t = threading.Thread(target=username_search, args=(username, url))
        t.start()
        threads.append(t)
    for thread in threads:
        thread.join()
        time.sleep(0.3)


if __name__ == "__main__":
    try:
        main(username)
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")

print("")
