"""Claude API calls: (1) research other sources with web search, (2) write the Thai article as JSON."""
from __future__ import annotations

import json
import os

import anthropic

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
FALLBACK_BETA = "server-side-fallback-2026-07-01"

_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


class Refused(Exception):
    pass


def _create(**kwargs):
    """Beta Messages call with server-side refusal fallbacks enabled."""
    resp = client().beta.messages.create(
        model=MODEL,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        **kwargs,
    )
    if resp.stop_reason == "refusal":
        raise Refused(getattr(resp.stop_details, "explanation", "refused"))
    return resp


RESEARCH_SYSTEM = """You are a cybersecurity news researcher. You are given a news story from The Hacker News.
Use web search to find 1 to 3 OTHER reliable sources about the same event that add useful detail, for example:
the vendor's security advisory, CISA/CERT alerts, NVD/CVE entries, the original researcher's blog, BleepingComputer,
SecurityWeek, The Record, or Thai sources such as ThaiCERT or NCSA (สกมช.) if relevant.

Then write concise research notes in English:
- Extra facts the other sources add (affected versions, CVE IDs, CVSS, patches, IOCs, timeline, who is behind it).
- Concrete recommended actions for organizations and ordinary users.
- Note any disagreement between sources.
End with a list of the sources you actually used, one per line as: SOURCE: <title> | <url>
Only list URLs that appeared in your search results. Do not invent facts."""


def research(title: str, url: str, article_text: str) -> tuple[str, list[dict]]:
    """Returns (notes, candidate_sources). candidate_sources are URLs seen in web search results."""
    messages = [{
        "role": "user",
        "content": f"Story title: {title}\nStory URL: {url}\n\nStory text:\n{article_text}",
    }]
    tools = [{
        "type": "web_search_20260209",
        "name": "web_search",
        "max_uses": 5,
        "blocked_domains": ["thehackernews.com"],
    }]
    seen: dict[str, str] = {}
    notes_parts: list[str] = []
    for _ in range(4):  # resume on pause_turn
        resp = _create(
            max_tokens=16000,
            system=RESEARCH_SYSTEM,
            tools=tools,
            messages=messages,
            output_config={"effort": "medium"},
        )
        for block in resp.content:
            if block.type == "web_search_tool_result" and isinstance(block.content, list):
                for r in block.content:
                    if getattr(r, "url", None):
                        seen.setdefault(r.url, getattr(r, "title", "") or r.url)
            elif block.type == "text":
                notes_parts.append(block.text)
        if resp.stop_reason != "pause_turn":
            break
        messages.append({"role": "assistant", "content": resp.content})
    candidates = [{"title": t, "url": u} for u, t in seen.items()]
    return "".join(notes_parts).strip(), candidates


ARTICLE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "title_th", "summary_th", "severity", "tags", "what_happened", "extra_details",
        "who_affected", "what_to_do", "glossary", "card_lines", "fb_caption", "hashtags",
        "reference_urls",
    ],
    "properties": {
        "title_th": {"type": "string", "description": "Thai headline, short and clear, max ~70 characters"},
        "summary_th": {"type": "string", "description": "2-3 sentence plain-Thai summary a non-expert understands"},
        "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
        "tags": {"type": "array", "items": {"type": "string"}, "description": "2-4 short Thai or English tags, e.g. Ransomware, ช่องโหว่"},
        "what_happened": {"type": "array", "items": {"type": "string"}, "description": "2-4 short Thai paragraphs"},
        "extra_details": {"type": "array", "items": {"type": "string"}, "description": "1-3 Thai paragraphs of extra detail from the other sources"},
        "who_affected": {"type": "array", "items": {"type": "string"}, "description": "Bullet points"},
        "what_to_do": {"type": "array", "items": {"type": "string"}, "description": "Practical action bullet points"},
        "glossary": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["term", "meaning"],
                "properties": {"term": {"type": "string"}, "meaning": {"type": "string"}},
            },
            "description": "2-4 technical terms used in the article, explained simply in Thai",
        },
        "card_lines": {
            "type": "array", "items": {"type": "string"},
            "description": "The headline for the image card split into 2-3 lines, each at most 22 characters, split at natural word boundaries",
        },
        "fb_caption": {"type": "string", "description": "Facebook caption in Thai: a hook line, then 2-3 short key points starting with an emoji, under 600 characters, no link and no hashtags"},
        "hashtags": {"type": "array", "items": {"type": "string"}, "description": "3-5 hashtags without the # sign"},
        "reference_urls": {"type": "array", "items": {"type": "string"}, "description": "URLs of the other sources you used, chosen ONLY from the provided candidate list"},
    },
}

WRITER_SYSTEM = """คุณคือบรรณาธิการข่าวไซเบอร์สำหรับคนไทยทั่วไป เขียนข่าวให้อ่านง่าย เข้าใจได้แม้ไม่ใช่สายไอที
กติกา:
- เขียนภาษาไทยที่เป็นธรรมชาติ ประโยคสั้น กระชับ ไม่ใช้ศัพท์ยากโดยไม่จำเป็น
- คำเทคนิค ชื่อผลิตภัณฑ์ ชื่อมัลแวร์ และหมายเลข CVE ให้คงเป็นภาษาอังกฤษ และอธิบายเป็นภาษาไทยเมื่อจำเป็น
- ใช้เฉพาะข้อเท็จจริงจากข่าวต้นฉบับและบันทึกการค้นคว้าที่ให้มาเท่านั้น ห้ามแต่งข้อมูลเพิ่ม
- คำแนะนำ "ควรทำอย่างไร" ต้องปฏิบัติได้จริง ทั้งสำหรับองค์กรและผู้ใช้ทั่วไป
- ไม่ลอกข้อความต้นฉบับ ให้เรียบเรียงใหม่ทั้งหมด
- reference_urls เลือกได้เฉพาะจากรายการ candidate sources ที่ให้มาเท่านั้น"""


def write_article(title: str, url: str, article_text: str, notes: str, candidates: list[dict]) -> dict:
    cand = "\n".join(f"- {c['title']} | {c['url']}" for c in candidates) or "(none)"
    content = (
        f"ข่าวต้นฉบับ (The Hacker News)\nหัวข้อ: {title}\nURL: {url}\n\n{article_text}\n\n"
        f"=== บันทึกการค้นคว้าจากแหล่งอื่น ===\n{notes or '(ไม่มี)'}\n\n"
        f"=== candidate sources ===\n{cand}"
    )
    resp = _create(
        max_tokens=16000,
        system=WRITER_SYSTEM,
        messages=[{"role": "user", "content": content}],
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": ARTICLE_SCHEMA}},
    )
    text = next(b.text for b in resp.content if b.type == "text")
    data = json.loads(text)
    allowed = {c["url"]: c["title"] for c in candidates}
    data["references"] = [
        {"title": allowed[u], "url": u} for u in data.pop("reference_urls", []) if u in allowed
    ][:4]
    return data
