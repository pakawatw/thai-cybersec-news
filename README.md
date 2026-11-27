# ข่าวไซเบอร์ง่ายๆ (Thai cybersecurity news pipeline)

This repo checks [The Hacker News](https://thehackernews.com/) for new stories and, for each new one:

1. **Agent 1 – News writer** (`scripts/news_writer.py` + a scheduled Claude task, see `AGENT_RUN.md`)
   - every hour, GitHub Actions reads the RSS feed and queues stories it hasn't done yet (`data/queue/`, `data/processed.json`)
   - every 6 hours, a scheduled Claude task (runs on your Claude plan, **no API key needed**) writes the queued stories
   - searches the web for 1–3 other sources (vendor advisories, CISA, NVD, researcher blogs…)
   - writes an easy Thai page: summary, what happened, extra details, who is affected, what to do, glossary, and **references at the bottom**
   - draws an original 1080×1080 image card with the Thai headline (no images copied from THN)
   - publishes everything to GitHub Pages (`docs/`)
2. **Agent 2 – Facebook poster** (`scripts/fb_poster.py`)
   - writes a short Thai caption with key points, a link to the page and hashtags
   - **draft mode (default):** opens a GitHub Issue per story with the image and caption. Edit the caption in the issue if you want, then add the label **`approved`** to post it. Close the issue to skip.
   - **auto mode:** posts straight to the Facebook Page

```
[hourly, GitHub]   RSS ─► news_writer.py fetch ─► data/queue/*.json
[6-hourly, Claude] queue ─► web search + Thai writing ─► data/stories/*.json ─► news_writer.py finalize
                          ─► docs/news/*.html + docs/images/*.png ─► GitHub Pages
[on push, GitHub]  fb_poster.py ─► GitHub Issue (draft) ─[label: approved]─► Facebook Page
```

## One-time setup

### 1. Turn on GitHub Pages
Repo **Settings → Pages → Build and deployment → Source: Deploy from a branch → Branch: `main`, folder `/docs` → Save**.
The site will be at `https://pakawatw.github.io/thai-cybersec-news/`.

### 2. Article writing (nothing to do)
The Thai articles are written by a scheduled Claude task on your Claude account, so no API key is needed.
*Alternative:* if you ever prefer an API key, add the secret `ANTHROPIC_API_KEY` and use the
"Optional: write news with an API key" workflow.

### 3. Connect the Facebook Page
You need a **Page access token** that never expires and has permission to post.

1. Go to <https://developers.facebook.com/apps> → **Create app** → choose a *Business* type app (any name).
2. Open **Graph API Explorer** (<https://developers.facebook.com/tools/explorer/>), pick your app, and under *User or Page* choose **Get User Access Token** with these permissions:
   `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`. Click **Generate Access Token** and log in.
3. Turn it into a long-lived token: open the **Access Token Debugger** (<https://developers.facebook.com/tools/debug/accesstoken/>), paste the token, click **Debug**, then **Extend Access Token**.
4. Back in Graph API Explorer, paste the long-lived user token and run `GET me/accounts`. Find your Page in the result. Copy its `id` and its `access_token` (this Page token does not expire when it comes from a long-lived user token).
5. In the repo add two **secrets**: `FB_PAGE_ID` = the Page id, `FB_PAGE_TOKEN` = the Page access token.

> Never paste tokens into chat, issues, or code. Only into GitHub secrets.

Your own account is an admin of the app, so posting works while the app stays in Development mode. You don't need App Review to post to a Page you manage.

### 4. Optional settings (Settings → Secrets and variables → Actions → **Variables**)
| Variable | Default | Meaning |
|---|---|---|
| `FB_MODE` | `draft` | `draft` = approve each post in an Issue, `auto` = post directly |
| `BRAND_NAME` | `ข่าวไซเบอร์ง่ายๆ` | Name shown on the site and image cards |
| `SITE_URL` | GitHub Pages URL | Set if you use a custom domain |

### 5. Run it
**Actions → Fetch new stories → Run workflow** queues stories right away (it also runs every hour by itself).
The first run queues only the 3 newest stories (it doesn't backfill the whole feed).

## Running locally
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
python scripts/news_writer.py fetch       # queue new stories
python scripts/news_writer.py finalize    # after writing data/stories/<slug>.json: cards + site
python scripts/news_writer.py api         # all-in-one, needs ANTHROPIC_API_KEY
python scripts/render.py                  # re-render the site after editing templates
```

## Cost
GitHub Actions and Pages are free for public repos. The scheduled Claude task uses your Claude plan's usage; The Hacker News publishes about 5–10 stories a day and each run writes at most 8.

## Files
- `scripts/` – pipeline code · `templates/` + `assets/style.css` – page design · `assets/fonts/` – Kanit font (SIL OFL)
- `data/queue/` – stories waiting to be written · `data/processed.json` – stories already seen · `data/stories/` – generated story content · `data/fb_posts.json` – Facebook status
- `docs/` – the published website
