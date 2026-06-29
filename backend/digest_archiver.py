#!/usr/bin/env python3
"""Nightly cron: archive today's digest, reset cache, mark all Miniflux entries read.

Mark-all-read is conditional: only fires when tonight's digest is valid (non-empty,
error-free, dated today UTC). On a no-valid-digest night articles are held unread
for tomorrow — never silently cleared. See CLA-247.
"""
import json
import os
from datetime import datetime, timezone
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
        print(f"[archiver] warning: could not load env from {path}: {e}")


_load_env("/home/ted/neo-repo/.env")

import httpx  # noqa: E402 — must come after env load
from digest_utils import is_valid_digest, today_utc  # noqa: E402

DATA_DIR = Path("/home/ted/neo-repo/agents/rss/data")
DIGEST_PATH = DATA_DIR / "fizzy_digest.json"
HISTORY_PATH = DATA_DIR / "fizzy_digest_history.jsonl"
MINIFLUX_BASE = os.environ.get("MINIFLUX_URL", "http://localhost:8085")
MINIFLUX_API_KEY = os.environ.get("MINIFLUX_API_KEY", "")


def archive_digest() -> tuple[str, int, int]:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    snapshotted_at = datetime.now(timezone.utc).isoformat()

    if not DIGEST_PATH.exists():
        print(f"[archiver] {today}: no digest file, skipping archive")
        return today, 0, 0

    try:
        with open(DIGEST_PATH) as f:
            digest = json.load(f)
    except Exception as e:
        print(f"[archiver] {today}: failed to read digest: {e}")
        return today, 0, 0

    topics = digest.get("topics") or []
    top_picks = digest.get("top_picks") or []
    dupe_map = digest.get("duplicates") or {}
    generated_at = digest.get("generated_at")

    if not topics:
        print(f"[archiver] {today}: digest has no topics, skipping archive")
        return today, 0, 0

    record = {
        "date": today,
        "snapshotted_at": snapshotted_at,
        "generated_at": generated_at,
        "topics": topics,
        "top_picks": top_picks,
        "dupe_map": dupe_map,
    }

    lines: list[str] = []
    replaced = False
    if HISTORY_PATH.exists():
        with open(HISTORY_PATH) as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    obj = json.loads(stripped)
                    if obj.get("date") == today:
                        lines.append(json.dumps(record))
                        replaced = True
                    else:
                        lines.append(stripped)
                except Exception:
                    lines.append(stripped)

    if not replaced:
        lines.append(json.dumps(record))

    with open(HISTORY_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")

    return today, len(topics), len(top_picks)


def reset_digest() -> None:
    if DIGEST_PATH.exists():
        DIGEST_PATH.unlink()
        print("[archiver] deleted digest cache")


def mark_all_read() -> int:
    if not MINIFLUX_API_KEY:
        print("[archiver] MINIFLUX_API_KEY not set, skipping mark-read")
        return 0

    headers = {"X-Auth-Token": MINIFLUX_API_KEY}
    all_ids: list[int] = []

    try:
        offset = 0
        while True:
            resp = httpx.get(
                f"{MINIFLUX_BASE}/v1/entries",
                headers=headers,
                params={"status": "unread", "limit": 1000, "offset": offset},
                timeout=30,
            )
            data = resp.json()
            batch = data.get("entries") or []
            if not batch:
                break
            all_ids.extend(e["id"] for e in batch)
            offset += len(batch)
            if len(batch) < 1000:
                break
    except Exception as e:
        print(f"[archiver] failed to fetch unread entries: {e}")
        return 0

    if not all_ids:
        return 0

    marked = 0
    for i in range(0, len(all_ids), 1000):
        chunk = all_ids[i : i + 1000]
        try:
            httpx.put(
                f"{MINIFLUX_BASE}/v1/entries",
                headers={**headers, "Content-Type": "application/json"},
                content=json.dumps({"entry_ids": chunk, "status": "read"}),
                timeout=30,
            )
            marked += len(chunk)
        except Exception as e:
            print(f"[archiver] failed to mark batch as read: {e}")

    return marked


if __name__ == "__main__":
    _today = today_utc()
    topic_count = 0
    entry_count = 0

    # Check validity BEFORE archive_digest() so we read the file while it's still present.
    # Valid = non-empty digest, no error field, dated today UTC. Stale/empty/error files
    # never trigger a mark-all-read.
    digest_valid = False
    if DIGEST_PATH.exists():
        try:
            with open(DIGEST_PATH) as f:
                digest_valid = is_valid_digest(json.load(f), _today)
        except Exception as e:
            print(f"[archiver] {_today}: could not read digest for validity check: {e}")

    try:
        _today, topic_count, _ = archive_digest()
    except Exception as e:
        print(f"[archiver] archive step failed: {e}")

    if digest_valid:
        try:
            reset_digest()
        except Exception as e:
            print(f"[archiver] reset step failed: {e}")
        try:
            entry_count = mark_all_read()
        except Exception as e:
            print(f"[archiver] mark-read step failed: {e}")
    else:
        print(f"[archiver] {_today}: no valid digest tonight — holding articles unread for tomorrow")

    print(f"[archiver] {_today}: archived {topic_count} topics, marked {entry_count} entries read")
