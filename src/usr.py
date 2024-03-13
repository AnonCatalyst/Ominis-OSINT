import sys
import concurrent.futures
import logging
import random
import time
from colorama import Fore, init
from requests_html import HTMLSession
from bs4 import BeautifulSoup

# Initialize colorama
init(autoreset=True)

# Set up logging
logging.basicConfig(filename='username_search.log', level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")

# Keep track of visited URLs to prevent duplicates
visited_urls = set()
visited_html_content = set()

# Function to search for username on a single URL
def search_username_on_url(username: str, url: str):
    global visited_urls, visited_html_content
    try:
        if username.lower() not in url.lower():
            if url.endswith('/'):
                url += username
            else:
                url += '/' + username

        if url in visited_urls:
            print(f"{Fore.YELLOW}⚠️ {Fore.RED}Skipping duplicate URL: {Fore.WHITE}{url}")
            return

        visited_urls.add(url)

        session = HTMLSession()
        time.sleep(random.uniform(1, 3))  # Introduce a random delay to mimic human behavior
        response = session.get(url)

        if response.status_code == 200:
            if response.html.raw_html in visited_html_content:
                print(f"{Fore.YELLOW}⚠️ {Fore.RED}Skipping duplicate HTML content for URL: {Fore.WHITE}{url}")
                return

            visited_html_content.add(response.html.raw_html)

            print(
                f"{Fore.CYAN}🔍 {Fore.BLUE}{username} {Fore.RED}| {Fore.YELLOW}[{Fore.GREEN}✅{Fore.YELLOW}]{Fore.WHITE} URL{Fore.YELLOW}: {Fore.LIGHTGREEN_EX}{url}{Fore.WHITE} {response.status_code}"
            )
            # Print HTML content with organized formatting if it's not empty
            html_content = response.html.raw_html
            if html_content:
                print_html(html_content, url)
            else:
                print(f"{Fore.YELLOW}HTML Content: {Fore.RED}Empty")
        else:
            # Skip processing for non-200 status codes
            return
    except UnicodeEncodeError:
        logging.error(f"UnicodeEncodeError occurred while printing to console for {username} on {url}")
    except Exception as e:
        logging.error(f"Error occurred while searching for {username} on {url}: Continueing...")


def print_html(html_content, url):
    soup = BeautifulSoup(html_content, 'html.parser')
    if soup:
        title_tags = soup.find_all("title")
        unique_titles = {}
        for title in title_tags:
            title_text = title.get_text(strip=True)
            # Exclude titles that are too short or common
            if len(title_text) > 10 and title_text.lower() not in ["404 not found", "page not found"]:
                unique_titles[title_text] = unique_titles.get(title_text, 0) + 1
        
        titles_to_print = []
        for title_text, count in unique_titles.items():
            if count == 1:
                titles_to_print.append(f"{Fore.WHITE}{title_text}")
            else:
                titles_to_print.append(f"{Fore.WHITE}{title_text} ({count})")
        
        if titles_to_print:
            print(f"{Fore.YELLOW}🔸 TITLE: {', '.join(titles_to_print)}")
        
        meta_description = soup.find("meta", attrs={"name": "description"})
        if meta_description:
            print(f"{Fore.YELLOW}🔸 DESCRIPTION: {Fore.WHITE}{meta_description['content']}")
        
        # Print a snippet of the HTML content
        snippet_length = 200  # Adjust as needed
        html_snippet = html_content[:snippet_length] + "..." if len(html_content) > snippet_length else html_content
        print(f"{Fore.YELLOW}🔸 HTML Content for URL {Fore.WHITE}{url}:{Fore.YELLOW}\n{html_snippet}")

        #print(f"{Fore.YELLOW}🔸 URL: {Fore.LIGHTBLACK_EX}{url}")
    else:
        print(f"{Fore.YELLOW}HTML Content: {Fore.RED}Empty")




def main(username):
    with open("urls.txt", "r") as f:
        url_list = [x.strip() for x in f.readlines()]

    if username is None:
        #print("❌ Error: Username cannot be None.")
        return

    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [executor.submit(search_username_on_url, username, url) for url in url_list]
        concurrent.futures.wait(futures)


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            print("❌ Error: Invalid number of arguments.")
            sys.exit(1)

        input_text = sys.argv[1]

        print(f" \n{Fore.RED}〘{Fore.WHITE} Username Search{Fore.YELLOW}: {Fore.CYAN}{input_text}{Fore.RED} 〙\n")

        main(input_text)
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        print(f"❌ An unexpected error occurred. Please check the logs for details.")
