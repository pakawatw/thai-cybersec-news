# ข่าวไซเบอร์ง่ายๆ (Thai cybersecurity news pipeline)

Every 6 hours this repo checks [The Hacker News](https://thehackernews.com/) for new stories and, for each new one:

1. **Agent 1 – News writer** (`scripts/news_writer.py`)
   - reads the RSS feed and skips stories it has already done (`data/processed.json`)
   - searches the web for 1–3 other sources (vendor advisories, CISA, NVD, researcher blogs…)
   - writes an easy Thai page: summary, what happened, extra details, who is affected, what to do, glossary, and **references at the bottom**
   - draws an original 1080×1080 image card with the Thai headline (no images copied from THN)
   - publishes everything to GitHub Pages (`docs/`)
2. **Agent 2 – Facebook poster** (`scripts/fb_poster.py`)
   - writes a short Thai caption with key points, a link to the page and hashtags
   - **draft mode (default):** opens a GitHub Issue per story with the image and caption. Edit the caption in the issue if you want, then add the label **`approved`** to post it. Close the issue to skip.
   - **auto mode:** posts straight to the Facebook Page

```
RSS ─► news_writer.py ─► data/stories/*.json ─► docs/news/*.html + docs/images/*.png ─► GitHub Pages
                                     │
                                     └─► fb_poster.py ─► GitHub Issue (draft) ─[label: approved]─► Facebook Page
```

## One-time setup

### 1. Turn on GitHub Pages
Repo **Settings → Pages → Build and deployment → Source: Deploy from a branch → Branch: `main`, folder `/docs` → Save**.
The site will be at `https://pakawatw.github.io/thai-cybersec-news/`.

### 2. Add the Anthropic API key
Create a key at <https://console.anthropic.com/settings/keys>, then in the repo go to
**Settings → Secrets and variables → Actions → New repository secret**: name `ANTHROPIC_API_KEY`.

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
**Actions → News every 6 hours → Run workflow.** The first run writes only the 3 newest stories (it doesn't backfill the whole feed). After that it runs at 07:17, 13:17, 19:17 and 01:17 Thai time.

## Running locally
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
python scripts/news_writer.py --dry-run   # list new stories only
python scripts/news_writer.py             # write pages
python scripts/render.py                  # re-render the site after editing templates
```

## Cost
Each story uses two Claude calls (research with web search, then writing). The Hacker News publishes about 5–10 stories a day. Set `MAX_PER_RUN` in the workflow to cap how many are written per run (default 8).

## Files
- `scripts/` – pipeline code · `templates/` + `assets/style.css` – page design · `assets/fonts/` – Kanit font (SIL OFL)
- `data/processed.json` – stories already seen · `data/stories/` – generated story content · `data/fb_posts.json` – Facebook status
- `docs/` – the published website
