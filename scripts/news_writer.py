"""Agent 1: check The Hacker News RSS, write a Thai page + image card for each NEW story.

Run:  python scripts/news_writer.py            (normal run)
      python scripts/news_writer.py --dry-run  (list new stories, write nothing)
"""
from __future__ import annotations

import argparse
import calendar
import os
import sys
from datetime import datetime, timezone

import feedparser
import requests
from bs4 import BeautifulSoup

import llm
from common import DOCS, PROCESSED_FILE, STORIES, load_json, now_iso, save_json, slug_from_url
from image_card import make_card
from render import render_site

FEED_URL = os.environ.get("FEED_URL", "https://feeds.feedburner.com/TheHackersNews")
MAX_PER_RUN = int(os.environ.get("MAX_PER_RUN", "8"))
FIRST_RUN_COUNT = int(os.environ.get("FIRST_RUN_COUNT", "3"))
MAX_ATTEMPTS = 3
UA = {"User-Agent": "Mozilla/5.0 (compatible; ThaiCyberNewsBot/1.0)"}


def fetch_feed() -> list[dict]:
    resp = requests.get(FEED_URL, headers=UA, timeout=30)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    items = []
    for e in feed.entries:
        t = e.get("published_parsed") or e.get("updated_parsed")
        published = (
            datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc).isoformat() if t else now_iso()
        )
        items.append({
            "url": e.link.split("?")[0],
            "title": e.title,
            "summary": BeautifulSoup(e.get("summary", ""), "html.parser").get_text(" ", strip=True),
            "published": published,
        })
    return sorted(items, key=lambda x: x["published"])  # oldest first


def fetch_article_text(url: str, fallback: str) -> str:
    try:
        r = requests.get(url, headers=UA, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        body = soup.select_one("div.articlebody") or soup.select_one("article")
        if body:
            for bad in body.select("script, style, .dog_two, .stophere, .check_two, .cf.note-b"):
                bad.decompose()
            parts = [el.get_text(" ", strip=True) for el in body.find_all(["p", "h2", "h3", "li"])]
            text = "\n".join(p for p in parts if p)
            if len(text) > 300:
                return text
    except requests.RequestException as e:
        print(f"  ! could not fetch article page ({e}); using RSS summary", file=sys.stderr)
    return fallback


def process(item: dict) -> dict:
    slug = slug_from_url(item["url"])
    print(f"→ {item['title']}  [{slug}]")
    text = fetch_article_text(item["url"], item["summary"])
    notes, candidates = llm.research(item["title"], item["url"], text)
    print(f"  research: {len(candidates)} candidate sources")
    art = llm.write_article(item["title"], item["url"], text, notes, candidates)
    story = {
        "slug": slug,
        "source_url": item["url"],
        "source_title": item["title"],
        "published": item["published"],
        "created": now_iso(),
        **art,
    }
    make_card(story, DOCS / "images" / f"{slug}.png")
    save_json(STORIES / f"{slug}.json", story)
    print(f"  ✓ {story['title_th']}  ({len(story['references'])} extra references)")
    return story


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    state = load_json(PROCESSED_FILE, {"items": {}})
    seen = state["items"]
    items = fetch_feed()
    print(f"Feed has {len(items)} stories")

    if not seen and FIRST_RUN_COUNT >= 0:
        # First run: don't backfill the whole feed. Mark older stories as skipped.
        for it in items[:-FIRST_RUN_COUNT] if FIRST_RUN_COUNT else items:
            seen[it["url"]] = {"status": "skipped_backlog", "at": now_iso()}

    todo = [
        it for it in items
        if seen.get(it["url"], {}).get("status") not in ("done", "skipped_backlog")
        and seen.get(it["url"], {}).get("attempts", 0) < MAX_ATTEMPTS
    ][:MAX_PER_RUN]
    print(f"New stories to process: {len(todo)}")
    if args.dry_run:
        for it in todo:
            print(" -", it["title"], it["url"])
        return 0
    if todo and not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set. Add it under Settings → Secrets and variables → Actions.", file=sys.stderr)
        return 1

    errors = 0
    for it in todo:
        rec = seen.setdefault(it["url"], {})
        rec["attempts"] = rec.get("attempts", 0) + 1
        try:
            story = process(it)
            seen[it["url"]] = {"status": "done", "slug": story["slug"], "at": now_iso()}
        except (llm.anthropic.AuthenticationError, llm.anthropic.PermissionDeniedError) as e:
            rec["attempts"] -= 1  # not the story's fault; don't use up its retries
            save_json(PROCESSED_FILE, state)
            print(f"Anthropic API key problem: {e}", file=sys.stderr)
            return 1
        except Exception as e:  # keep going; retry next run
            errors += 1
            rec.update(status="failed", error=f"{type(e).__name__}: {e}"[:300], at=now_iso())
            print(f"  ✗ failed: {e}", file=sys.stderr)
        save_json(PROCESSED_FILE, state)  # save after each story so progress survives crashes

    save_json(PROCESSED_FILE, state)
    render_site()
    print(f"Done. {len(todo) - errors} written, {errors} failed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
