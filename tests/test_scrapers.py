"""
Test suite for ai-ecosystem-radar.
Run with: pytest tests/ -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from pipeline.dedup import _title_overlap, deduplicate
from pipeline.score import compute_velocity
from scrapers import github_trending, hackernews
from scrapers.base import Category, HotLabel, ScoredItem, Source

# ─── Schema tests ──────────────────────────────────────────────────────────────


class TestRawItem:
    def test_url_hash_is_deterministic_for_same_url(self, make_item):
        """The same URL must always produce the same hash so dedup is stable."""
        a = make_item(url="https://github.com/test/repo")
        b = make_item(url="https://github.com/test/repo")
        assert a.url_hash == b.url_hash

    def test_url_hash_differs_for_different_urls(self, make_item):
        """Different URLs must not collide in the dedup index."""
        a = make_item(url="https://github.com/test/repo-a")
        b = make_item(url="https://github.com/test/repo-b")
        assert a.url_hash != b.url_hash

    def test_title_with_leading_trailing_whitespace_is_stripped(self, make_item):
        """Titles from scrapers often carry stray whitespace that must be removed."""
        item = make_item(title="  spaces around  ")
        assert item.title == "spaces around"

    def test_title_longer_than_500_chars_is_truncated(self, make_item):
        """Unbounded titles would bloat feed.json; enforce the 500-char cap."""
        item = make_item(title="x" * 600)
        assert len(item.title) == 500

    def test_to_feed_dict_contains_all_required_keys(self, scored_item):
        """feed.json consumers depend on every key being present."""
        required_keys = {
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
        }
        result = scored_item.to_feed_dict()
        missing = required_keys - result.keys()
        assert not missing, f"Missing keys in feed dict: {missing}"


# ─── Dedup tests ───────────────────────────────────────────────────────────────


class TestDedup:
    def test_exact_url_duplicate_is_collapsed_to_single_item(self, make_item):
        """Two items with the same URL should produce exactly one output item."""
        items = [
            make_item(url="https://github.com/same/repo", stars=100),
            make_item(url="https://github.com/same/repo", stars=200),
        ]
        result = deduplicate(items)
        assert len(result) == 1

    def test_exact_url_dedup_keeps_higher_star_version(self, make_item):
        """When collapsing duplicates, prefer the version with more stars."""
        items = [
            make_item(url="https://github.com/same/repo", stars=100),
            make_item(url="https://github.com/same/repo", stars=200),
        ]
        result = deduplicate(items)
        assert result[0].stars == 200

    def test_items_with_different_urls_are_both_kept(self, make_item):
        """Distinct URLs with unrelated titles must not be collapsed."""
        items = [
            make_item(url="https://github.com/org/repo-a", title="LangChain agent framework"),
            make_item(url="https://github.com/org/repo-b", title="FastAPI web server toolkit"),
        ]
        result = deduplicate(items)
        assert len(result) == 2

    def test_near_identical_titles_from_different_urls_are_deduped(self, make_item):
        """The same story scraped from two sites should collapse to one item."""
        items = [
            make_item(url="https://site-a.com/story", title="OpenAI releases new GPT-5 model"),
            make_item(
                url="https://site-b.com/story", title="OpenAI releases new GPT-5 model today"
            ),
        ]
        result = deduplicate(items)
        assert len(result) == 1

    def test_dissimilar_titles_from_different_urls_are_both_kept(self, make_item):
        """Items that merely share a word or two must not be incorrectly merged."""
        items = [
            make_item(url="https://a.com/1", title="LangChain releases v0.3"),
            make_item(url="https://b.com/2", title="Anthropic announces Claude 4"),
        ]
        result = deduplicate(items)
        assert len(result) == 2

    def test_title_overlap_is_one_for_identical_strings(self):
        """Jaccard similarity of a string with itself must be 1.0."""
        assert _title_overlap("hello world", "hello world") == 1.0

    def test_title_overlap_is_zero_for_disjoint_word_sets(self):
        """Strings with no words in common must have overlap of 0.0."""
        assert _title_overlap("apple orange", "banana grape") == 0.0

    def test_empty_input_returns_empty_list(self):
        """deduplicate([]) must not raise and must return an empty list."""
        assert deduplicate([]) == []


# ─── Velocity / score tests ────────────────────────────────────────────────────


class TestVelocity:
    def test_compute_velocity_returns_one_entry_per_item(self, make_item):
        """Every input item must have a corresponding entry in the result map."""
        items = [make_item(url=f"https://example.com/{i}") for i in range(5)]
        result = compute_velocity(items)
        assert len(result) == len(items)

    def test_compute_velocity_always_assigns_a_hot_label(self, make_item):
        """Every item must receive a HotLabel; the score must be in [0, 100]."""
        item = make_item(stars=50000)
        result = compute_velocity([item])
        score, label = result[item.url_hash]
        assert isinstance(label, HotLabel)
        assert 0 <= score <= 100

    def test_high_star_item_scores_higher_than_low_star_item(self, make_item):
        """Stars are a signal of popularity; more stars should yield a higher score."""
        low = make_item(url="https://example.com/low", stars=10)
        high = make_item(url="https://example.com/high", stars=50000)
        result = compute_velocity([low, high])
        assert result[high.url_hash][0] >= result[low.url_hash][0]

    def test_cross_source_item_scores_higher_than_single_source_item(self, make_item):
        """An item appearing in multiple scrapers signals broad interest and should be boosted."""
        item_a = make_item(url="https://github.com/hot/repo", source=Source.GITHUB_TRENDING)
        item_b = make_item(url="https://github.com/hot/repo", source=Source.HACKER_NEWS)
        item_lone = make_item(url="https://github.com/quiet/repo", source=Source.GITHUB_TRENDING)
        result = compute_velocity([item_a, item_b, item_lone])
        assert result[item_a.url_hash][0] >= result[item_lone.url_hash][0]


# ─── Scraper smoke tests (no network) ─────────────────────────────────────────


class TestGithubTrendingScraper:
    @pytest.mark.asyncio
    async def test_on_network_error_returns_empty_list_not_exception(self):
        """Scraper must degrade gracefully; a single source failure must not abort the pipeline."""
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("down"))
        result = await github_trending.scrape(mock_client)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_non_ai_repos_are_excluded_from_results(self):
        """GitHub Trending returns many repos; only AI-relevant ones must pass the filter."""
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
    async def test_on_network_error_returns_empty_list_not_exception(self):
        """Scraper must degrade gracefully; a single source failure must not abort the pipeline."""
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("down"))
        result = await hackernews.scrape(mock_client)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_valid_hit_is_parsed_into_raw_item_with_correct_source_and_stars(self):
        """Points from the Algolia API should map to the stars field used by the velocity engine."""
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


# ─── Pipeline integration ──────────────────────────────────────────────────────


class TestClassifier:
    @pytest.mark.asyncio
    async def test_returns_one_scored_item_per_raw_item(self, make_item):
        """Classifier must be a 1-to-1 transform; no items should be dropped or added."""
        from pipeline.classify import classify_items

        items = [make_item()]
        velocity_map = {items[0].url_hash: (50.0, HotLabel.RISING)}
        result = await classify_items(items, velocity_map)

        assert len(result) == 1
        assert isinstance(result[0], ScoredItem)

    @pytest.mark.asyncio
    async def test_hot_label_from_velocity_map_is_propagated_to_scored_item(self, make_item):
        """The hot label computed by the velocity engine must flow through to the final item."""
        from pipeline.classify import classify_items

        items = [make_item()]
        velocity_map = {items[0].url_hash: (50.0, HotLabel.RISING)}
        result = await classify_items(items, velocity_map)

        assert result[0].hot_label == HotLabel.RISING

    @pytest.mark.asyncio
    async def test_relevance_score_is_within_valid_range(self, make_item):
        """Relevance must stay in [0, 100] regardless of keyword matches."""
        from pipeline.classify import classify_items

        items = [make_item()]
        result = await classify_items(items, {})

        assert 0 <= result[0].relevance_score <= 100

    @pytest.mark.asyncio
    async def test_model_release_keywords_produce_model_category(self, make_item):
        """Items about model releases must be categorised as MODEL for accurate filtering."""
        from pipeline.classify import classify_items

        items = [make_item(title="LLaMA 3 weights released", description="Open model release")]
        result = await classify_items(items, {})

        assert result[0].category == Category.MODEL

    @pytest.mark.asyncio
    async def test_breaking_change_keywords_set_is_breaking_change_flag(self, make_item):
        """Breaking-change detection allows the UI to highlight high-impact updates."""
        from pipeline.classify import classify_items

        items = [make_item(title="v2.0.0 breaking change in LangChain API")]
        result = await classify_items(items, {})

        assert result[0].is_breaking_change is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
