# Changelog

## 2026-09-17 — CLA-269: Add source filter + read-state filter to the "All" tab

Audited first and found one premise in the ticket didn't hold: the "All" tab's
backend endpoint (`/miniflux/v1/entries?order=published_at&direction=desc&limit=200`)
has no `status=unread` filter, and the client-side unread-only filter in
`ArticleListView` is gated behind `showUnreadToggle`, which is `false` for "All" —
so read articles were already present in the list, just with no way to isolate them.
The real gap was the missing filter *controls*, not missing data.

Also checked whether a separate category filter (beyond per-feed) was worth adding
for "newsletters" specifically, per the ticket's "source/category" framing — found
all newsletter senders are already funneled through one synthetic Miniflux feed
("Neo Newsletters", `/rss/newsletter-feed`), so a plain per-feed source filter
already isolates newsletters as a single selectable option. Skipped a separate
category layer as redundant. Also skipped topic-tag filtering per the ticket's own
scope note — real topic tags aren't reliably available per-entry from Miniflux
(only `feed.title`), so adding that would've meant new backend work.

Added to the "All" tab only (Feed and Starred unchanged):
- A source dropdown listing every distinct feed present in the current entries,
  filtering the list to that feed
- A three-way All/Unread/Read filter (pill buttons, reusing `.tab-btn` styling)

Changes:
- `frontend/index.html`: `ArticleListView` gained a `showFilterBar` prop (wired to
  `activeTab === "all"`), `sourceFilter`/`readFilter` state, and the filter bar UI;
  small CSS additions (`.filter-select`, `.read-filter-group`).

## 2026-09-17 — CLA-254: Fix newsletter tap-to-open and reappearing duplicates

Two reported bugs (2026-08-27, untouched since) turned out to share one root cause,
not two. Audited the frontend click handler and `digest_archiver.py`'s mark-as-read
flow first, per usual, and found the actual mechanism was different from what CLA-218's
history suggested.

**What CLA-218 (Jun 2026) actually did:** removed the in-app `ReaderOverlay` and
decoupled expand-to-preview from mark-as-read — `toggle()` just shows an AI summary +
content preview, `handleRead()` is the separate action that opens the URL and marks
read via Miniflux. This already works correctly for regular RSS articles today. It
is NOT what's broken for newsletters.

**What's actually broken:** `_generate_digest()` read newsletter articles from
`newsletter_articles.jsonl` directly, using `newsletter_ingestor.py`'s own
`nl-<hash>` id scheme — but newsletter articles are *also* already ingested into
Miniflux as a real subscribed feed (`/rss/newsletter-feed`, confirmed live as feed id
31, category "Newsletters"), where Miniflux assigns them its own integer entry id.
Every newsletter article was being fed into the Gemini digest prompt **twice**, once
under each id. This caused both bugs:
- **Tap-to-open silently failing**: the frontend's `expandTrigger` mechanism matches
  a tapped digest card's id against the live Miniflux `entries` array by id — an
  `nl-<hash>` id never matches anything there, so tapping a newsletter card did
  nothing. Regular articles work because the digest already uses their real Miniflux
  id.
- **Duplicates reappearing**: the JSONL read had no unread/read filter at all — it
  unconditionally included the first 30 lines of the file (oldest-first, since it's
  append-only) in *every* digest generation, forever, regardless of whether the
  article had already been read via Miniflux.

**Fix:** removed the redundant JSONL read from `_generate_digest()` entirely.
Newsletter articles now flow through the exact same path as regular RSS articles —
same id space, same unread-status filtering, same tap-to-open mechanism, no
bespoke reader UI needed.

**Secondary finding, also fixed:** confirmed `newsletter_ingestor.py`'s thread-level
dedup (AgentMail thread_id) is stable and correct — each email is only ever
processed once. But its *article*-level dedup hash includes the raw extracted URL,
which varies issue-to-issue for the same destination (tracking query strings,
`http` vs `https`) — found two real examples in the live data
(`coached.com/elevator-pitch?ref=coachedweekly` vs the bare URL; `http://` vs
`https://coached.com/quiz`), each producing a fresh id for what's the same article.
Added `_normalize_url_for_dedup()` (strips scheme/query/fragment/trailing slash for
hashing only — the stored/displayed URL is untouched) so future occurrences of the
same link don't re-appear as "new."

Changes:
- `backend/rss_api.py`: removed the `newsletter_articles.jsonl` read and its article
  loop from `_generate_digest()`.
- `agents/rss/scripts/newsletter_ingestor.py` (neo-repo): added
  `_normalize_url_for_dedup()`, applied to the article-id hash.

## 2026-09-17 — CLA-262 / CLA-263: Fix two digest failure modes in `_generate_digest()`

Two related bugs in the same function, both causing the digest to come back empty or
broken. Bundled since fixing one without the other left the digest path still fragile.

**CLA-262 — "ID:" prefix breaks article ID matching.** Article lines in the Gemini
prompt are formatted `ID:{eid} | Feed:... | title`, and Gemini intermittently echoes
that literal `ID:` label back in its response (`"id": "ID:18892"`) instead of just the
bare id. The validation loops do an exact match against `valid_ids` (bare ids), so a
prefixed id never matches — when this happens across most/all returned ids, the digest
comes back empty. Non-deterministic; accounted for ~4 digest failures in the 2 weeks
prior to 2026-09-16. Fixed by stripping the `ID:` prefix (`_strip_id_prefix()`) before
matching, applied in the top_picks loop and the topics article loop as specced, plus
the duplicates loop (`dupe_id` / `canonical_id`) — found during audit to have the same
exact-match vulnerability, not explicitly named in the ticket but same bug class.

**CLA-263 — malformed JSON on large digest output.** Gemini occasionally returns
malformed JSON (unterminated strings, missing commas) once output gets large.
`max_output_tokens` was bumped 4000→8000 on 2026-09-04 (830f51f) as a short-term
mitigation. Added `response_mime_type="application/json"` to the Gemini
`GenerateContentConfig` to constrain the sampler so it can't produce invalid JSON in
the first place, and extended the existing single retry to 3 attempts with a 2s
backoff between them.

## 2026-07-01 — Alert on digest failure

`evening_generate.py` now posts `⚠️ RSS digest failed: <reason>` to #homeserver
whenever digest generation fails (Gemini error, fetch failure, or doorbell failure).
Approved by Ted in #rss 2026-07-01.

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
