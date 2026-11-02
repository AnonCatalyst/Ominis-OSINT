import re
import urllib.parse
import html
import json
import csv
import base64
import logging
import validators

from . import platforms

# Initialize logging
logger = logging.getLogger(__name__)

#: Query parameters that track a click rather than identify a resource.
#: Removing them lets the same result from two engines de-duplicate.
TRACKING_PARAMS = frozenset({
    "fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid", "igshid",
    "yclid", "twclid", "ttclid", "wickedid", "vero_id", "oly_enc_id",
    "oly_anon_id", "ref", "ref_src", "ref_url", "referrer", "source",
    "spm", "scid", "elqTrackId", "elqTrack", "assetType", "assetId",
})


def clean_text(value):
    """Decode escaped entities and normalise remote text for a report.

    Search snippets occasionally arrive double-escaped (``&amp;#39;``), so a
    single ``html.unescape`` left the raw entity visible. Decode until the text
    stops changing, then collapse the whitespace the decode exposed.
    """
    text = str(value or "")
    for _ in range(3):
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded
    for invisible in ("\u200b", "\u200c", "\u200d", "\ufeff"):
        text = text.replace(invisible, "")
    return re.sub(r"\s+", " ", text).strip()


def canonical_url(url):
    """A stable key for de-duplicating the same search result.

    ``http``/``https``, ``www.``, a trailing slash, the fragment and common
    click-tracking parameters do not make a different page. Path case is kept
    because some sites treat it as significant.
    """
    if not isinstance(url, str) or not url.strip():
        return ""
    parsed = urllib.parse.urlsplit(url.strip())
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        return url.strip().casefold()
    if host.startswith("www."):
        host = host[4:]
    if host == "twitter.com":
        host = "x.com"
    port = parsed.port
    if port and port not in (80, 443):
        host = f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    pairs = []
    for key, value in urllib.parse.parse_qsl(parsed.query,
                                             keep_blank_values=True):
        folded = key.casefold()
        if folded in TRACKING_PARAMS or folded.startswith("utm_"):
            continue
        pairs.append((key, value))
    pairs.sort()
    query = urllib.parse.urlencode(pairs)
    return f"https://{host}{path}" + (f"?{query}" if query else "")


def host_matches(url, domain):
    """True when ``url`` belongs to ``domain`` or one of its subdomains.

    Compares the parsed hostname exactly, so ``duckduckgo.com.example.net``
    and ``evilduckduckgo.com`` never match while ``html.duckduckgo.com`` does.
    """
    if not isinstance(url, str):
        return False
    host = (urllib.parse.urlparse(url).hostname or "").lower().rstrip(".")
    domain = domain.lower().rstrip(".")
    return bool(host) and (host == domain or host.endswith("." + domain))


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
    """Detect profile-shaped URLs across the full platform table.

    The precise registry is tried first, then the wide table that earlier
    releases shipped, then the generic forum check. The returned records keep
    the original ``platform`` and ``profile_url`` keys and add ``category``
    and ``confidence`` for ranking.
    """
    if not isinstance(url, str):
        raise ValueError("URL must be a string")

    profiles = platforms.detect_profiles(url)
    if (not profiles and not platforms.is_known_host(url)
            and platforms.is_forum_url(url)):
        profiles = [{"platform": "Forum", "profile_url": url,
                     "category": "forum", "confidence": 30}]
    return profiles


def is_potential_forum(url):
    """True for obvious forum/community URLs (whole words, not substrings)."""
    return platforms.is_forum_url(url)

# Define the extract_mentions function
def _count_phrase(text, phrase):
    """Count whole-word occurrences of a phrase, ignoring word-internal hits.

    ``acme`` in ``acmecorp`` is not a mention, and a two-word query should
    still match when the page breaks the phrase across a line. Word
    boundaries are applied only when the phrase starts or ends with a letter
    or digit, so ``C++`` keeps working.
    """
    phrase = re.sub(r"\s+", " ", phrase.strip())
    if not phrase:
        return 0
    pattern = re.escape(phrase).replace(r"\ ", r"\s+")
    if phrase[0].isalnum() or phrase[0] == "_":
        pattern = r"(?<![A-Za-z0-9_])" + pattern
    if phrase[-1].isalnum() or phrase[-1] == "_":
        pattern = pattern + r"(?![A-Za-z0-9_])"
    return len(re.findall(pattern, text, re.IGNORECASE))


def extract_mentions(text, query):
    if not isinstance(text, str) or not text:
        raise ValueError("Input 'text' must be a non-empty string.")

    if isinstance(query, str):
        queries = [query]
    elif not isinstance(query, list) or not all(isinstance(q, str) for q in query):
        raise ValueError("Input 'query' must be a string or a list of strings.")
    else:
        queries = query

    mention_count = {q: _count_phrase(text, q) for q in queries}
    # A phrase query such as "acme corp" should still show which names were
    # actually seen. Adding the individual words keeps a multi-word search
    # from reporting zero mentions while every result names one of its words.
    for q in queries:
        words = [word.strip(".,;:!?()[]{}\"'")
                 for word in re.split(r"\s+", q) if word.strip()]
        if len(words) < 2:
            continue
        for word in words:
            if len(word) < 3:
                continue
            mention_count.setdefault(word, _count_phrase(text, word))
    return mention_count

# Additional Features

# Function to validate URL
def validate_url(url):
    if not validators.url(url):
        raise ValueError("Invalid URL")

# Function to save results in JSON format
def save_results_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as file:
        json.dump(data, file, indent=4, ensure_ascii=False)

# Function to save results in CSV format
def save_results_csv(filename, data):
    if data:
        with open(filename, 'w', encoding='utf-8', newline='') as file:
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

