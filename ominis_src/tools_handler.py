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
from httpx import TimeoutException, RequestError
from urllib.parse import urlencode, quote_plus, parse_qs, urlparse

# Load utility functions from ominis_src/utils.py
from ominis_src.utils import (extract_mentions, find_social_profiles,
                              host_matches, is_potential_forum,
                              unwrap_bing_url, unwrap_duckduckgo_url)

# Initialize colorama for colored output
init(autoreset=True)

# Configure logging. A library must not create files in its own package
# directory, and a CLI decides where its own output goes.
logging.getLogger('httpx').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Global variables
visited_urls = set()
counter_emojis = ['🍻', '📑', '📌', '🌐', '🔰', '💀', '🔍', '📮', 'ℹ️', '📂', '📜', '📋', '📨', '🌟', '💫', '✨', '🔥', '🆔', '🎲']
MAX_RETRY_COUNT = 5
MAX_PROXY_RETRY_COUNT = 3
PROXY_REQUEST_TIMEOUT = 30.0
REQUEST_TIMEOUT = 60.0
MAX_BACKOFF = 15.0
MAX_REDIRECTS = 5
show_message = None

# Fixed local list: no download at import time.
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0",
]

# Load social platform patterns
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'social_platforms.json'), "r") as json_file:
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

def _normalize_proxy(proxy):
    """Validate one proxy endpoint without disclosing credentials in errors."""
    if not isinstance(proxy, str) or any(ord(char) < 32 or ord(char) == 127 for char in proxy):
        raise ValueError("Proxy entries must be non-empty strings without control characters")
    proxy = proxy.strip()
    if not proxy:
        raise ValueError("Proxy entries must be non-empty strings")

    bare_endpoint = "://" not in proxy
    if bare_endpoint:
        proxy = "http://" + proxy
    try:
        parsed = urllib.parse.urlsplit(proxy)
        host, port = parsed.hostname, parsed.port
        if parsed.scheme not in ("http", "https", "socks5", "socks5h"):
            raise ValueError("Unsupported proxy scheme")
        if not host or any(char.isspace() or char in "\\/" for char in host):
            raise ValueError("Invalid proxy hostname")
        if parsed.netloc.endswith(":") or (bare_endpoint and port is None):
            raise ValueError("A bare proxy endpoint must include a valid port")
        if port is not None and not 1 <= port <= 65535:
            raise ValueError("Invalid proxy port")
        if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("Proxy endpoints must not include a path, query, or fragment")
        normalized = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
        httpx.Proxy(normalized)
        return normalized
    except (ValueError, httpx.InvalidURL):
        raise ValueError("Invalid proxy endpoint; use host:port or an HTTP(S)/SOCKS5 URL") from None


def _normalize_proxy_pool(proxies):
    if proxies is None:
        return None
    if not isinstance(proxies, (list, tuple)) or not proxies:
        raise ValueError("Supply a non-empty proxy pool, or None for environment routing")
    return [_normalize_proxy(proxy) for proxy in proxies]


def _redact_proxy(proxy):
    parsed = urllib.parse.urlsplit(proxy)
    endpoint = parsed.netloc.rsplit("@", 1)[-1]
    return urllib.parse.urlunsplit((parsed.scheme, endpoint, "", "", ""))


def _safe_proxy_error(error, proxy):
    message = str(error)
    if proxy is not None:
        message = message.replace(proxy, _redact_proxy(proxy))
        parsed = urllib.parse.urlsplit(proxy)
        credentials = {value for value in (parsed.username, parsed.password) if value}
        credentials.update(urllib.parse.unquote(value) for value in list(credentials))
        for value in sorted(credentials, key=len, reverse=True):
            message = message.replace(value, "[redacted]")
    return message


async def make_request_async(url, proxies=None):
    proxies = _normalize_proxy_pool(proxies)
    if proxies is None:
        # A blocked or stalled host must not consume the whole run: the retry
        # loop, its backoff and every request share one wall-clock budget.
        try:
            return await asyncio.wait_for(
                _make_request_with_retries(url, proxies, MAX_RETRY_COUNT),
                timeout=REQUEST_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error("Request exceeded %g-second budget for %s", REQUEST_TIMEOUT, url)
            raise RuntimeError(
                f"Request failed: network budget of {REQUEST_TIMEOUT:g} seconds exceeded"
            ) from None

    # User input must not consume the network retry budget.
    global show_message
    if show_message is None:
        show_message = await ask_to_show_message()
    max_retries = min(MAX_RETRY_COUNT, MAX_PROXY_RETRY_COUNT)
    try:
        return await asyncio.wait_for(
            _make_request_with_retries(url, proxies, max_retries),
            timeout=PROXY_REQUEST_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error("Explicit proxy request exceeded %g-second budget for %s", PROXY_REQUEST_TIMEOUT, url)
        raise RuntimeError(f"Request failed: explicit proxy budget of {PROXY_REQUEST_TIMEOUT:g} seconds exceeded") from None


async def _make_request_with_retries(url, proxies, max_retries):
    retry_count = 0
    while retry_count < max_retries:
        proxy = random.choice(proxies) if proxies is not None else None
        try:
            async with httpx.AsyncClient(
                proxy=proxy,
                http2=True,
                verify=True,
                timeout=10.0,
                follow_redirects=True,
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            ) as client:
                # Advanced evasion techniques
                headers = random.choice(EVASION_HEADERS).copy()
                headers["User-Agent"] = random.choice(USER_AGENTS)
                
                # JA3/JA4 evasion simulation
                headers["Sec-Ch-Ua"] = '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"'
                headers["Sec-Ch-Ua-Mobile"] = "?0"
                headers["Sec-Ch-Ua-Platform"] = '"Windows"'
                headers["X-Evasion-Fingerprint"] = random.choice(JA4_STRINGS)
                
                if proxy is not None:
                    if show_message:
                        print(f"  {Fore.LIGHTBLACK_EX}Rotated Proxy{Fore.YELLOW}:{Fore.LIGHTBLACK_EX} {_redact_proxy(proxy)} {Fore.RED}| ", end='')

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
            detail = _safe_proxy_error(e, proxy) or type(e).__name__
            logger.error(f"Connection error ({retry_count + 1}/{max_retries}): {detail}")
            retry_count += 1
            if retry_count < max_retries:
                print(f"{Fore.LIGHTBLACK_EX}Retrying ({retry_count}/{max_retries})...{Style.RESET_ALL}")
                # Exponential backoff with jitter, capped so a blocked host
                # cannot spend minutes asleep between attempts.
                sleep_time = min(2 ** retry_count + random.uniform(0, 1), MAX_BACKOFF)
                await asyncio.sleep(sleep_time)
            else:
                logger.error(f"Max retries exceeded for {url}")
                raise RuntimeError(f"Request failed after {max_retries} attempts") from None
    
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

    # Validate configuration outside the catch for recoverable search failures.
    proxies = _normalize_proxy_pool(proxies)
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
                href = unwrap_duckduckgo_url(title_elem.get('href', ''))
                if not href or not href.startswith('http'):
                    continue
                tracked = urlparse(href)
                if (host_matches(href, 'duckduckgo.com')
                        and tracked.path.startswith('/y.js')):
                    continue
                    
                results.append({
                    'title': title_elem.get_text(strip=True),
                    'url': href
                })
                
        elif engine == "bing":
            for result in soup.select('.b_algo'):
                title_elem = result.find('h2')
                link_elem = result.find('a', href=True)
                if title_elem and link_elem:
                    results.append({
                        'title': title_elem.get_text(strip=True),
                        'url': unwrap_bing_url(link_elem['href'])
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
    proxies = _normalize_proxy_pool(proxies)
    engines = ["duckduckgo", "bing"]
    seen_urls = set()
    all_results = []
    all_mention_links = []
    all_unique_social_profiles = set()
    
    # Create results directory if not exists
    os.makedirs("Results", exist_ok=True)
    # The query is free text; slug it so it cannot escape Results/.
    from . import report

    output_file = report.results_path("Results", query, "dual-engine_results.txt")
    
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
