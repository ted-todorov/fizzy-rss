# Fizzy RSS — Claude Code instructions

## What this is
Fizzy RSS is a personal RSS reader web app. FastAPI backend serves both the API and the static frontend HTML. Runs on a Raspberry Pi 5 as a systemd user service.

## Pi access
SSH: ted@10.3.5.103
Repo on Pi: /home/ted/fizzy-rss
Service: fizzy-rss.service (port 8088)
Restart: `systemctl --user restart fizzy-rss`

## Deploy workflow
```
# Mac
git push origin main

# Pi
cd /home/ted/fizzy-rss && git pull
# If backend changed:
systemctl --user restart fizzy-rss
# If only index.html changed: no restart needed (file is read on each request)
```

## Data files (in neo-repo, not this repo)
All persistent data lives at `/home/ted/neo-repo/agents/rss/data/`
Do NOT move these files — the RSS agent in neo-repo reads/writes them too.

Key files:
- `rss_weights.json` — taste profile weights
- `click_events.jsonl` — click tracking (grows unbounded; prune if >5 MB)
- `newsletter_articles.jsonl` — newsletter ingestion output
- `fizzy_digest.json` — digest cache (regenerated daily or on `?refresh=true`)

## Key environment variables (from /home/ted/neo-repo/.env)
The service loads `.env` from `/home/ted/neo-repo/.env` — do not create a separate .env.

- `MINIFLUX_API_KEY` — Miniflux authentication
- `GOOGLE_API_KEY` — Gemini Flash Lite (not GEMINI_API_KEY)
- `FIZZY_API_KEY` — Bearer token for write endpoints (/rss/click, /rss/react, /rss/brief)

## Miniflux
Runs in Docker on the Pi. Access from host: http://localhost:8085
Do NOT use localhost from inside any other Docker container — use 172.19.0.1:8085

## Ports in use on Pi
- 8085: Miniflux (Docker)
- 8086: InfluxDB (Docker) — do not use
- 8088: Fizzy RSS (this service)

## neo-repo dependency
`backend/rss_api.py` adds `/home/ted/neo-repo` to `sys.path` at startup so it can import:
- `agents.rss.scripts.rss_weights.record_feedback`
- `agents.rss.scripts.rss_reaction_poller._post_brief_request`

These scripts live in neo-repo and must not be copied here — keep them in one place.

## Audit-first rule
Always SSH and read current files before writing any code. The Pi is the source of truth.

## Never touch
- `/home/ted/neo-repo/agents/rss/data/` — shared data, owned by neo-repo
- The RSS agent scripts in neo-repo — separate codebase

## Workflow

### Linear
Use the `linear-claude` connector for all Linear operations (not the planning connector).

When starting a ticket:
- Move it to In Progress immediately before doing any work

When finishing a ticket:
- Post a comment summarising: what was audited, what was changed, any findings beyond the spec, any caveats
- Move to In Review
- Never move to Done — that's Ted's gate

### Three-actor model
- Ted — decision-maker, approves Done, provides direction via Claude.ai
- Claude (claude.ai project) — planner, spec writer, Linear ticket author
- Claude Code (this) — implementation executor on Pi via SSH

### Audit-first rule
Always SSH and read current files before writing any code. The Pi is the source of truth. Specs that skip audit have repeatedly targeted wrong files.

### Minimal correct solution
Scope down to the smallest working fix. Don't redesign when a targeted change solves the problem.

### No restart needed for index.html changes
`fizzy-rss.service` restart only required when `backend/rss_api.py` changes. Frontend changes to `index.html` take effect immediately on next page load.

### Deploy pattern
On Mac: `git add . && git commit -m "..." && git push`
On Pi: `cd /home/ted/fizzy-rss && git pull`
Then if backend changed: `systemctl --user restart fizzy-rss`
