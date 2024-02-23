import sys
import json
from colorama import Fore, Style, init  
from serpapi import GoogleSearch


# Initialize colorama to enable ANSI escape code support on Windows
init()
print(f"{Fore.WHITE}")
def load_api_key(api_key_file):
    try:
        with open(api_key_file, 'r') as file:
            api_key_data = json.load(file)
            return api_key_data.get('api_key')
    except FileNotFoundError:
        print(f"Error: API key file '{api_key_file}' not found.")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in '{api_key_file}'.")
        sys.exit(1)

def get_user_api_key():
    return input("Enter your SerpApi API key: ")

def confirm_continue():
    user_input = input(f"\n{Fore.RED}[{Fore.CYAN}?{Fore.RED}] {Fore.YELLOW}~ {Fore.WHITE}Do you want to continue the search with {Fore.RED}({Fore.BLUE}SerpAPI{Fore.RED}){Fore.YELLOW}? {Fore.RED}({Fore.WHITE}Y{Fore.YELLOW}/{Fore.WHITE}n{Fore.RED}){Fore.YELLOW}:{Fore.GREEN} ").lower()
    return user_input == 'yes', 'Y', 'y'
    print("")

def print_colored_result(index, result):
    print(f"{Fore.BLUE}Result {index + 1}:{Style.RESET_ALL}")
    print(json.dumps(result, indent=2))
    print("\n" + f"{Fore.RED}_" * 80 + "\n")  # Separate results for better readability


def print_colored_result(index, result):
    print(f"{Fore.BLUE}Result {index + 1}:{Style.RESET_ALL}")
    print(json.dumps(result, indent=2, ensure_ascii=False).replace('"', f'{Fore.WHITE}"'))
    print("\n" + f"{Fore.RED}_" * 80 + "\n")  # Separate results for better readability

def main():
    if not confirm_continue():
        print("Exiting.")
        sys.exit(0)

    if len(sys.argv) != 2:
        print("Usage: python3 usr.py <search_query>")
        sys.exit(1)

    search_query = sys.argv[1]

    # Load API key from a JSON file or get it from the user
    try:
        api_key = load_api_key('src/api_key.json')
    except KeyboardInterrupt:
        print("\nUser interrupted. Exiting.")
        sys.exit(1)

    if api_key is None:
        api_key = get_user_api_key()

    # Set up the search parameters
    params = {
        "engine": "google",
        "q": search_query,
        "location": "Seattle-Tacoma, WA, Washington, United States",
        "hl": "en",
        "gl": "us",
        "google_domain": "google.com",
        "num": "5",  # Display only the first 5 results
        "start": "10",
        "safe": "active",
        "api_key": api_key
    }

    # Create a GoogleSearch object with the specified parameters
    search = GoogleSearch(params)

    # Perform the search and get the results as a dictionary
    results = search.get_dict()

    # Save all results to a text file
    with open('results/serpapi_results.txt', 'w', encoding='utf-8') as file:
        file.write(json.dumps(results, indent=2, ensure_ascii=False))

    # Print the first 5 results on the screen
    for i, result in enumerate(results.get('organic_results', [])[:5]):
        print_colored_result(i, result)
        
        # Inform the user that the rest of the results were printed to the file
        print(f"{Fore.YELLOW}The rest of the results were saved to 'serpapi_results.txt'.{Style.RESET_ALL}\n")

if __name__ == "__main__":
    main()

