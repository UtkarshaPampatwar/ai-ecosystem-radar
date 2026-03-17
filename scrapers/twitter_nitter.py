"""
Twitter/X scraper via Nitter RSS instances.
No API key, no cost. Monitors key AI researchers and labs.
Falls back through multiple Nitter instances if one is down.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import feedparser
import httpx

from .base import RawItem, Source

# Public Nitter instances — tried in order
NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
]

# High-signal AI accounts to monitor
ACCOUNTS = [
    "AnthropicAI",
    "OpenAI",
    "GoogleDeepMind",
    "MistralAI",
    "huggingface",
    "karpathy",
    "ylecun",
    "sama",
    "DrJimFan",
    "swyx",
    "simonw",
    "LangChainAI",
]

AI_KEYWORDS = [
    "release",
    "launch",
    "announcing",
    "open source",
    "agent",
    "model",
    "llm",
    "api",
    "paper",
    "github",
    "benchmark",
]

CUTOFF_HOURS = 48


def _is_signal(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in AI_KEYWORDS)


async def _fetch_nitter(client: httpx.AsyncClient, account: str) -> list[RawItem]:
    cutoff = datetime.now(UTC) - timedelta(hours=CUTOFF_HOURS)

    for instance in NITTER_INSTANCES:
        try:
            url = f"{instance}/{account}/rss"
            resp = await client.get(url, follow_redirects=True, timeout=15)
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)

            items = []
            for entry in feed.entries[:15]:
                published = entry.get("published_parsed")
                if not published:
                    continue
                pub_dt = datetime(*published[:6], tzinfo=UTC)
                if pub_dt < cutoff:
                    continue

                title = entry.get("title", "")
                # Clean RT / reply prefix
                import re

                title = re.sub(r"^R to @\w+: ", "", title)
                title = re.sub(r"^RT @\w+: ", "", title)

                if not _is_signal(title):
                    continue

                link = entry.get("link", "")
                # Convert nitter links back to twitter.com
                twitter_link = link.replace(instance, "https://twitter.com")

                items.append(
                    RawItem(
                        url=twitter_link or link,
                        title=f"@{account}: {title[:120]}",
                        description=title[:400],
                        source=Source.TWITTER,
                        scraped_at=pub_dt,
                        author=f"@{account}",
                        tags=[account.lower()],
                        extra={"account": account, "nitter_url": link},
                    )
                )
            return items
        except Exception:
            continue  # try next instance

    return []


async def scrape(client: httpx.AsyncClient) -> list[RawItem]:
    import asyncio

    results = await asyncio.gather(
        *[_fetch_nitter(client, account) for account in ACCOUNTS],
        return_exceptions=True,
    )
    items = []
    for r in results:
        if isinstance(r, list):
            items.extend(r)
    return items
