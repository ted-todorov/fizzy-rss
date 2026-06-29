#!/usr/bin/env python3
"""Evening digest generation with success-bound Discord doorbell.

Runs at 19:30 daily via cron. Hits /rss/digest?refresh=true on the local Fizzy
service, validates the result, and posts a doorbell to #rss only when the digest
is non-empty. Updates agents/rss/data/last_run.json on every run (success or
failure) so both the Fizzy Stats health panel and the morning brief stay current.

Does NOT mark anything read — that is the archiver's job at 23:00.
"""
import datetime
import json
import os
import sys
from pathlib import Path


def _load_env(path: str) -> None:
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())
    except Exception as e:
        print(f"[evening_generate] warning: could not load env from {path}: {e}")


_load_env("/home/ted/neo-repo/.env")

import httpx  # noqa: E402 — must come after env load
from digest_utils import is_valid_digest, today_utc  # noqa: E402

FIZZY_PORT = 8088
FIZZY_DIGEST_URL = f"http://localhost:{FIZZY_PORT}/rss/digest"
RSS_CHANNEL_ID = "1476628292420505731"
DISCORD_API = "https://discord.com/api/v10"
LAST_RUN_PATH = Path("/home/ted/neo-repo/agents/rss/data/last_run.json")


def _write_last_run(status: str, detail: str) -> None:
    data = {
        "agent": "RSS Digest",
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "detail": detail,
    }
    LAST_RUN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LAST_RUN_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _post_doorbell(n_picks: int, n_topics: int) -> None:
    token = os.environ.get("DISCORD_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("DISCORD_BOT_TOKEN not set")
    content = (
        f"📰 Your RSS digest is ready — {n_picks} top picks across {n_topics} topics\n"
        f"http://10.3.5.103:{FIZZY_PORT}"
    )
    resp = httpx.post(
        f"{DISCORD_API}/channels/{RSS_CHANNEL_ID}/messages",
        headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
        json={"content": content},
        timeout=10,
    )
    resp.raise_for_status()
    print(f"[evening_generate] doorbell posted (HTTP {resp.status_code})")


if __name__ == "__main__":
    print(f"[evening_generate] starting {datetime.datetime.now().isoformat(timespec='seconds')}")

    # Step 1: trigger generation via the running Fizzy service
    try:
        resp = httpx.get(
            FIZZY_DIGEST_URL,
            params={"refresh": "true"},
            timeout=90,  # Gemini can take up to 60s; margin for cold start
        )
        resp.raise_for_status()
        digest = resp.json()
    except Exception as e:
        print(f"[evening_generate] ERROR: digest fetch failed: {e}")
        _write_last_run("error", f"fetch failed: {e}")
        sys.exit(1)

    # Step 2: validate using the same predicate as the archiver
    if not is_valid_digest(digest, today_utc()):
        reason = digest.get("error") or "empty or stale digest"
        print(f"[evening_generate] digest unavailable ({reason}) — no doorbell posted")
        _write_last_run("error", f"digest_unavailable: {reason}")
        sys.exit(0)

    n_picks = len(digest.get("top_picks") or [])
    n_topics = len(digest.get("topics") or [])
    detail = f"{n_picks} top picks across {n_topics} topics"
    print(f"[evening_generate] valid digest: {detail}")

    # Step 3: post doorbell only on valid digest
    try:
        _post_doorbell(n_picks, n_topics)
    except Exception as e:
        print(f"[evening_generate] ERROR: doorbell failed: {e}")
        _write_last_run("error", f"doorbell failed: {e}")
        sys.exit(1)

    _write_last_run("ok", detail)
    print(f"[evening_generate] done — {detail}")
