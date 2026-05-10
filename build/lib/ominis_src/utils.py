import re
import urllib.parse
import json
import logging
import csv
import validators

# Initialize logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

visited_urls = set()
# Load social platform patterns from a JSON file
with open("src/social_platforms.json", "r") as json_file:
    social_platforms = json.load(json_file)

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

# Additional Features

# Function to validate URL
def validate_url(url):
    if not validators.url(url):
        raise ValueError("Invalid URL")

# Function to save results in JSON format
def save_results_json(filename, data):
    with open(filename, 'w') as file:
        json.dump(data, file, indent=4)

# Function to save results in CSV format
def save_results_csv(filename, data):
    if data:
        with open(filename, 'w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
    else:
        logging.warning("No data to save to CSV.")

# Example usage
if __name__ == "__main__":
    test_url = "https://twitter.com/user"
    
    # Validate URL
    try:
        validate_url(test_url)
    except ValueError as e:
        logging.error(f"URL validation error: {e}")
    
    # Find social profiles
    try:
        profiles = find_social_profiles(test_url)
        save_results_json("profiles.json", profiles)
        save_results_csv("profiles.csv", profiles)
        logging.info(f"Profiles found: {profiles}")
    except Exception as e:
        logging.error(f"Error finding profiles: {e}")

    # Extract mentions
    text = "Here is a mention of mention1 and another mention1."
    try:
        mentions = extract_mentions(text, ["mention1", "mention2"])
        save_results_json("mentions.json", mentions)
        logging.info(f"Mentions found: {mentions}")
    except Exception as e:
        logging.error(f"Error extracting mentions: {e}")

