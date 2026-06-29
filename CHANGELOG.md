# Changelog

## 2026-06-29 — CLA-247: Conditional archiver + Gemini JSON retry

Motivated by the Jun 26 incident: Gemini returned malformed JSON on both the
19:30 and 22:55 runs, yet the 23:00 archiver still marked 123 articles read —
silently destroying a full day of accumulated reading.

### Core fix — conditional mark-all-read in `digest_archiver.py`
- `digest_archiver.py` — `mark_all_read()` and `reset_digest()` are now gated
  on a validity check at 23:00: the digest must exist, be error-free, be dated
  today (UTC), and have ≥1 topic and ≥1 top pick. On a no-valid-digest night
  the archiver logs "holding articles unread for tomorrow" and does not clear
  Miniflux. A valid-digest night behaves exactly as before.
- A stale file from a previous night (rare crash scenario) cannot trigger a
  mark-all-read because the UTC date check rejects it.

### Shared predicate — `backend/digest_utils.py` (new)
- `is_valid_digest(digest, today_utc)` — single source of truth for "did
  tonight produce a valid digest?" Imported by both `digest_archiver.py` and
  `evening_generate.py` so the two scripts can never drift on the definition.
- `today_utc()` — convenience helper returning today's YYYY-MM-DD in UTC.

### `evening_generate.py` — uses shared predicate
- Inline validity check replaced with `is_valid_digest(digest, today_utc())`.
  Behaviour unchanged; predicate is now shared.

### Secondary fix — Gemini JSON parse retry in `rss_api.py`
- `_generate_digest()` — on `json.JSONDecodeError` the Gemini call is retried
  once before failing. Logs `[digest] Gemini JSON parse error, retrying once:
  ...` on the first failure. Any exception on the retry (including a second
  parse error) propagates to the outer handler and returns `digest_unavailable`
  as before. 503 / network errors still go directly to the outer handler.

## 2026-06-29 — CLA-246: Evening digest doorbell + cron cleanup

- `backend/evening_generate.py` (new) — standalone cron script replacing the blind 19:30 curl.
  Hits `GET /rss/digest?refresh=true` on the running Fizzy service, validates the result
  (≥1 topic, ≥1 top pick), and posts a doorbell to `#rss` **only on a non-empty digest**.
  Writes `agents/rss/data/last_run.json` on every run so the Stats health panel and the
  morning brief reflect actual evening-script health rather than the retired RSS agent's
  last run. Does not mark any articles read.
- Cron 19:30 — replaced `curl` with `python3 backend/evening_generate.py`; log now goes to
  `/tmp/evening-generate.log`.
- Cron 22:55 — curl kept (silent regeneration, no doorbell); log split to
  `/tmp/fizzy-refresh-2255.log`.
- Cron 23:00 — `digest_archiver.py` unchanged; archives + resets + marks all read.
- Old `run_digest.py` (19:25) and `run_post.py` (19:30) remain commented/paused; their cron
  comments updated to reference `evening_generate.py (CLA-246)` as the replacement.

## 2026-06-17 — Bundle CDN scripts locally
- Downloaded React 18, ReactDOM, and Babel standalone from unpkg.com to `frontend/` static directory
- Updated `index.html` to load from `/static/` instead of unpkg.com CDN (fixes blank screen on devices where CDN is blocked/unavailable)

## 2026-06-08 — CLA-237: CLAUDE.md repo boundary note
- Added `## Repo boundary` section near the top of `CLAUDE.md` clarifying this repo contains no email, newsletter, or AgentMail code — all of that lives in neo-repo at `/home/ted/neo-repo/agents/rss/scripts/`

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
