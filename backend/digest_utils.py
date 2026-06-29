"""Shared digest validity predicate used by digest_archiver.py and evening_generate.py."""
from datetime import datetime, timezone


def is_valid_digest(digest: dict, today_utc: str) -> bool:
    """Return True iff digest is non-empty, error-free, and dated today (UTC YYYY-MM-DD).

    'today_utc' must be a YYYY-MM-DD string in UTC so that a stale file from a
    previous day (generated_at starts with a different date) is never treated as valid.
    Both the archiver and the evening script must pass the same today string so they
    agree on what 'valid' means.
    """
    if digest.get("error"):
        return False
    generated_at = digest.get("generated_at") or ""
    if not generated_at.startswith(today_utc):
        return False
    return bool(digest.get("topics")) and bool(digest.get("top_picks"))


def today_utc() -> str:
    """Return today's date as YYYY-MM-DD in UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
