"""
Shared pytest fixtures for ai-ecosystem-radar tests.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from scrapers.base import Category, HotLabel, RawItem, ScoredItem, Source


@pytest.fixture()
def make_item():
    """Factory fixture: call make_item() or make_item(url=..., title=...) in tests."""

    def _factory(
        url: str = "https://example.com/test",
        title: str = "Test AI agent framework",
        description: str = "A great agent framework for LLMs.",
        source: Source = Source.GITHUB_TRENDING,
        stars: int | None = 500,
    ) -> RawItem:
        return RawItem(
            url=url,
            title=title,
            description=description,
            source=source,
            scraped_at=datetime.now(UTC),
            stars=stars,
        )

    return _factory


@pytest.fixture()
def scored_item():
    """A minimal valid ScoredItem for schema/serialisation tests."""
    return ScoredItem(
        url="https://example.com",
        url_hash="abc123",
        title="Test",
        description="desc",
        summary="one line summary",
        source=Source.HACKER_NEWS,
        category=Category.TOOL,
        relevance_score=75,
        velocity_score=40.0,
        hot_label=HotLabel.RISING,
        is_breaking_change=False,
        scraped_at=datetime.now(UTC),
        scored_at=datetime.now(UTC),
    )
