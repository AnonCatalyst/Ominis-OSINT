import sys
import concurrent.futures
import logging
import random
import time
from colorama import Fore, Style, init
from requests_html import HTMLSession
from bs4 import BeautifulSoup

# Initialize colorama
init(autoreset=True)

# Set up logging
logging.basicConfig(filename='src/username_search.log', level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")

# Set up file for saving results
results_file = open("Results/username-search_results.txt", "w")

# Keep track of visited URLs to prevent duplicates
visited_urls = set()
visited_html_content = set()


# Function to search for username on a single URL
def search_username_on_url(username: str, url: str, include_titles=True, include_descriptions=True, include_html_content=True):
    global visited_urls, visited_html_content
    try:
        if username.lower() not in url.lower():
            url += f'/{username}' if url.endswith('/') else f'/{username}'

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

            print(f"{Fore.CYAN}🔍 {Fore.BLUE}{username} {Fore.RED}| {Fore.YELLOW}[{Fore.GREEN}✅{Fore.YELLOW}]{Fore.WHITE} URL{Fore.YELLOW}: {Fore.LIGHTGREEN_EX}{url}{Fore.WHITE} {response.status_code}")

            if include_titles or include_descriptions or include_html_content:
                # Print HTML content with organized formatting if requested
                print_html(response.html.raw_html, url, include_titles, include_descriptions, include_html_content)

            # Write results to file
            write_to_file(username, url, response.status_code, response.html.raw_html, include_titles, include_descriptions, include_html_content)
        else:
            # Skip processing for non-200 status codes
            return
    except UnicodeEncodeError:
        logging.error(f"UnicodeEncodeError occurred while printing to console for {username} on {url}")
    except Exception as e:
        logging.error(f"Error occurred while searching for {username} on {url}: {e}")


def write_to_file(username, url, status_code, html_content, include_titles=True, include_descriptions=True, include_html_content=True):
    try:
        results_file.write(f"Username: {username}\n")
        results_file.write(f"URL: {url}\n")
        results_file.write(f"Status Code: {status_code}\n")
        if include_titles or include_descriptions or include_html_content:
            results_file.write("Details:\n")
            if include_titles:
                results_file.write("Title: ...\n")  # Placeholder, will be replaced if available
            if include_descriptions:
                results_file.write("Description: ...\n")  # Placeholder, will be replaced if available
            if include_html_content:
                results_file.write("HTML Content: ...\n")  # Placeholder, will be replaced if available
        results_file.write("\n")
    except Exception as e:
        logging.error(f"Error occurred while writing to file for {username} on {url}: {e}")


def print_html(html_content, url, include_titles=True, include_descriptions=True, include_html_content=True):
    try:
        if not html_content:
            print(f"{Fore.YELLOW}HTML Content for URL {Fore.WHITE}{url}:{Fore.YELLOW} Empty")
            return

        soup = BeautifulSoup(html_content, 'html.parser')
        if soup:
            if include_titles:
                title = soup.title.get_text(strip=True) if soup.title else "No title found"
                print(f"{Fore.YELLOW}🔸 TITLE: {Fore.WHITE}{title}")
            if include_descriptions:
                meta_description = soup.find("meta", attrs={"name": "description"})
                description = meta_description['content'] if meta_description else "No meta description found"
                print(f"{Fore.YELLOW}🔸 DESCRIPTION: {Fore.WHITE}{description}")

            if include_html_content:
                print(f"{Fore.YELLOW}🔸 HTML Content for URL {Fore.WHITE}{url}:{Fore.YELLOW}")
                # Decode bytes to string
                html_content_str = html_content.decode('utf-8')
                # Print a snippet of the HTML content with line breaks for better readability
                snippet_length = 200  # Adjust as needed
                html_snippet = html_content_str[:snippet_length] + ("..." if len(html_content_str) > snippet_length else "")
                print("\n".join([f"{Fore.CYAN}{line}" for line in html_snippet.split("\n")]))

        else:
            print(f"{Fore.YELLOW}HTML Content for URL {Fore.WHITE}{url}:{Fore.RED} Empty")
    except Exception as e:
        print(f"{Fore.RED}Error occurred while parsing HTML content for URL {Fore.WHITE}{url}:{Fore.RED} {str(e)}")


def main(username):
    with open("src/urls.txt", "r") as f:
        url_list = [x.strip() for x in f.readlines()]

    if not username:
        print("❌ Error: Username cannot be empty.")
        return

    run_script = input(f"\n {Fore.RED}[{Fore.YELLOW}!{Fore.RED}]{Fore.WHITE} Do you want to run a username search? (y/n):{Style.RESET_ALL} ").lower()
    if run_script != 'y':
        print(f"{fore.RED}- {Fore.LIGHTBLACK_EX}Skipping the script.{Style.RESET_ALL}")
        return

    print(f"{Fore.RED}_" * 80 + "\n")
    include_titles = input(f" {Fore.RED}[{Fore.YELLOW}!{Fore.RED}]{Fore.WHITE} Include titles? (y/n): {Style.RESET_ALL}").lower() == 'y'
    include_descriptions = input(f" {Fore.RED}[{Fore.YELLOW}!{Fore.RED}]{Fore.WHITE} Include descriptions? (y/n):{Style.RESET_ALL} ").lower() == 'y'
    include_html_content = input(f" {Fore.RED}[{Fore.YELLOW}!{Fore.RED}]{Fore.WHITE} Include HTML content? (y/n):{Style.RESET_ALL} ").lower() == 'y'
    print(f"{Fore.RED}_" * 80 + "\n")

    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [executor.submit(search_username_on_url, username, url, include_titles, include_descriptions, include_html_content) for url in url_list]
        concurrent.futures.wait(futures)


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            print("❌ Error: Invalid number of arguments.")
            sys.exit(1)

        if sys.argv[1] == '--skip':
            print(" - src/usr.py[ Skipping the username search...")
            sys.exit(0)


        input_text = sys.argv[1]
       # print(f" \n{Fore.RED}〘{Fore.WHITE} Username Search{Fore.YELLOW}: {Fore.CYAN}{input_text}{Fore.RED} 〙\n")

        main(input_text)
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        print(f"❌ Exited.")

# Close the results file
results_file.close()
