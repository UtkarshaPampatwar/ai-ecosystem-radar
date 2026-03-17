#!/usr/bin/env python3
"""
validate_sources.py
Validates data/sources.json against the schema and (optionally)
live-tests each RSS feed to confirm it returns real entries.

Usage:
  python validate_sources.py           # schema check only (fast)
  python validate_sources.py --live    # schema + HTTP fetch each feed
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import feedparser
import httpx

SOURCES_PATH = Path(__file__).parent / "data" / "sources.json"

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET}  {msg}")


def err(msg: str) -> None:
    print(f"  {RED}✗{RESET}  {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}!{RESET}  {msg}")


def validate_schema(data: dict) -> list[str]:
    errors: list[str] = []
    sources = data.get("sources", [])
    if not isinstance(sources, list):
        errors.append("'sources' must be a list")
        return errors

    seen_names: set[str] = set()
    seen_urls: set[str] = set()

    for i, s in enumerate(sources):
        label = f"sources[{i}] ({s.get('name', '?')})"

        if not s.get("name"):
            errors.append(f"{label}: missing 'name'")
        elif s["name"] in seen_names:
            errors.append(f"{label}: duplicate name '{s['name']}'")
        else:
            seen_names.add(s["name"])

        stype = s.get("type")
        if stype not in ("rss", "twitter"):
            errors.append(f"{label}: 'type' must be 'rss' or 'twitter', got '{stype}'")
            continue

        if stype == "rss":
            url = s.get("url", "")
            if not url:
                errors.append(f"{label}: RSS source missing 'url'")
            elif not url.startswith("http"):
                errors.append(f"{label}: 'url' must start with http(s)")
            elif url in seen_urls:
                errors.append(f"{label}: duplicate url '{url}'")
            else:
                seen_urls.add(url)

        if stype == "twitter":
            account = s.get("account", "")
            if not account:
                errors.append(f"{label}: Twitter source missing 'account'")
            elif not account.replace("_", "").isalnum():
                errors.append(f"{label}: 'account' must be alphanumeric (no @)")

    return errors


async def live_test_feed(source: dict) -> tuple[bool, str]:
    """Try fetching a single RSS feed. Returns (success, message)."""
    url = source.get("url", "")
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        entry_count = len(feed.entries)
        if entry_count == 0:
            return False, "feed returned 0 entries — may be invalid or empty"
        return True, f"{entry_count} entries found"
    except Exception as exc:
        return False, str(exc)


async def live_test_all(sources: list[dict]) -> None:
    rss_sources = [s for s in sources if s.get("type") == "rss"]
    print(f"\n{BOLD}Live feed tests ({len(rss_sources)} RSS sources):{RESET}")

    results = await asyncio.gather(*[live_test_feed(s) for s in rss_sources])

    passed = failed = 0
    for source, (success, msg) in zip(rss_sources, results):
        name = source.get("name", source.get("url"))
        if success:
            ok(f"{name}: {msg}")
            passed += 1
        else:
            err(f"{name}: {msg}")
            failed += 1

    print(f"\n  {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate sources.json")
    parser.add_argument("--live", action="store_true", help="Also HTTP-test each RSS feed")
    args = parser.parse_args()

    print(f"\n{BOLD}AI Ecosystem Radar — source validator{RESET}\n")

    if not SOURCES_PATH.exists():
        err(f"sources.json not found at {SOURCES_PATH}")
        sys.exit(1)

    try:
        data = json.loads(SOURCES_PATH.read_text())
    except json.JSONDecodeError as exc:
        err(f"sources.json is not valid JSON: {exc}")
        sys.exit(1)

    ok("sources.json is valid JSON")

    print(f"\n{BOLD}Schema validation:{RESET}")
    schema_errors = validate_schema(data)
    if schema_errors:
        for msg in schema_errors:
            err(msg)
        print(f"\n  {RED}{len(schema_errors)} schema error(s) found.{RESET}")
        sys.exit(1)

    sources = data.get("sources", [])
    rss_count = sum(1 for s in sources if s.get("type") == "rss")
    twitter_count = sum(1 for s in sources if s.get("type") == "twitter")
    ok(f"{len(sources)} sources found: {rss_count} RSS, {twitter_count} Twitter")
    ok("All entries pass schema validation")

    if args.live:
        asyncio.run(live_test_all(sources))
    else:
        warn("Skipping live feed tests (pass --live to enable)")

    print(f"\n{GREEN}{BOLD}All checks passed.{RESET}\n")


if __name__ == "__main__":
    main()
