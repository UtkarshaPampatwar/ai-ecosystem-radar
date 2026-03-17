"""
Hacker News scraper via the Algolia HN Search API.
Searches for AI/agent/LLM stories from the past 24 hours.
Free, no key needed, returns clean JSON.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from .base import RawItem, Source

ALGOLIA_URL = "https://hn.algolia.com/api/v1/search"

QUERIES = [
    "LLM agent",
    "AI engineering",
    "MCP model context protocol",
    "prompt engineering",
    "RAG retrieval",
    "open source AI",
    "Claude OpenAI Gemini",
    "LangChain LangGraph CrewAI AutoGen",
]

MIN_POINTS = 20


async def scrape(client: httpx.AsyncClient) -> list[RawItem]:
    items: list[RawItem] = []
    seen: set[str] = set()
    cutoff = datetime.now(UTC) - timedelta(hours=48)

    for query in QUERIES:
        try:
            resp = await client.get(
                ALGOLIA_URL,
                params={
                    "query": query,
                    "tags": "story",
                    "numericFilters": (
                        f"created_at_i>{int(cutoff.timestamp())},points>={MIN_POINTS}"
                    ),
                    "hitsPerPage": 20,
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            continue

        for hit in data.get("hits", []):
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            if url in seen:
                continue
            seen.add(url)

            title = hit.get("title", "")
            desc = hit.get("story_text") or ""
            points = hit.get("points", 0)
            comments = hit.get("num_comments", 0)

            try:
                scraped_at = datetime.fromtimestamp(hit["created_at_i"], tz=UTC)
            except Exception:
                scraped_at = datetime.now(UTC)

            items.append(
                RawItem(
                    url=url,
                    title=title,
                    description=desc[:300]
                    if desc
                    else f"HN story with {points} points and {comments} comments.",
                    source=Source.HACKER_NEWS,
                    scraped_at=scraped_at,
                    stars=points,
                    author=hit.get("author"),
                    tags=[],
                    extra={
                        "hn_id": hit.get("objectID"),
                        "points": points,
                        "comments": comments,
                        "hn_url": f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                    },
                )
            )

    return items
