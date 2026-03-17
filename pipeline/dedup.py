"""
Deduplication — removes duplicate RawItems before classification.
Two passes:
  1. Exact URL hash match
  2. Title similarity (catches same story from different URL variants)
"""

from __future__ import annotations

from scrapers.base import RawItem


def _normalise_title(title: str) -> str:
    import re

    t = title.lower()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _title_overlap(a: str, b: str) -> float:
    """Jaccard similarity on word sets."""
    wa = set(_normalise_title(a).split())
    wb = set(_normalise_title(b).split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def deduplicate(items: list[RawItem], title_threshold: float = 0.75) -> list[RawItem]:
    """
    Returns deduplicated list, preferring the item with more stars
    (or the earlier scraped_at if no stars).
    """
    # Pass 1: exact URL hash
    seen_hashes: dict[str, RawItem] = {}
    for item in items:
        h = item.url_hash
        if h not in seen_hashes:
            seen_hashes[h] = item
        else:
            # Keep the one with more stars
            existing = seen_hashes[h]
            if (item.stars or 0) > (existing.stars or 0):
                seen_hashes[h] = item

    unique = list(seen_hashes.values())

    # Pass 2: title fuzzy dedup (catches same story, different URLs)
    deduped: list[RawItem] = []
    for candidate in unique:
        is_dup = False
        for kept in deduped:
            if _title_overlap(candidate.title, kept.title) >= title_threshold:
                # Keep the one with more stars
                if (candidate.stars or 0) > (kept.stars or 0):
                    deduped.remove(kept)
                    deduped.append(candidate)
                is_dup = True
                break
        if not is_dup:
            deduped.append(candidate)

    return deduped
