import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

# neo-repo must be on sys.path for shared scripts (rss_weights, rss_reaction_poller)
_NEO_REPO = Path("/home/ted/neo-repo")
if str(_NEO_REPO) not in sys.path:
    sys.path.insert(0, str(_NEO_REPO))

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

MINIFLUX_BASE = "http://localhost:8085"
MINIFLUX_API_KEY = os.environ["MINIFLUX_API_KEY"]
GEMINI_API_KEY = os.environ["GOOGLE_API_KEY"]
FIZZY_API_KEY = os.environ["FIZZY_API_KEY"]
GEMINI_MODEL = "gemini-2.5-flash-lite"

# Frontend lives at ../frontend/ relative to this file (backend/rss_api.py)
FIZZY_DIR = Path(__file__).parent.parent / "frontend"
# Data files stay in neo-repo (shared with RSS agent — do not move)
DATA_DIR = Path("/home/ted/neo-repo/agents/rss/data")
CLICK_EVENTS_PATH = DATA_DIR / "click_events.jsonl"
DIGEST_PATH = DATA_DIR / "fizzy_digest.json"
HISTORY_PATH = DATA_DIR / "fizzy_digest_history.jsonl"

app = FastAPI()

app.mount("/static", StaticFiles(directory=str(FIZZY_DIR)), name="static")


def _check_auth(request: Request) -> bool:
    auth = request.headers.get("authorization", "")
    return auth == f"Bearer {FIZZY_API_KEY}"


@app.get("/apple-touch-icon.png", include_in_schema=False)
async def apple_touch_icon():
    return FileResponse(str(FIZZY_DIR / "apple-touch-icon.png"), media_type="image/png")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(str(FIZZY_DIR / "favicon.ico"), media_type="image/x-icon")


@app.get("/", response_class=HTMLResponse)
async def index():
    html = (FIZZY_DIR / "index.html").read_text()
    return html.replace("__FIZZY_API_KEY__", FIZZY_API_KEY)


@app.api_route("/miniflux/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def miniflux_proxy(path: str, request: Request):
    url = f"{MINIFLUX_BASE}/{path}"
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "authorization", "x-auth-token", "content-length")
    }
    headers["X-Auth-Token"] = MINIFLUX_API_KEY

    body = await request.body()
    async with httpx.AsyncClient() as client:
        resp = await client.request(
            method=request.method,
            url=url,
            headers=headers,
            params=dict(request.query_params),
            content=body,
            timeout=30,
        )
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type", "application/json"),
    )


def _gemini_summarise(prompt: str) -> str:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=GEMINI_API_KEY)
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=200),
    )
    return resp.text or ""


@app.post("/summarise")
async def summarise(payload: dict):
    title = payload.get("title", "")
    text = payload.get("text", "")
    prompt = (
        f"1-2 crisp sentences for a busy investor. Lead with the key fact.\n\n"
        f"Title: {title}\n\n{text[:3000]}"
    )
    summary = await asyncio.to_thread(_gemini_summarise, prompt)
    return JSONResponse({"summary": summary})


# ---------------------------------------------------------------------------
# Phase 2 endpoints
# ---------------------------------------------------------------------------

@app.post("/rss/click")
async def rss_click(request: Request, payload: dict):
    if not _check_auth(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    url = payload.get("url", "")
    title = payload.get("title", "")
    feed_name = payload.get("feed_name", "")
    topics = payload.get("topics") or ([feed_name] if feed_name else [])
    weight_override = payload.get("weight_override")  # 0.1 (expand), 0.3 (default), 0.5 (read)
    # "click" base topic_delta is 0.3 — scale relative to that
    scale = (float(weight_override) / 0.3) if weight_override is not None else 1.0

    def _record():
        from agents.rss.scripts.rss_weights import record_feedback
        record_feedback("click", topics, feed_name, weight_scale=scale)

    await asyncio.to_thread(_record)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CLICK_EVENTS_PATH, "a") as f:
        f.write(json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(),
            "url": url,
            "title": title,
            "topics": topics,
        }) + "\n")

    return JSONResponse({"ok": True})


@app.post("/rss/brief")
async def rss_brief(request: Request, payload: dict):
    if not _check_auth(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    title = payload.get("title", "")
    url = payload.get("url", "")
    source = payload.get("source", "")

    from agents.rss.scripts.rss_reaction_poller import _post_brief_request
    asyncio.create_task(asyncio.to_thread(_post_brief_request, title, url, source))

    return JSONResponse({"ok": True})


@app.post("/rss/react")
async def rss_react(request: Request, payload: dict):
    if not _check_auth(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    signal = payload.get("signal", "")
    topics = payload.get("topics") or []
    feed_name = payload.get("feed_name", "")
    emoji = "👍" if signal == "up" else "👎"

    def _record():
        from agents.rss.scripts.rss_weights import record_feedback
        record_feedback(emoji, topics, feed_name)

    await asyncio.to_thread(_record)
    return JSONResponse({"ok": True})


@app.get("/rss/weights")
async def rss_weights():
    weights_path = DATA_DIR / "rss_weights.json"
    if not weights_path.exists():
        return JSONResponse({"topics": {}, "sources": {}, "blacklist": [], "version": 1})
    with open(weights_path) as f:
        return JSONResponse(json.load(f))


@app.get("/rss/newsletter-feed")
async def newsletter_feed():
    import xml.etree.ElementTree as ET

    articles = []
    articles_path = DATA_DIR / "newsletter_articles.jsonl"
    if articles_path.exists():
        with open(articles_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    articles.append(json.loads(line))
                except Exception:
                    pass

    # Newest first, cap at 50
    articles.sort(key=lambda a: a.get("published_at", ""), reverse=True)
    articles = articles[:50]

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Neo Newsletters"
    ET.SubElement(channel, "link").text = "http://10.3.5.103:8088"
    ET.SubElement(channel, "description").text = "Email newsletters ingested by Neo"

    for art in articles:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = art.get("title", "")
        ET.SubElement(item, "link").text = art.get("url", "")
        ET.SubElement(item, "description").text = art.get("body_preview", "")
        ET.SubElement(item, "guid").text = art.get("id", "")
        pub = art.get("published_at", "")
        if pub:
            ET.SubElement(item, "pubDate").text = pub

    xml_bytes = ET.tostring(rss, encoding="unicode")
    xml_str = f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_bytes}'
    return Response(content=xml_str, media_type="application/rss+xml; charset=utf-8")


def _generate_digest() -> dict:
    """Sync: fetch recent entries, call Gemini, return digest dict."""
    import xml.etree.ElementTree as ET
    from google import genai
    from google.genai import types

    # Fetch up to 200 recent unread entries from Miniflux
    import httpx as _httpx
    try:
        resp = _httpx.get(
            f"{MINIFLUX_BASE}/v1/entries",
            headers={"X-Auth-Token": MINIFLUX_API_KEY},
            params={"status": "unread", "limit": 200, "order": "published_at", "direction": "desc"},
            timeout=15,
        )
        data = resp.json()
        entries = data.get("entries") or []
    except Exception as e:
        print(f"[digest] Miniflux fetch failed: {e}")
        return {"error": "digest_unavailable", "generated_at": None, "topics": [], "duplicates": {}}

    if not entries:
        return {"error": "digest_unavailable", "generated_at": None, "topics": [], "duplicates": {}}

    # Also load newsletter articles
    newsletter_entries = []
    if (DATA_DIR / "newsletter_articles.jsonl").exists():
        with open(DATA_DIR / "newsletter_articles.jsonl") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        newsletter_entries.append(json.loads(line))
                    except Exception:
                        pass

    # Build article list for prompt + feed_domain map for favicon
    article_lines = []
    valid_ids: set[str] = set()
    feed_domain_map: dict[str, str] = {}

    def _extract_domain(url: str) -> str:
        try:
            h = urlparse(url).hostname or ""
            return h[4:] if h.startswith("www.") else h
        except Exception:
            return ""

    for e in entries[:100]:
        eid = str(e.get("id", ""))
        title = str(e.get("title", ""))[:200]
        feed_info = e.get("feed") or {}
        feed = feed_info.get("title", "")[:80]
        valid_ids.add(eid)
        article_lines.append(f'ID:{eid} | Feed:{feed} | {title}')
        domain = _extract_domain(feed_info.get("site_url", "")) or _extract_domain(e.get("url", ""))
        if domain:
            feed_domain_map[eid] = domain

    for a in newsletter_entries[:30]:
        eid = str(a.get("id", ""))
        title = str(a.get("title", ""))[:200]
        feed = str(a.get("feed_title", ""))[:80]
        valid_ids.add(eid)
        article_lines.append(f'ID:{eid} | Feed:{feed} | {title}')
        domain = _extract_domain(a.get("url", ""))
        if domain:
            feed_domain_map[eid] = domain

    articles_text = "\n".join(article_lines)

    prompt = (
        "You are a personalized news editor for a busy investor and technologist.\n\n"
        "Article list (ID | Feed | Title):\n"
        f"{articles_text}\n\n"
        "Return ONLY valid JSON with this exact structure:\n"
        "{\n"
        '  "top_picks": ["id1", "id2", "id3"],\n'
        '  "topics": [\n'
        '    {\n'
        '      "label": "Topic Name (≤4 words)",\n'
        '      "summary": "1 sentence on why this topic matters today.",\n'
        '      "articles": [\n'
        '        {\n'
        '          "id": "entry_id",\n'
        '          "title": "article title",\n'
        '          "source": "feed/source name",\n'
        '          "summary": "1 factual sentence on why this article matters.",\n'
        '          "tags": ["tag1", "tag2", "tag3"]\n'
        '        }\n'
        '      ]\n'
        '    }\n'
        '  ],\n'
        '  "duplicates": {\n'
        '    "dupe_id": {"canonical_id": "id", "reason": "≤8 words"}\n'
        '  }\n'
        "}\n\n"
        "Rules:\n"
        "- top_picks: 2-3 IDs of the most significant stories of the day (any topic)\n"
        "- topics: up to 5 groups, each with 2-4 articles, ordered by investor/tech relevance\n"
        "- article summary: 1 factual sentence; never start with 'This article discusses'\n"
        "- tags: 2-4 lowercase single-word tags per article, no spaces\n"
        "- duplicates: if 2+ articles cover the same event, mark dupes pointing to the most reputable canonical\n"
        "- Return ONLY valid JSON, no markdown, no preamble"
    )

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=4000, temperature=0.2),
        )
        raw = (resp.text or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rstrip("` \n")
        result = json.loads(raw.strip())
    except Exception as e:
        print(f"[digest] Gemini failed: {e}")
        return {"error": "digest_unavailable", "generated_at": None, "top_picks": [], "topics": [], "duplicates": {}}

    # Validate and sanitize top_picks
    top_picks = [str(i) for i in (result.get("top_picks") or []) if str(i) in valid_ids][:3]

    # Validate topics — support both new {articles:[]} and old {article_ids:[]} shape
    topics = []
    for t in (result.get("topics") or [])[:5]:
        label = str(t.get("label", ""))[:60]
        summary = str(t.get("summary", ""))[:300]
        raw_articles = t.get("articles") or []
        if not raw_articles and t.get("article_ids"):
            raw_articles = [{"id": str(i)} for i in t["article_ids"]]
        articles = []
        for a in raw_articles[:4]:
            aid = str(a.get("id", ""))
            if aid not in valid_ids:
                continue
            articles.append({
                "id": aid,
                "title": str(a.get("title", ""))[:200],
                "source": str(a.get("source", ""))[:80],
                "summary": str(a.get("summary", ""))[:300],
                "tags": [str(tag)[:30].lower() for tag in (a.get("tags") or [])[:4] if tag],
                "feed_domain": feed_domain_map.get(aid, ""),
            })
        if label and articles:
            topics.append({"label": label, "summary": summary, "articles": articles})

    duplicates = {}
    for dupe_id, info in (result.get("duplicates") or {}).items():
        if str(dupe_id) in valid_ids and str(info.get("canonical_id", "")) in valid_ids:
            duplicates[str(dupe_id)] = {
                "canonical_id": str(info["canonical_id"]),
                "reason": str(info.get("reason", ""))[:80],
            }

    generated_at = datetime.now(timezone.utc).isoformat()
    digest = {"generated_at": generated_at, "top_picks": top_picks, "topics": topics, "duplicates": duplicates}

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DIGEST_PATH, "w") as f:
        json.dump(digest, f)

    return digest


@app.get("/rss/digest")
async def rss_digest(request: Request):
    force = request.query_params.get("refresh", "").lower() == "true"
    # Return cached digest if < 24 hours old and not forcing refresh
    if not force and DIGEST_PATH.exists():
        try:
            with open(DIGEST_PATH) as f:
                cached = json.load(f)
            generated_at = cached.get("generated_at")
            if generated_at:
                age = time.time() - datetime.fromisoformat(generated_at).timestamp()
                if age < 86400:
                    return JSONResponse(cached)
        except Exception:
            pass

    try:
        digest = await asyncio.wait_for(asyncio.to_thread(_generate_digest), timeout=60)
    except asyncio.TimeoutError:
        return JSONResponse({"error": "digest_unavailable", "generated_at": None, "top_picks": [], "topics": [], "duplicates": {}})

    return JSONResponse(digest)


@app.get("/rss/digest/history")
async def rss_digest_history():
    if not HISTORY_PATH.exists():
        return JSONResponse({"dates": []})
    dates = []
    with open(HISTORY_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                dates.append({
                    "date": obj["date"],
                    "snapshotted_at": obj.get("snapshotted_at", ""),
                    "topic_count": len(obj.get("topics") or []),
                    "top_pick_count": len(obj.get("top_picks") or []),
                })
            except Exception:
                pass
    dates.sort(key=lambda x: x["date"], reverse=True)
    return JSONResponse({"dates": dates[:30]})


@app.get("/rss/digest/history/{date}")
async def rss_digest_history_date(date: str):
    if not HISTORY_PATH.exists():
        raise HTTPException(status_code=404, detail="No history available")
    with open(HISTORY_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if obj.get("date") == date:
                    return JSONResponse({
                        "generated_at": obj.get("generated_at"),
                        "top_picks": obj.get("top_picks") or [],
                        "topics": obj.get("topics") or [],
                        "duplicates": obj.get("dupe_map") or {},
                    })
            except Exception:
                pass
    raise HTTPException(status_code=404, detail="Date not found")


LAST_RUN_PATH = DATA_DIR / "last_run.json"
HEALTH_FILES = [
    "rss_weights.json",
    "click_events.jsonl",
    "newsletter_articles.jsonl",
    "fizzy_digest.json",
]


def _status_worst(*statuses: str) -> str:
    for s in ("red", "amber", "green"):
        if s in statuses:
            return s
    return "green"


def _hours_since(iso_ts: str) -> float:
    try:
        dt = datetime.fromisoformat(iso_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except Exception:
        return 9999.0


@app.get("/rss/health")
async def rss_health():
    import shutil
    import subprocess

    now_iso = datetime.now(timezone.utc).isoformat()

    # --- agent section ---
    agent: dict = {}
    if LAST_RUN_PATH.exists():
        try:
            with open(LAST_RUN_PATH) as f:
                lr = json.load(f)
            ts = lr.get("timestamp") or lr.get("last_run_at", "")
            hours = _hours_since(ts)
            status = "green" if hours < 26 else ("amber" if hours < 48 else "red")
            agent = {
                "last_run_at": ts,
                "hours_since_run": round(hours, 1),
                "detail": lr.get("detail", ""),
                "run_status": lr.get("status", ""),
                "status": status,
                "message": f"Last run {hours:.1f}h ago",
            }
        except Exception as e:
            agent = {"status": "red", "message": f"Error reading last_run.json: {e}"}
    else:
        agent = {"status": "red", "message": "No run data found"}

    # --- miniflux section ---
    feeds_data: list = []
    miniflux_section_status = "green"
    feed_count = 0
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{MINIFLUX_BASE}/v1/feeds",
                headers={"X-Auth-Token": MINIFLUX_API_KEY},
                timeout=10,
            )
        raw_feeds = resp.json()
        feed_count = len(raw_feeds) if isinstance(raw_feeds, list) else 0
        for f in (raw_feeds if isinstance(raw_feeds, list) else []):
            checked_at = f.get("checked_at", "")
            hours_check = _hours_since(checked_at) if checked_at else 9999.0
            err_count = int(f.get("parsing_error_count") or 0)
            if err_count > 3 or hours_check > 24:
                fstatus = "red"
            elif err_count > 0 or hours_check > 6:
                fstatus = "amber"
            else:
                fstatus = "green"
            feeds_data.append({
                "title": f.get("title", ""),
                "checked_at": checked_at,
                "hours_since_check": round(hours_check, 1),
                "error_count": err_count,
                "error_message": (f.get("parsing_error_message") or "")[:120],
                "status": fstatus,
            })
        order = {"red": 0, "amber": 1, "green": 2}
        feeds_data.sort(key=lambda x: order.get(x["status"], 3))
        miniflux_section_status = _status_worst(*[f["status"] for f in feeds_data]) if feeds_data else "green"
    except Exception as e:
        miniflux_section_status = "red"
        feeds_data = [{"title": "Error fetching feeds", "error_message": str(e), "status": "red"}]

    miniflux = {
        "feed_count": feed_count,
        "feeds": feeds_data,
        "section_status": miniflux_section_status,
    }

    # --- digest section ---
    digest_section: dict = {}
    if DIGEST_PATH.exists():
        try:
            with open(DIGEST_PATH) as f:
                ddata = json.load(f)
            gen_at = ddata.get("generated_at", "")
            hours_dig = _hours_since(gen_at)
            dstatus = "green" if hours_dig < 25 else ("amber" if hours_dig < 48 else "red")
            digest_section = {
                "generated_at": gen_at,
                "hours_since_generated": round(hours_dig, 1),
                "topic_count": len(ddata.get("topics") or []),
                "dupe_count": len(ddata.get("duplicates") or {}),
                "status": dstatus,
            }
        except Exception as e:
            digest_section = {"status": "red", "message": str(e)}
    else:
        digest_section = {"status": "red", "message": "Digest not generated yet"}

    # --- storage section ---
    try:
        du = shutil.disk_usage("/home/ted")
        disk_pct = du.used / du.total * 100
        disk_status = "green" if disk_pct < 80 else ("amber" if disk_pct < 90 else "red")
        files_info = []
        for fname in HEALTH_FILES:
            fpath = DATA_DIR / fname
            if fpath.exists():
                size_kb = round(os.path.getsize(fpath) / 1024, 1)
                fstatus = "green" if size_kb < 5120 else ("amber" if size_kb < 20480 else "red")
            else:
                size_kb = 0.0
                fstatus = "green"
            files_info.append({"name": fname, "size_kb": size_kb, "status": fstatus})
        storage_section_status = _status_worst(disk_status, *[f["status"] for f in files_info])
        storage = {
            "disk_total_gb": round(du.total / 1e9, 1),
            "disk_used_gb": round(du.used / 1e9, 1),
            "disk_free_gb": round(du.free / 1e9, 1),
            "disk_percent_used": round(disk_pct, 1),
            "disk_status": disk_status,
            "files": files_info,
            "section_status": storage_section_status,
        }
    except Exception as e:
        storage = {"section_status": "red", "message": str(e)}

    # --- service section ---
    try:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", "fizzy-rss"],
            capture_output=True, text=True, timeout=5,
        )
        active = result.stdout.strip() == "active"
        service = {"fizzy_rss_active": active, "status": "green" if active else "red"}
    except Exception as e:
        service = {"fizzy_rss_active": False, "status": "red", "message": str(e)}

    # --- overall ---
    section_statuses = [
        agent.get("status", "green"),
        miniflux.get("section_status", "green"),
        digest_section.get("status", "green"),
        storage.get("section_status", "green"),
        service.get("status", "green"),
    ]
    overall = _status_worst(*section_statuses)

    return JSONResponse({
        "generated_at": now_iso,
        "overall": overall,
        "sections": {
            "agent": agent,
            "miniflux": miniflux,
            "digest": digest_section,
            "storage": storage,
            "service": service,
        },
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8088)
