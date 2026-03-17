"""
Trend velocity engine.
Computes a velocity score for each item based on:
  - star growth rate (for GitHub repos)
  - cross-source signal (same story appearing in multiple scrapers)
  - recency decay (older items score lower)
  - previous run comparison (pulled from archived feed.json)
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from scrapers.base import HotLabel, RawItem

ARCHIVE_DIR = Path(__file__).parent.parent / "data" / "archive"
FEED_PATH = Path(__file__).parent.parent / "data" / "feed.json"


def _load_previous_stars() -> dict[str, int]:
    """Load star counts from the most recent archived feed for delta calculation."""
    if not ARCHIVE_DIR.exists():
        return {}
    snapshots = sorted(ARCHIVE_DIR.glob("*.json"), reverse=True)
    for snap in snapshots[:3]:
        try:
            data = json.loads(snap.read_text())
            return {item["hash"]: item.get("stars", 0) for item in data if item.get("hash")}
        except Exception:
            continue
    return {}


def _recency_factor(scraped_at: datetime) -> float:
    """1.0 = just scraped, decays to 0.1 over 7 days."""
    age_hours = (datetime.now(UTC) - scraped_at).total_seconds() / 3600
    return max(0.1, 1.0 - (age_hours / 168))  # 168h = 7 days


def _hot_label(velocity: float) -> HotLabel:
    if velocity >= 70:
        return HotLabel.HOT
    if velocity >= 35:
        return HotLabel.RISING
    return HotLabel.STABLE


def compute_velocity(items: list[RawItem]) -> dict[str, tuple[float, HotLabel]]:
    """
    Returns a map of url_hash → (velocity_score, hot_label).
    velocity_score is 0–100.
    """
    prev_stars = _load_previous_stars()

    # Count how many sources picked up the same domain/url
    source_counts: dict[str, int] = defaultdict(int)
    for item in items:
        source_counts[item.url_hash] += 1

    results: dict[str, tuple[float, HotLabel]] = {}

    for item in items:
        score = 0.0

        # Base: recency
        score += _recency_factor(item.scraped_at) * 20

        # Cross-source boost: appearing in 2+ scrapers is a strong signal
        sources = source_counts[item.url_hash]
        if sources >= 3:
            score += 40
        elif sources == 2:
            score += 20

        # Star velocity: delta since last run
        if item.stars is not None:
            prev = prev_stars.get(item.url_hash, 0)
            delta = item.stars - prev
            if delta > 500:
                score += 30
            elif delta > 100:
                score += 20
            elif delta > 20:
                score += 10

            # Absolute star count adds baseline signal
            if item.stars > 10_000:
                score += 10
            elif item.stars > 1_000:
                score += 5

        score = min(100.0, score)
        results[item.url_hash] = (round(score, 2), _hot_label(score))

    return results
