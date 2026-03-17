"""
Test suite for ai-ecosystem-radar.
Run with: pytest tests/ -v
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.dedup import _title_overlap, deduplicate
from pipeline.score import compute_velocity
from scrapers.base import Category, HotLabel, RawItem, ScoredItem, Source

# ─── Fixtures ────────────────────────────────────────────────────────────────


def make_item(
    url="https://example.com/test",
    title="Test AI agent framework",
    description="A great agent framework for LLMs.",
    source=Source.GITHUB_TRENDING,
    stars=500,
) -> RawItem:
    return RawItem(
        url=url,
        title=title,
        description=description,
        source=source,
        scraped_at=datetime.now(UTC),
        stars=stars,
    )


# ─── Schema tests ─────────────────────────────────────────────────────────────


class TestRawItem:
    def test_url_hash_is_deterministic(self):
        a = make_item(url="https://github.com/test/repo")
        b = make_item(url="https://github.com/test/repo")
        assert a.url_hash == b.url_hash

    def test_different_urls_different_hashes(self):
        a = make_item(url="https://github.com/test/repo-a")
        b = make_item(url="https://github.com/test/repo-b")
        assert a.url_hash != b.url_hash

    def test_title_stripped(self):
        item = make_item(title="  spaces around  ")
        assert item.title == "spaces around"

    def test_title_truncated_to_500(self):
        item = make_item(title="x" * 600)
        assert len(item.title) == 500

    def test_to_feed_dict_has_required_keys(self):
        scored = ScoredItem(
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
        d = scored.to_feed_dict()
        for key in [
            "url",
            "hash",
            "title",
            "summary",
            "source",
            "category",
            "relevance",
            "hot",
            "breaking",
            "scraped_at",
            "scored_at",
        ]:
            assert key in d, f"Missing key: {key}"


# ─── Dedup tests ──────────────────────────────────────────────────────────────


class TestDedup:
    def test_exact_url_dedup(self):
        items = [
            make_item(url="https://github.com/same/repo", stars=100),
            make_item(url="https://github.com/same/repo", stars=200),
        ]
        result = deduplicate(items)
        assert len(result) == 1
        assert result[0].stars == 200  # keeps higher-star version

    def test_different_urls_kept(self):
        items = [
            make_item(url="https://github.com/org/repo-a"),
            make_item(url="https://github.com/org/repo-b"),
        ]
        result = deduplicate(items)
        assert len(result) == 2

    def test_fuzzy_title_dedup(self):
        items = [
            make_item(url="https://site-a.com/story", title="OpenAI releases new GPT-5 model"),
            make_item(
                url="https://site-b.com/story", title="OpenAI releases new GPT-5 model today"
            ),
        ]
        result = deduplicate(items)
        assert len(result) == 1

    def test_dissimilar_titles_kept(self):
        items = [
            make_item(url="https://a.com/1", title="LangChain releases v0.3"),
            make_item(url="https://b.com/2", title="Anthropic announces Claude 4"),
        ]
        result = deduplicate(items)
        assert len(result) == 2

    def test_title_overlap_identical(self):
        assert _title_overlap("hello world", "hello world") == 1.0

    def test_title_overlap_disjoint(self):
        assert _title_overlap("apple orange", "banana grape") == 0.0

    def test_empty_list(self):
        assert deduplicate([]) == []


# ─── Velocity / score tests ───────────────────────────────────────────────────


class TestVelocity:
    def test_returns_entry_for_each_item(self):
        items = [make_item(url=f"https://example.com/{i}") for i in range(5)]
        result = compute_velocity(items)
        assert len(result) == len(items)

    def test_hot_label_returned(self):
        item = make_item(stars=50000)
        result = compute_velocity([item])
        score, label = result[item.url_hash]
        assert isinstance(label, HotLabel)
        assert 0 <= score <= 100

    def test_high_stars_boosts_score(self):
        low = make_item(url="https://example.com/low", stars=10)
        high = make_item(url="https://example.com/high", stars=50000)
        result = compute_velocity([low, high])
        assert result[high.url_hash][0] >= result[low.url_hash][0]

    def test_cross_source_boost(self):
        """Same URL appearing from two sources should get a boost."""
        item_a = make_item(url="https://github.com/hot/repo", source=Source.GITHUB_TRENDING)
        item_b = make_item(url="https://github.com/hot/repo", source=Source.HACKER_NEWS)
        item_lone = make_item(url="https://github.com/quiet/repo", source=Source.GITHUB_TRENDING)
        result = compute_velocity([item_a, item_b, item_lone])
        # The cross-source item should outscore the lone item
        assert result[item_a.url_hash][0] >= result[item_lone.url_hash][0]


# ─── Scraper smoke tests (no network) ────────────────────────────────────────


class TestGithubTrendingScraper:
    @pytest.mark.asyncio
    async def test_returns_list_on_http_error(self):
        """Scraper should return empty list, not raise, on network failure."""
        import httpx

        from scrapers import github_trending

        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("down"))
        result = await github_trending.scrape(mock_client)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_filters_non_ai_repos(self):
        """Repos without AI keywords should be excluded."""
        from scrapers import github_trending

        html = """
        <article class="Box-row">
          <h2><a href="/cooking/recipes">cooking / recipes</a></h2>
          <p>Best cooking recipes ever</p>
          <a href="/cooking/recipes/stargazers">1,200</a>
        </article>
        """

        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        result = await github_trending.scrape(mock_client)
        assert len(result) == 0


class TestHackerNewsScraper:
    @pytest.mark.asyncio
    async def test_returns_list_on_http_error(self):
        import httpx

        from scrapers import hackernews

        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("down"))
        result = await hackernews.scrape(mock_client)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_parses_valid_response(self):

        from scrapers import hackernews

        fake_response = {
            "hits": [
                {
                    "objectID": "12345",
                    "title": "New open-source LLM agent framework",
                    "url": "https://github.com/test/agent",
                    "points": 250,
                    "num_comments": 80,
                    "author": "testuser",
                    "created_at_i": 1700000000,
                    "story_text": "",
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.json = MagicMock(return_value=fake_response)
        mock_resp.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        result = await hackernews.scrape(mock_client)
        assert len(result) >= 1
        assert result[0].source == Source.HACKER_NEWS
        assert result[0].stars == 250


# ─── Pipeline integration ─────────────────────────────────────────────────────


class TestClassifier:
    @pytest.mark.asyncio
    async def test_classify_returns_scored_items(self):
        """Classifier returns a ScoredItem for every RawItem passed in."""
        from pipeline.classify import classify_items

        items = [make_item()]
        velocity_map = {items[0].url_hash: (50.0, HotLabel.RISING)}
        result = await classify_items(items, velocity_map)

        assert len(result) == 1
        assert isinstance(result[0], ScoredItem)
        assert result[0].hot_label == HotLabel.RISING
        assert 0 <= result[0].relevance_score <= 100

    @pytest.mark.asyncio
    async def test_classify_detects_model_category(self):
        """Items with model-release keywords are classified as MODEL."""
        from pipeline.classify import classify_items

        items = [make_item(title="LLaMA 3 weights released", description="Open model release")]
        result = await classify_items(items, {})

        assert result[0].category == Category.MODEL

    @pytest.mark.asyncio
    async def test_classify_detects_breaking_change(self):
        """Items mentioning breaking changes set is_breaking_change=True."""
        from pipeline.classify import classify_items

        items = [make_item(title="v2.0.0 breaking change in LangChain API")]
        result = await classify_items(items, {})

        assert result[0].is_breaking_change is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
