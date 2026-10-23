"""Parse the official CNSSI 1253 overlay PDFs into versioned reference JSON (run: python parse_overlays.py <rev5.json> <public_out> <restricted_out>)."""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REF = Path("/app/reference/cnssi1253")
ID = r"[A-Z]{2}-\d+(?:\s?\(\d+\))?"
LABEL = re.compile(r"^\s*(?:\(U\)\s*)?((?:[A-Za-z,/()\- ]{0,60}?)(?:Justification|Guidance|Parameter Value|Reference|Extension)[A-Za-z,/()\- ]{0,60}?):\s*(.*)$")
NOISE = [r"UNCLASSIFIED//FOUO", r"^\s*\(U//FOUO\)\s*$", r"Attachment \d to Appendix [EF]", r"^\s*\d{2}/\d{2}/\d{4}\s*$", r"^\s*\d{1,3}\s*$",
         r"^\s*\d{1,2} (January|February|March|April|May|June|July|August|September|October|November|December) \d{4}\s*$",
         r"Space Platform Overlay August 2025", r"^\s*Page \d+\s*$"]

DOCS = {
    "privacy": dict(file="CNSSI-1253F_Attachment_6_Privacy_Overlay_20241031.pdf", title="CNSSI 1253F Attachment 6 – Privacy Overlays",
                    cite="CNSSI 1253F Att. 6", date="2024-10-31", marking="No classification banner, CUI or FOUO marking, or distribution statement found",
                    public=True, table=(r"Table 2: Privacy Overlays Security and Privacy Controls", r"^6\s+Detailed Overlays"),
                    cols=[("acct", "ACCT"), ("low", "Low"), ("moderate", "Mod"), ("high", "High"), ("enhancing", "Enhancing")],
                    detail=(r"^6\s+Detailed Overlays Control Specifications", r"^7\s+Implementation Considerations|^7\s+[A-Z]"),
                    var_words={"acct": r"\bACCT\b", "low": r"\bLow\b", "moderate": r"\bModerate\b", "high": r"\bHigh\b", "enhancing": r"Privacy Enhancing"}),
    "classified": dict(file="Classified_Systems_Overlay_FINAL_Dated.pdf", title="CNSSI 1253 Appendix E Attachment 5 – Classified System Overlay",
                       cite="CNSSI 1253 App. E Att. 5", date="2022-09-30", marking="No classification banner, CUI or FOUO marking, or distribution statement found",
                       public=True, table=(r"Table 1: Classified System Overlay Summary", r"Controls with Implementation Considerations"),
                       cols=[("classified", "Overlay")], detail=(r"^6\. Detailed Overlay Control Specifications", r"^7\. Implementation Considerations"),
                       var_words={}),
    "space": dict(file="CNSSI_1253F_Attachment_2_Space_Overlay_Aug_2025.pdf", title="CNSSI 1253F Attachment 2 – Space Platform Overlay",
                  cite="CNSSI 1253F Att. 2", date="2025-08", marking="No classification banner, CUI or FOUO marking, or distribution statement found "
                  "(content paragraphs carry (U) portion marks)", public=True,
                  table=(r"Table 2 - Summary of Control Specifications", r"^\s*6\. Detailed Control Specifications"), cols=[("space", "Overlay")],
                  detail=(r"^\s*6\. Detailed Control Specifications", r"^\s*Appendix A\. Applicable Baseline Controls"), var_words={}),
    "intelligence": dict(file="Intelligence_Overlays_.pdf", title="CNSSI 1253 – Intelligence Overlays (INT-A, INT-B, INT-C)", cite="CNSSI 1253 Intelligence Overlays",
                         date="2023-11-27", marking="UNCLASSIFIED//FOUO on every page", public=False,
                         table=(r"Table 1: Intelligence Overlays Control Specifications Summary", r"Table 2 below identifies"),
                         cols=[("int-a", "INT-A"), ("int-b", "INT-B"), ("int-c", "INT-C")],
                         detail=(r"^6\. \(U\) Detailed Control Specifications", r"^7\. \(U\)"),
                         var_words={"int-a": r"INT-A", "int-b": r"INT-B", "int-c": r"INT-C"}),
    "cds": dict(file="CDS_Overlay_Admin_Update_20240109.pdf", title="CNSSI 1253 Appendix E Attachment 3 – Cross Domain Solution (CDS) Overlays",
                cite="CNSSI 1253 App. E Att. 3", date="2023-02-01 (admin update 2024-01-09)", marking="UNCLASSIFIED//FOUO on every page", public=False,
                table=(r"Table 1: CDS Overlays Security and Privacy Controls", r"^\s*6\. \(U\) Detailed Control Specifications"),
                cols=[("spec", "Specifications"), ("impl", "Considerations")],
                detail=(r"^\s*6\. \(U\) Detailed Control Specifications", r"^\s*7\. \(U\)"), var_words={}),
}


def norm(raw):
    m = re.match(r"([A-Z]{2})-(\d+)(?:\((\d+)\))?$", raw.replace(" ", ""))
    return f"{m[1].lower()}-{int(m[2])}" + (f".{int(m[3])}" if m[3] else "")


def load_pages(pdf):
    out = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout.split("\f")
    return [[ln for ln in p.splitlines() if not any(re.search(n, ln) for n in NOISE)] for p in out]


def flat(pages, start, end):
    rows, on = [], False
    for pi, p in enumerate(pages, start=1):
        for ln in p:
            if not on and re.search(start, ln):
                on = True
                continue
            if on and re.search(end, ln):
                return rows
            if on:
                rows.append((pi, ln))
    return rows


TOK = re.compile(r"(?<!\S)(\+[EGVRA]*|--[GVR]*|\*[EGVR]*|[PSA+GVR]{1,7}|-{2})(?!\S)")


def parse_table(cfg, rows):
    single = len(cfg["cols"]) == 1
    centers, out, i = {}, [], 0
    lines = [(p, ln) for p, ln in rows if ln.strip()]
    hdr_pos = {}
    parsed = []
    for p, ln in lines:
        for key, word in cfg["cols"]:
            if word in ln and not re.match(rf"^\s*\(?{ID}", ln.strip()):
                hdr_pos.setdefault(p, {})
                if key not in hdr_pos[p]:
                    hdr_pos[p][key] = ln.index(word) + len(word) / 2
        full = re.match(rf"^\s{{0,12}}({ID})(\*{{0,2}})(?=\s|$)", ln)
        pref = re.match(r"^\s{0,4}([A-Z]{2}-)\s*(?:\s{2,}|$)", ln)
        suf = re.match(r"^\s{0,4}(\d+\(\d+\))(?=\s|$)", ln)
        body_start = full.end() if full else (pref.end() if pref else (suf.end() if suf else 0))
        toks = [] if "CNSS Privacy Baseline" in ln else [(m.start() + len(m.group()) / 2, m.group()) for m in TOK.finditer(ln, body_start)]
        if single:
            cx = (hdr_pos.get(p) or {}).get(cfg["cols"][0][0])
            toks = [t for t in toks if (abs(t[0] - cx) <= 10 if cx else t[0] > 55)]
        parsed.append(dict(p=p, ln=ln, full=full, pref=pref, suf=suf, toks=toks, base="CNSS Privacy Baseline" in ln))
    used = set()
    k = 0
    while k < len(parsed):
        r = parsed[k]
        span = []
        if r["full"]:
            raw, star = r["full"].group(1), r["full"].group(2)
            span = [k]
        elif r["pref"]:
            j = next((j for j in range(k + 1, min(k + 4, len(parsed))) if parsed[j]["suf"]), None)
            if j is None:
                k += 1
                continue
            raw, star = r["pref"].group(1) + parsed[j]["suf"].group(1), ""
            span = list(range(k, j + 1))
        else:
            k += 1
            continue
        toks, base = [], any(parsed[s]["base"] for s in span)
        for s in span:
            toks += parsed[s]["toks"]
            used.add(s)
        if not toks and not base:
            for s in (span[-1] + 1, span[0] - 1):
                if 0 <= s < len(parsed) and s not in used and not (parsed[s]["full"] or parsed[s]["pref"] or parsed[s]["suf"]) and parsed[s]["toks"]:
                    toks = parsed[s]["toks"]
                    used.add(s)
                    break
        pos = hdr_pos.get(r["p"]) or next((v for pp, v in sorted(hdr_pos.items(), reverse=True) if pp <= r["p"]), {})
        cells, amb = {}, []
        for x, t in toks:
            if single:
                key = cfg["cols"][0][0]
            else:
                key, d = min(((c, abs(x - cx)) for c, cx in pos.items()), key=lambda z: z[1], default=(None, 99))
                if d > 9:
                    amb.append(f"token {t} at column {x:.0f} not under a header")
                    continue
            if key in cells:
                amb.append(f"two tokens in column {key}")
            cells[key] = t
        if base:
            cells = {c: "BASELINE" for c, _ in cfg["cols"] if c != "enhancing"}
        out.append(dict(source_id=raw.replace(" ", ""), star=star, page=r["p"], cells=cells, ambiguous=amb))
        k = span[-1] + 1
    return out


def xy_lines(pdf, start, end):
    import pdfplumber

    out, on = [], False
    with pdfplumber.open(pdf) as doc:
        for pi, page in enumerate(doc.pages, start=1):
            lines = []
            for w in sorted(page.extract_words(x_tolerance=1.5), key=lambda w: (w["top"], w["x0"])):
                if lines and abs(lines[-1][0] - w["top"]) <= 2.5:
                    lines[-1][1].append(w)
                else:
                    lines.append([w["top"], [w]])
            for top, ws in lines:
                ws.sort(key=lambda w: w["x0"])
                text = " ".join(w["text"] for w in ws)
                if not on and re.search(start, text):
                    on = True
                    continue
                if on and re.search(end, text):
                    return out
                if on and not any(re.search(n, text) for n in NOISE):
                    out.append((pi, ws, text))
    return out


def parse_table_xy(cfg, lines):
    hdr, parsed = {}, []
    words = {w for _, w in cfg["cols"]}
    for p, ws, text in lines:
        if any(w["text"] in words for w in ws) and not re.match(ID, ws[0]["text"]):
            for key, word in cfg["cols"]:
                for w in ws:
                    if w["text"] == word:
                        hdr.setdefault(p, {})[key] = (w["x0"] + w["x1"]) / 2
            continue
        first = ws[0]["text"]
        full = re.fullmatch(rf"({ID})(\*{{0,2}})", first)
        pref = re.fullmatch(r"[A-Z]{2}-", first)
        suf = re.fullmatch(r"\d+\(\d+\)", first)
        pos = hdr.get(p) or {}
        lim = min(pos.values()) - 20 if pos else 300
        toks = [((w["x0"] + w["x1"]) / 2, w["text"]) for w in ws[1:] + ([] if (full or pref or suf) else ws[:1])
                if TOK.fullmatch(w["text"]) and w["x0"] > lim]
        parsed.append(dict(p=p, full=full, pref=first if pref else None, suf=first if suf else None, toks=toks, base="CNSS Privacy Baseline" in text))
    out, used, k = [], set(), 0
    while k < len(parsed):
        r = parsed[k]
        if r["full"]:
            raw, star, span = r["full"].group(1), r["full"].group(2), [k]
        elif r["pref"]:
            j = next((j for j in range(k + 1, min(k + 4, len(parsed))) if parsed[j]["suf"]), None)
            if j is None:
                k += 1
                continue
            raw, star, span = r["pref"] + parsed[j]["suf"], "", list(range(k, j + 1))
        else:
            k += 1
            continue
        toks, base = [], any(parsed[s]["base"] for s in span)
        for s in span:
            toks += parsed[s]["toks"]
            used.add(s)
        if not toks and not base:
            for s in (span[-1] + 1, span[0] - 1):
                if 0 <= s < len(parsed) and s not in used and not (parsed[s]["full"] or parsed[s]["pref"] or parsed[s]["suf"]) and parsed[s]["base"]:
                    base = True
                    used.add(s)
                    break
        if not toks and not base:
            for s in (span[-1] + 1, span[0] - 1):
                if 0 <= s < len(parsed) and s not in used and not (parsed[s]["full"] or parsed[s]["pref"] or parsed[s]["suf"]) and parsed[s]["toks"]:
                    toks = parsed[s]["toks"]
                    used.add(s)
                    break
        pos = hdr.get(r["p"]) or next((v for pp, v in sorted(hdr.items(), reverse=True) if pp <= r["p"]), {})
        cells, amb = {}, []
        for x, t in toks:
            key, d = min(((c, abs(x - cx)) for c, cx in pos.items()), key=lambda z: z[1], default=(None, 999))
            if d > 18:
                amb.append(f"token {t} at x={x:.0f}pt not under a column header")
                continue
            if key in cells:
                amb.append(f"two tokens in column {key}")
            cells[key] = t
        if base:
            cells = {c: "BASELINE" for c, _ in cfg["cols"] if c != "enhancing"}
        out.append(dict(source_id=raw.replace(" ", ""), star=star, page=r["p"], cells=cells, ambiguous=amb))
        k = span[-1] + 1
    return out


def parse_details(cfg, rows):
    heads, cur = {}, None
    for p, ln in rows:
        m = re.match(rf"^(?:\(U\)\s*)?({ID})(\*{{0,2}}),\s+(.+)$", ln)
        if m and not ln.startswith(" "):
            cur = norm(m.group(1))
            heads.setdefault(cur, {"page": p, "name": m.group(3).strip(), "fields": []})
            continue
        if cur is None:
            continue
        lm = LABEL.match(ln)
        if lm and len(lm.group(1)) < 90:
            heads[cur]["fields"].append([lm.group(1).strip(), lm.group(2).strip(), p])
        elif heads[cur]["fields"]:
            heads[cur]["fields"][-1][1] = (heads[cur]["fields"][-1][1] + " " + ln.strip()).strip()
    return heads


def scope(label, cfg):
    hit = [v for v, rx in cfg["var_words"].items() if re.search(rx, label)]
    return hit or None


def action_of(tok):
    if tok == "BASELINE":
        return "baseline"
    if tok.startswith("+"):
        return "add"
    if tok.startswith("--"):
        return "remove"
    if tok.startswith("*"):
        return "optional"
    return "guidance" if any(c in tok for c in "GVR") else "baseline"


def summarize(t, n=600):
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + "…"


def build(key, cfg, rev5):
    pdf = REF / cfg["file"]
    pages = load_pages(pdf)
    if key in ("privacy", "intelligence"):
        table = parse_table_xy(cfg, xy_lines(pdf, *[re.sub(r"\\s\+|\\s\*", " ", p).replace("^ ", "^").replace("^", "") for p in cfg["table"]]))
    else:
        table = parse_table(cfg, flat(pages, *cfg["table"]))
    det = parse_details(cfg, flat(pages, *cfg["detail"]))
    doc = {"file": cfg["file"], "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(), "pdf_pages": len(pages) - 1, "date": cfg["date"],
           "marking": cfg["marking"], "public_release_ok": cfg["public"], "cite": cfg["cite"], "title": cfg["title"]}
    controls, flagged, ambiguous = [], [], []
    for r in table:
        cid = norm(r["source_id"])
        ref = rev5.get(cid)
        if ref is None or ref["withdrawn"]:
            flagged.append({"source_id": r["source_id"], "control_id": cid, "page": r["page"], "issue": "not in Rev 5 catalog" if ref is None else "withdrawn in Rev 5"})
        d = det.get(cid, {})
        fields = []
        for label, text, p in d.get("fields", []):
            fields.append({"label": label, "text": summarize(text, 1500 if "Parameter" in label else 600), "page": p, "variants": scope(label, cfg)})
        cells = r["cells"]
        if key == "cds":
            spec, impl = cells.get("spec", ""), cells.get("impl", "")
            variants = {"access": "**" == r["star"] or r["star"] == "", "transfer": r["star"] in ("*", "")}
            acts = {}
            for v, on in variants.items():
                if not on:
                    continue
                if spec:
                    a = "add" if spec.startswith("+") else "remove" if spec.startswith("--") else ("guidance" if any(c in spec.replace("P", "").replace("S", "").replace("A", "") for c in "GVR") else "baseline")
                    acts[v] = {"action": a, "flags": spec}
                elif impl:
                    acts[v] = {"action": "consideration", "flags": impl}
            if r["star"] == "**":
                acts.pop("transfer", None)
            if r["star"] == "*":
                acts.pop("access", None)
        else:
            acts = {v: {"action": action_of(t), "flags": t} for v, t in cells.items()}
        if not acts:
            ambiguous.append({"control_id": cid, "page": r["page"], "issue": "no specification token parsed for this row"})
        for a in r["ambiguous"]:
            ambiguous.append({"control_id": cid, "page": r["page"], "issue": a})
        controls.append({"control_id": cid, "source_id": r["source_id"] + r["star"], "name": d.get("name") or (ref or {}).get("title"),
                         "summary_page": r["page"], "detail_page": d.get("page"), "by_variant": acts, "fields": fields,
                         "in_rev5": bool(ref and not ref["withdrawn"])})
    return doc, controls, flagged, ambiguous


def main():
    rev5 = json.load(open(sys.argv[1]))
    out = {}
    for key, cfg in DOCS.items():
        doc, controls, flagged, amb = build(key, cfg, rev5)
        out[key] = {"document": doc, "controls": controls, "flagged_ids": flagged, "ambiguous": amb}
        print(key, len(controls), "flagged", len(flagged), "ambiguous", len(amb))
    pub = {k: v for k, v in out.items() if v["document"]["public_release_ok"]}
    res = {k: v for k, v in out.items() if not v["document"]["public_release_ok"]}
    Path(sys.argv[2]).write_text(json.dumps({"schema": 1, "overlays": pub}, indent=1))
    Path(sys.argv[3]).parent.mkdir(parents=True, exist_ok=True)
    Path(sys.argv[3]).write_text(json.dumps({"schema": 1, "overlays": res}, indent=1))


if __name__ == "__main__":
    main()
