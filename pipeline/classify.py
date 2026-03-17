"""
Rule-based classifier — tags, scores, and summarises each RawItem without an API key.
Uses keyword heuristics for zero-cost, offline classification.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from scrapers.base import Category, HotLabel, RawItem, ScoredItem

# ---------------------------------------------------------------------------
# Source-level category overrides — applied before any keyword matching.
# ArXiv items are always research papers regardless of title keywords.
# ---------------------------------------------------------------------------

_SOURCE_CATEGORY_OVERRIDE: dict[str, Category] = {
    "arxiv": Category.PAPER,
}

# ---------------------------------------------------------------------------
# Category keyword rules — scored across all categories; highest count wins.
# Ties are broken by list order below (MODEL > PAPER > FRAMEWORK > TOOL > REPO > NEWS).
# ---------------------------------------------------------------------------

_CATEGORY_RULES: list[tuple[Category, list[str]]] = [
    (
        # TOOL is checked before MODEL so that proxy/app/UI items that merely
        # mention model names in their descriptions don't get misclassified.
        #
        # A TOOL is software you use to work with AI models:
        #   apps, UIs, proxies, runners, trainers, plugins, CLIs, gateways.
        Category.TOOL,
        [
            # Interfaces & apps
            "web ui",
            "desktop app",
            "web app",
            "chat interface",
            "chat ui",
            "dashboard",
            "playground",
            "studio",  # e.g. Unsloth Studio, LM Studio
            "gui",
            # Dev tools
            "cli tool",
            "command-line tool",
            "vscode extension",
            "browser extension",
            "chrome extension",
            "plugin",
            # Infra / services
            "proxy",
            "relay",
            "gateway",
            "api server",
            "inference server",
            "model server",
            # Local runners
            "run locally",
            "run llms locally",
            "run models locally",
            "local llm",
            "ollama",
            "lmstudio",
            # Training & fine-tuning applications (the software, not the technique)
            "fine-tuning tool",
            "training tool",
            "train on your",
            "fine-tune on your",
        ],
    ),
    (
        # MODEL means the item *is* a model being released or announced.
        # Keywords here describe release language and specific named model families.
        # Technique keywords (lora, gguf, fine-tun) are intentionally excluded —
        # they appear in tool descriptions and would cause false positives.
        Category.MODEL,
        [
            # Explicit release language
            "model weights",
            "model checkpoint",
            "open weights",
            "weights released",
            "new model",
            "model release",
            "releasing model",
            "billion parameter",
            # Named model families (the model itself, not tools that use it)
            "llama",
            "mistral",
            "phi-",
            "qwen",
            "deepseek",
            "falcon",
            "bloom",
            "nemotron",
            "grok",
            "gemma",
        ],
    ),
    (
        Category.PAPER,
        [
            "we propose",
            "we present",
            "our method",
            "experiments show",
            "state-of-the-art",
            "preprint",
            "research paper",
        ],
    ),
    (
        Category.FRAMEWORK,
        [
            # Named AI development frameworks only.
            "langchain",
            "llamaindex",
            "llama_index",
            "crewai",
            "autogen",
            "langgraph",
            "dspy",
            "haystack",
            "pydantic-ai",
            "smolagents",
            "semantic kernel",
            "agno",
            "openai agents sdk",
            "swarm",
        ],
    ),
    # REPO is not scored here — it is used as a fallback for GitHub items only.
    # See _detect_category for the fallback logic.
    (
        Category.NEWS,
        [
            "blog post",
            "announcement",
            "interview",
            "opinion",
            "newsletter",
            "weekly digest",
        ],
    ),
]

# ---------------------------------------------------------------------------
# Semantic tag extraction — maps content keywords → human-readable tags shown
# in the UI. Replaces raw scraper tags (language names, academic codes).
# ---------------------------------------------------------------------------

_SEMANTIC_TAG_RULES: list[tuple[str, list[str]]] = [
    ("agents", ["agent", "agentic", "multi-agent"]),
    ("rag", ["rag", "retrieval-augmented", "retrieval augmented"]),
    ("mcp", ["mcp", "model context protocol"]),
    ("llm", ["llm", "large language model"]),
    ("fine-tuning", ["fine-tun", "lora", "qlora", "finetun"]),
    ("embeddings", ["embedding", "vector database", "vector store"]),
    ("prompt-engineering", ["prompt engineering", "chain of thought", "few-shot"]),
    ("inference", ["inference", "gguf", "ggml", "quantiz", "serving"]),
    ("evaluation", ["benchmark", "leaderboard", "state-of-the-art", "sota"]),
    ("security", ["security", "attack", "adversar", "jailbreak", "red-team"]),
    ("multimodal", ["multimodal", "vision-language", "text-to-image", "text-to-video"]),
    ("code-generation", ["code generation", "coding assistant", "copilot"]),
    ("robotics", ["robot", "embodied"]),
    ("reasoning", ["reasoning", "chain of thought", "cot", "o1", "thinking"]),
    ("memory", ["context window", "long-context", "kv cache", "memory augmented"]),
]

# High-signal AI engineering keywords — each occurrence boosts relevance.
_HIGH_SIGNAL_KEYWORDS = [
    "mcp",
    "model context protocol",
    "agentic",
    "agent framework",
    "rag",
    "retrieval-augmented",
    "inference",
    "large language model",
    "llm",
    "prompt engineering",
    "embedding",
    "vector database",
    "transformer",
    "open source",
    "breaking change",
    "deprecated",
    "api change",
    "major release",
    "v2.0",
]

# Base relevance score by source.
_SOURCE_BASE: dict[str, int] = {
    "github_trending": 60,
    "hacker_news": 55,
    "arxiv": 65,
    "reddit": 45,
    "rss_blog": 50,
    "twitter": 40,
}

# Category relevance boosts.
_CATEGORY_BOOST: dict[Category, int] = {
    Category.MODEL: 25,
    Category.FRAMEWORK: 20,
    Category.TOOL: 15,
    Category.PAPER: 10,
    Category.REPO: 10,
    Category.NEWS: 5,
    Category.UNKNOWN: 0,
}

_BREAKING_RE = re.compile(
    r"\b(breaking[- ]change|deprecated?|removed?|major[- ]update|"
    r"v\d+\.\d+\.0\b|api[- ]change|not backward[- ]compat|incompatible)\b",
    re.IGNORECASE,
)

_HTML_TAG_RE = re.compile(r"<[^>]+>")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


_NEWS_SOURCES = {"hacker_news", "reddit", "rss_blog", "twitter"}


def _detect_category(text: str, source: str | None = None, url: str = "") -> Category:
    # Source-level override takes absolute priority (e.g. arxiv → always PAPER).
    if source and source in _SOURCE_CATEGORY_OVERRIDE:
        return _SOURCE_CATEGORY_OVERRIDE[source]

    lower = text.lower()
    is_github_item = source == "github_trending" or "github.com" in url

    # Score every category; pick the one with the most keyword hits.
    # REPO is excluded from scoring — it is only valid as a GitHub fallback (below).
    scores: dict[Category, int] = {}
    for category, keywords in _CATEGORY_RULES:
        hits = sum(1 for kw in keywords if kw in lower)
        if hits:
            scores[category] = hits

    if scores:
        return max(scores, key=lambda c: scores[c])

    # No keyword matched — fall back based on source type.
    # GitHub items without a stronger signal are repos, not unknowns.
    if is_github_item:
        return Category.REPO
    if source in _NEWS_SOURCES:
        return Category.NEWS
    return Category.UNKNOWN


def _extract_tags(item: RawItem) -> list[str]:
    """Return human-readable semantic tags derived from item content."""
    text = f"{item.title} {item.description}".lower()
    return [tag for tag, keywords in _SEMANTIC_TAG_RULES if any(kw in text for kw in keywords)]


def _score_relevance(item: RawItem, category: Category) -> int:
    text = f"{item.title} {item.description}".lower()
    base = _SOURCE_BASE.get(item.source.value, 40)
    category_boost = _CATEGORY_BOOST.get(category, 0)

    # High-signal keyword boost (capped at +20).
    signal_count = sum(1 for kw in _HIGH_SIGNAL_KEYWORDS if kw in text)
    signal_boost = min(signal_count * 4, 20)

    # Star-count boost for GitHub items.
    star_boost = 0
    if item.stars:
        if item.stars >= 10_000:
            star_boost = 10
        elif item.stars >= 1_000:
            star_boost = 5

    return min(base + category_boost + signal_boost + star_boost, 100)


def _make_summary(item: RawItem) -> str:
    text = item.description.strip() if item.description else item.title
    text = _HTML_TAG_RE.sub("", text)
    text = " ".join(text.split())
    return (text or item.title)[:120]


def _is_breaking(item: RawItem) -> bool:
    return bool(_BREAKING_RE.search(f"{item.title} {item.description}"))


# ---------------------------------------------------------------------------
# Public API — async wrapper preserves the signature expected by pipeline/run.py
# ---------------------------------------------------------------------------


async def classify_items(
    items: list[RawItem],
    velocity_map: dict[str, tuple[float, HotLabel]],
) -> list[ScoredItem]:
    """Classify and score all items using rule-based heuristics (no API key required)."""
    now = datetime.now(UTC)
    scored: list[ScoredItem] = []

    for raw in items:
        text = f"{raw.title} {raw.description}"
        category = _detect_category(text, source=raw.source.value, url=raw.url)
        relevance = _score_relevance(raw, category)
        velocity, hot = velocity_map.get(raw.url_hash, (0.0, HotLabel.STABLE))

        scored.append(
            ScoredItem(
                url=raw.url,
                url_hash=raw.url_hash,
                title=raw.title,
                description=raw.description,
                summary=_make_summary(raw),
                source=raw.source,
                category=category,
                relevance_score=relevance,
                velocity_score=round(velocity, 2),
                hot_label=hot,
                is_breaking_change=_is_breaking(raw),
                scraped_at=raw.scraped_at,
                scored_at=now,
                stars=raw.stars,
                author=raw.author,
                tags=_extract_tags(raw),
                extra=raw.extra,
            )
        )

    return scored
