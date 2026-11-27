"""Render story JSON files into the static site under docs/."""
from __future__ import annotations

import shutil
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape

from common import ASSETS, BRAND_NAME, DOCS, SEVERITY_TH, STORIES, TEMPLATES, load_json, site_url, thai_date

env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))
env.filters["domain"] = lambda u: urlparse(u).netloc.removeprefix("www.")


def all_stories() -> list[dict]:
    # only finalized stories (finalize adds slug/published after validation)
    stories = [s for s in (load_json(p, {}) for p in STORIES.glob("*.json")) if s.get("slug") and s.get("published")]
    return sorted(stories, key=lambda s: s.get("published", ""), reverse=True)


def render_article(s: dict) -> None:
    html = env.get_template("article.html").render(
        s=s, brand=BRAND_NAME, site=site_url(),
        sev_th=SEVERITY_TH.get(s["severity"], ""), date_th=thai_date(s["published"]),
    )
    out = DOCS / "news" / f"{s['slug']}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")


def render_site() -> None:
    DOCS.mkdir(exist_ok=True)
    (DOCS / ".nojekyll").touch()
    shutil.copy(ASSETS / "style.css", DOCS / "style.css")
    stories = all_stories()
    for s in stories:
        render_article(s)
    items = [dict(s, sev_th=SEVERITY_TH.get(s["severity"], ""), date_th=thai_date(s["published"])) for s in stories]
    (DOCS / "index.html").write_text(
        env.get_template("index.html").render(stories=items, brand=BRAND_NAME), encoding="utf-8"
    )


if __name__ == "__main__":
    render_site()
