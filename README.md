# AI Ecosystem Radar

> Live signal for engineers building with AI. Tracks repos, tools, models, papers, and news — automatically, every 6 hours.

**[View the radar →](https://ai-radar-hq.github.io/ai-ecosystem-radar)**  |  **[Subscribe to weekly digest →](https://github.com/ai-radar-hq/ai-ecosystem-radar/releases)**

---

## The problem

The AI engineering ecosystem moves faster than any engineer can track. A game-changing framework drops on a Tuesday, you hear about it three weeks later. You're using an outdated library when a better one has existed for months. Newsletters are manually curated, slow, and biased.

This repo is the fix: a fully automated, community-owned radar that watches six data sources, classifies everything, and surfaces only what's relevant to engineers building AI systems.

---

## What it tracks

| Source | What we pull |
|--------|-------------|
| GitHub Trending | AI/ML repos gaining stars fast |
| Hacker News | Stories with 20+ points mentioning LLMs, agents, RAG |
| Reddit | r/MachineLearning, r/LocalLLaMA top posts |
| ArXiv | cs.AI/cs.CL papers on agents, prompting, RAG |
| Model blogs | Anthropic, OpenAI, Google DeepMind, Mistral, Meta AI, HuggingFace |
| Twitter / X | High-signal AI researchers and lab accounts |

---

## How it works

```
6 scrapers (parallel) → dedup → classifier → trend engine → feed.json → UI + digest
```

1. **GitHub Actions** runs every 6 hours and triggers all scrapers in parallel
2. **Deduplication** removes exact URL matches and near-duplicate titles
3. **Classifier** tags each item (tool / model / paper / etc.), scores engineer relevance 0–100, and writes a one-line summary — no API key required
4. **Trend engine** computes velocity from star delta, cross-source signal, and recency
5. Results are committed to `data/feed.json` and served by a zero-dependency static UI
6. Every Monday, a `WEEKLY_DIGEST.md` is auto-generated and cut as a GitHub Release

**Total cost: $0/month** — no API keys, hosting and CI are free.

---

## Quickstart

```bash
git clone https://github.com/ai-radar-hq/ai-ecosystem-radar
cd ai-ecosystem-radar
poetry install
poetry run python -m pipeline.run
mkdir -p site/data && cp data/feed.json site/data/
python3 -m http.server 8080 --directory site
# Then open http://localhost:8080
```

---

## Deploying your own instance

1. Fork this repo
2. Enable **GitHub Pages** from the `site/` folder
3. Enable **GitHub Actions** — the cron job starts automatically

The radar will populate on the first run (~5 minutes) and update every 6 hours from then on.

---

## Contributing

The fastest contribution: **add a source in 2 minutes**.

Edit `data/sources.json`:
```json
{ "name": "Your Blog", "type": "rss", "url": "https://yourblog.com/feed.xml" }
```

Open a PR. CI validates it. Done.

See [CONTRIBUTING.md](CONTRIBUTING.md) for scraper development, classifier tuning, and running the full pipeline locally.

---

## Architecture

```
ai-ecosystem-radar/
├── scrapers/
│   ├── base.py               ← RawItem + ScoredItem schemas (pydantic)
│   ├── github_trending.py
│   ├── hackernews.py
│   ├── reddit.py
│   ├── arxiv.py
│   ├── rss_blogs.py
│   └── twitter_nitter.py
├── pipeline/
│   ├── run.py                ← main orchestrator
│   ├── classify.py           ← rule-based classifier (no API key)
│   ├── score.py              ← trend velocity engine
│   ├── dedup.py              ← URL hash + fuzzy title dedup
│   └── digest.py             ← weekly digest generator
├── data/
│   ├── feed.json             ← live feed (auto-updated every 6h)
│   ├── sources.json          ← community-editable source list
│   ├── sources.schema.json   ← JSON schema for PR validation
│   └── archive/              ← daily snapshots (YYYY-MM-DD.json)
├── site/
│   └── index.html            ← radar UI (zero dependencies)
├── tests/
│   └── test_scrapers.py
├── validate_sources.py       ← run locally before opening a PR
├── ROADMAP.md
└── .github/
    └── workflows/
        ├── scrape.yml        ← runs every 6h
        ├── digest.yml        ← runs every Monday
        ├── deploy.yml        ← deploys site/ to GitHub Pages
        └── ci.yml            ← runs on every PR
```

---

## API / raw data access

The live feed is plain JSON — consume it directly:

```bash
curl https://raw.githubusercontent.com/ai-radar-hq/ai-ecosystem-radar/main/data/feed.json
```

Each item:
```json
{
  "url": "https://github.com/...",
  "title": "repo / name",
  "summary": "One-line summary.",
  "source": "github_trending",
  "category": "framework",
  "relevance": 91,
  "hot": "rising",
  "breaking": false,
  "stars": 4200,
  "scraped_at": "2025-03-17T08:00:00+00:00"
}
```

---

## License

MIT — fork it, run your own, build on top of it.
