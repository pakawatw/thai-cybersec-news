"""Shared helpers: paths, JSON state files, site URL, Thai dates."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
STORIES = DATA / "stories"
DOCS = ROOT / "docs"
TEMPLATES = ROOT / "templates"
ASSETS = ROOT / "assets"

PROCESSED_FILE = DATA / "processed.json"
FB_POSTS_FILE = DATA / "fb_posts.json"

BRAND_NAME = os.environ.get("BRAND_NAME") or "ข่าวไซเบอร์ง่ายๆ"

THAI_MONTHS = [
    "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
]

SEVERITY_TH = {
    "low": "ความรุนแรงต่ำ",
    "medium": "ความรุนแรงปานกลาง",
    "high": "ความรุนแรงสูง",
    "critical": "วิกฤต",
}


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def slug_from_url(url: str) -> str:
    """https://thehackernews.com/2026/11/some-story.html -> 2026-11-some-story"""
    m = re.search(r"/(\d{4})/(\d{2})/([^/?#]+?)(?:\.html)?(?:[?#].*)?$", url)
    if m:
        base = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    else:
        base = url.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"[^a-z0-9-]+", "-", base.lower()).strip("-")[:90]


def site_url() -> str:
    """Public base URL of the GitHub Pages site, without a trailing slash."""
    url = os.environ.get("SITE_URL")
    if url:
        return url.rstrip("/")
    repo = os.environ.get("GITHUB_REPOSITORY", "pakawatw/thai-cybersec-news")
    owner, name = repo.split("/", 1)
    return f"https://{owner.lower()}.github.io/{name}"


def article_url(slug: str) -> str:
    return f"{site_url()}/news/{slug}.html"


def thai_date(iso: str) -> str:
    d = datetime.fromisoformat(iso)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    # Show Bangkok time (UTC+7) and Buddhist-era year.
    from datetime import timedelta

    d = d.astimezone(timezone(timedelta(hours=7)))
    return f"{d.day} {THAI_MONTHS[d.month - 1]} {d.year + 543}"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
