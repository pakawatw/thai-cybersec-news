"""Original 1080x1080 news card with the Thai headline (no images copied from the source site)."""
from __future__ import annotations

import hashlib
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from common import ASSETS, BRAND_NAME, SEVERITY_TH

FONTS = ASSETS / "fonts"
W = H = 1080
PAD = 80

SEVERITY_COLOR = {
    "low": (46, 204, 113),
    "medium": (241, 196, 15),
    "high": (230, 126, 34),
    "critical": (231, 76, 60),
}

THAI_COMBINING = set(chr(c) for c in [0x0E31, *range(0x0E34, 0x0E3B), *range(0x0E47, 0x0E4F)])
THAI_LEADING = set("เแโใไ")


def _fonts(size: int, bold: bool):
    w = 700 if bold else 400
    return (
        ImageFont.truetype(str(FONTS / f"kanit-thai-{w}-normal.woff"), size),
        ImageFont.truetype(str(FONTS / f"kanit-latin-{w}-normal.woff"), size),
    )


def _runs(text: str):
    """Split text into (is_thai, chunk) runs so each uses a font that has its glyphs."""
    out: list[tuple[bool, str]] = []
    for ch in text:
        thai = "฀" <= ch <= "๿"
        if out and out[-1][0] == thai:
            out[-1] = (thai, out[-1][1] + ch)
        else:
            out.append((thai, ch))
    return out


def text_width(text: str, fonts) -> float:
    th, la = fonts
    return sum((th if t else la).getlength(s) for t, s in _runs(text))


def draw_text(draw: ImageDraw.ImageDraw, xy, text: str, fonts, fill):
    x, y = xy
    th, la = fonts
    for t, s in _runs(text):
        f = th if t else la
        draw.text((x, y), s, font=f, fill=fill)
        x += f.getlength(s)


def wrap(text: str, fonts, max_w: float) -> list[str]:
    """Wrap on spaces, falling back to safe Thai character boundaries."""
    lines: list[str] = []
    cur = ""
    for word in text.split(" "):
        trial = f"{cur} {word}".strip()
        if text_width(trial, fonts) <= max_w:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        cur = ""
        for ch in word:
            trial = cur + ch
            if text_width(trial, fonts) <= max_w or not cur or ch in THAI_COMBINING:
                cur = trial
                continue
            # don't leave a leading vowel stranded at the end of a line
            carry = ""
            while cur and cur[-1] in THAI_LEADING:
                carry = cur[-1] + carry
                cur = cur[:-1]
            lines.append(cur)
            cur = carry + ch
    if cur:
        lines.append(cur)
    return lines


def _background(img: Image.Image, seed: str, accent):
    d = ImageDraw.Draw(img)
    top, bottom = (10, 18, 40), (16, 42, 84)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    rnd = random.Random(int(hashlib.sha1(seed.encode()).hexdigest(), 16))
    # circuit-like grid of dots and lines, unique per story
    for _ in range(70):
        x, y = rnd.randrange(0, W, 40), rnd.randrange(0, H, 40)
        r = rnd.choice([2, 2, 3, 4])
        d.ellipse([x - r, y - r, x + r, y + r], fill=(60, 110, 170))
        if rnd.random() < 0.5:
            dx, dy = rnd.choice([(80, 0), (0, 80), (120, 0), (0, 120)])
            d.line([(x, y), (x + dx, y + dy)], fill=(40, 80, 130), width=2)
    # shield motif, top right
    cx, cy, s = W - 190, 210, 110
    shield = [(cx, cy - s), (cx + s, cy - s * 0.6), (cx + s * 0.9, cy + s * 0.4),
              (cx, cy + s * 1.1), (cx - s * 0.9, cy + s * 0.4), (cx - s, cy - s * 0.6)]
    d.polygon(shield, outline=accent, width=8)
    d.line([(cx - 40, cy + 5), (cx - 8, cy + 40), (cx + 50, cy - 35)], fill=accent, width=12)
    d.rectangle([0, 0, 18, H], fill=accent)


def make_card(story: dict, out: Path) -> Path:
    accent = SEVERITY_COLOR.get(story.get("severity"), (52, 152, 219))
    img = Image.new("RGB", (W, H))
    _background(img, story["slug"], accent)
    d = ImageDraw.Draw(img)

    small = _fonts(34, False)
    draw_text(d, (PAD, PAD), BRAND_NAME, _fonts(40, True), (255, 255, 255))

    # severity pill
    label = SEVERITY_TH.get(story.get("severity"), "ข่าวไซเบอร์")
    pf = _fonts(32, True)
    pw = text_width(label, pf)
    d.rounded_rectangle([PAD, PAD + 80, PAD + pw + 48, PAD + 140], radius=30, fill=accent)
    draw_text(d, (PAD + 24, PAD + 86), label, pf, (15, 15, 25))

    # headline: largest size that fits in at most 4 lines
    lines_src = story.get("card_lines") or [story["title_th"]]
    max_w = W - 2 * PAD
    # prefer keeping the given line breaks intact; otherwise allow wrapping up to 4 lines
    best = None
    for size in range(88, 46, -4):
        f = _fonts(size, True)
        lines = [ln for src in lines_src for ln in wrap(src.strip(), f, max_w)]
        if len(lines) == len(lines_src) and size >= 64:
            best = (size, f, lines)
            break
        if len(lines) <= 4 and best is None:
            best = (size, f, lines)
    size, f, lines = best or (size, f, lines)
    lines = lines[:4]
    line_h = int(size * 1.45)
    y = H - PAD - 150 - line_h * len(lines)
    for ln in lines:
        draw_text(d, (PAD, y), ln, f, (255, 255, 255))
        y += line_h

    # footer
    d.line([(PAD, H - PAD - 90), (W - PAD, H - PAD - 90)], fill=(80, 120, 170), width=2)
    tags = "  ·  ".join(story.get("tags", [])[:3])
    draw_text(d, (PAD, H - PAD - 60), tags, small, (170, 200, 235))
    cta = "อ่านต่อในลิงก์"
    draw_text(d, (W - PAD - text_width(cta, small), H - PAD - 60), cta, small, accent)

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", optimize=True)
    return out
