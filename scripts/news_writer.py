"""Agent 1: check The Hacker News RSS, write a Thai page + image card for each NEW story.

Two ways to run it:

A. Claude subscription (default, no API key):
   python scripts/news_writer.py fetch      GitHub Actions: queue new stories in data/queue/
   (scheduled Claude task writes data/stories/<slug>.json for each queued story, see AGENT_RUN.md)
   python scripts/news_writer.py finalize   make image cards, render the site, clear the queue

B. Anthropic API key (ANTHROPIC_API_KEY set):
   python scripts/news_writer.py api        do everything in one go
   python scripts/news_writer.py api --dry-run
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

from common import DATA, DOCS, PROCESSED_FILE, STORIES, load_json, now_iso, save_json, slug_from_url
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


QUEUE = DATA / "queue"

REQUIRED = {
    "title_th": str, "summary_th": str, "severity": str, "tags": list, "what_happened": list,
    "extra_details": list, "who_affected": list, "what_to_do": list, "glossary": list,
    "card_lines": list, "fb_caption": str, "hashtags": list, "references": list,
}


def validate_story(s: dict) -> list[str]:
    errs = [f"missing or wrong type: {k}" for k, t in REQUIRED.items() if not isinstance(s.get(k), t)]
    if s.get("severity") not in ("low", "medium", "high", "critical"):
        errs.append("severity must be low|medium|high|critical")
    for g in s.get("glossary") or []:
        if not (isinstance(g, dict) and g.get("term") and g.get("meaning")):
            errs.append("glossary items need term and meaning")
    for r in s.get("references") or []:
        if not (isinstance(r, dict) and str(r.get("url", "")).startswith("http") and r.get("title")):
            errs.append("references items need title and http(s) url")
    if "thehackernews.com" in " ".join(r.get("url", "") for r in s.get("references") or [] if isinstance(r, dict)):
        errs.append("references must be OTHER sources (the THN source is added automatically)")
    return errs


def new_items(state: dict, items: list[dict]) -> list[dict]:
    seen = state["items"]
    if not seen and FIRST_RUN_COUNT >= 0:
        # First run: don't backfill the whole feed. Mark older stories as skipped.
        for it in items[:-FIRST_RUN_COUNT] if FIRST_RUN_COUNT else items:
            seen[it["url"]] = {"status": "skipped_backlog", "at": now_iso()}
    return [
        it for it in items
        if seen.get(it["url"], {}).get("status") not in ("done", "skipped_backlog", "queued")
        and seen.get(it["url"], {}).get("attempts", 0) < MAX_ATTEMPTS
    ]


def process(item: dict) -> dict:
    import llm

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


def cmd_fetch() -> int:
    state = load_json(PROCESSED_FILE, {"items": {}})
    items = fetch_feed()
    todo = new_items(state, items)
    print(f"Feed has {len(items)} stories; {len(todo)} new")
    for it in todo:
        slug = slug_from_url(it["url"])
        text = fetch_article_text(it["url"], it["summary"])
        save_json(QUEUE / f"{slug}.json", {**it, "slug": slug, "article_text": text, "queued": now_iso()})
        state["items"][it["url"]] = {"status": "queued", "slug": slug, "at": now_iso()}
        print(f"  queued {slug}")
    save_json(PROCESSED_FILE, state)
    return 0


def cmd_finalize() -> int:
    """After Claude wrote data/stories/<slug>.json for queued items: cards, site, clear queue."""
    state = load_json(PROCESSED_FILE, {"items": {}})
    bad = 0
    for q in sorted(QUEUE.glob("*.json")):
        item = load_json(q, {})
        sp = STORIES / f"{item['slug']}.json"
        if not sp.exists():
            print(f"  … not written yet: {item['slug']}")
            continue
        story = load_json(sp, {})
        errs = validate_story(story)
        if errs:
            bad += 1
            print(f"  ✗ {sp.name}: " + "; ".join(errs), file=sys.stderr)
            continue
        story.update(slug=item["slug"], source_url=item["url"], source_title=item["title"],
                     published=item["published"], created=story.get("created") or now_iso())
        save_json(sp, story)
        make_card(story, DOCS / "images" / f"{item['slug']}.png")
        state["items"][item["url"]] = {"status": "done", "slug": item["slug"], "at": now_iso()}
        q.unlink()
        print(f"  ✓ {item['slug']}: {story['title_th']}")
    save_json(PROCESSED_FILE, state)
    render_site()
    return 1 if bad else 0


def cmd_api(dry_run: bool) -> int:
    state = load_json(PROCESSED_FILE, {"items": {}})
    seen = state["items"]
    items = fetch_feed()
    todo = new_items(state, items)[:MAX_PER_RUN]
    print(f"Feed has {len(items)} stories; processing {len(todo)}")
    if dry_run:
        for it in todo:
            print(" -", it["title"], it["url"])
        return 0
    if todo and not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set. Add it under Settings → Secrets and variables → Actions.", file=sys.stderr)
        return 1
    import anthropic

    errors = 0
    for it in todo:
        rec = seen.setdefault(it["url"], {})
        rec["attempts"] = rec.get("attempts", 0) + 1
        try:
            story = process(it)
            seen[it["url"]] = {"status": "done", "slug": story["slug"], "at": now_iso()}
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
            rec["attempts"] -= 1  # not the story's fault; don't use up its retries
            save_json(PROCESSED_FILE, state)
            print(f"Anthropic API key problem: {e}", file=sys.stderr)
            return 1
        except Exception as e:  # keep going; retry next run
            errors += 1
            rec.update(status="failed", error=f"{type(e).__name__}: {e}"[:300], at=now_iso())
            print(f"  ✗ failed: {e}", file=sys.stderr)
        save_json(PROCESSED_FILE, state)  # save after each story so progress survives crashes
    render_site()
    print(f"Done. {len(todo) - errors} written, {errors} failed.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch")
    sub.add_parser("finalize")
    a = sub.add_parser("api")
    a.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.cmd == "fetch":
        return cmd_fetch()
    if args.cmd == "finalize":
        return cmd_finalize()
    return cmd_api(args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
