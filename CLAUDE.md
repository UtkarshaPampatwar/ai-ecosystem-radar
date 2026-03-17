# AI Ecosystem Radar — Claude Instructions

## Project overview

Automated AI ecosystem signal aggregator. Six scrapers run every 6 hours, feed a
rule-based classifier + velocity engine, and publish results to a static dashboard
on GitHub Pages. Zero external API keys required.

**Pipeline:** `scrapers/` → `pipeline/dedup.py` → `pipeline/score.py` → `pipeline/classify.py` → `data/feed.json` → `site/index.html`

## Tech stack

- **Python 3.12**, managed with **Poetry**
- **Pydantic v2** for all data schemas (`scrapers/base.py`)
- **httpx** (async HTTP), **feedparser** (RSS), **BeautifulSoup4** (HTML)
- **pytest + pytest-asyncio** for tests (`asyncio_mode = "auto"`)
- **ruff** for linting and formatting (line length 100, rules E/F/I/UP)
- **poethepoet** task runner — use `poe <task>` not raw commands

## Common commands

```bash
poe format      # sort imports then format (ruff check --select I --fix + ruff format)
poe lint        # ruff check
poe test        # pytest tests/ -v
poe pipeline    # python -m pipeline.run  (regenerates data/feed.json)
poetry run python validate_sources.py          # schema check on data/sources.json
poetry run python validate_sources.py --live   # + live HTTP test each feed
```

To preview the dashboard locally:
```bash
python3 -m http.server 8081 --directory site
```

## Code conventions

- All scrapers return `list[RawItem]` — never raise, always return an empty list on failure
- `RawItem.tags` is populated by `pipeline/classify.py::_extract_tags()`, not by scrapers
  (scrapers used to pass raw language/academic tags; classify.py generates semantic tags)
- `ScoredItem.to_feed_dict()` is the only serialisation path — never bypass it
- Async functions use `async def` + `await`; sync helpers are plain `def`
- No `sys.path` hacks in tests — use `pythonpath = ["."]` in `pyproject.toml`

## Classification rules (pipeline/classify.py)

These definitions matter — wrong categories confuse users.

| Category | Means | Examples |
|---|---|---|
| **model** | A new AI model being released or announced | Mistral Small 3B weights, LLaMA 3.1 release |
| **tool** | Software you use to work with models | Proxy/relay, web UI, plugin, CLI, local runner |
| **framework** | Named AI dev framework only | LangChain, LangGraph, CrewAI, DSPy |
| **repo** | A GitHub repository (GitHub source/URL only) | Trending repos with no stronger signal |
| **paper** | Research paper (ArXiv source = always paper) | ArXiv abstracts, preprints |
| **news** | Blog posts, announcements, opinions | RSS blogs, tweets, HN discussions |

Key rules:
- `arxiv` source → always **paper**, regardless of title keywords
- `github_trending` source or `github.com` URL → **repo** as fallback when no other signal matches
- **tool** is checked before **model** — proxy/app items that mention model names stay as tool
- `REPO` is not in keyword scoring at all — it is only a source-based fallback
- `FRAMEWORK` requires a named framework (langchain, langgraph, etc.) — the word "framework" alone does not qualify

## Test conventions (TDD)

All tests live in `tests/`. Run the TDD skill with `/tdd` when adding features.
Full details: [.github/instructions/pytest.instructions.md](.github/instructions/pytest.instructions.md)

### Structure
- Fixtures in `tests/conftest.py` — `make_item` (factory) and `scored_item`
- One test class per unit: `TestRawItem`, `TestDedup`, `TestVelocity`, `TestClassifier`, `TestExtractTags`
- Test naming: `test_<unit>_<condition>_<expected_result>`
- Every test has a docstring explaining **why** the behaviour matters (the spec rationale)

### Given / When / Then

GWT lives in the **docstring** — the test body is plain code, no `# Given/When/Then` comments.

```python
def test_exact_url_dedup_keeps_higher_star_version(self, make_item: Callable[..., RawItem]) -> None:
    """Given two duplicates with different star counts, when deduplicated,
    then the higher-star version is kept so the velocity engine sees the freshest signal."""
    items: list[RawItem] = [
        make_item(url="https://github.com/same/repo", stars=100),
        make_item(url="https://github.com/same/repo", stars=200),
    ]
    result: list[RawItem] = deduplicate(items)
    assert result[0].stars == 200
```

### Mocking rules
- **Never use `monkeypatch`** — always use `unittest.mock.patch.object`, `MagicMock`, `AsyncMock`
- Async methods must use `AsyncMock`, not `MagicMock`
- **All imports at the top of the file** — never inside a function or class (PEP 8 / ruff E402)

### Code style in tests
- `from __future__ import annotations` at the top of every test file
- Full type annotations on every function signature and local variable
- PEP 8 throughout — enforced by `poe lint` and `poe format`

### What to test
- Schema validation and edge cases (`RawItem`, `ScoredItem`)
- Dedup: exact URL, fuzzy title, empty input
- Velocity: score range, hot labels, cross-source boost
- Classifier: each category, the source overrides, semantic tags
- Scrapers: network failure → empty list (mocked, never real HTTP)

### What not to test
- The contents of `data/feed.json` or `data/sources.json`
- GitHub Actions workflow logic
- Anything requiring real network calls
