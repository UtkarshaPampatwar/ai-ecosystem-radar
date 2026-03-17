"""
GitHub Trending scraper.
Scrapes https://github.com/trending filtered to AI/ML repos.
Uses the unofficial trending endpoint — no API key required.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
from bs4 import BeautifulSoup

from .base import RawItem, Source

AI_KEYWORDS = [
    "llm",
    "agent",
    "ai",
    "gpt",
    "claude",
    "gemini",
    "mistral",
    "langchain",
    "embeddings",
    "rag",
    "transformer",
    "diffusion",
    "prompt",
    "anthropic",
    "openai",
    "huggingface",
    "mcp",
    "crewai",
    "autogen",
    "langgraph",
    "vector",
    "inference",
]

TRENDING_URLS = [
    "https://github.com/trending/python?since=daily",
    "https://github.com/trending/javascript?since=daily",
    "https://github.com/trending/typescript?since=daily",
    "https://github.com/trending?since=daily",
]


def _is_ai_related(title: str, desc: str) -> bool:
    combined = (title + " " + desc).lower()
    return any(kw in combined for kw in AI_KEYWORDS)


def _parse_stars(text: str) -> int | None:
    text = text.strip().replace(",", "").replace("k", "000").replace("K", "000")
    try:
        return int(text.split()[0])
    except (ValueError, IndexError):
        return None


async def scrape(client: httpx.AsyncClient) -> list[RawItem]:
    items: list[RawItem] = []
    seen_urls: set[str] = set()

    for url in TRENDING_URLS:
        try:
            resp = await client.get(url, follow_redirects=True, timeout=15)
            resp.raise_for_status()
        except httpx.HTTPError:
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        articles = soup.select("article.Box-row")

        for article in articles:
            try:
                h2 = article.select_one("h2 a")
                if not h2:
                    continue

                repo_path = h2["href"].strip("/")
                repo_url = f"https://github.com/{repo_path}"

                if repo_url in seen_urls:
                    continue
                seen_urls.add(repo_url)

                title = repo_path.replace("/", " / ")
                desc_el = article.select_one("p")
                description = desc_el.get_text(strip=True) if desc_el else ""

                if not _is_ai_related(title, description):
                    continue

                stars_el = article.select_one("a[href$='/stargazers']")
                stars = _parse_stars(stars_el.get_text()) if stars_el else None

                lang_el = article.select_one("[itemprop='programmingLanguage']")
                language = lang_el.get_text(strip=True) if lang_el else ""

                items.append(
                    RawItem(
                        url=repo_url,
                        title=title,
                        description=description or f"Trending GitHub repository: {title}",
                        source=Source.GITHUB_TRENDING,
                        scraped_at=datetime.now(UTC),
                        stars=stars,
                        tags=[language] if language else [],
                        extra={"repo_path": repo_path},
                    )
                )
            except Exception:
                continue

    return items
