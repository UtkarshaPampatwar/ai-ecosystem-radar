"""
RSS/Atom blog scraper for model release announcements.
Covers Anthropic, OpenAI, Google DeepMind, Mistral, Meta AI,
Hugging Face, LangChain blog, and more.
New sources can be added to data/sources.json without touching code.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import feedparser
import httpx

from .base import RawItem, Source

# Fallback sources if sources.json not found
DEFAULT_FEEDS = [
    {"name": "Anthropic", "url": "https://www.anthropic.com/rss.xml"},
    {"name": "OpenAI", "url": "https://openai.com/blog/rss.xml"},
    {"name": "Google DeepMind", "url": "https://deepmind.google/blog/rss/"},
    {"name": "Mistral AI", "url": "https://mistral.ai/news/rss"},
    {"name": "Meta AI", "url": "https://ai.meta.com/blog/rss/"},
    {"name": "Hugging Face", "url": "https://huggingface.co/blog/feed.xml"},
    {"name": "LangChain", "url": "https://blog.langchain.dev/rss/"},
    {"name": "LlamaIndex", "url": "https://www.llamaindex.ai/blog/rss"},
]

CUTOFF_DAYS = 7


def _load_feeds() -> list[dict]:
    sources_path = Path(__file__).parent.parent / "data" / "sources.json"
    if sources_path.exists():
        try:
            data = json.loads(sources_path.read_text())
            rss = [s for s in data.get("sources", []) if s.get("type") == "rss"]
            return rss if rss else DEFAULT_FEEDS
        except Exception:
            pass
    return DEFAULT_FEEDS


async def scrape(client: httpx.AsyncClient) -> list[RawItem]:
    items: list[RawItem] = []
    seen: set[str] = set()
    feeds = _load_feeds()
    cutoff = datetime.now(UTC) - timedelta(days=CUTOFF_DAYS)

    for feed_meta in feeds:
        feed_url = feed_meta.get("url", "")
        feed_name = feed_meta.get("name", "Blog")

        try:
            resp = await client.get(feed_url, follow_redirects=True, timeout=20)
            resp.raise_for_status()
        except Exception:
            continue

        feed = feedparser.parse(resp.text)

        for entry in feed.entries[:20]:
            url = entry.get("link", "")
            if not url or url in seen:
                continue
            seen.add(url)

            published = entry.get("published_parsed")
            if published:
                pub_dt = datetime(*published[:6], tzinfo=UTC)
            else:
                pub_dt = datetime.now(UTC)

            if pub_dt < cutoff:
                continue

            title = entry.get("title", "").strip()
            summary = entry.get("summary", "")
            # Strip basic HTML tags from summary
            import re

            summary = re.sub(r"<[^>]+>", " ", summary).strip()[:400]

            items.append(
                RawItem(
                    url=url,
                    title=title,
                    description=summary or f"New post from {feed_name}.",
                    source=Source.RSS_BLOG,
                    scraped_at=pub_dt,
                    author=feed_name,
                    tags=[feed_name.lower().replace(" ", "-")],
                    extra={"feed_name": feed_name, "feed_url": feed_url},
                )
            )

    return items
