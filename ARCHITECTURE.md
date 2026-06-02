# Fizzy RSS — Architecture

## Overview
Single-process FastAPI application serving both API and frontend. No build step — frontend is a self-contained HTML file with inline React (Babel CDN).

## Component map

```
Browser (local network or Tailscale)
    │
    ▼
FastAPI  /home/ted/fizzy-rss/backend/rss_api.py  (Pi :8088)
    ├── GET /                     → serves frontend/index.html (key injected at serve time)
    ├── GET /apple-touch-icon.png → serves frontend/apple-touch-icon.png
    ├── GET /favicon.ico          → serves frontend/favicon.ico
    ├── ANY /miniflux/{path}      → proxies to Miniflux :8085 (injects MINIFLUX_API_KEY)
    ├── POST /summarise           → Gemini Flash Lite, returns 1-2 sentence summary
    ├── GET  /rss/digest          → daily digest: topic grouping + dedup (24h cache)
    ├── GET  /rss/health          → live system health check (agent, Miniflux, storage, service)
    ├── GET  /rss/weights         → returns rss_weights.json
    ├── POST /rss/click           → records article click → rss_weights.json
    ├── POST /rss/react           → records 👍/👎 → rss_weights.json
    ├── POST /rss/brief           → triggers investing agent brief (async, Discord path)
    └── GET  /rss/newsletter-feed → RSS 2.0 feed from newsletter_articles.jsonl
           │
           ├── Miniflux (Docker :8085) — RSS feed engine + article storage
           ├── Gemini Flash Lite — digest generation, article summaries
           └── /home/ted/neo-repo/agents/rss/data/ — shared data with RSS agent
               ├── rss_weights.json
               ├── click_events.jsonl
               ├── newsletter_articles.jsonl
               ├── fizzy_digest.json
               └── last_run.json

Neo RSS Agent  (separate process, neo-repo)
    ├── Reads/writes rss_weights.json
    ├── Writes newsletter_articles.jsonl (via newsletter_ingestor.py)
    └── Triggers brief via rss_reaction_poller.py (Discord 💲 emoji path)
```

## Data flow: taste profile
1. User expands article → `POST /rss/click` (weight_override=0.1)
2. User clicks "Read article" → `POST /rss/click` (weight_override=0.5)
3. User reacts 👍/👎 → `POST /rss/react`
4. All calls `record_feedback()` in `neo-repo/agents/rss/scripts/rss_weights.py`
5. `GET /rss/weights` reads `rss_weights.json` → Stats tab displays taste profile

## Data flow: daily digest
1. Page load → `GET /rss/digest`
2. If `fizzy_digest.json` < 24h old → return cached JSON
3. Else (or `?refresh=true`): fetch 200 unread from Miniflux → Gemini Flash Lite prompt
4. Gemini returns: `top_picks[]`, `topics[]{label, summary, articles[]{id,title,source,summary,tags}}`, `duplicates{}`
5. Validated, cached to `fizzy_digest.json`, returned
6. Frontend: renders DigestCard (amber header, Top Picks, topic sections); builds `dupeMap` for article list deduplication

## Frontend architecture
`frontend/index.html` — single file, ~1100 lines
- React 18 (UMD) + Babel standalone (CDN, no build step)
- `FIZZY_API_KEY` injected by server at serve time via `__FIZZY_API_KEY__` placeholder
- Components: `App`, `ArticleListView`, `DigestCard`, `Article`, `NestedDupe`, `StatsView`, `TasteStrip`, `Thumbnail`, `Toast`, health sub-components
- Tabs: Feed (unread + digest card), Starred, All, Stats (health dashboard + taste profile)

## Key invariants
- `FIZZY_DIR` = `Path(__file__).parent.parent / "frontend"` — relative to backend/rss_api.py
- `DATA_DIR` = absolute `/home/ted/neo-repo/agents/rss/data` — never changes
- neo-repo added to `sys.path` at startup for shared script imports
- EnvironmentFile = `/home/ted/neo-repo/.env` — single source of secrets

## Deployment (current)
Pi serves everything. Browser must be on local network or Tailscale VPN.

## Deployment (target)
Frontend: Vercel CDN (static HTML)
Backend: Pi exposed via Cloudflare Tunnel at `https://api.fizzy.<domain>`
