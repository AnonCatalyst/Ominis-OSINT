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
from urllib.parse import urlencode, quote_plus, parse_qs, urlparse
import urllib3
import ssl

# Load utility functions from src/utils.py
from src.utils import find_social_profiles, is_potential_forum, extract_mentions

# Initialize colorama for colored output
init(autoreset=True)

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ssl._create_default_https_context = ssl._create_unverified_context

# Set up error logger
error_logger = logging.getLogger('gfetcherror')
error_logger.setLevel(logging.ERROR)
error_handler = logging.FileHandler('src/gfetcherror.log')
error_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
error_logger.addHandler(error_handler)

# Configure logging
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.basicConfig(
    level=logging.INFO,
    filename='src/gfetcherror.log',
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global variables
visited_urls = set()
counter_emojis = ['🍻', '📑', '📌', '🌐', '🔰', '💀', '🔍', '📮', 'ℹ️', '📂', '📜', '📋', '📨', '🌟', '💫', '✨', '🔥', '🆔', '🎲']
MAX_RETRY_COUNT = 20
MAX_REDIRECTS = 5
show_message = None

# Load social platform patterns
with open("src/social_platforms.json", "r") as json_file:
    social_platforms = json.load(json_file)

# Advanced evasion headers
EVASION_HEADERS = [
    {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "DNT": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1"
    },
    {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "max-age=0",
        "Connection": "keep-alive",
        "TE": "Trailers",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1"
    },
    {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.7",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1"
    }
]

# JA4 fingerprint evasion
JA4_STRINGS = [
    "t13d1516h2_8daaf6152771_0275b9b5b656",  # Chrome-like
    "t13d1516h2_8daaf6152771_61e2afb5b656",  # Firefox-like
    "t13d1516h2_8daaf6152771_9d3b5b5b656"    # Safari-like
]

async def make_request_async(url, proxies=None):
    retry_count = 0
    global show_message
    
    while retry_count < MAX_RETRY_COUNT:
        try:
            # Create custom SSL context for JA3 evasion
            ssl_context = ssl.create_default_context()
            ssl_context.set_ciphers("ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256")
            
            async with httpx.AsyncClient(
                http2=True,
                verify=False,
                timeout=10.0,
                follow_redirects=True,
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            ) as client:
                # Advanced evasion techniques
                headers = random.choice(EVASION_HEADERS).copy()
                headers["User-Agent"] = UserAgent().random.strip()
                
                # JA3/JA4 evasion simulation
                headers["Sec-Ch-Ua"] = '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"'
                headers["Sec-Ch-Ua-Mobile"] = "?0"
                headers["Sec-Ch-Ua-Platform"] = '"Windows"'
                headers["X-Evasion-Fingerprint"] = random.choice(JA4_STRINGS)
                
                if proxies:
                    proxy = random.choice(proxies)
                    if show_message is None:
                        show_message = await ask_to_show_message()
                    if show_message:
                        print(f"  {Fore.LIGHTBLACK_EX}Rotated Proxy{Fore.YELLOW}:{Fore.LIGHTBLACK_EX} {proxy} {Fore.RED}| ", end='')
                    client.proxies = {"http://": proxy, "https://": proxy}

                # Add random delay to simulate human behavior
                await asyncio.sleep(random.uniform(0.1, 0.5))
                
                response = await client.get(
                    url,
                    headers=headers,
                )
                
                if response.status_code in [403, 429]:
                    raise httpx.HTTPStatusError(f"Blocked by server (HTTP {response.status_code})", request=response.request, response=response)
                
                response.raise_for_status()
                return response.text

        except (TimeoutException, RequestError, httpx.HTTPStatusError) as e:
            logger.error(f"Connection error ({retry_count + 1}/{MAX_RETRY_COUNT}): {e}")
            retry_count += 1
            if retry_count < MAX_RETRY_COUNT:
                print(f"{Fore.LIGHTBLACK_EX}Retrying ({retry_count}/{MAX_RETRY_COUNT})...{Style.RESET_ALL}")
                # Exponential backoff with jitter
                sleep_time = min(2 ** retry_count + random.uniform(0, 1), 30)
                await asyncio.sleep(sleep_time)
            else:
                logger.error(f"Max retries exceeded for {url}")
                raise RuntimeError(f"Request failed after {MAX_RETRY_COUNT} retries")
    
    logger.error("All evasion attempts failed")
    return None

async def ask_to_show_message():
    global show_message
    if show_message is None:
        response = await asyncio.to_thread(
            input, 
            f'{Fore.RED}_'*80 + f"\n{Fore.RED}[{Fore.YELLOW}!{Fore.RED}] {Fore.WHITE}Enable proxy rotation display? {Fore.LIGHTBLACK_EX}(y/n){Fore.YELLOW}:{Style.RESET_ALL} "
        )
        show_message = response.strip().lower() == 'y'
    return show_message

async def fetch_engine_results(engine, query, start=0, proxies=None):
    if engine == "duckduckgo":
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}&s={start}"
    elif engine == "bing":
        url = f"https://www.bing.com/search?q={quote_plus(query)}&first={start}"
    else:
        raise ValueError("Unsupported search engine")
    
    try:
        response_text = await make_request_async(url, proxies)
        if not response_text:
            return []
        
        soup = BeautifulSoup(response_text, 'html.parser')
        results = []
        
        if engine == "duckduckgo":
            for result in soup.select('.result'):
                title_elem = result.find('a', class_='result__a')
                if not title_elem:
                    continue
                    
                # Extract URL from DuckDuckGo's redirect link
                href = title_elem.get('href', '')
                if href.startswith('/l/?'):
                    # Parse query parameters from redirect URL
                    parsed = urlparse(href)
                    query_params = parse_qs(parsed.query)
                    real_url = query_params.get('uddg', [''])[0]
                    if real_url:
                        real_url = urllib.parse.unquote(real_url)
                else:
                    real_url = href
                    
                # Skip if we couldn't extract a valid URL
                if not real_url or not real_url.startswith('http'):
                    continue
                    
                results.append({
                    'title': title_elem.get_text(strip=True),
                    'url': real_url
                })
                
        elif engine == "bing":
            for result in soup.select('.b_algo'):
                title_elem = result.find('h2')
                link_elem = result.find('a', href=True)
                if title_elem and link_elem:
                    results.append({
                        'title': title_elem.get_text(strip=True),
                        'url': link_elem['href']
                    })
        
        return results
    
    except Exception as e:
        logger.error(f"{engine.upper()} search failed: {e}")
        return []

async def fetch_dual_engine_results(query, language=None, country=None, date_range=None, proxies=None, max_results=100):
    """
    Main function for dual-engine search that matches the import expectation in ominis.py
    Accepts language, country, and date_range parameters for future compatibility
    """
    # Currently language, country, and date_range are not implemented
    # They are accepted for future compatibility and API consistency
    print(f"{Fore.YELLOW}Note:{Fore.WHITE} Language, country, and date filters are not yet implemented{Style.RESET_ALL}")
    
    # Run the dual-engine search
    return await dual_engine_search(query, proxies, max_results)

async def dual_engine_search(query, proxies=None, max_results=100):
    """
    Actual implementation of the dual-engine search
    """
    engines = ["duckduckgo", "bing"]
    seen_urls = set()
    all_results = []
    all_mention_links = []
    all_unique_social_profiles = set()
    
    # Create results directory if not exists
    os.makedirs("Results", exist_ok=True)
    output_file = f"Results/{query}_dual-engine_results.txt"
    
    with open(output_file, 'w', encoding='utf-8') as file:
        print(f"Search Query: {query}\n{'='*80}", file=file)
        print(f"{Fore.YELLOW}Starting dual-engine search:{Fore.CYAN} DuckDuckGo & Bing{Style.RESET_ALL}")
        print(f"{Fore.LIGHTBLACK_EX}Maximum results set to:{Fore.WHITE} {max_results}{Style.RESET_ALL}")
        
        for engine in engines:
            start = 0
            engine_results_count = 0
            print(f"\n{Fore.YELLOW}Searching{Fore.LIGHTBLACK_EX}:{Fore.CYAN} {engine.upper()}{Style.RESET_ALL}")
            
            while engine_results_count < max_results / len(engines):
                results = await fetch_engine_results(engine, query, start, proxies)
                if not results:
                    print(f"{Fore.LIGHTBLACK_EX}No more results from {engine.upper()}{Style.RESET_ALL}")
                    break
                
                new_results = 0
                for result in results:
                    if result['url'] in seen_urls:
                        continue
                    
                    seen_urls.add(result['url'])
                    all_results.append(result)
                    new_results += 1
                    engine_results_count += 1
                    
                    # Write to file
                    print(f"[{engine.upper()}] Title: {result['title']}\nURL: {result['url']}\n{'-'*80}", file=file)
                    
                    # Console output
                    print('_' * 80)
                    print(f"{random.choice(counter_emojis)} {Fore.YELLOW}Engine{Fore.LIGHTBLACK_EX}:{Fore.CYAN} {engine.upper()}{Style.RESET_ALL}")
                    print(f"{random.choice(counter_emojis)} {Fore.YELLOW}Title{Fore.LIGHTBLACK_EX}: {Fore.BLUE}{result['title']}{Style.RESET_ALL}")
                    print(f"{random.choice(counter_emojis)} {Fore.YELLOW}URL{Fore.LIGHTBLACK_EX}: {Fore.LIGHTBLACK_EX}{result['url']}{Style.RESET_ALL}")
                    
                    # Extract mentions
                    text = f"{result['title']} {result['url']}"
                    mentions = extract_mentions(text, query)
                    for term, count in mentions.items():
                        if count > 0:
                            print(f"{random.choice(counter_emojis)} {Fore.BLUE}{term}{Fore.YELLOW} mentioned {Fore.WHITE}{count}x{Style.RESET_ALL}")
                            all_mention_links.append({"url": result['url'], "count": count})
                    
                    # Find social profiles
                    social_profiles = find_social_profiles(result['url'])
                    if social_profiles:
                        for profile in social_profiles:
                            print(f"{random.choice(counter_emojis)} {Fore.GREEN}{profile['platform']}{Fore.YELLOW}:{Fore.GREEN} {profile['profile_url']}{Style.RESET_ALL}")
                            all_unique_social_profiles.add(profile['profile_url'])
                    
                    # Random delay between processing results
                    await asyncio.sleep(random.uniform(0.3, 1.2))
                
                if new_results == 0:
                    print(f"{Fore.LIGHTBLACK_EX}No new results from {engine.upper()}, moving on...{Style.RESET_ALL}")
                    break
                
                # Update start position for next page
                start += len(results)
                print(f"{Fore.LIGHTBLACK_EX}Page completed for {engine.upper()}. Total: {engine_results_count}{Style.RESET_ALL}")
                
                # Random delay between pages
                await asyncio.sleep(random.uniform(1.5, 3.5))
        
        # Final statistics
        print(f"\n{Fore.GREEN}Search completed!{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Total results:{Fore.WHITE} {len(all_results)}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Unique mentions found:{Fore.WHITE} {len(all_mention_links)}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Social profiles discovered:{Fore.WHITE} {len(all_unique_social_profiles)}{Style.RESET_ALL}")
        
        # Write summary to file
        print(f"\nSummary\n{'='*30}", file=file)
        print(f"Total results: {len(all_results)}", file=file)
        print(f"Unique mentions found: {len(all_mention_links)}", file=file)
        print(f"Social profiles discovered: {len(all_unique_social_profiles)}", file=file)
    
    return len(all_results), all_mention_links, list(all_unique_social_profiles)

# Utility functions (reused from original)
def find_social_profiles(url):
    if not isinstance(url, str):
        raise ValueError("URL must be a string")

    profiles = []

    if url in visited_urls:
        return profiles

    for platform, pattern in social_platforms.items():
        match = re.search(pattern, url)
        if match:
            profile_url = match.group(0)
            profiles.append({"platform": platform, "profile_url": profile_url})

    if is_potential_forum(url):
        profiles.append({"platform": "Forum", "profile_url": url})

    visited_urls.add(url)
    return profiles

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
    subdomain = url_parts.hostname.split('.')[0].lower() if url_parts.hostname else ""
    path_keywords = any(re.search(keyword, path) for keyword in forum_keywords)
    subdomain_keywords = any(re.search(keyword, subdomain) for keyword in forum_keywords)
    return path_keywords or subdomain_keywords

def extract_mentions(text, query):
    if not isinstance(text, str) or not text:
        raise ValueError("Input 'text' must be a non-empty string.")

    if isinstance(query, str):
        query = [query]
    elif not isinstance(query, list) or not all(isinstance(q, str) for q in query):
        raise ValueError("Input 'query' must be a string or a list of strings.")

    mention_count = {q: len(re.findall(re.escape(q), text, re.IGNORECASE)) for q in query}
    return mention_count
