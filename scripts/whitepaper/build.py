#!/usr/bin/env python3
"""Builds the IronVision AI whitepaper (PDF via headless Chromium, DOCX via python-docx).
Usage: python3 scripts/whitepaper/build.py [--openapi URL]   → backend/app/static/whitepaper/IronVision_AI_Whitepaper.{pdf,docx}"""
import html
import io
import json
import re
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright
from pypdf import PdfReader

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from blocks import NOTE_LABEL, PB, H1, P, TABLE  # noqa: E402
from content_a import PART_A  # noqa: E402
from content_b import PART_B  # noqa: E402

ROOT = HERE.parent.parent
OUT = ROOT / "backend/app/static/whitepaper"
WORK = Path("/tmp/whitepaper_build")
BRAND = ROOT / "frontend/src/assets/brand"
FONTS = ROOT / "frontend/public/fonts"
TITLE = "IronVision AI"
SUBTITLE = "Human-approved AI for the NIST Risk Management Framework"
VERSION = "Version 1.1 · October 2026"
NOTE_COLORS = {"mocked": ("#FFF4E5", "#B45309"), "human": ("#FDECEC", "#B42318"), "sme": ("#F1ECFB", "#5B3FA6"),
               "info": ("#E8F6F9", "#15697F"), "never": ("#FDECEC", "#B42318")}


def api_appendix(url: str) -> list:
    spec = json.load(urllib.request.urlopen(url, timeout=30))
    groups = defaultdict(list)
    for path, ops in spec["paths"].items():
        for m in ops:
            if m in ("get", "post", "put", "patch", "delete"):
                seg = path.removeprefix("/api/v1/").split("/")[0] or "root"
                groups[seg].append(f"{m.upper()} {path.removeprefix('/api/v1')}")
    total = sum(len(v) for v in groups.values())
    rows = [[g, str(len(v)), "; ".join(sorted(v)[:4]) + (" …" if len(v) > 4 else "")] for g, v in sorted(groups.items())]
    return [PB, H1("A", "API endpoint summary (appendix)"),
            P(f"Generated from the live OpenAPI specification (/api/openapi.json): **{len(spec['paths'])} paths, {total} operations**, grouped "
              "by the first path segment under /api/v1. Every mutating operation requires a permission (see section 11); only sign-in, demo login, "
              "refresh, logout, sign-up, health and the public whitepaper downloads are unauthenticated."),
            TABLE(["Group", "Ops", "Examples"], rows, [16, 7, 77])]


def render_diagram(page) -> Path:
    page.set_viewport_size({"width": 1400, "height": 860})
    page.goto((HERE / "diagram.html").as_uri())
    out = WORK / "architecture.png"
    page.locator("#d").screenshot(path=str(out))
    return out


def prep_image(src: str, diagram: Path) -> Path:
    if src == "__DIAGRAM__":
        return diagram
    p = Path(src)
    out = WORK / (p.parent.name + "_" + p.stem + ".jpg")
    im = Image.open(p).convert("RGB")
    if im.width > 1600:
        im = im.resize((1600, int(im.height * 1600 / im.width)), Image.LANCZOS)
    im.save(out, "JPEG", quality=82, optimize=True)
    return out


INLINE = re.compile(r"(\*\*.+?\*\*|`.+?`)")


def inline_html(text: str) -> str:
    out = []
    for part in INLINE.split(text):
        if part.startswith("**") and part.endswith("**"):
            out.append(f"<b>{html.escape(part[2:-2])}</b>")
        elif part.startswith("`") and part.endswith("`"):
            out.append(f"<code>{html.escape(part[1:-1])}</code>")
        else:
            out.append(html.escape(part))
    return "".join(out)


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


CSS = """
@font-face{font-family:Inter;src:url('%(f)s/Inter-400.woff2');font-weight:400}
@font-face{font-family:Inter;src:url('%(f)s/Inter-600.woff2');font-weight:600}
@font-face{font-family:Inter;src:url('%(f)s/Inter-700.woff2');font-weight:700}
@font-face{font-family:Jakarta;src:url('%(f)s/PlusJakartaSans-600.woff2');font-weight:600}
@font-face{font-family:Jakarta;src:url('%(f)s/PlusJakartaSans-700.woff2');font-weight:700}
@page{size:A4;margin:20mm 17mm 20mm 17mm}
body{margin:0;font-family:Inter,Arial,sans-serif;font-size:10.2pt;line-height:1.5;color:#1F2D33}
h1,h2,h3{font-family:Jakarta,Inter,sans-serif;color:#0A3540;break-after:avoid}
h1{font-size:21pt;margin:0 0 10pt;padding-bottom:6pt;border-bottom:3px solid #2597B2}
h1 .n{color:#2597B2;margin-right:8pt}
h2{font-size:13.5pt;margin:16pt 0 6pt;color:#0F4F5F}
h3{font-size:11.5pt;margin:12pt 0 4pt;color:#15697F}
p{margin:0 0 7pt}
ul,ol{margin:0 0 8pt 0;padding-left:16pt} li{margin:0 0 3pt}
code{font-family:'DejaVu Sans Mono',monospace;font-size:8.6pt;background:#EEF5F7;padding:0 2pt;border-radius:2pt}
table{border-collapse:collapse;width:100%;margin:6pt 0 11pt;font-size:8.6pt;break-inside:auto}
th{background:#15697F;color:#fff;text-align:left;padding:4pt 5pt;font-family:Jakarta,Inter,sans-serif;font-weight:700}
td{border-bottom:1px solid #D5E6EB;padding:3.5pt 5pt;vertical-align:top}
tr{break-inside:avoid} tr:nth-child(even) td{background:#F5FAFB}
.note{border-left:4px solid;padding:6pt 9pt;margin:6pt 0 10pt;border-radius:3pt;break-inside:avoid;font-size:9.4pt}
.note b.l{display:block;font-size:7.8pt;letter-spacing:.08em;margin-bottom:2pt}
figure{margin:8pt 0 12pt;text-align:center;break-inside:avoid}
figure img{max-width:100%;border:1px solid #D5E6EB;border-radius:4pt}
figcaption{font-size:8.4pt;color:#4B6470;margin-top:3pt}
.screen{border:1px solid #CFE3E9;border-radius:6pt;padding:7pt 10pt;margin:0 0 9pt;break-inside:avoid;background:#FBFDFE}
.screen h3{margin:0 0 4pt}
.screen dl{display:grid;grid-template-columns:72pt 1fr;gap:2pt 8pt;margin:0;font-size:9.1pt}
.screen dt{color:#15697F;font-weight:700} .screen dd{margin:0}
.pb{break-after:page}
.cover{height:236mm;display:flex;flex-direction:column;justify-content:space-between;break-after:page}
.cover .band{background:linear-gradient(135deg,#2597B2,#0F4F5F);color:#fff;border-radius:10pt;padding:28pt 26pt}
.cover h1{color:#fff;border:0;font-size:34pt;margin:0}
.cover .sub{font-size:15pt;margin-top:8pt;color:#E8F6F9}
.cover .meta{font-size:10pt;color:#4B6470}
.toc h1{margin-bottom:12pt} .toc a{color:#1F2D33;text-decoration:none}
.toc .l1{display:flex;font-weight:700;margin:6pt 0 2pt;font-family:Jakarta,Inter,sans-serif;color:#0A3540}
.toc .l2{display:flex;margin:1pt 0 1pt 18pt;font-size:9.3pt}
.toc .dots{flex:1;border-bottom:1px dotted #9CC9D5;margin:0 4pt 3pt}
"""


def html_doc(blocks, img_map, toc_pages) -> str:
    out = [f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS.replace('%(f)s', FONTS.as_uri())}</style></head><body>"]
    logo = (BRAND / "logo-lockup-576.png").as_uri()
    out.append(f"""<section class='cover'><div><img src='{logo}' style='width:150pt'></div>
<div class='band'><h1>{TITLE}</h1><div class='sub'>{SUBTITLE}</div>
<div style='margin-top:18pt;font-size:11pt'>Whitepaper · formerly AegisRMF</div></div>
<div class='meta'><b>{VERSION}</b><br>Derived from the code base, migrations, API specification and project reports.<br>
Labels used: <b>MOCKED</b> (simulated capability) · <b>REQUIRES HUMAN VERIFICATION</b> · <b>SME REVIEW REQUIRED</b>.<br>
Demonstration content is synthetic. IronVision AI is not FedRAMP-authorized and holds no ATO.</div></section>""")
    out.append("<section class='toc pb'><h1>Contents</h1>")
    for b in blocks:
        if b[0] in ("h1", "h2"):
            title = f"{b[1]}  {b[2]}" if b[0] == "h1" else b[1]
            key = slug(title)
            cls = "l1" if b[0] == "h1" else "l2"
            out.append(f"<div class='{cls}'><a href='#{key}'>{html.escape(title)}</a><span class='dots'></span><span>{toc_pages.get(key, '')}</span></div>")
    out.append("</section>")
    for b in blocks:
        k = b[0]
        if k == "h1":
            out.append(f"<h1 id='{slug(b[1] + '  ' + b[2])}'><span class='n'>{b[1]}</span>{html.escape(b[2])}</h1>")
        elif k == "h2":
            out.append(f"<h2 id='{slug(b[1])}'>{html.escape(b[1])}</h2>")
        elif k == "h3":
            out.append(f"<h3>{html.escape(b[1])}</h3>")
        elif k == "p":
            out.append(f"<p>{inline_html(b[1])}</p>")
        elif k in ("ul", "ol"):
            out.append(f"<{k}>" + "".join(f"<li>{inline_html(i)}</li>" for i in b[1]) + f"</{k}>")
        elif k == "table":
            _, head, rows, widths = b
            cols = "".join(f"<col style='width:{w}%'>" for w in widths) if widths else ""
            out.append(f"<table><colgroup>{cols}</colgroup><thead><tr>" + "".join(f"<th>{html.escape(h)}</th>" for h in head) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{inline_html(c)}</td>" for c in r) + "</tr>" for r in rows) + "</tbody></table>")
        elif k == "img":
            out.append(f"<figure><img src='{img_map[b[1]].as_uri()}' style='width:{b[3]}%'><figcaption>Figure: {html.escape(b[2])}</figcaption></figure>")
        elif k == "note":
            bg, fg = NOTE_COLORS[b[1]]
            out.append(f"<div class='note' style='background:{bg};border-color:{fg}'><b class='l' style='color:{fg}'>{NOTE_LABEL[b[1]]}</b>{inline_html(b[2])}</div>")
        elif k == "screen":
            _, name, purpose, users, actions, outputs, guard = b
            out.append(f"<div class='screen'><h3>{html.escape(name)}</h3><dl>" + "".join(
                f"<dt>{lbl}</dt><dd>{inline_html(v)}</dd>" for lbl, v in
                (("Purpose", purpose), ("Used by", users), ("Key actions", actions), ("Outputs", outputs), ("Guardrails", guard))) + "</dl></div>")
        elif k == "pb":
            out.append("<div class='pb'></div>")
    out.append("</body></html>")
    return "".join(out)


FOOTER = ("<div style='font-family:Arial;font-size:7.5pt;color:#6B8590;width:100%;padding:0 17mm;display:flex;justify-content:space-between'>"
          "<span>IronVision AI – Whitepaper · Version 1.0 · October 2026</span><span>Page <span class='pageNumber'></span> of "
          "<span class='totalPages'></span></span></div>")


def render_pdf(page, doc_html: str, out: Path) -> None:
    src = WORK / "whitepaper.html"
    src.write_text(doc_html)
    page.goto(src.as_uri())
    page.wait_for_load_state("networkidle")
    page.pdf(path=str(out), format="A4", print_background=True, display_header_footer=True, header_template="<div></div>",
             footer_template=FOOTER, margin={"top": "18mm", "bottom": "18mm", "left": "17mm", "right": "17mm"})


def toc_pages(pdf: Path, blocks) -> dict:
    texts = [re.sub(r"\s+", " ", (pg.extract_text() or "")) for pg in PdfReader(str(pdf)).pages]
    found, start = {}, 2
    for b in blocks:
        if b[0] not in ("h1", "h2"):
            continue
        title = f"{b[1]} {b[2]}" if b[0] == "h1" else b[1]
        probe = re.sub(r"\s+", " ", (b[2] if b[0] == "h1" else b[1]))[:40]
        for i in range(start, len(texts)):
            if probe in texts[i]:
                found[slug(f"{b[1]}  {b[2]}" if b[0] == "h1" else title)] = i + 1
                start = i
                break
    return found


# ---------- DOCX ----------
def build_docx(blocks, img_map, out: Path) -> None:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    teal, dark = RGBColor(0x15, 0x69, 0x7F), RGBColor(0x0A, 0x35, 0x40)
    d = Document()
    sec = d.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    for m in ("left_margin", "right_margin"):
        setattr(sec, m, Cm(1.9))
    sec.top_margin = sec.bottom_margin = Cm(2)
    st = d.styles["Normal"]
    st.font.name, st.font.size = "Calibri", Pt(10.5)
    for name, size, color in (("Heading 1", 20, dark), ("Heading 2", 14, teal), ("Heading 3", 12, teal)):
        s = d.styles[name]
        s.font.name, s.font.size, s.font.color.rgb, s.font.bold = "Calibri", Pt(size), color, True

    def shade(cell, hexcolor):
        tcPr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), hexcolor)
        tcPr.append(shd)

    def runs(par, text, size=None, color=None):
        for part in INLINE.split(text):
            if not part:
                continue
            if part.startswith("**") and part.endswith("**"):
                r = par.add_run(part[2:-2])
                r.bold = True
            elif part.startswith("`") and part.endswith("`"):
                r = par.add_run(part[1:-1])
                r.font.name = "Consolas"
            else:
                r = par.add_run(part)
            if size:
                r.font.size = Pt(size)
            if color:
                r.font.color.rgb = color

    def field(par, instr):
        r = par.add_run()
        for tag, attr in (("w:fldChar", "begin"), ("w:instrText", instr), ("w:fldChar", "separate"), ("w:t", "1"), ("w:fldChar", "end")):
            el = OxmlElement(tag)
            if tag == "w:fldChar":
                el.set(qn("w:fldCharType"), attr)
            else:
                el.text = attr
                if tag == "w:instrText":
                    el.set(qn("xml:space"), "preserve")
            r._r.append(el)

    fp = sec.footer.paragraphs[0]
    fp.text = "IronVision AI – Whitepaper · Version 1.0 · October 2026 · Page "
    field(fp, "PAGE")
    for r in fp.runs:
        r.font.size, r.font.color.rgb = Pt(8), RGBColor(0x6B, 0x85, 0x90)

    d.add_picture(str(BRAND / "logo-lockup-576.png"), width=Cm(5))
    for _ in range(3):
        d.add_paragraph()
    t = d.add_paragraph()
    r = t.add_run(TITLE)
    r.bold, r.font.size, r.font.color.rgb = True, Pt(36), dark
    s2 = d.add_paragraph()
    r = s2.add_run(SUBTITLE)
    r.font.size, r.font.color.rgb = Pt(16), teal
    d.add_paragraph().add_run("Whitepaper · formerly AegisRMF").font.size = Pt(12)
    for _ in range(8):
        d.add_paragraph()
    m = d.add_paragraph()
    runs(m, f"**{VERSION}**\nDerived from the code base, migrations, API specification and project reports. Labels: **MOCKED** · "
            "**REQUIRES HUMAN VERIFICATION** · **SME REVIEW REQUIRED**. Demonstration content is synthetic. IronVision AI is not "
            "FedRAMP-authorized and holds no ATO.", 9.5)
    m.add_run().add_break(WD_BREAK.PAGE)
    d.add_heading("Contents", 1)
    tp = d.add_paragraph()
    field(tp, 'TOC \\o "1-2" \\h \\z \\u')
    d.add_paragraph().add_run("(Right-click → Update field to refresh page numbers.)").italic = True
    d.add_page_break()

    def table(head, rows, widths, header_fill="15697F"):
        tb = d.add_table(rows=1, cols=len(head))
        tb.style = "Table Grid"
        for i, h in enumerate(head):
            c = tb.rows[0].cells[i]
            c.text = ""
            runs(c.paragraphs[0], f"**{h}**", 8.5, RGBColor(0xFF, 0xFF, 0xFF))
            shade(c, header_fill)
        for row in rows:
            cells = tb.add_row().cells
            for i, v in enumerate(row):
                cells[i].text = ""
                runs(cells[i].paragraphs[0], v, 8.5)
        if widths:
            total = 17.2
            for row in tb.rows:
                for i, w in enumerate(widths):
                    row.cells[i].width = Cm(total * w / 100)
        d.add_paragraph()

    for b in blocks:
        k = b[0]
        if k == "h1":
            d.add_heading(f"{b[1]}  {b[2]}", 1)
        elif k == "h2":
            d.add_heading(b[1], 2)
        elif k == "h3":
            d.add_heading(b[1], 3)
        elif k == "p":
            runs(d.add_paragraph(), b[1])
        elif k in ("ul", "ol"):
            for i in b[1]:
                runs(d.add_paragraph(style="List Bullet" if k == "ul" else "List Number"), i)
        elif k == "table":
            table(b[1], b[2], b[3])
        elif k == "img":
            d.add_picture(str(img_map[b[1]]), width=Cm(17.2 * b[3] / 100))
            d.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            cap = d.add_paragraph()
            runs(cap, f"Figure: {b[2]}", 8.5, RGBColor(0x4B, 0x64, 0x70))
            cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif k == "note":
            bg, fg = NOTE_COLORS[b[1]]
            tb = d.add_table(rows=1, cols=1)
            c = tb.rows[0].cells[0]
            shade(c, bg.lstrip("#"))
            c.text = ""
            runs(c.paragraphs[0], f"**{NOTE_LABEL[b[1]]}**", 8, RGBColor.from_string(fg.lstrip("#")))
            runs(c.add_paragraph(), b[2], 9.5)
            d.add_paragraph()
        elif k == "screen":
            _, name, purpose, users, actions, outputs, guard = b
            d.add_heading(name, 3)
            table(["Aspect", "Detail"], [["Purpose", purpose], ["Used by", users], ["Key actions", actions], ["Outputs", outputs],
                                         ["Guardrails", guard]], [18, 82], "2597B2")
        elif k == "pb":
            d.add_page_break()
    d.save(str(out))


def main():
    url = sys.argv[sys.argv.index("--openapi") + 1] if "--openapi" in sys.argv else "http://localhost:8001/api/openapi.json"
    WORK.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    blocks = PART_A + PART_B + api_appendix(url)
    pdf, docx = OUT / "IronVision_AI_Whitepaper.pdf", OUT / "IronVision_AI_Whitepaper.docx"
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        diagram = render_diagram(page)
        img_map = {b[1]: prep_image(b[1], diagram) for b in blocks if b[0] == "img"}
        render_pdf(page, html_doc(blocks, img_map, {}), pdf)
        pages = toc_pages(pdf, blocks)
        render_pdf(page, html_doc(blocks, img_map, pages), pdf)
        browser.close()
    build_docx(blocks, img_map, docx)
    n = len(PdfReader(str(pdf)).pages)
    print(json.dumps({"pdf": str(pdf), "pages": n, "pdf_bytes": pdf.stat().st_size, "docx": str(docx), "docx_bytes": docx.stat().st_size,
                      "toc_entries_with_page": len(pages)}))
    _ = io


if __name__ == "__main__":
    main()
