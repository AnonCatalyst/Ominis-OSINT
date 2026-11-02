"""Platform detection for URLs found by the search and username checks.

The old detector matched one regular expression per platform against the whole
URL, so ``github.com/features`` looked like a GitHub profile, ``pornhub.com``
looked like a forum because the host contains "hub", and an issue page was
reported as its author. This module keeps a small, auditable table of
platforms: an exact host, a path shape, a category and a confidence. A URL is
only a profile when the host matches *and* the path is profile-shaped.

Detection is deliberately conservative. A false negative costs one lead; a
false positive costs an analyst's trust in the whole report.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Mapping

#: Path words that are sections of a site, never handles.
#:
#: ``p`` is here because almost every site that uses a single-letter path
#: reserves it for a content item (``instagram.com/p/<code>``,
#: ``twitch.tv/p/...``). A bare ``/p`` is too ambiguous to call a profile, and
#: treating it as one produced a false positive on every platform in the wide
#: table.
RESERVED = frozenset({
    "about", "account", "accounts", "admin", "api", "apps", "blog", "business",
    "careers", "category", "clips", "collections", "community", "company",
    "contact", "create", "dashboard", "developers", "discover", "docs",
    "download", "downloads", "edit", "events", "explore", "features", "feed",
    "followers", "following", "friends", "gaming", "groups", "help", "home",
    "index", "investors", "jobs", "join", "legal", "login", "logout",
    "marketplace", "media", "members", "messages", "new", "news",
    "notifications", "p", "pages", "partners", "photos", "playlists", "press",
    "pricing", "privacy", "products", "profile", "reels", "register", "rss",
    "saved", "search", "security", "settings", "shop", "signin", "signup",
    "sitemap", "sponsors", "status", "stories", "store", "support", "tags",
    "team", "terms", "topics", "trending", "upload", "user", "users", "videos",
    "watch",
})

_HANDLE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@-]{0,63}")
_NUMERIC = re.compile(r"[0-9]{1,25}")


@dataclass(frozen=True)
class Platform:
    """One site with a profile-shaped URL."""

    name: str
    hosts: tuple[str, ...]
    pattern: str
    category: str
    confidence: int = 80
    #: Read the handle from this query parameter instead of the path.
    query_param: str = ""
    #: The handle is the left-most host label (``name.bandcamp.com``).
    subdomain: bool = False

    @property
    def regex(self) -> re.Pattern[str]:
        return _compile(self.pattern)


@lru_cache(maxsize=None)
def _compile(pattern: str) -> re.Pattern[str]:
    # Only the URL shape is matched here; handles are checked separately.
    # Ignoring case lets templates such as ``/wiki/user:`` match Wikipedia's
    # case-sensitive-looking but equivalent ``User:`` pages.
    return re.compile(pattern, re.IGNORECASE)


#: Ordered so that specific hosts are tried before the generic fallbacks.
PLATFORMS: tuple[Platform, ...] = (
    # --- social / microblog ------------------------------------------------
    Platform("X (Twitter)", ("x.com", "twitter.com"),
             r"^/(?!i/|home|explore|search|hashtag|intent|share|settings|login|"
             r"signup|messages|notifications|compose|tos|privacy)"
             r"([A-Za-z0-9_]{1,15})/?$", "social", 90),
    Platform("Threads", ("threads.net", "threads.com"),
             r"^/@([A-Za-z0-9._]{1,30})/?$", "social", 90),
    Platform("Bluesky", ("bsky.app",),
             r"^/profile/([A-Za-z0-9.-]{3,100})/?$", "social", 95),
    Platform("Mastodon", (
        "mastodon.social", "mastodon.online", "mstdn.social", "fosstodon.org",
        "hachyderm.io", "infosec.exchange", "techhub.social", "mas.to",
        "toot.community", "mastodon.world", "universeodon.com",
        "social.tchncs.de", "mastodon.cloud", "mstdn.jp", "pawoo.net"),
             r"^/@([A-Za-z0-9_]{1,64})(?:@[A-Za-z0-9.-]+)?/?$",
             "social", 85),
    Platform("Instagram", ("instagram.com",),
             r"^/(?!p/|reel|reels|explore|accounts|stories|tv/|direct|about|"
             r"legal|developer)([A-Za-z0-9._]{1,30})/?$", "social", 85),
    Platform("Facebook", ("facebook.com", "fb.com"),
             r"^/(?:people/[A-Za-z0-9._-]{2,60}/)?([A-Za-z0-9.]{5,50})/?$",
             "social", 75),
    Platform("Facebook (numeric id)", ("facebook.com", "fb.com"),
             r"^/profile\.php/?$", "social", 75, query_param="id"),
    Platform("TikTok", ("tiktok.com",),
             r"^/@([A-Za-z0-9._]{2,24})", "social", 95),
    Platform("Snapchat", ("snapchat.com",),
             r"^/add/([A-Za-z0-9._-]{1,30})/?$", "social", 85),
    Platform("Tumblr", ("tumblr.com",),
             r"^/([A-Za-z0-9-]{1,32})/?$", "social", 70),
    Platform("Pinterest", ("pinterest.com",),
             r"^/(?!pin/|ideas|search|explore|today)([A-Za-z0-9_]{1,30})/?$",
             "social", 75),
    Platform("Reddit", ("reddit.com",),
             r"^/(?:user|u)/([A-Za-z0-9_-]{3,20})/?$", "forum", 90),
    Platform("Quora", ("quora.com",),
             r"^/profile/([A-Za-z0-9-]{2,60})/?$", "social", 85),
    Platform("Telegram", ("t.me", "telegram.me"),
             r"^/(?!s/|joinchat|addstickers|share|proxy)([A-Za-z0-9_]{4,32})/?$",
             "messaging", 80),
    Platform("Discord", ("discord.com", "discordapp.com"),
             r"^/users/([0-9]{5,25})/?$", "messaging", 85),
    Platform("VK", ("vk.com",),
             r"^/(?!video|wall|away|feed|im|friends|groups|photos|audio|market)"
             r"([A-Za-z0-9._-]{3,32})/?$", "social", 75),
    Platform("OK.ru", ("ok.ru",),
             r"^/profile/([0-9]{3,20})/?$", "social", 80),
    Platform("Weibo", ("weibo.com",),
             r"^/u/([0-9]{3,20})/?$", "social", 80),
    Platform("Keybase", ("keybase.io",),
             r"^/([A-Za-z0-9_]{2,16})/?$", "social", 80),
    Platform("Minds", ("minds.com",),
             r"^/(?!newsfeed|discovery|settings|wallet|groups|channels)"
             r"([A-Za-z0-9._-]{2,40})/?$", "social", 70),
    Platform("Gab", ("gab.com",),
             r"^/(?!explore|discover|settings|search)([A-Za-z0-9._-]{2,40})/?$",
             "social", 70),
    Platform("Linktree", ("linktr.ee",),
             r"^/([A-Za-z0-9._-]{1,40})/?$", "links", 75),
    Platform("About.me", ("about.me",),
             r"^/([A-Za-z0-9._-]{1,40})/?$", "links", 70),

    # --- video / streaming -------------------------------------------------
    Platform("YouTube", ("youtube.com",),
             r"^/(?:@([A-Za-z0-9._-]{3,30})|c/([A-Za-z0-9._-]+)|"
             r"user/([A-Za-z0-9._-]+)|channel/(UC[A-Za-z0-9_-]{20,}))/?$",
             "video", 90),
    Platform("Twitch", ("twitch.tv",),
             r"^/(?!directory|p/|search|settings|subscriptions|inventory|wallet)"
             r"([A-Za-z0-9_]{3,25})/?$", "video", 85),
    Platform("Vimeo", ("vimeo.com",),
             r"^/(?!channels|groups|ondemand|features|watch|search|upgrade)"
             r"([A-Za-z0-9._-]{1,40})/?$", "video", 80),
    Platform("Rumble", ("rumble.com",),
             r"^/(?:user|c)/([A-Za-z0-9._-]{1,50})/?$", "video", 80),
    Platform("Odysee", ("odysee.com",),
             r"^/@([A-Za-z0-9._-]{1,60})", "video", 80),
    Platform("Kick", ("kick.com",),
             r"^/(?!categories|browse|following)([A-Za-z0-9_]{3,25})/?$",
             "video", 80),
    Platform("Dailymotion", ("dailymotion.com",),
             r"^/(?:user/)?([A-Za-z0-9._-]{2,40})/?$", "video", 65),
    Platform("Bitchute", ("bitchute.com",),
             r"^/channel/([A-Za-z0-9_-]{3,60})/?$", "video", 80),

    # --- music -------------------------------------------------------------
    Platform("SoundCloud", ("soundcloud.com",),
             r"^/(?!you|discover|search|stream|upload|pages|imprint|charts)"
             r"([A-Za-z0-9._-]{1,50})/?$", "music", 75),
    Platform("Bandcamp", ("bandcamp.com",), r"^/(?:album|track)/",
             "music", 80, subdomain=True),
    Platform("Spotify", ("spotify.com",),
             r"^/(?:user|artist)/([A-Za-z0-9]{5,40})/?$", "music", 80),
    Platform("Last.fm", ("last.fm",),
             r"^/user/([A-Za-z0-9_-]{2,50})/?$", "music", 85),
    Platform("Mixcloud", ("mixcloud.com",),
             r"^/(?!upload|search|discover|features)([A-Za-z0-9_-]{2,50})/?$",
             "music", 70),
    Platform("Discogs", ("discogs.com",),
             r"^/user/([A-Za-z0-9._-]{2,50})/?$", "music", 80),
    Platform("Genius", ("genius.com",),
             r"^/(?:artists/)?([A-Za-z0-9_-]{2,60})/?$", "music", 65),

    # --- developer ---------------------------------------------------------
    Platform("GitHub", ("github.com",),
             r"^/([A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?)/?$",
             "dev", 90),
    Platform("GitLab", ("gitlab.com",),
             r"^/(?!explore|help|users|admin|search|dashboard|projects|groups|"
             r"-/)([A-Za-z0-9._-]{1,60})/?$", "dev", 80),
    Platform("Bitbucket", ("bitbucket.org",),
             r"^/(?!product|account|site|blog|dashboard|repo|plugins)"
             r"([A-Za-z0-9._-]{1,60})/?$", "dev", 80),
    Platform("Codeberg", ("codeberg.org",),
             r"^/(?!explore|help|api|user)([A-Za-z0-9._-]{1,60})/?$",
             "dev", 80),
    Platform("Sourcehut", ("sr.ht",),
             r"^/~([A-Za-z0-9._-]{1,60})/?$", "dev", 85),
    Platform("Stack Overflow", ("stackoverflow.com",),
             r"^/users/([0-9]{2,15})/?$", "dev", 90),
    Platform("Stack Exchange", ("stackexchange.com", "superuser.com",
                                "serverfault.com", "askubuntu.com"),
             r"^/users/([0-9]{2,15})/?$", "dev", 85),
    Platform("Hacker News", ("news.ycombinator.com",), r"^/user/?$",
             "forum", 85, query_param="id"),
    Platform("Lobsters", ("lobste.rs",),
             r"^/~([A-Za-z0-9._-]{1,40})/?$", "forum", 80),
    Platform("Dev.to", ("dev.to",),
             r"^/(?!t/|tags|top|latest|search|new|settings|dashboard)"
             r"([A-Za-z0-9_]{1,30})/?$", "dev", 80),
    Platform("Hashnode", ("hashnode.com",),
             r"^/@([A-Za-z0-9_-]{1,40})/?$", "dev", 80),
    Platform("CodePen", ("codepen.io",),
             r"^/(?!pen/|search|challenges|pens|settings)([A-Za-z0-9_-]{3,30})/?$",
             "dev", 80),
    Platform("Replit", ("replit.com",),
             r"^/@([A-Za-z0-9_-]{1,40})/?$", "dev", 80),
    Platform("Hugging Face", ("huggingface.co",),
             r"^/(?!models|datasets|spaces|docs|pricing|blog|papers|tasks|search)"
             r"([A-Za-z0-9_.-]{1,60})/?$", "dev", 75),
    Platform("Kaggle", ("kaggle.com",),
             r"^/(?!competitions|datasets|code|discussions|learn|search)"
             r"([A-Za-z0-9_-]{2,50})/?$", "dev", 80),
    Platform("LeetCode", ("leetcode.com",),
             r"^/(?:u/)?([A-Za-z0-9_-]{2,40})/?$", "dev", 75),
    Platform("npm", ("npmjs.com",),
             r"^/~([A-Za-z0-9._-]{1,60})/?$", "dev", 85),
    Platform("PyPI", ("pypi.org",),
             r"^/user/([A-Za-z0-9._-]{1,60})/?$", "dev", 85),
    Platform("Docker Hub", ("hub.docker.com",),
             r"^/u/([A-Za-z0-9._-]{1,60})/?$", "dev", 85),
    Platform("crates.io", ("crates.io",),
             r"^/users/([A-Za-z0-9_-]{1,60})/?$", "dev", 85),
    Platform("RubyGems", ("rubygems.org",),
             r"^/profiles/([A-Za-z0-9._-]{1,60})/?$", "dev", 85),

    # --- writing / blogs ---------------------------------------------------
    Platform("Medium", ("medium.com",),
             r"^/@([A-Za-z0-9._-]{1,60})/?$", "blog", 85),
    Platform("Substack", ("substack.com",), r"^/",
             "blog", 85, subdomain=True),
    Platform("WordPress", ("wordpress.com",),
             r"^/(?!tag/|category/|about|read|search|themes|plugins|start)"
             r"([A-Za-z0-9._-]{1,60})/?$", "blog", 70),
    Platform("Blogger", ("blogspot.com",), r"^/",
             "blog", 80, subdomain=True),
    Platform("Wattpad", ("wattpad.com",),
             r"^/user/([A-Za-z0-9._-]{1,60})/?$", "writing", 80),
    Platform("Archive of Our Own", ("archiveofourown.org",),
             r"^/users/([A-Za-z0-9_-]{1,60})/?$", "writing", 85),
    Platform("Goodreads", ("goodreads.com",),
             r"^/user/show/([0-9]{2,15})", "writing", 85),
    Platform("Letterboxd", ("letterboxd.com",),
             r"^/(?!films|lists|members|journal|reviews|search)"
             r"([A-Za-z0-9_]{2,30})/?$", "writing", 75),
    Platform("Trakt", ("trakt.tv",),
             r"^/users/([A-Za-z0-9._-]{1,60})/?$", "writing", 85),
    Platform("RateYourMusic", ("rateyourmusic.com",),
             r"^/user/([A-Za-z0-9._-]{1,60})/?$", "writing", 85),
    Platform("MyAnimeList", ("myanimelist.net",),
             r"^/profile/([A-Za-z0-9_-]{1,60})/?$", "anime", 85),
    Platform("AniList", ("anilist.co",),
             r"^/user/([A-Za-z0-9_-]{1,60})/?$", "anime", 85),

    # --- photo / art -------------------------------------------------------
    Platform("Flickr", ("flickr.com",),
             r"^/(?:people|photos)/([A-Za-z0-9@._-]{1,60})/?$", "photo", 85),
    Platform("500px", ("500px.com",),
             r"^/(?!photo/|search|marketplace|blog)([A-Za-z0-9._-]{1,60})/?$",
             "photo", 70),
    Platform("DeviantArt", ("deviantart.com",),
             r"^/(?!art/|gallery|search|shop|join|users|tag)"
             r"([A-Za-z0-9-]{2,30})/?$", "photo", 75),
    Platform("Behance", ("behance.net",),
             r"^/(?!search|gallery|joblist|assets|services)"
             r"([A-Za-z0-9._-]{1,60})/?$", "photo", 80),
    Platform("Dribbble", ("dribbble.com",),
             r"^/(?!search|jobs|tags|stories|shots|designers|resources)"
             r"([A-Za-z0-9._-]{1,60})/?$", "photo", 80),
    Platform("ArtStation", ("artstation.com",),
             r"^/(?!artwork|jobs|contests|learning|search|marketplace)"
             r"([A-Za-z0-9._-]{1,60})/?$", "photo", 75),
    Platform("Unsplash", ("unsplash.com",),
             r"^/@([A-Za-z0-9._-]{1,60})/?$", "photo", 80),
    Platform("VSCO", ("vsco.co",),
             r"^/(?!search|discover|about|create)([A-Za-z0-9._-]{1,60})/?$",
             "photo", 70),

    # --- professional / marketplace ---------------------------------------
    Platform("LinkedIn", ("linkedin.com",),
             r"^/(?:in|company|school)/([A-Za-z0-9._-]{2,100})/?$",
             "professional", 90),
    Platform("XING", ("xing.com",),
             r"^/profile/([A-Za-z0-9._-]{2,60})/?$", "professional", 85),
    Platform("Wellfound", ("wellfound.com", "angel.co"),
             r"^/u/([A-Za-z0-9._-]{2,60})/?$", "professional", 80),
    Platform("Product Hunt", ("producthunt.com",),
             r"^/@([A-Za-z0-9_-]{1,60})/?$", "professional", 80),
    Platform("Crunchbase", ("crunchbase.com",),
             r"^/person/([A-Za-z0-9._-]{2,60})/?$", "professional", 85),
    Platform("Fiverr", ("fiverr.com",),
             r"^/(?!search|join|categories|pro|support|login)"
             r"([A-Za-z0-9._-]{1,60})/?$", "marketplace", 70),
    Platform("Upwork", ("upwork.com",),
             r"^/freelancers/~([0-9a-f]{10,40})/?$", "marketplace", 85),
    Platform("Freelancer", ("freelancer.com",),
             r"^/u/([A-Za-z0-9._-]{1,60})/?$", "marketplace", 80),
    Platform("Toptal", ("toptal.com",),
             r"^/profiles/([A-Za-z0-9._-]{1,60})/?$", "professional", 85),
    Platform("Etsy", ("etsy.com",),
             r"^/(?:shop|people)/([A-Za-z0-9._-]{1,60})/?$", "marketplace", 80),
    Platform("eBay", ("ebay.com",),
             r"^/usr/([A-Za-z0-9._-]{1,60})/?$", "marketplace", 85),

    # --- gaming ------------------------------------------------------------
    Platform("Steam", ("steamcommunity.com",),
             r"^/(?:id|profiles)/([A-Za-z0-9_-]{2,40})/?$", "gaming", 85),
    Platform("PlayStation Network", ("my.playstation.com",),
             r"^/profile/([A-Za-z0-9_-]{2,60})/?$", "gaming", 75),
    Platform("Roblox", ("roblox.com",),
             r"^/users/([0-9]{3,20})/profile/?$", "gaming", 85),
    Platform("itch.io", ("itch.io",),
             r"^/profile/([A-Za-z0-9._-]{1,60})/?$", "gaming", 80),
    Platform("Speedrun.com", ("speedrun.com",),
             r"^/user/([A-Za-z0-9._-]{1,60})/?$", "gaming", 80),
    Platform("Chess.com", ("chess.com",),
             r"^/member/([A-Za-z0-9_-]{1,40})/?$", "gaming", 85),
    Platform("Lichess", ("lichess.org",),
             r"^/@/([A-Za-z0-9_-]{1,40})/?$", "gaming", 80),
    Platform("BoardGameGeek", ("boardgamegeek.com",),
             r"^/user/([A-Za-z0-9_-]{1,60})/?$", "gaming", 80),

    # --- research / education ---------------------------------------------
    Platform("ORCID", ("orcid.org",),
             r"^/([0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X])/?$",
             "research", 90),
    Platform("Google Scholar", ("scholar.google.com",), r"^/citations/?$",
             "research", 85, query_param="user"),
    Platform("ResearchGate", ("researchgate.net",),
             r"^/profile/([A-Za-z0-9._-]{2,80})/?$", "research", 85),
    Platform("Academia.edu", ("academia.edu",),
             r"^/(?!search|about|jobs|topics)([A-Za-z0-9._-]{2,60})/?$",
             "research", 65),

    # --- forums / community ------------------------------------------------
    Platform("BitcoinTalk", ("bitcointalk.org",), r"^/index\.php/?$",
             "forum", 80, query_param="u"),
    Platform("XDA Forums", ("xdaforums.com",),
             r"^/members/([A-Za-z0-9._-]{1,60})/?$", "forum", 80),

    # --- recovered from the original platform tables -----------------------
    Platform("WhatsApp", ("wa.me",), r"^/([0-9+]{6,20})/?$", "messaging", 85),
    Platform("Patreon", ("patreon.com",),
             r"^/([A-Za-z0-9._-]{2,60})/?$", "social", 80),
    Platform("PayPal.me", ("paypal.me",),
             r"^/([A-Za-z0-9._-]{2,60})/?$", "finance", 85),
    Platform("DonationAlerts", ("donationalerts.com",),
             r"^/r/([A-Za-z0-9._-]{1,60})/?$", "finance", 85),
    Platform("Pastebin", ("pastebin.com",),
             r"^/u/([A-Za-z0-9._-]{1,60})/?$", "leak", 85),
    Platform("JustPaste.it", ("justpaste.it",),
             r"^/u/([A-Za-z0-9._-]{1,60})/?$", "leak", 80),
    Platform("Doxbin", ("doxbin.com",),
             r"^/user/([A-Za-z0-9._-]{1,60})/?$", "leak", 85),
    Platform("Duolingo", ("duolingo.com",),
             r"^/profile/([A-Za-z0-9._-]{1,60})/?$", "education", 85),
    Platform("Khan Academy", ("khanacademy.org",),
             r"^/profiles/([A-Za-z0-9._-]{1,60})/?$", "education", 80),
    Platform("Wikipedia", ("wikipedia.org",),
             r"^/wiki/User:([A-Za-z0-9._-]{1,80})/?$", "research", 85),
    Platform("OpenStreetMap", ("openstreetmap.org",),
             r"^/user/([A-Za-z0-9._-]{1,80})/?$", "research", 85),
    Platform("Yelp", ("yelp.com",), r"^/user_details/?$",
             "review", 80, query_param="userid"),
    Platform("TripAdvisor", ("tripadvisor.com",),
             r"^/members/([A-Za-z0-9._-]{1,60})/?$", "travel", 80),
    Platform("AllTrails", ("alltrails.com",),
             r"^/members/([A-Za-z0-9._-]{1,60})/?$", "fitness", 80),
    Platform("Couchsurfing", ("couchsurfing.com",),
             r"^/people/([A-Za-z0-9._-]{1,60})/?$", "travel", 80),
    Platform("Trustpilot", ("trustpilot.com",),
             r"^/users/([A-Za-z0-9._-]{1,60})/?$", "review", 80),
    Platform("Newgrounds", ("newgrounds.com",),
             r"^/([A-Za-z0-9._-]{2,40})/?$", "gaming", 70),
    Platform("9GAG", ("9gag.com",),
             r"^/u/([A-Za-z0-9._-]{1,60})/?$", "social", 80),
    Platform("Giphy", ("giphy.com",),
             r"^/channel/([A-Za-z0-9._-]{1,60})/?$", "video", 75),
    Platform("Kickstarter", ("kickstarter.com",),
             r"^/profile/([A-Za-z0-9._-]{1,60})/?$", "finance", 80),
    Platform("Anime-Planet", ("anime-planet.com",),
             r"^/users/([A-Za-z0-9._-]{1,60})/?$", "anime", 80),
    Platform("Crunchyroll", ("crunchyroll.com",),
             r"^/user/([A-Za-z0-9._-]{1,60})/?$", "anime", 80),
    Platform("Zotero", ("zotero.org",),
             r"^/([A-Za-z0-9._-]{2,40})/?$", "research", 70),
    Platform("Instructables", ("instructables.com",),
             r"^/member/([A-Za-z0-9._-]{1,60})/?$", "diy", 80),
    Platform("Thingiverse", ("thingiverse.com",),
             r"^/([A-Za-z0-9._-]{2,60})/?$", "diy", 70),
    Platform("Houzz", ("houzz.com",),
             r"^/user/([0-9]{2,20})/?$", "marketplace", 75),
    Platform("Slack", ("slack.com",), r"^/team/",
             "messaging", 70, subdomain=True),
    Platform("Foursquare", ("foursquare.com",),
             r"^/user/([A-Za-z0-9._-]{1,60})/?$", "social", 75),
    Platform("Meetup", ("meetup.com",),
             r"^/members/([A-Za-z0-9._-]{1,60})/?$", "social", 80),
    Platform("Badoo", ("badoo.com",),
             r"^/profile/([A-Za-z0-9._-]{1,60})/?$", "dating", 80),
    Platform("Mamba", ("mamba.ru",),
             r"^/([A-Za-z0-9._-]{2,40})/?$", "dating", 65),

    # --- adult model pages (public profiles only) --------------------------
    Platform("RedTube", ("redtube.com",),
             r"^/users/([A-Za-z0-9._-]{1,60})/?$", "adult", 80),
    Platform("XVideos", ("xvideos.com",),
             r"^/profiles/([A-Za-z0-9._-]{1,60})/?$", "adult", 80),
    Platform("YouPorn", ("youporn.com",),
             r"^/(?:users|model)/([A-Za-z0-9._-]{1,60})/?$", "adult", 75),
    Platform("Chaturbate", ("chaturbate.com",),
             r"^/([A-Za-z0-9_]{2,40})/?$", "adult", 70),
    Platform("StripChat", ("stripchat.com",),
             r"^/([A-Za-z0-9_]{2,40})/?$", "adult", 70),
    Platform("CamSoda", ("camsoda.com",),
             r"^/([A-Za-z0-9_]{2,40})/?$", "adult", 65),
    Platform("BongaCams", ("bongacams.com",),
             r"^/([A-Za-z0-9_]{2,40})/?$", "adult", 65),
    Platform("LiveJasmin", ("livejasmin.com",),
             r"^/([A-Za-z0-9_]{2,40})/?$", "adult", 65),
    Platform("MyFreeCams", ("myfreecams.com",),
             r"^/([A-Za-z0-9_]{2,40})/?$", "adult", 65),
    Platform("Flirt4Free", ("flirt4free.com",),
             r"^/([A-Za-z0-9_]{2,40})/?$", "adult", 65),
    Platform("ImLive", ("imlive.com",),
             r"^/([A-Za-z0-9_]{2,40})/?$", "adult", 60),
    Platform("Cam4", ("cam4.com",),
             r"^/([A-Za-z0-9_]{2,40})/?$", "adult", 60),

    # --- recovered blog / community / gaming hosts -------------------------
    Platform("LiveJournal", ("livejournal.com",),
             r"^/users/([A-Za-z0-9._-]{1,60})/?$", "blog", 75),
    Platform("Myspace", ("myspace.com",),
             r"^/([A-Za-z0-9._-]{2,40})/?$", "social", 65),
    Platform("Ello", ("ello.co",),
             r"^/([A-Za-z0-9._-]{2,40})/?$", "social", 65),
    Platform("BlogLovin", ("bloglovin.com",),
             r"^/@([A-Za-z0-9._-]{1,60})/?$", "blog", 75),
    Platform("Wix", ("wixsite.com",), r"^/", "blog", 70, subdomain=True),
    Platform("Weebly", ("weebly.com",), r"^/", "blog", 70, subdomain=True),
    Platform("Squarespace", ("squarespace.com",), r"^/", "blog", 65,
             subdomain=True),
    Platform("Ghost", ("ghost.io",), r"^/", "blog", 70, subdomain=True),
    Platform("Xbox", ("account.xbox.com",), r"^/profile/?$",
             "gaming", 80, query_param="gamertag"),
    Platform("Nintendo", ("nintendo.com",),
             r"^/profile/([A-Za-z0-9._-]{1,60})/?$", "gaming", 75),
    Platform("GOG.com", ("gog.com",),
             r"^/u/([A-Za-z0-9._-]{1,60})/?$", "gaming", 80),
    Platform("Rockstar Social Club", ("socialclub.rockstargames.com",),
             r"^/member/([A-Za-z0-9._-]{1,60})/?$", "gaming", 80),
    Platform("Gaia Online", ("gaiaonline.com",),
             r"^/profiles/([A-Za-z0-9._-]{1,60})/?$", "gaming", 75),
    Platform("HackerRank", ("hackerrank.com",),
             r"^/(?:profile/)?([A-Za-z0-9._-]{2,40})/?$", "dev", 75),
    Platform("DZone", ("dzone.com",),
             r"^/users/([A-Za-z0-9._-]{1,60})/?$", "dev", 75),
    Platform("Slashdot", ("slashdot.org",),
             r"^/~([A-Za-z0-9._-]{1,60})/?$", "forum", 80),
    Platform("Linux.org", ("linux.org",),
             r"^/members/([A-Za-z0-9._-]{1,60})/?$", "forum", 75),
    Platform("BitcoinForum", ("bitcoinforum.com",),
             r"^/profile/([0-9]{1,20})/?$", "forum", 85),
    Platform("AnalystForum", ("analystforum.com",),
             r"^/u/([A-Za-z0-9._-]{1,60})/?$", "finance", 80),
    Platform("Signal Community", ("community.signalusers.org",),
             r"^/u/([A-Za-z0-9._-]{1,60})/?$", "forum", 80),

    # --- adult (public profiles only) -------------------------------------
    Platform("Pornhub", ("pornhub.com",),
             r"^/(?:users|model|pornstar)/([A-Za-z0-9._-]{1,60})/?$",
             "adult", 75),
    Platform("xHamster", ("xhamster.com",),
             r"^/profile/([A-Za-z0-9._-]{1,60})/?$", "adult", 70),
)

#: The wide platform table shipped by every earlier release. It is a
#: first-class detection layer, not a fallback: the precise entries above run
#: first for accuracy, then this table covers the long tail (dating, cams,
#: regional forums, niche marketplaces). Every pattern is anchored to its host
#: and must consume the whole path, so deep links such as
#: ``reddit.com/user/x/comments/y`` are not misread as a profile.
_EXTENDED_FILE = Path(__file__).with_name("social_platforms.json")
EXTENDED_CATEGORIES = {
    name: category
    for category, names in {
        "social": (
            "Instagram", "Twitter", "Facebook", "Pinterest", "Tumblr",
            "Snapchat", "TikTok", "Foursquare", "Meetup", "Quora",
            "Bumble", "Hinge",
        ),
        "professional": ("LinkedIn",),
        "messaging": ("WhatsApp", "Skype", "Slack", "Discord"),
        "forum": ("Reddit",),
        "blog": (
            "Medium", "WordPress", "Blogger", "LiveJournal", "Wix", "Weebly",
            "Squarespace", "Ghost", "Hashnode",
        ),
        "video": ("YouTube", "Vimeo", "Twitch"),
        "music": ("SoundCloud", "Spotify", "Last.fm"),
        "photo": (
            "Flickr", "Dribbble", "Behance", "500px", "DeviantArt",
            "ArtStation", "Coroflot",
        ),
        "dating": (
            "Badoo", "Zoosk", "OkCupid", "Plenty of Fish", "Tinder",
            "Match.com", "Eharmony", "MeetMe", "Coffee Meets Bagel", "Her",
            "Grindr", "Jack'd", "Hornet", "Scruff", "PlanetRomeo", "Gays.com",
            "Ashley Madison", "AdultFriendFinder",
        ),
        "adult": (
            "Xvideos", "Pornhub", "YouPorn", "RedTube", "Xhamster",
            "Chaturbate", "CamSoda", "MyFreeCams", "BongaCams", "StripChat",
            "ImLive", "Flirt4Free", "Cams.com", "Jasmin", "LiveJasmin",
            "MyDirtyHobby", "Cameraprive", "CamWithHer", "iFriends",
            "LiveSexAsian",
        ),
        "dev": (
            "GitHub", "Docker", "GitLab", "Bitbucket", "Stack Overflow",
            "DZone", "HackerRank", "Kaggle", "Codecademy", "LeetCode",
            "Dev.to", "FreeCodeCamp", "CodeNewbie", "CodePen", "AngelList",
            "Product Hunt",
        ),
        "gaming": (
            "Steam", "PlayStation Network", "Xbox Live", "Nintendo Network",
            "Epic Games", "Origin", "Ubisoft Connect", "Battle.net",
            "Rockstar Games", "GOG.com", "itch.io", "Roblox", "Minecraft",
            "PlayFab", "Unity",
        ),
        "marketplace": (
            "Etsy", "Amazon Handmade", "Fiverr", "Upwork", "Freelancer",
            "Toptal", "Guru", "PeoplePerHour",
        ),
        "leak": ("Doxbin",),
        "writing": ("Goodreads",),
    }.items()
    for name in names
}

#: Words that make a single path segment a section, a content item or a
#: pagination marker rather than somebody's handle.
_CONTENT_WORDS = RESERVED | frozenset({
    "album", "albums", "article", "articles", "author", "authors", "channel",
    "channels", "collection", "collections", "group", "groups", "item",
    "items", "listing", "listings", "member", "members", "model", "models",
    "page", "pages", "photo", "photos", "pin", "pins", "playlist",
    "playlists", "post", "posts", "product", "products", "reel", "reels",
    "status", "statuses", "story", "stories", "thread", "threads", "track",
    "tracks", "video", "videos", "view", "watch", "wiki",
})


@lru_cache(maxsize=1)
def _extended_table() -> tuple[tuple[str, str, re.Pattern[str]], ...]:
    try:
        raw = json.loads(_EXTENDED_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    table: list[tuple[str, str, re.Pattern[str]]] = []
    for name, pattern in raw.items():
        if not isinstance(name, str) or not isinstance(pattern, str):
            continue
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
        except re.error:
            continue
        table.append((name, pattern, compiled))
    return tuple(table)


def extended_platform_count() -> int:
    """How many additional platforms the wide original table contributes."""
    return len(_extended_table())


def platform_count() -> int:
    """Total distinct platform names the detector knows about."""
    return len({platform.name for platform in PLATFORMS}
               | {name for name, _, _ in _extended_table()})


def _extended_host_ok(host: str, pattern: str) -> bool:
    prefix = pattern.split("/", 1)[0]
    try:
        return bool(re.fullmatch(r"(?:[A-Za-z0-9-]+\.)*" + prefix, host,
                                 re.IGNORECASE))
    except re.error:
        return False


def _extended_handle(matched: str) -> str:
    tail = matched.rstrip("/").rsplit("/", 1)[-1]
    tail = tail.split("?", 1)[0].split("&", 1)[0]
    if "=" in tail:
        tail = tail.rsplit("=", 1)[-1]
    return re.sub(r"^(?:user|u):", "", tail.lstrip("@~"), flags=re.IGNORECASE)


def _extended_profiles(host: str, path: str, query: str) -> list[dict[str, object]]:
    # Patterns in the wide table start at the bare host, so ``www.`` and other
    # subdomains have to be removed before matching.
    hosts = [host]
    if host.startswith("www."):
        hosts.append(host[4:])
    for name, pattern, compiled in _extended_table():
        if not _extended_host_ok(host, pattern):
            continue
        text = ""
        match = None
        for candidate in hosts:
            text = f"{candidate}{path}".rstrip("/")
            if query:
                text = f"{text}?{query}"
            match = compiled.search(text)
            if match and match.start() == 0 and match.end() == len(text):
                break
            match = None
        if match is None:
            continue
        handle = _extended_handle(match.group(0))
        if not _valid_handle(handle):
            continue
        tokens = set(re.split(r"[^a-z0-9]+", handle.casefold())) - {""}
        if tokens & _CONTENT_WORDS:
            continue
        return [{
            "platform": name,
            "profile_url": "https://" + match.group(0),
            "category": EXTENDED_CATEGORIES.get(name, "other"),
            "confidence": 45 if name in EXTENDED_CATEGORIES else 35,
        }]
    return []

#: Hosts that look like a forum even without a per-platform entry.
FORUM_WORDS = frozenset({
    "forum", "forums", "community", "communities", "discussion", "discussions",
    "board", "boards", "bbs", "discourse", "phpbb", "vbulletin", "xenforo",
})
_FORUM_PATH_WORDS = FORUM_WORDS | {
    "topic", "topics", "thread", "threads", "viewtopic",
    "showthread", "viewforum",
}
_DISCOURSE = re.compile(r"^/u/([A-Za-z0-9._-]{2,64})/?$")
_FEDIVERSE = re.compile(
    r"^/@([A-Za-z0-9_][A-Za-z0-9_.-]{1,63})(?:@[A-Za-z0-9.-]+)?/?$")

#: Profile subpages that are only a view of the parent channel/profile.
#: Canonicalising them keeps ``youtube.com/@name/posts`` from being reported as
#: a forum and from creating a second, near-duplicate profile.
_YOUTUBE_SUBPAGE = re.compile(
    r"^/(@[A-Za-z0-9._-]{3,30}|c/[A-Za-z0-9._-]+|user/[A-Za-z0-9._-]+|"
    r"channel/UC[A-Za-z0-9_-]{20,})/"
    r"(?:featured|videos|shorts|streams|playlists|community|about|posts|search)"
    r"/?$", re.IGNORECASE)
_TWITCH_SUBPAGE = re.compile(
    r"^/([A-Za-z0-9_]{3,25})/"
    r"(?:videos|about|schedule|clips|chat|followers|following|collections)"
    r"/?$", re.IGNORECASE)

#: Click-tracking query parameters, kept in sync with ``utils.TRACKING_PARAMS``
#: without importing ``utils`` (it imports this module).
_TRACKING_QUERY = frozenset({
    "fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid", "igshid",
    "yclid", "twclid", "ttclid", "ref", "ref_src", "ref_url", "referrer",
    "source", "spm",
})


def host_matches(url: str, domain: str) -> bool:
    """True when ``url`` belongs to ``domain`` or one of its subdomains.

    Compares the parsed hostname exactly, so ``duckduckgo.com.example.net``
    and ``evilduckduckgo.com`` never match while ``html.duckduckgo.com`` does.
    """
    if not isinstance(url, str):
        return False
    host = (urllib.parse.urlparse(url).hostname or "").lower().rstrip(".")
    domain = str(domain).lower().rstrip(".")
    return bool(host) and (host == domain or host.endswith("." + domain))


def _host_ok(host: str, domains: Iterable[str]) -> bool:
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def profile_key(profile: Mapping[str, object]) -> str:
    """A stable identity for de-duplicating the same profile URL.

    Twitter and X are one site, ``www`` and a trailing slash do not change the
    profile, and the query string is kept so ``user_details?userid=...`` pages
    do not collapse into one entry.
    """
    url = str(profile.get("profile_url") or "")
    if not url:
        return ""
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    if host in {"twitter.com", "x.com"}:
        host = "x.com"
    path = parts.path.rstrip("/").replace("/$", "/")
    key = f"{host}{path}"
    pairs = [(name, value)
             for name, value in urllib.parse.parse_qsl(parts.query,
                                                       keep_blank_values=True)
             if name.casefold() not in _TRACKING_QUERY
             and not name.casefold().startswith("utm_")]
    if pairs:
        pairs.sort()
        key += "?" + urllib.parse.urlencode(pairs)
    return key.casefold() or url.casefold()


def host_label(url: str) -> str:
    """A readable site name for a URL that has no registry entry.

    Username checks already know the platform from the template they used, so
    an unregistered host still deserves a label rather than an empty cell.
    """
    if not isinstance(url, str):
        return ""
    host = (urllib.parse.urlsplit(url).hostname or "").lower().rstrip(".")
    labels = [part for part in host.split(".") if part]
    if len(labels) < 2:
        return ""
    # Take the registrable-ish label, skipping suffixes such as ``co.uk``.
    label = labels[-2]
    if label in {"co", "com", "org", "net", "gov", "ac"} and len(labels) >= 3:
        label = labels[-3]
    if label in {"www", "web", "m"}:
        return ""
    return label.replace("-", " ").replace("_", " ").title()


def _valid_handle(value: str) -> bool:
    if not value or value.casefold() in _CONTENT_WORDS:
        return False
    if _NUMERIC.fullmatch(value):
        return True
    return bool(_HANDLE.fullmatch(value))


def _platform_handle(platform: Platform, host: str, path: str,
                     query: dict[str, list[str]]) -> str:
    if not _host_ok(host, platform.hosts):
        return ""
    if position := platform.regex.match(path):
        pass
    else:
        return ""
    if platform.query_param:
        value = (query.get(platform.query_param) or [""])[0]
        return value if _valid_handle(value) else ""
    if platform.subdomain:
        for suffix in platform.hosts:
            if host == suffix:
                return ""
            if host.endswith("." + suffix):
                label = host[: -len(suffix) - 1]
                if "." in label:
                    label = label.split(".")[-1]
                # ``www.bandcamp.com`` is the site itself, not a profile.
                if label.casefold() == "www" or not _valid_handle(label):
                    return ""
                return label
        return ""
    handle = next((group for group in position.groups() if group), "")
    return handle if _valid_handle(handle) else ""


def _profile_url(platform: Platform, host: str, path: str,
                 handle: str) -> str:
    if platform.query_param:
        query = urllib.parse.urlencode({platform.query_param: handle})
        return f"https://{host}{path.rstrip('/')}?{query}"
    if platform.subdomain:
        suffix = next(domain for domain in platform.hosts
                      if host == domain or host.endswith("." + domain))
        return f"https://{handle}.{suffix}/"
    return f"https://{host}{path.rstrip('/')}"


def detect_profiles(url: str) -> list[dict[str, object]]:
    """Return at most one profile record for a URL.

    The record is ``platform``, ``profile_url``, ``category`` and
    ``confidence``. ``profile_url`` is the canonical profile address, not the
    raw URL, so tracking parameters are dropped.
    """
    if not isinstance(url, str) or not url.strip():
        return []
    parsed = urllib.parse.urlsplit(url.strip())
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host or "." not in host:
        return []
    path = parsed.path or "/"
    query = urllib.parse.parse_qs(parsed.query)
    for platform in PLATFORMS:
        handle = _platform_handle(platform, host, path, query)
        if not handle:
            continue
        return [{
            "platform": platform.name,
            "profile_url": _profile_url(platform, host, path, handle),
            "category": platform.category,
            "confidence": platform.confidence,
        }]
    subpage = _known_subpage(host, path)
    if subpage:
        return [subpage]
    for profile in _fallbacks(host, path):
        return [profile]
    return _extended_profiles(host, path, parsed.query)


def _known_subpage(host: str, path: str) -> dict[str, object] | None:
    """Canonicalise a channel subpage back to its parent profile."""
    if _host_ok(host, ("youtube.com",)):
        match = _YOUTUBE_SUBPAGE.match(path)
        if match:
            segment = match.group(1)
            handle = segment.rsplit("/", 1)[-1].lstrip("@")
            if _valid_handle(handle):
                return {
                    "platform": "YouTube",
                    "profile_url": f"https://{host}/{segment}",
                    "category": "video",
                    "confidence": 90,
                }
    if _host_ok(host, ("twitch.tv",)):
        match = _TWITCH_SUBPAGE.match(path)
        if match and _valid_handle(match.group(1)):
            return {
                "platform": "Twitch",
                "profile_url": f"https://{host}/{match.group(1)}",
                "category": "video",
                "confidence": 85,
            }
    return None


@lru_cache(maxsize=1)
def _known_hosts() -> frozenset[str]:
    hosts = {host for platform in PLATFORMS for host in platform.hosts}
    for _, pattern, _ in _extended_table():
        prefix = pattern.split("/", 1)[0].replace("\\.", ".")
        hosts.add(prefix.casefold())
    return frozenset(host for host in hosts if host)


def is_known_host(url: str) -> bool:
    """True when the URL belongs to a host the platform tables already know.

    Known sites get their profile rules applied; the generic forum fallback
    must not second-guess a platform page such as ``youtube.com/@x/posts``.
    """
    if not isinstance(url, str):
        return False
    host = (urllib.parse.urlsplit(url).hostname or "").lower().rstrip(".")
    if not host:
        return False
    return any(host == known or host.endswith("." + known)
               for known in _known_hosts())


def _fallbacks(host: str, path: str) -> list[dict[str, object]]:
    match = _DISCOURSE.match(path)
    if match:
        return [{
            "platform": "Discourse forum",
            "profile_url": f"https://{host}/u/{match.group(1)}",
            "category": "forum",
            "confidence": 55,
        }]
    match = _FEDIVERSE.match(path)
    if match:
        return [{
            "platform": "Fediverse (Mastodon-compatible)",
            "profile_url": f"https://{host}/@{match.group(1)}",
            "category": "social",
            "confidence": 45,
        }]
    return []


def is_forum_url(url: str) -> bool:
    """True for obvious forum/community URLs, without guessing from substrings.

    The old check treated any host or path containing "hub" as a forum, so
    ``pornhub.com`` and ``github.com`` were reported as forums. Host labels and
    path segments must match a whole word from a short, explicit list.
    """
    if not isinstance(url, str):
        return False
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    labels = set(re.split(r"[^a-z0-9]+", host)) - {""}
    if labels & FORUM_WORDS:
        return True
    segments = set(re.split(r"[^a-z0-9]+", (parsed.path or "").lower())) - {""}
    if segments & _FORUM_PATH_WORDS:
        return True
    return bool(_DISCOURSE.match(parsed.path or ""))
