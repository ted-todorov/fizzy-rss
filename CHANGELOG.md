# Changelog

## 2026-06-04 — CLA-228: Taste profile personalisation
- Digest generation now reads rss_weights.json and injects top 10 interests into Gemini prompt
- Top picks ranked by relevance to taste profile; each pick includes a relevance_reason
- Taste profile display redesigned: "Your reading DNA" header, emoji pills, top 3 amber-tinted, no raw numbers

## 2026-06-04 — CLA-227: Daily digest archiver + history browser + favicon chips
- digest_archiver.py: nightly cron (23:00) snapshots digest to fizzy_digest_history.jsonl, marks all Miniflux entries read, clears digest cache
- GET /rss/digest/history and GET /rss/digest/history/{date} endpoints added
- DigestCard: "📅 Previous Digests" section with expandable day cards; archived article links fetch original URL from Miniflux
- Article chips redesigned: favicon (Google S2) + title, replacing "Source — Title..." text

## 2026-06-04 — CLA-229: Workflow instructions added to CLAUDE.md
- Added ## Workflow section: Linear connector usage, In Progress/In Review flow, audit-first rule, deploy pattern

## 2026-06-04 — CLA-223: Digest card redesign
- Enriched Gemini prompt: per-article summary, tags, top_picks array, feed_domain
- DigestCard: amber header strip, Top Picks section with rich article cards, coloured topic sections with left borders
- Refresh button bypasses 24h cache (?refresh=true)

## 2026-06-04 — CLA-221: System health dashboard
- GET /rss/health endpoint: 5 sections (agent, miniflux, digest, storage, service), green/amber/red logic
- Stats tab redesigned: overall health bar + collapsible section cards

## 2026-06-04 — CLA-220: Daily digest card + article deduplication
- GET /rss/digest endpoint: Gemini-powered topic grouping and deduplication, cached to fizzy_digest.json
- DigestCard added to Feed tab
- Dupe articles hidden from main list; canonical articles show 🔁 N sources pill

## 2026-06-02 — Initial extraction from neo-repo (CLA-222)

Fizzy RSS extracted from `ted-todorov/neo` into its own standalone repo.

### What exists at extraction
- FastAPI backend (`backend/rss_api.py`) serving frontend + API on port 8088
- Single-file React frontend (`frontend/index.html`) with inline Babel, ~1100 lines
- Miniflux proxy: all `/miniflux/*` routes proxy to Docker Miniflux, injecting API key server-side
- AI summaries via Gemini Flash Lite (`POST /summarise`)
- Taste profile: click tracking (0.1× expand, 0.5× read), reactions (1.0×); weights at `GET /rss/weights`
- Daily digest (`GET /rss/digest`): Gemini-powered topic grouping, per-article summaries/tags, top picks, article dedup; 24h cache; `?refresh=true` bypass
- Digest card UI: amber header, Top Picks section with rich article cards, topic sections with colored left borders
- Article deduplication: `dupeMap` from digest hides duplicate articles in Feed/All tabs; canonical shows `🔁 N sources` pill; nested dupe cards in expanded view
- Newsletter feed: `GET /rss/newsletter-feed` serves `newsletter_articles.jsonl` as RSS 2.0
- Investing brief trigger: `POST /rss/brief` replicates Discord 💲 reaction path (async)
- iOS PWA: `apple-touch-icon.png`, `favicon.ico`, `apple-mobile-web-app-capable` meta tags
- System health dashboard: `GET /rss/health` endpoint; Stats tab shows green/amber/red section cards (Agent, Miniflux, Digest, Storage, Service)
- Miniflux "Newsletters" category registered with Neo newsletter feed

### Infrastructure notes
- Port 8088 (8086 occupied by InfluxDB Docker — do not use)
- Miniflux in Docker: use `172.19.0.1:8085` from within Docker; `localhost:8085` from Pi host
- `FETCHER_ALLOW_PRIVATE_NETWORKS=1` set in Miniflux Docker Compose
- `ufw` allows ports 8085 and 8088
- Data files remain in `/home/ted/neo-repo/agents/rss/data/` (shared with RSS agent)
- `.env` loaded from `/home/ted/neo-repo/.env` (shared with neo-repo)
- `sys.path` includes `/home/ted/neo-repo` for shared script imports
