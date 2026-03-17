# Roadmap

This is a living document. Items move from **Planned** → **In Progress** → **Done** via community PRs.
If you want to pick something up, comment on the relevant GitHub Issue or open a new one.

---

## ✅ Done (v0.1 — initial release)

- [x] 6 scrapers: GitHub Trending, Hacker News, Reddit, ArXiv, RSS blogs, Twitter/Nitter
- [x] Pydantic v2 schemas (`RawItem`, `ScoredItem`)
- [x] URL-hash + fuzzy title deduplication
- [x] Claude AI classifier: category, relevance score, 1-line summary, breaking-change flag
- [x] Trend velocity engine: star delta, cross-source boost, recency decay
- [x] GitHub Actions: scrape every 6h, digest every Monday, CI on every PR
- [x] Auto-deploy to GitHub Pages on every data commit
- [x] Zero-dependency radar UI: filter, search, sort
- [x] `sources.json` contributor workflow — add a source without writing Python
- [x] `validate_sources.py` local validation script
- [x] Full pytest suite

---

## 🔨 In Progress

- [ ] **Diff-based notifications** — only alert when genuinely *new* items appear, not on every run
- [ ] **`--dry-run` mode** for pipeline** — runs all scrapers and prints results without calling the AI API or writing files (useful for testing new scrapers)

---

## 📋 Planned — contributions welcome

### Data quality
- [ ] **Confidence scores on classification** — flag uncertain classifications for human review
- [ ] **Duplicate cluster report** — weekly summary of items that nearly-deduped, for tuning the threshold
- [ ] **False-positive tracker** — persistent list of URLs to always exclude (spam, off-topic viral posts)
- [ ] **Domain allowlist / blocklist** — community-managed lists in `data/`

### Sources
- [ ] **YouTube channel RSS** — monitor AI channels (Andrej Karpathy, Yannic Kilcher, etc.)
- [ ] **GitHub releases feed** — track version releases for top AI frameworks directly
- [ ] **Discord / Slack digests** — pull highlights from public AI community servers
- [ ] **Product Hunt** — catch AI tool launches on launch day
- [ ] **Dev.to / Hashnode** — surface well-received technical AI posts

### Intelligence layer
- [ ] **Change detection** — compare consecutive snapshots to flag when a repo changes category (e.g. script → framework)
- [ ] **Prompt versioning** — version-control the classifier prompt alongside eval results, so prompt changes are traceable
- [ ] **Local model option** — allow running classifier with Ollama for fully offline / zero-cost operation
- [ ] **Embedding-based dedup** — replace fuzzy title match with vector similarity for better cross-language dedup

### Delivery
- [ ] **JSON RSS feed** — expose `data/feed.json` as a valid RSS/Atom feed for feed readers
- [ ] **Category digest emails** — opt-in digest filtered to a single category (e.g. "only models")
- [ ] **Slack / Discord bot** — post hot items to a channel in real time
- [ ] **CLI tool** — `radar search <query>`, `radar top --category tool`, installable via pipx

### UI
- [ ] **Timeline view** — visualise item volume per day as a sparkline
- [ ] **Star growth chart** — inline sparkline per repo showing 7-day star history
- [ ] **Tag cloud** — most common tags this week as a clickable word cloud
- [ ] **Dark mode toggle** — currently follows system preference; add manual override
- [ ] **Keyboard shortcuts** — `j/k` to navigate, `o` to open, `/` to search
- [ ] **Saved items** — browser-local bookmark list

### Community
- [ ] **Leaderboard** — top contributors by merged PRs (sources added, bugs fixed)
- [ ] **Source health dashboard** — public page showing uptime / last-successful-fetch per source
- [ ] **Classifier eval harness** — small labelled dataset + script to measure classifier accuracy across prompt versions

---

## 💡 Ideas under consideration

- **Multi-language support** — Japanese, Chinese, and German AI ecosystems have strong independent communities
- **Company tracker** — follow specific companies (Anthropic, OpenAI, etc.) and surface all their activity in one view
- **Trend alerts via GitHub Actions summary** — post a summary table to the Actions run summary for easy inspection without cloning

---

## How to contribute

Pick any **Planned** item, open an Issue to claim it, then submit a PR.
See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide.

Small contributions matter too — adding a single RSS source to `data/sources.json` takes 2 minutes and immediately benefits every user.
