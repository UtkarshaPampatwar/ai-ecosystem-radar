---
applyTo: "tests/**"
---

# Pytest instructions — ai-ecosystem-radar

## Running tests

```bash
poe test                                                          # full suite
poetry run pytest tests/ -v                                       # verbose
poetry run pytest tests/ -v --tb=short                           # CI mode
poetry run pytest tests/test_scrapers.py::TestClassifier -v      # single class
```

## Project test layout

```
tests/
├── conftest.py        # shared fixtures: make_item (factory), scored_item
└── test_scrapers.py   # all tests, one class per unit
```

## Style — PEP 8 and type annotations

All test files must:

- Begin with `from __future__ import annotations` for string-based type annotations
- Use full type annotations on every function signature, including test methods and fixtures
- Follow PEP 8: 4-space indent, max line length 100 (enforced by ruff), two blank lines
  between top-level definitions, one blank line between methods inside a class
- Pass `poe lint` and `poe format` with zero errors before any test is considered done

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from scrapers.base import RawItem, Source


class TestHackerNewsScraper:
    @pytest.mark.asyncio
    async def test_on_network_error_returns_empty_list_not_exception(self) -> None:
        """Given a network failure, the scraper returns an empty list instead of raising,
        so a single source outage does not abort the entire pipeline run."""
        import httpx
        from scrapers import hackernews

        # Given
        mock_client: MagicMock = MagicMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("down"))

        # When
        result: list[RawItem] = await hackernews.scrape(mock_client)

        # Then
        assert isinstance(result, list)
```

## Test structure — Given / When / Then

Given/When/Then belongs in the **docstring**, not as comments in the test body.
The test body is plain code with no section comments.

```python
# ✓ Correct — GWT in the docstring, clean body
def test_exact_url_dedup_keeps_higher_star_version(self, make_item: ...) -> None:
    """Given two duplicates with different star counts, when deduplicated,
    then the higher-star version is kept so the velocity engine sees the freshest signal."""
    items: list[RawItem] = [
        make_item(url="https://github.com/same/repo", stars=100),
        make_item(url="https://github.com/same/repo", stars=200),
    ]
    result: list[RawItem] = deduplicate(items)
    assert result[0].stars == 200


# ✗ Wrong — GWT as inline comments, vague docstring
def test_exact_url_dedup_keeps_higher_star_version(self, make_item: ...) -> None:
    """When collapsing duplicates, prefer the version with more stars."""
    # Given
    items = [...]
    # When
    result = deduplicate(items)
    # Then
    assert result[0].stars == 200
```

Docstring format:
```
Given [the starting state or inputs],
when [the single action under test],
then [the observable outcome and why it matters].
```

## Naming convention

```
test_<unit>_<condition>_<expected_result>
```

| ✓ Good | ✗ Bad |
|---|---|
| `test_url_hash_is_deterministic_for_same_url` | `test_something` |
| `test_arxiv_source_always_produces_paper_category_regardless_of_title` | `test_dedup` |
| `test_proxy_service_mentioning_model_names_is_tool_not_model` | `test_classifier_works` |

## Docstrings

Every test must have a docstring written in Given/When/Then plain English that explains
**why** the behaviour matters, not just what is being tested.

```python
# Bad — describes what, not why
"""Tests that dedup keeps the higher star item."""

# Good — explains the business reason using Given/When/Then language
"""Given two scraped items for the same URL with different star counts,
when deduplicated, the higher-star version is kept so the velocity engine
always sees the most recent popularity signal."""
```

## Mocking — always use mock.patch.object, never monkeypatch

**Never use pytest's `monkeypatch` fixture.** Always use `unittest.mock.patch.object`
for patching and `MagicMock` / `AsyncMock` for fakes.

```python
# ✗ Never — monkeypatch is forbidden
def test_something(self, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "attr", fake_value)

# ✓ Always — mock.patch.object as a context manager
from unittest.mock import AsyncMock, MagicMock, patch

def test_something(self) -> None:
    with patch.object(module, "attr", new_value):
        ...

# ✓ Always — MagicMock for HTTP client fakes (no patch needed for injected deps)
async def test_scraper_parses_valid_response(self) -> None:
    from scrapers import hackernews

    mock_resp: MagicMock = MagicMock()
    mock_resp.json = MagicMock(return_value={"hits": [...]})
    mock_resp.raise_for_status = MagicMock()

    mock_client: MagicMock = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)

    result: list[RawItem] = await hackernews.scrape(mock_client)
    assert len(result) >= 1
```

For async methods always use `AsyncMock`, never `MagicMock`:

```python
mock_client.get = AsyncMock(return_value=mock_resp)    # async method ✓
mock_client.get = MagicMock(return_value=mock_resp)    # async method ✗ — will not await
```

## Fixtures

Always use fixtures from `conftest.py`. Never construct `RawItem` or `ScoredItem` inline.

```python
# make_item — factory fixture; call with keyword overrides
def test_something(self, make_item: Callable[..., RawItem]) -> None:
    item: RawItem = make_item(title="LLaMA weights released", source=Source.REDDIT)

# scored_item — pre-built ScoredItem for serialisation tests
def test_something(self, scored_item: ScoredItem) -> None:
    result: dict[str, object] = scored_item.to_feed_dict()
```

New fixtures go in `conftest.py` only, never inline in a test file.

## Imports

All imports must be at the top of the file, never inside functions or classes.
This is a PEP 8 requirement enforced by ruff rule E402.

```python
# ✓ Correct — all imports at the top
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from pipeline.classify import _extract_tags, classify_items
from scrapers import github_trending, hackernews
from scrapers.base import Category, RawItem, Source

# ✗ Never — imports inside a function or class
async def test_something(self) -> None:
    from pipeline.classify import classify_items   # forbidden
    ...
```

Import order (enforced by `poe format`):
1. `from __future__ import annotations`
2. Standard library
3. Third-party packages
4. Local project modules

## Async tests

Mark every async test explicitly with `@pytest.mark.asyncio` even though
`asyncio_mode = "auto"` is set in `pyproject.toml` — it makes intent clear.

```python
@pytest.mark.asyncio
async def test_on_network_error_returns_empty_list_not_exception(self) -> None:
    """..."""
    # Given
    mock_client: MagicMock = MagicMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("down"))

    # When
    result: list[RawItem] = await github_trending.scrape(mock_client)

    # Then
    assert isinstance(result, list)
```

## Test classes

One class per unit. Do not mix units in one class.

| Class | Unit under test |
|---|---|
| `TestRawItem` | `scrapers/base.py` — schema, validators, `url_hash` |
| `TestDedup` | `pipeline/dedup.py` — `deduplicate`, `_title_overlap` |
| `TestVelocity` | `pipeline/score.py` — `compute_velocity` |
| `TestGithubTrendingScraper` | `scrapers/github_trending.py` |
| `TestHackerNewsScraper` | `scrapers/hackernews.py` |
| `TestClassifier` | `pipeline/classify.py` — `classify_items`, category + tag logic |
| `TestExtractTags` | `pipeline/classify.py` — `_extract_tags` |

## What to test

- Schema validation and field validators (`RawItem`, `ScoredItem`)
- Dedup: exact URL collision, fuzzy title match, empty input
- Velocity: score is in `[0, 100]`, hot label is always set, cross-source boost
- Classifier: each category rule, source overrides (arxiv → paper), semantic tags
- Scrapers: network failure returns `[]`, valid response is parsed correctly

## What not to test

- Contents of `data/feed.json` or `data/sources.json`
- GitHub Actions workflow behaviour
- Anything that requires a real network call
- Internal implementation details that are not part of the public contract

## TDD workflow

Use the `/tdd` slash command when adding a new feature or fixing a bug.
It enforces: Red → Green → Refactor, with `poe format` and `poe lint` at the end.
