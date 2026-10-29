import re
import os
import urllib.parse
import json
import csv
import base64
import logging
import validators

# Initialize logging
logger = logging.getLogger(__name__)

# Load social platform patterns from a JSON file
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'social_platforms.json'), "r", encoding="utf-8") as json_file:
    social_platforms = json.load(json_file)


def unwrap_duckduckgo_url(url):
    """Return the destination behind DuckDuckGo's ``/l/`` redirect.

    The HTML endpoint emits both ``/l/?uddg=...`` and protocol-relative
    ``//duckduckgo.com/l/?uddg=...`` links; treating either as a result URL
    loses every hit.
    """
    if not isinstance(url, str) or not url:
        return url
    absolute = "https:" + url if url.startswith("//") else url
    parsed = urllib.parse.urlparse(absolute)
    host = (parsed.hostname or "").lower()
    if host and not (host == "duckduckgo.com" or host.endswith(".duckduckgo.com")):
        return url
    if not parsed.path.startswith("/l/"):
        return url
    target = urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
    return urllib.parse.unquote(target) if target else url


def unwrap_bing_url(url):
    """Return the destination behind Bing's ``/ck/a`` click tracker.

    Modern Bing results link to ``bing.com/ck/a?...&u=a1<base64url>`` rather
    than the destination, which made every result point back at Bing.
    """
    if not isinstance(url, str):
        return url
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if not (host == "bing.com" or host.endswith(".bing.com")):
        return url
    if not parsed.path.startswith("/ck/a"):
        return url
    target = urllib.parse.parse_qs(parsed.query).get("u", [""])[0]
    if not target.startswith("a1"):
        return url
    encoded = target[2:]
    encoded += "=" * (-len(encoded) % 4)
    try:
        decoded = base64.urlsafe_b64decode(encoded).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return url
    return decoded if decoded.startswith("http") else url


def find_social_profiles(url):
    if not isinstance(url, str):
        raise ValueError("URL must be a string")

    profiles = []

    for platform, pattern in social_platforms.items():
        match = re.search(pattern, url)
        if match:
            profile_url = match.group(0)
            profiles.append({"platform": platform, "profile_url": profile_url})

    if is_potential_forum(url):
        profiles.append({"platform": "Forum", "profile_url": url})

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
    subdomain = (url_parts.hostname or "").split('.')[0].lower()
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

