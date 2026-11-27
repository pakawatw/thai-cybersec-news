"""Agent 2: post stories to a Facebook Page (photo + Thai caption + link).

Modes (FB_MODE env var / GitHub variable):
  draft (default) – for each new story, open a GitHub Issue with the image and caption.
                    Edit the caption in the issue if you like, then add the label `approved` to post it.
                    Close the issue to skip the story.
  auto            – post new stories straight to Facebook.

Commands:
  python scripts/fb_poster.py queue            handle all stories not yet queued/posted
  python scripts/fb_poster.py approve --issue N  post the story from an approved issue
"""
from __future__ import annotations

import argparse
import os
import re
import sys

import requests

from common import DOCS, FB_POSTS_FILE, STORIES, article_url, load_json, now_iso, save_json

GRAPH = f"https://graph.facebook.com/{os.environ.get('FB_GRAPH_VERSION', 'v23.0')}"
GH_API = "https://api.github.com"
APPROVE_LABEL = "approved"
DRAFT_LABEL = "fb-draft"


# ---------- caption ----------

def build_caption(story: dict) -> str:
    tags = " ".join("#" + h.lstrip("#").replace(" ", "") for h in story.get("hashtags", []))
    return f"{story['fb_caption'].strip()}\n\n👉 อ่านต่อ: {article_url(story['slug'])}\n\n{tags}".strip()


# ---------- Facebook ----------

def fb_post_photo(story: dict, caption: str) -> str:
    page_id = os.environ["FB_PAGE_ID"]
    token = os.environ["FB_PAGE_TOKEN"]
    img = DOCS / "images" / f"{story['slug']}.png"
    with img.open("rb") as fh:
        r = requests.post(
            f"{GRAPH}/{page_id}/photos",
            data={"message": caption, "published": "true", "access_token": token},
            files={"source": (img.name, fh, "image/png")},
            timeout=120,
        )
    if r.status_code != 200:
        # never print the token; Graph errors don't echo it
        raise RuntimeError(f"Facebook API error {r.status_code}: {r.text[:500]}")
    data = r.json()
    return data.get("post_id") or data["id"]


def fb_configured() -> bool:
    return bool(os.environ.get("FB_PAGE_ID") and os.environ.get("FB_PAGE_TOKEN"))


# ---------- GitHub issues (draft & approve) ----------

def gh(method: str, path: str, **kw):
    r = requests.request(
        method, f"{GH_API}/repos/{os.environ['GITHUB_REPOSITORY']}{path}",
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json"},
        timeout=30, **kw,
    )
    if r.status_code >= 400 and not (method == "POST" and path == "/labels" and r.status_code == 422):
        raise RuntimeError(f"GitHub API {method} {path}: {r.status_code} {r.text[:300]}")
    return r.json() if r.content else {}


def ensure_labels():
    gh("POST", "/labels", json={"name": APPROVE_LABEL, "color": "2ecc71", "description": "Post this to Facebook"})
    gh("POST", "/labels", json={"name": DRAFT_LABEL, "color": "1a5fb4", "description": "Facebook post draft"})


def issue_body(story: dict, caption: str) -> str:
    repo = os.environ["GITHUB_REPOSITORY"]
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    img = f"https://raw.githubusercontent.com/{repo}/{branch}/docs/images/{story['slug']}.png"
    return f"""<!-- slug: {story['slug']} -->
**Article:** {article_url(story['slug'])}
**Source:** {story['source_url']}

<img src="{img}" width="420">

### Caption (edit this issue to change it before approving)
<!-- caption-start -->
{caption}
<!-- caption-end -->

---
➡️ To post: add the label **`{APPROVE_LABEL}`**.  ➡️ To skip: close this issue.
"""


def create_draft_issue(story: dict) -> int:
    issue = gh("POST", "/issues", json={
        "title": f"FB draft: {story['title_th']}",
        "body": issue_body(story, build_caption(story)),
        "labels": [DRAFT_LABEL],
    })
    return issue["number"]


# ---------- commands ----------

def cmd_queue() -> int:
    mode = os.environ.get("FB_MODE", "draft").strip().lower() or "draft"
    posts = load_json(FB_POSTS_FILE, {})
    stories = sorted((load_json(p, {}) for p in STORIES.glob("*.json")), key=lambda s: s["published"])
    new = [s for s in stories if s["slug"] not in posts]
    print(f"FB mode: {mode}. Stories not yet handled: {len(new)}")
    if mode == "auto" and not fb_configured():
        print("FB_PAGE_ID / FB_PAGE_TOKEN not set – skipping Facebook posting this run.")
        return 0
    if mode != "auto" and new:
        ensure_labels()
    failed = 0
    for s in new:
        try:
            if mode == "auto":
                pid = fb_post_photo(s, build_caption(s))
                posts[s["slug"]] = {"status": "posted", "post_id": pid, "at": now_iso()}
                print(f"  ✓ posted {s['slug']} → {pid}")
            else:
                num = create_draft_issue(s)
                posts[s["slug"]] = {"status": "awaiting_approval", "issue": num, "at": now_iso()}
                print(f"  ✓ draft issue #{num} for {s['slug']}")
        except Exception as e:
            failed += 1
            print(f"  ✗ {s['slug']}: {e}", file=sys.stderr)
        save_json(FB_POSTS_FILE, posts)
    return 1 if failed and failed == len(new) else 0


def cmd_approve(issue_no: int) -> int:
    issue = gh("GET", f"/issues/{issue_no}")
    body = issue.get("body") or ""
    m = re.search(r"<!-- slug: ([a-z0-9-]+) -->", body)
    if not m:
        print("Not a Facebook draft issue; nothing to do.")
        return 0
    slug = m.group(1)
    posts = load_json(FB_POSTS_FILE, {})
    if posts.get(slug, {}).get("status") == "posted":
        print("Already posted.")
        return 0
    cm = re.search(r"<!-- caption-start -->\s*(.*?)\s*<!-- caption-end -->", body, re.S)
    story = load_json(STORIES / f"{slug}.json", None)
    if story is None:
        raise SystemExit(f"Story {slug} not found")
    caption = cm.group(1).strip() if cm else build_caption(story)
    if not fb_configured():
        gh("POST", f"/issues/{issue_no}/comments", json={
            "body": "⚠️ Facebook secrets `FB_PAGE_ID` / `FB_PAGE_TOKEN` are not set yet, so nothing was posted. "
                    "Add them, then remove and re-add the `approved` label."})
        return 1
    try:
        pid = fb_post_photo(story, caption)
    except Exception as e:
        gh("POST", f"/issues/{issue_no}/comments", json={"body": f"❌ Posting failed: {e}"})
        raise
    posts[slug] = {"status": "posted", "post_id": pid, "issue": issue_no, "at": now_iso()}
    save_json(FB_POSTS_FILE, posts)
    gh("POST", f"/issues/{issue_no}/comments", json={"body": f"✅ Posted to Facebook: https://www.facebook.com/{pid}"})
    gh("PATCH", f"/issues/{issue_no}", json={"state": "closed", "state_reason": "completed"})
    print(f"Posted {slug} → {pid}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("queue")
    a = sub.add_parser("approve")
    a.add_argument("--issue", type=int, required=True)
    args = ap.parse_args()
    return cmd_queue() if args.cmd == "queue" else cmd_approve(args.issue)


if __name__ == "__main__":
    sys.exit(main())
