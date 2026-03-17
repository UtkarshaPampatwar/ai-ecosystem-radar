"""
ArXiv scraper — uses the official ArXiv API (no key needed).
Targets cs.AI, cs.CL, cs.LG categories for agent/LLM papers.
"""

from __future__ import annotations

from datetime import UTC, datetime

import feedparser
import httpx

from .base import RawItem, Source

ARXIV_API = "https://export.arxiv.org/api/query"

SEARCHES = [
    "ti:LLM+agent OR ti:AI+agent OR ti:multi-agent",
    "ti:prompt+engineering OR ti:chain+of+thought",
    "ti:RAG OR ti:retrieval+augmented",
    "ti:MCP OR ti:model+context+protocol",
    "cat:cs.AI+AND+ti:agent",
]

MAX_RESULTS = 15


async def scrape(client: httpx.AsyncClient) -> list[RawItem]:
    items: list[RawItem] = []
    seen: set[str] = set()

    for search in SEARCHES:
        try:
            resp = await client.get(
                ARXIV_API,
                params={
                    "search_query": search,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                    "max_results": MAX_RESULTS,
                },
                timeout=20,
            )
            resp.raise_for_status()
        except Exception:
            continue

        feed = feedparser.parse(resp.text)

        for entry in feed.entries:
            url = entry.get("link", "")
            if not url or url in seen:
                continue
            seen.add(url)

            title = entry.get("title", "").replace("\n", " ").strip()
            abstract = entry.get("summary", "").replace("\n", " ")[:400]

            authors = [a.get("name", "") for a in entry.get("authors", [])]
            author_str = ", ".join(authors[:3])
            if len(authors) > 3:
                author_str += " et al."

            published = entry.get("published_parsed")
            if published:
                scraped_at = datetime(*published[:6], tzinfo=UTC)
            else:
                scraped_at = datetime.now(UTC)

            categories = [t.get("term", "") for t in entry.get("tags", [])]

            items.append(
                RawItem(
                    url=url,
                    title=title,
                    description=abstract,
                    source=Source.ARXIV,
                    scraped_at=scraped_at,
                    author=author_str,
                    tags=categories[:5],
                    extra={
                        "arxiv_id": entry.get("id", ""),
                        "authors": authors,
                        "categories": categories,
                    },
                )
            )

    return items
