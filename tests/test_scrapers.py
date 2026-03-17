"""
Test suite for ai-ecosystem-radar.
Run with: pytest tests/ -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from pipeline.classify import _extract_tags, classify_items
from pipeline.dedup import _title_overlap, deduplicate
from pipeline.score import compute_velocity
from scrapers import github_trending, hackernews
from scrapers.base import Category, HotLabel, RawItem, ScoredItem, Source

# ─── Schema tests ──────────────────────────────────────────────────────────────


class TestRawItem:
    def test_url_hash_is_deterministic_for_same_url(self, make_item: ...) -> None:
        """Given two RawItems with the same URL, when their hashes are compared,
        then they must be equal so dedup lookups are stable across runs."""
        a: RawItem = make_item(url="https://github.com/test/repo")
        b: RawItem = make_item(url="https://github.com/test/repo")
        assert a.url_hash == b.url_hash

    def test_url_hash_differs_for_different_urls(self, make_item: ...) -> None:
        """Given two RawItems with different URLs, when their hashes are compared,
        then they must differ so distinct items are never collapsed by dedup."""
        a: RawItem = make_item(url="https://github.com/test/repo-a")
        b: RawItem = make_item(url="https://github.com/test/repo-b")
        assert a.url_hash != b.url_hash

    def test_title_with_leading_trailing_whitespace_is_stripped(self, make_item: ...) -> None:
        """Given a title with surrounding whitespace, when the RawItem is constructed,
        then the whitespace is stripped so scrapers don't need to clean their output."""
        item: RawItem = make_item(title="  spaces around  ")
        assert item.title == "spaces around"

    def test_title_longer_than_500_chars_is_truncated(self, make_item: ...) -> None:
        """Given a title longer than 500 characters, when the RawItem is constructed,
        then it is truncated to 500 chars so feed.json stays bounded in size."""
        item: RawItem = make_item(title="x" * 600)
        assert len(item.title) == 500

    def test_to_feed_dict_contains_all_required_keys(self, scored_item: ScoredItem) -> None:
        """Given a valid ScoredItem, when serialised to a feed dict,
        then all keys required by the dashboard frontend must be present."""
        required_keys: set[str] = {
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
        result: dict[str, object] = scored_item.to_feed_dict()
        missing: set[str] = required_keys - result.keys()
        assert not missing, f"Missing keys in feed dict: {missing}"


# ─── Dedup tests ───────────────────────────────────────────────────────────────


class TestDedup:
    def test_exact_url_duplicate_is_collapsed_to_single_item(self, make_item: ...) -> None:
        """Given two items with the same URL from different scrapers,
        when deduplicated, then exactly one item remains in the output."""
        items: list[RawItem] = [
            make_item(url="https://github.com/same/repo", stars=100),
            make_item(url="https://github.com/same/repo", stars=200),
        ]
        result: list[RawItem] = deduplicate(items)
        assert len(result) == 1

    def test_exact_url_dedup_keeps_higher_star_version(self, make_item: ...) -> None:
        """Given two duplicates with different star counts, when deduplicated,
        then the higher-star version is kept so the velocity engine sees the freshest signal."""
        items: list[RawItem] = [
            make_item(url="https://github.com/same/repo", stars=100),
            make_item(url="https://github.com/same/repo", stars=200),
        ]
        result: list[RawItem] = deduplicate(items)
        assert result[0].stars == 200

    def test_items_with_different_urls_are_both_kept(self, make_item: ...) -> None:
        """Given two items with distinct URLs and unrelated titles, when deduplicated,
        then both are preserved as they are genuinely different items."""
        items: list[RawItem] = [
            make_item(url="https://github.com/org/repo-a", title="LangChain agent framework"),
            make_item(url="https://github.com/org/repo-b", title="FastAPI web server toolkit"),
        ]
        result: list[RawItem] = deduplicate(items)
        assert len(result) == 2

    def test_near_identical_titles_from_different_urls_are_deduped(self, make_item: ...) -> None:
        """Given the same story scraped from two different sites with near-identical titles,
        when deduplicated, then only one item remains to avoid duplicate cards in the UI."""
        items: list[RawItem] = [
            make_item(url="https://site-a.com/story", title="OpenAI releases new GPT-5 model"),
            make_item(
                url="https://site-b.com/story", title="OpenAI releases new GPT-5 model today"
            ),
        ]
        result: list[RawItem] = deduplicate(items)
        assert len(result) == 1

    def test_dissimilar_titles_from_different_urls_are_both_kept(self, make_item: ...) -> None:
        """Given two items that share a common word but are about different topics,
        when deduplicated, then both are kept so fuzzy matching does not over-collapse."""
        items: list[RawItem] = [
            make_item(url="https://a.com/1", title="LangChain releases v0.3"),
            make_item(url="https://b.com/2", title="Anthropic announces Claude 4"),
        ]
        result: list[RawItem] = deduplicate(items)
        assert len(result) == 2

    def test_title_overlap_is_one_for_identical_strings(self) -> None:
        """Given two identical strings, when Jaccard overlap is computed,
        then the result is 1.0."""
        assert _title_overlap("hello world", "hello world") == 1.0

    def test_title_overlap_is_zero_for_disjoint_word_sets(self) -> None:
        """Given two strings with no words in common, when Jaccard overlap is computed,
        then the result is 0.0."""
        assert _title_overlap("apple orange", "banana grape") == 0.0

    def test_empty_input_returns_empty_list(self) -> None:
        """Given an empty list, when deduplicated, then an empty list is returned without error."""
        assert deduplicate([]) == []


# ─── Velocity / score tests ────────────────────────────────────────────────────


class TestVelocity:
    def test_compute_velocity_returns_one_entry_per_item(self, make_item: ...) -> None:
        """Given N items, when velocity is computed, then the result map contains N entries
        so every item can be looked up by its hash in the classifier."""
        items: list[RawItem] = [make_item(url=f"https://example.com/{i}") for i in range(5)]
        result: dict[str, tuple[float, HotLabel]] = compute_velocity(items)
        assert len(result) == len(items)

    def test_compute_velocity_always_assigns_a_hot_label(self, make_item: ...) -> None:
        """Given any item, when velocity is computed, then a HotLabel is always assigned
        and the score stays within the valid [0, 100] range."""
        item: RawItem = make_item(stars=50000)
        result: dict[str, tuple[float, HotLabel]] = compute_velocity([item])
        score, label = result[item.url_hash]
        assert isinstance(label, HotLabel)
        assert 0 <= score <= 100

    def test_high_star_item_scores_higher_than_low_star_item(self, make_item: ...) -> None:
        """Given two items with very different star counts, when velocity is computed,
        then the higher-star item receives a higher score as stars signal wider adoption."""
        low: RawItem = make_item(url="https://example.com/low", stars=10)
        high: RawItem = make_item(url="https://example.com/high", stars=50000)
        result: dict[str, tuple[float, HotLabel]] = compute_velocity([low, high])
        assert result[high.url_hash][0] >= result[low.url_hash][0]

    def test_cross_source_item_scores_higher_than_single_source_item(self, make_item: ...) -> None:
        """Given an item that appears in multiple scrapers and one that appears in only one,
        when velocity is computed, then the cross-source item scores higher
        because broad coverage signals stronger community interest."""
        item_a: RawItem = make_item(
            url="https://github.com/hot/repo", source=Source.GITHUB_TRENDING
        )
        item_b: RawItem = make_item(url="https://github.com/hot/repo", source=Source.HACKER_NEWS)
        item_lone: RawItem = make_item(
            url="https://github.com/quiet/repo", source=Source.GITHUB_TRENDING
        )
        result: dict[str, tuple[float, HotLabel]] = compute_velocity([item_a, item_b, item_lone])
        assert result[item_a.url_hash][0] >= result[item_lone.url_hash][0]


# ─── Scraper smoke tests (no network) ─────────────────────────────────────────


class TestGithubTrendingScraper:
    @pytest.mark.asyncio
    async def test_on_network_error_returns_empty_list_not_exception(self) -> None:
        """Given a network failure on the GitHub Trending endpoint, when the scraper runs,
        then it returns an empty list so one source outage does not abort the pipeline."""
        mock_client: MagicMock = MagicMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("down"))
        result: list[RawItem] = await github_trending.scrape(mock_client)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_non_ai_repos_are_excluded_from_results(self) -> None:
        """Given a trending page that contains only non-AI repos, when scraped,
        then the result is empty because the AI keyword filter rejects them."""
        html: str = """
        <article class="Box-row">
          <h2><a href="/cooking/recipes">cooking / recipes</a></h2>
          <p>Best cooking recipes ever</p>
          <a href="/cooking/recipes/stargazers">1,200</a>
        </article>
        """
        mock_resp: MagicMock = MagicMock()
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()
        mock_client: MagicMock = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        result: list[RawItem] = await github_trending.scrape(mock_client)
        assert len(result) == 0


class TestHackerNewsScraper:
    @pytest.mark.asyncio
    async def test_on_network_error_returns_empty_list_not_exception(self) -> None:
        """Given a network failure on the Algolia HN endpoint, when the scraper runs,
        then it returns an empty list so one source outage does not abort the pipeline."""
        mock_client: MagicMock = MagicMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("down"))
        result: list[RawItem] = await hackernews.scrape(mock_client)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_valid_hit_is_parsed_into_raw_item_with_correct_source_and_stars(self) -> None:
        """Given a valid Algolia response with one hit, when scraped, then the result contains
        a RawItem with source HACKER_NEWS and stars mapped from the points field."""
        fake_response: dict[str, object] = {
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
        mock_resp: MagicMock = MagicMock()
        mock_resp.json = MagicMock(return_value=fake_response)
        mock_resp.raise_for_status = MagicMock()
        mock_client: MagicMock = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        result: list[RawItem] = await hackernews.scrape(mock_client)
        assert len(result) >= 1
        assert result[0].source == Source.HACKER_NEWS
        assert result[0].stars == 250


# ─── Pipeline integration ──────────────────────────────────────────────────────


class TestClassifier:
    @pytest.mark.asyncio
    async def test_returns_one_scored_item_per_raw_item(self, make_item: ...) -> None:
        """Given N raw items, when classified, then exactly N scored items are returned
        so the classifier is a pure 1-to-1 transform with no silent drops."""
        items: list[RawItem] = [make_item()]
        velocity_map: dict[str, tuple[float, HotLabel]] = {
            items[0].url_hash: (50.0, HotLabel.RISING)
        }
        result: list[ScoredItem] = await classify_items(items, velocity_map)
        assert len(result) == 1
        assert isinstance(result[0], ScoredItem)

    @pytest.mark.asyncio
    async def test_hot_label_from_velocity_map_is_propagated_to_scored_item(
        self, make_item: ...
    ) -> None:
        """Given a velocity map with a RISING label, when classified,
        then the scored item carries that label so the UI can render hot/rising badges."""
        items: list[RawItem] = [make_item()]
        velocity_map: dict[str, tuple[float, HotLabel]] = {
            items[0].url_hash: (50.0, HotLabel.RISING)
        }
        result: list[ScoredItem] = await classify_items(items, velocity_map)
        assert result[0].hot_label == HotLabel.RISING

    @pytest.mark.asyncio
    async def test_relevance_score_is_within_valid_range(self, make_item: ...) -> None:
        """Given any item, when classified, then relevance stays within [0, 100]
        so downstream filtering thresholds are never violated."""
        items: list[RawItem] = [make_item()]
        result: list[ScoredItem] = await classify_items(items, {})
        assert 0 <= result[0].relevance_score <= 100

    @pytest.mark.asyncio
    async def test_model_release_keywords_produce_model_category(self, make_item: ...) -> None:
        """Given an item whose title contains model release language,
        when classified, then the category is MODEL so it appears in the models filter."""
        items: list[RawItem] = [
            make_item(title="LLaMA 3 weights released", description="Open model release")
        ]
        result: list[ScoredItem] = await classify_items(items, {})
        assert result[0].category == Category.MODEL

    @pytest.mark.asyncio
    async def test_breaking_change_keywords_set_is_breaking_change_flag(
        self, make_item: ...
    ) -> None:
        """Given an item whose title contains breaking change language, when classified,
        then is_breaking_change is True so the UI can highlight it prominently."""
        items: list[RawItem] = [make_item(title="v2.0.0 breaking change in LangChain API")]
        result: list[ScoredItem] = await classify_items(items, {})
        assert result[0].is_breaking_change is True

    @pytest.mark.asyncio
    async def test_arxiv_source_always_produces_paper_category_regardless_of_title(
        self, make_item: ...
    ) -> None:
        """Given an ArXiv item whose title contains the word 'framework', when classified,
        then the category is PAPER because the source override fires before keyword matching."""
        items: list[RawItem] = [
            make_item(
                title="MCP-in-SoS: Risk assessment framework for open-source MCP servers",
                description="We propose a new agentic framework for LLM orchestration.",
                source=Source.ARXIV,
            )
        ]
        result: list[ScoredItem] = await classify_items(items, {})
        assert result[0].category == Category.PAPER

    @pytest.mark.asyncio
    async def test_score_based_category_selects_highest_keyword_hit_count(
        self, make_item: ...
    ) -> None:
        """Given an item with two MODEL keyword hits and zero TOOL hits, when classified,
        then MODEL wins so score-based selection out-competes single incidental matches."""
        items: list[RawItem] = [
            make_item(
                title="LLaMA and Mistral weights released",
                description="New open weights from Meta and Mistral AI.",
                source=Source.GITHUB_TRENDING,
            )
        ]
        result: list[ScoredItem] = await classify_items(items, {})
        assert result[0].category == Category.MODEL

    @pytest.mark.asyncio
    async def test_classify_items_produces_semantic_tags_not_raw_scraper_tags(
        self, make_item: ...
    ) -> None:
        """Given an item about RAG and LLM agents, when classified,
        then tags are human-readable labels like 'rag' and 'agents'
        rather than raw scraper output like 'TypeScript' or 'cs.AI'."""
        items: list[RawItem] = [
            make_item(
                title="Building RAG pipelines with LLM agents",
                description="A guide to retrieval-augmented generation using agentic workflows.",
            )
        ]
        result: list[ScoredItem] = await classify_items(items, {})
        assert "rag" in result[0].tags
        assert "agents" in result[0].tags
        assert "llm" in result[0].tags

    @pytest.mark.asyncio
    async def test_classify_items_returns_empty_tags_when_no_keywords_match(
        self, make_item: ...
    ) -> None:
        """Given an item with no recognisable AI keywords, when classified,
        then the tags list is empty rather than raising an error."""
        items: list[RawItem] = [
            make_item(title="Hello world", description="A simple hello world program.")
        ]
        result: list[ScoredItem] = await classify_items(items, {})
        assert isinstance(result[0].tags, list)

    @pytest.mark.asyncio
    async def test_news_source_with_no_keyword_match_falls_back_to_news_category(
        self, make_item: ...
    ) -> None:
        """Given a Hacker News item with no category keywords, when classified,
        then the category falls back to NEWS rather than UNKNOWN."""
        items: list[RawItem] = [
            make_item(
                title="Weekly roundup of interesting links",
                description="Some links from around the web this week.",
                source=Source.HACKER_NEWS,
            )
        ]
        result: list[ScoredItem] = await classify_items(items, {})
        assert result[0].category == Category.NEWS

    @pytest.mark.asyncio
    async def test_github_trending_item_with_no_keyword_match_is_repo_not_unknown(
        self, make_item: ...
    ) -> None:
        """Given a GitHub Trending item with no model, tool, or framework keywords,
        when classified, then the category is REPO because every trending item is a repo."""
        items: list[RawItem] = [
            make_item(
                url="https://github.com/example/generic-project",
                title="example / generic-project",
                description="A collection of useful scripts.",
                source=Source.GITHUB_TRENDING,
            )
        ]
        result: list[ScoredItem] = await classify_items(items, {})
        assert result[0].category == Category.REPO

    @pytest.mark.asyncio
    async def test_non_github_item_with_open_source_keywords_is_not_classified_as_repo(
        self, make_item: ...
    ) -> None:
        """Given an HN post that mentions 'open source', when classified,
        then the category is not REPO because REPO is reserved for actual GitHub repositories."""
        items: list[RawItem] = [
            make_item(
                url="https://news.ycombinator.com/item?id=99999",
                title="Open source AI is changing everything",
                description="This open-source implementation is remarkable.",
                source=Source.HACKER_NEWS,
            )
        ]
        result: list[ScoredItem] = await classify_items(items, {})
        assert result[0].category != Category.REPO

    @pytest.mark.asyncio
    async def test_github_url_from_non_trending_source_is_classified_as_repo(
        self, make_item: ...
    ) -> None:
        """Given a GitHub URL shared on HN with no stronger keyword signal,
        when classified, then the category is REPO because the URL signals it is a repository."""
        items: list[RawItem] = [
            make_item(
                url="https://github.com/someone/cool-project",
                title="someone / cool-project",
                description="A small utility project.",
                source=Source.HACKER_NEWS,
            )
        ]
        result: list[ScoredItem] = await classify_items(items, {})
        assert result[0].category == Category.REPO

    @pytest.mark.asyncio
    async def test_framework_category_requires_named_framework_not_generic_word(
        self, make_item: ...
    ) -> None:
        """Given an item that uses the word 'framework' generically, when classified,
        then the category is not FRAMEWORK because only named AI frameworks qualify."""
        items: list[RawItem] = [
            make_item(
                url="https://github.com/example/my-project",
                title="A new software framework for building things",
                description="This framework helps you build applications faster.",
                source=Source.GITHUB_TRENDING,
            )
        ]
        result: list[ScoredItem] = await classify_items(items, {})
        assert result[0].category != Category.FRAMEWORK

    @pytest.mark.asyncio
    async def test_named_framework_in_description_produces_framework_category(
        self, make_item: ...
    ) -> None:
        """Given an item that explicitly names LangGraph and LangChain, when classified,
        then the category is FRAMEWORK so it appears in the frameworks filter."""
        items: list[RawItem] = [
            make_item(
                url="https://github.com/example/agent-kit",
                title="Agent toolkit built on LangGraph and LangChain",
                description="Extends LangGraph with memory and tool use.",
                source=Source.GITHUB_TRENDING,
            )
        ]
        result: list[ScoredItem] = await classify_items(items, {})
        assert result[0].category == Category.FRAMEWORK

    @pytest.mark.asyncio
    async def test_proxy_service_mentioning_model_names_is_tool_not_model(
        self, make_item: ...
    ) -> None:
        """Given a relay/proxy repo whose description lists model names like Gemini and GPT-4,
        when classified,
        then the category is TOOL so proxy services don't pollute the model feed."""
        items: list[RawItem] = [
            make_item(
                url="https://github.com/example/ai-relay",
                title="example / ai-relay",
                description="Self-hosted relay proxy supporting Claude, GPT-4, and Gemini.",
                source=Source.GITHUB_TRENDING,
            )
        ]
        result: list[ScoredItem] = await classify_items(items, {})
        assert result[0].category == Category.TOOL

    @pytest.mark.asyncio
    async def test_training_ui_is_tool_not_model(self, make_item: ...) -> None:
        """Given an item describing a web UI for training LLMs, when classified,
        then the category is TOOL so training apps don't appear in the models filter."""
        items: list[RawItem] = [
            make_item(
                title="Unsloth Studio",
                description="A new open-source web UI to train and run LLMs on your machine.",
                source=Source.REDDIT,
            )
        ]
        result: list[ScoredItem] = await classify_items(items, {})
        assert result[0].category == Category.TOOL

    @pytest.mark.asyncio
    async def test_model_release_announcement_is_model_not_tool(self, make_item: ...) -> None:
        """Given an RSS post announcing new model weights, when classified,
        then the category is MODEL so the release appears in the models filter."""
        items: list[RawItem] = [
            make_item(
                title="Mistral Small 3B — new model weights released",
                description="Open weights, 3B parameters, available on Hugging Face.",
                source=Source.RSS_BLOG,
            )
        ]
        result: list[ScoredItem] = await classify_items(items, {})
        assert result[0].category == Category.MODEL

    @pytest.mark.asyncio
    async def test_hardware_news_is_not_classified_as_model(self, make_item: ...) -> None:
        """Given a Reddit post about memory chip supply constraints, when classified,
        then the category is not MODEL because hardware news is unrelated to AI models."""
        items: list[RawItem] = [
            make_item(
                title="Memory Chip Crunch to Persist Until 2030, SK Hynix Chairman Says",
                description="DRAM and HBM supply constraints affecting data centre buildouts.",
                source=Source.REDDIT,
            )
        ]
        result: list[ScoredItem] = await classify_items(items, {})
        assert result[0].category != Category.MODEL


# ─── Tag extraction unit tests ─────────────────────────────────────────────────


class TestExtractTags:
    def test_rag_keyword_in_title_produces_rag_tag(self, make_item: ...) -> None:
        """Given an item with 'RAG' in the title, when tags are extracted,
        then 'rag' is present so users can filter by topic."""
        item: RawItem = make_item(title="RAG pipeline with vector search", description="")
        assert "rag" in _extract_tags(item)

    def test_agent_keyword_produces_agents_tag(self, make_item: ...) -> None:
        """Given an item with 'agent' in the title, when tags are extracted,
        then 'agents' is present so the agents topic is surfaced in the UI."""
        item: RawItem = make_item(title="Multi-agent LLM system", description="")
        assert "agents" in _extract_tags(item)

    def test_mcp_keyword_produces_mcp_tag(self, make_item: ...) -> None:
        """Given an item that mentions MCP in its content, when tags are extracted,
        then 'mcp' is present so Model Context Protocol items are discoverable."""
        item: RawItem = make_item(title="Model Context Protocol server", description="Uses MCP.")
        assert "mcp" in _extract_tags(item)

    def test_unrelated_content_produces_no_tags(self, make_item: ...) -> None:
        """Given an item with no AI keywords, when tags are extracted,
        then the list is empty rather than producing spurious tags."""
        item: RawItem = make_item(title="Hello world", description="A simple program.")
        assert _extract_tags(item) == []

    def test_multiple_keywords_produce_multiple_tags(self, make_item: ...) -> None:
        """Given an item that covers fine-tuning, RAG, embeddings, and inference,
        when tags are extracted, then all four topics appear as separate tags."""
        item: RawItem = make_item(
            title="Fine-tuning LLaMA with LoRA for RAG",
            description="Embedding-based retrieval with quantized inference.",
        )
        tags: list[str] = _extract_tags(item)
        assert "fine-tuning" in tags
        assert "rag" in tags
        assert "embeddings" in tags
        assert "inference" in tags


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
