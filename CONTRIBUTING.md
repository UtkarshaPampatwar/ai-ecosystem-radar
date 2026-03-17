# Contributing to AI Ecosystem Radar

Thanks for helping keep the signal strong. There are four ways to contribute — pick whichever fits your time.

---

## 1. Add a new source (easiest — no Python needed)

Edit `data/sources.json` and add one entry:

```json
{ "name": "Your Source", "type": "rss", "url": "https://example.com/feed.xml" }
```

Or for a Twitter/X account:

```json
{ "name": "Karpathy", "type": "twitter", "account": "karpathy" }
```

Open a PR. CI will validate the schema automatically. That's it.

**Good sources to add:**
- AI lab blogs with RSS feeds
- Framework changelogs (LangChain, CrewAI, AutoGen, etc.)
- High-signal individual researchers on Twitter

---

## 2. Fix a bad classification

If an item is tagged with the wrong category or scored too high/low:

1. Open an issue using the **Bad tag** template
2. Or directly edit the keyword rules in `pipeline/classify.py`
3. Run `poe test` to confirm nothing broke

---

## 3. Improve a scraper

Each scraper lives in `scrapers/`. They're simple async functions:

```python
async def scrape(client: httpx.AsyncClient) -> list[RawItem]:
    ...
```

To test a single scraper locally:

```bash
python -c "
import asyncio, httpx
from scrapers import github_trending
async def run():
    async with httpx.AsyncClient() as c:
        items = await github_trending.scrape(c)
        print(f'{len(items)} items')
        for i in items[:3]: print(' -', i.title)
asyncio.run(run())
"
```

---

## 4. Run the full pipeline locally

```bash
# Clone and set up
git clone https://github.com/your-org/ai-ecosystem-radar
cd ai-ecosystem-radar
poetry install

# Run the full pipeline (no API key needed)
poe pipeline

# Open the UI (no server needed)
open site/index.html

# Generate this week's digest
python -m pipeline.digest
```

---

## Development guidelines

- **One scraper per file** in `scrapers/`. Each must return `list[RawItem]`.
- **Never raise** in a scraper — catch all exceptions and return an empty list. The pipeline must always complete.
- **No hardcoded secrets** — use environment variables.
- **Run tests before opening a PR:** `poe test`
- **Lint and format before opening a PR:** `poe fix && poe format`
- **Keep PRs focused** — one source addition or one bug fix per PR is ideal.

---

## Project structure recap

```
scrapers/     ← one file per data source
pipeline/     ← classify.py, score.py, dedup.py, run.py, digest.py
data/         ← feed.json (auto-updated), sources.json (you edit this)
site/         ← index.html (the UI)
tests/        ← pytest test suite
.github/      ← Actions workflows + PR/issue templates
```

Questions? Open a Discussion on GitHub.
