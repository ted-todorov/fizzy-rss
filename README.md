# Fizzy RSS

Personal RSS reader with AI digest and taste profile. Runs on a Raspberry Pi as a FastAPI service.

## What it does

- **Feed tab**: unread articles from Miniflux, filtered by taste profile, with a daily AI digest card at the top
- **Digest card**: Gemini-curated Top Picks + topic groupings with per-article summaries and tags
- **Article dedup**: duplicate stories collapsed under the most informative canonical, with `🔁 N sources` indicator
- **Taste profile**: click/read/react signals update per-topic and per-source weights in real time
- **Stats tab**: system health dashboard (RSS agent, Miniflux feeds, digest freshness, disk, service status)
- **iOS PWA**: add to home screen for a native-feeling reading experience

## Stack

- **Backend**: FastAPI + uvicorn, Python 3.11+
- **Frontend**: Single HTML file with React 18 (UMD) + Babel CDN — no build step
- **AI**: Gemini Flash Lite (digest generation, article summaries)
- **RSS engine**: Miniflux (self-hosted in Docker on Pi)

## Repo layout

```
backend/
  rss_api.py         FastAPI app — serves frontend + all API routes
  requirements.txt
frontend/
  index.html         Single-file React app (~1100 lines)
  apple-touch-icon.png
  favicon.ico
  make_icons.py      Icon generator (Pillow)
```

## Running locally (Pi)

```bash
cd /home/ted/fizzy-rss
source /home/ted/neo-repo/.env
python3 -m uvicorn backend.rss_api:app --host 0.0.0.0 --port 8088
```

The service runs as a systemd user unit: `systemctl --user restart fizzy-rss`

## Data files

All persistent data lives in `/home/ted/neo-repo/agents/rss/data/` and is **not** in this repo. Those files are shared with the Neo RSS agent — do not move them.

## Docs

- [ARCHITECTURE.md](ARCHITECTURE.md) — component map, data flows, key invariants
- [CLAUDE.md](CLAUDE.md) — instructions for Claude Code sessions
- [CHANGELOG.md](CHANGELOG.md) — history of changes
