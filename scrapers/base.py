"""
Shared schemas for all scrapers.
Every scraper must return a list[RawItem].
The pipeline converts these to ScoredItem after classification.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, field_validator


class Category(StrEnum):
    TOOL = "tool"
    REPO = "repo"
    NEWS = "news"
    MODEL = "model"
    PAPER = "paper"
    FRAMEWORK = "framework"
    UNKNOWN = "unknown"


class HotLabel(StrEnum):
    HOT = "hot"
    RISING = "rising"
    STABLE = "stable"


class Source(StrEnum):
    GITHUB_TRENDING = "github_trending"
    HACKER_NEWS = "hacker_news"
    REDDIT = "reddit"
    ARXIV = "arxiv"
    RSS_BLOG = "rss_blog"
    TWITTER = "twitter"


class RawItem(BaseModel):
    """Normalised output from any scraper — before classification."""

    url: str
    title: str
    description: str
    source: Source
    scraped_at: datetime
    stars: int | None = None
    author: str | None = None
    tags: list[str] = []
    extra: dict = {}

    @property
    def url_hash(self) -> str:
        return hashlib.sha256(self.url.encode()).hexdigest()[:16]

    @field_validator("title", "description", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()[:500]


class ScoredItem(BaseModel):
    """RawItem enriched by the classifier and trend engine."""

    url: str
    url_hash: str
    title: str
    description: str
    summary: str  # AI-generated one-liner
    source: Source
    category: Category
    relevance_score: int  # 0-100, engineer relevance
    velocity_score: float  # star growth rate / cross-source boost
    hot_label: HotLabel
    is_breaking_change: bool
    scraped_at: datetime
    scored_at: datetime
    stars: int | None = None
    author: str | None = None
    tags: list[str] = []
    extra: dict = {}

    def to_feed_dict(self) -> dict:
        return {
            "url": self.url,
            "hash": self.url_hash,
            "title": self.title,
            "summary": self.summary,
            "source": self.source.value,
            "category": self.category.value,
            "relevance": self.relevance_score,
            "hot": self.hot_label.value,
            "breaking": self.is_breaking_change,
            "stars": self.stars,
            "tags": self.tags,
            "scraped_at": self.scraped_at.isoformat(),
            "scored_at": self.scored_at.isoformat(),
        }
