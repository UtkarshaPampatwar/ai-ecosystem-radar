"""
pipeline/run.py — main orchestrator.
Run with: python -m pipeline.run
Steps:
  1. Run all scrapers in parallel
  2. Deduplicate
  3. Compute velocity scores
  4. Classify with rule-based heuristics
  5. Write data/feed.json and data/archive/YYYY-MM-DD.json
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from pipeline.classify import classify_items
from pipeline.dedup import deduplicate
from pipeline.score import compute_velocity
from scrapers import arxiv, github_trending, hackernews, reddit, rss_blogs, twitter_nitter
from scrapers.base import RawItem

DATA_DIR = Path(__file__).parent.parent / "data"
FEED_PATH = DATA_DIR / "feed.json"
ARCHIVE_DIR = DATA_DIR / "archive"
MIN_RELEVANCE = 25  # drop items below this score from the live feed
MAX_FEED_ITEMS = 200  # cap feed size


async def run_scrapers(client: httpx.AsyncClient) -> list[RawItem]:
    print("[pipeline] running all scrapers in parallel...")
    results = await asyncio.gather(
        github_trending.scrape(client),
        hackernews.scrape(client),
        reddit.scrape(client),
        arxiv.scrape(client),
        rss_blogs.scrape(client),
        twitter_nitter.scrape(client),
        return_exceptions=True,
    )
    items: list[RawItem] = []
    names = ["github_trending", "hackernews", "reddit", "arxiv", "rss_blogs", "twitter"]
    for name, result in zip(names, results):
        if isinstance(result, Exception):
            print(f"  [{name}] FAILED: {result}")
        else:
            print(f"  [{name}] {len(result)} items")
            items.extend(result)
    return items


def write_outputs(scored_items) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    ARCHIVE_DIR.mkdir(exist_ok=True)

    # Filter and sort
    filtered = [i for i in scored_items if i.relevance_score >= MIN_RELEVANCE]
    filtered.sort(
        key=lambda i: i.relevance_score * 0.6 + i.velocity_score * 0.4,
        reverse=True,
    )
    filtered = filtered[:MAX_FEED_ITEMS]

    feed_data = [item.to_feed_dict() for item in filtered]

    # Write live feed
    FEED_PATH.write_text(json.dumps(feed_data, indent=2, default=str))
    print(f"[pipeline] wrote {len(feed_data)} items → data/feed.json")

    # Write daily archive
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    archive_path = ARCHIVE_DIR / f"{today}.json"
    archive_path.write_text(json.dumps(feed_data, indent=2, default=str))
    print(f"[pipeline] archived → data/archive/{today}.json")


async def main() -> None:
    start = datetime.now(UTC)
    print(f"[pipeline] started at {start.isoformat()}")

    async with httpx.AsyncClient(
        headers={"User-Agent": "ai-ecosystem-radar/1.0"},
        follow_redirects=True,
    ) as client:
        raw_items = await run_scrapers(client)

    print(f"[pipeline] {len(raw_items)} raw items collected")

    deduped = deduplicate(raw_items)
    print(f"[pipeline] {len(deduped)} items after deduplication")

    velocity_map = compute_velocity(deduped)

    print(f"[pipeline] classifying {len(deduped)} items...")
    scored = await classify_items(deduped, velocity_map)

    write_outputs(scored)

    elapsed = (datetime.now(UTC) - start).total_seconds()
    print(f"[pipeline] done in {elapsed:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
