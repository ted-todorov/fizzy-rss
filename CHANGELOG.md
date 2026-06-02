# Changelog

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
