"""
Reddit scraper — uses the public .json endpoint, no OAuth needed.
Monitors r/MachineLearning, r/LocalLLaMA, r/artificial, r/singularity.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from .base import RawItem, Source

SUBREDDITS = [
    "MachineLearning",
    "LocalLLaMA",
    "artificial",
    "singularity",
]

MIN_SCORE = 50
HEADERS = {"User-Agent": "ai-ecosystem-radar/1.0 (github.com/your-org/ai-ecosystem-radar)"}


async def scrape(client: httpx.AsyncClient) -> list[RawItem]:
    items: list[RawItem] = []
    seen: set[str] = set()

    for sub in SUBREDDITS:
        for sort in ["hot", "new"]:
            try:
                resp = await client.get(
                    f"https://www.reddit.com/r/{sub}/{sort}.json",
                    params={"limit": 25},
                    headers=HEADERS,
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                continue

            for post in data.get("data", {}).get("children", []):
                p = post.get("data", {})

                score = p.get("score", 0)
                if score < MIN_SCORE:
                    continue

                # Use external URL if it's a link post, else the reddit thread
                url = p.get("url", "")
                if not url or "reddit.com" in url:
                    url = f"https://reddit.com{p.get('permalink', '')}"

                if url in seen:
                    continue
                seen.add(url)

                title = p.get("title", "")
                selftext = p.get("selftext", "")[:300]

                items.append(
                    RawItem(
                        url=url,
                        title=title,
                        description=selftext if selftext else f"r/{sub} post — {score} upvotes.",
                        source=Source.REDDIT,
                        scraped_at=datetime.fromtimestamp(p.get("created_utc", 0), tz=UTC),
                        stars=score,
                        author=p.get("author"),
                        tags=[f"r/{sub}"],
                        extra={
                            "subreddit": sub,
                            "score": score,
                            "comments": p.get("num_comments", 0),
                            "reddit_url": f"https://reddit.com{p.get('permalink', '')}",
                        },
                    )
                )

    return items
