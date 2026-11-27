# Scheduled news run (instructions for Claude)

This file is the job description for the scheduled Claude task that runs every 6 hours.
GitHub Actions (`fetch.yml`) has already queued new stories from The Hacker News in `data/queue/*.json`
(each has `url`, `title`, `published`, `slug`, `article_text`). Your job is to write the Thai pages for them.

## Steps

1. `cd` into the repo and run `pip install -q -r requirements.txt`. Then refresh the queue yourself, because GitHub's hourly schedule is best-effort and sometimes doesn't fire:
   `gh workflow run fetch.yml -R pakawatw/thai-cybersec-news --ref main`, wait about 10 seconds, find the new run with
   `gh run list -R pakawatw/thai-cybersec-news --workflow fetch.yml --limit 1 --json databaseId --jq '.[0].databaseId'`,
   then `gh run watch <id> -R pakawatw/thai-cybersec-news --exit-status`. If `gh` fails, use the GitHub tools to run the `fetch.yml` workflow on `main` and wait for it to finish. If that fails too, carry on with whatever is already queued.
   Finally, run `git pull --rebase origin main`.
2. List `data/queue/*.json`. If there are none, stop: there is nothing new. Process at most 8 per run, oldest first.
3. For each queued story:
   1. Read its `article_text`. Do not try to fetch thehackernews.com, because the text is already there.
   2. Use **WebSearch** to find 1 to 3 **other** reliable sources about the same event that add detail. Good sources are the vendor advisory, CISA/CERT alerts, NVD/CVE, the original researcher's blog, BleepingComputer, SecurityWeek and The Record, plus ThaiCERT or NCSA (สกมช.) when relevant. Only use URLs that actually appeared in your search results, and never thehackernews.com. If you have a page-reading tool (WebFetch or a web-fetch agent), read the best 1 or 2 of them for extra details. If you don't, use only facts from the article text and search results, and don't guess.
   3. Write `data/stories/<slug>.json` in the format below.
4. Run `python scripts/news_writer.py finalize`. It checks each file, draws the image card, renders the site and removes the story from the queue. If it reports an error for a file, fix that file and run it again.
5. Commit and push:
   `git add -A data docs && git commit -m "News: <n> new stories" && git pull --rebase origin main && git push origin main`
   If the push fails because main moved, pull with rebase and push again. Pushing triggers the Facebook draft workflow.
6. Finish with a short summary listing the Thai titles written.

## Writing rules (Thai, for ordinary readers)
- Write natural, easy Thai with short sentences. The reader is a general Thai audience, not an IT expert.
- Keep product names, malware names, CVE IDs and technical terms in English, with a simple Thai explanation where needed.
- Use only facts from the article text and the other sources you found. Never invent numbers, versions, names or CVE IDs.
- Rewrite everything in your own words. Do not translate THN sentence by sentence.
- Make "what to do" practical for both organizations and ordinary users.

## `data/stories/<slug>.json` format
```json
{
  "title_th": "Thai headline, clear, at most ~70 characters",
  "summary_th": "2-3 sentence plain-Thai summary",
  "severity": "low | medium | high | critical",
  "tags": ["2-4 short tags, e.g. ช่องโหว่, Ransomware"],
  "what_happened": ["2-4 short Thai paragraphs"],
  "extra_details": ["1-3 Thai paragraphs with what the OTHER sources add"],
  "who_affected": ["bullet", "..."],
  "what_to_do": ["practical action", "..."],
  "glossary": [{"term": "Zero-day", "meaning": "simple Thai explanation"}],
  "card_lines": ["headline split into 2-3 lines", "each at most 22 characters", "split at word boundaries"],
  "fb_caption": "Thai Facebook caption: a hook line, then 2-3 short key points each starting with an emoji. Under 600 characters. No link and no hashtags, because those are added automatically.",
  "hashtags": ["3-5 hashtags without #, e.g. ข่าวไซเบอร์"],
  "references": [{"title": "page title", "url": "https://other-source/..."}]
}
```
`slug`, `source_url`, `source_title` and `published` are filled in by `finalize`, so you don't need to add them.
The Hacker News link is always listed first in the references on the page, so leave it out of `references`.
