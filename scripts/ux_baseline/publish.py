#!/usr/bin/env python3
"""Publish the Phase-1 UX proposal: copy mockup PNGs to frontend/public/ux-proposal-assets/ (not /ux-proposal: a public dir of the page name makes the dev server 301) and build one PDF bundle
(README + IA + METRICS + BACKLOG + images). Run: python3 scripts/ux_baseline/publish.py"""
import asyncio
import html
import re
import shutil
from pathlib import Path

from playwright.async_api import async_playwright

UX, PUB = Path("/app/docs/ux"), Path("/app/frontend/public/ux-proposal-assets")
DOCS = ["README.md", "IA.md", "METRICS.md", "BACKLOG.md"]


def inline(s: str) -> str:
    s = html.escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    return re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', s)


def md(text: str) -> str:
    """Minimal Markdown → HTML: headings, tables, lists, code fences, paragraphs."""
    out, lines, i = [], text.splitlines(), 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append("<pre>" + html.escape("\n".join(lines[i + 1:j])) + "</pre>")
            i = j + 1
            continue
        if m := re.match(r"^(#{1,4}) (.*)", ln):
            out.append(f"<h{len(m[1])}>{inline(m[2])}</h{len(m[1])}>")
        elif ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                if not re.match(r"^\|[\s|:-]+\|$", lines[i]):
                    rows.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            head, *body = rows
            out.append("<table><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr>"
                       + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body) + "</table>")
            continue
        elif re.match(r"^\s*([-*]|\d+\.) ", ln):
            items = []
            while i < len(lines) and re.match(r"^\s*([-*]|\d+\.) ", lines[i]):
                items.append(re.sub(r"^\s*([-*]|\d+\.) ", "", lines[i]))
                i += 1
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>")
            continue
        elif ln.strip():
            out.append(f"<p>{inline(ln)}</p>")
        i += 1
    return "\n".join(out)


CSS = """body{font:11px/1.45 Inter,Arial,sans-serif;color:#1E293B;margin:0}h1{font-size:20px;color:#0f4f5f}h2{font-size:15px;color:#0f4f5f;margin-top:18px}h3{font-size:13px}
table{border-collapse:collapse;width:100%;margin:6px 0;page-break-inside:auto}td,th{border:1px solid #cbd5e1;padding:3px 5px;vertical-align:top;text-align:left}th{background:#f1f5f9}
code{background:#f1f5f9;padding:0 3px}pre{background:#f8fafc;border:1px solid #e2e8f0;padding:6px;white-space:pre-wrap;font-size:9px}.doc{page-break-before:always}
.banner{background:#F5A623;font-weight:700;text-align:center;padding:5px;letter-spacing:.1em}figure{page-break-inside:avoid;margin:10px 0}img{width:100%;border:1px solid #cbd5e1}figcaption{font-weight:600;margin-bottom:3px}"""


def bundle() -> str:
    parts = ['<div class="banner">PROPOSAL – NON-FUNCTIONAL MOCKUPS · SYNTHETIC DEMONSTRATION DATA</div>']
    for d in DOCS:
        parts.append(f'<div class="doc">{md((UX / d).read_text())}</div>')
    parts.append('<div class="doc"><h1>Mockups (non-functional)</h1>')
    for p in sorted((UX / "mockups/png").glob("*.png")):
        parts.append(f'<figure><figcaption>{p.stem}</figcaption><img src="{p.as_uri()}"></figure>')
    parts.append('</div><div class="doc"><h1>Before / after</h1>')
    for p in sorted((UX / "before_after").glob("*.png")):
        parts.append(f'<figure><figcaption>{p.stem}: current UI (left) vs proposal (right)</figcaption><img src="{p.as_uri()}"></figure>')
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{''.join(parts)}</div></body></html>"


async def pdf():
    tmp = UX / "data/_bundle.html"
    tmp.write_text(bundle())
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await b.new_page()
        await page.goto(tmp.as_uri(), wait_until="load")
        await page.pdf(path=str(PUB / "IronVision_UX_Proposal_Phase1.pdf"), format="Letter", landscape=True, print_background=True,
                       margin={"top": "0.4in", "bottom": "0.4in", "left": "0.4in", "right": "0.4in"})
        await b.close()
    tmp.unlink()


if __name__ == "__main__":
    for sub in ("mockups", "before_after"):
        (PUB / sub).mkdir(parents=True, exist_ok=True)
        src = UX / ("mockups/png" if sub == "mockups" else sub)
        for f in src.glob("*.png"):
            shutil.copy(f, PUB / sub / f.name)
    asyncio.run(pdf())
    print("published", PUB)
