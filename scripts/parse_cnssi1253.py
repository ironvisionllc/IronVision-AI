#!/usr/bin/env python3
"""Parse CNSSI No. 1253 (29 July 2022, corrected copy 6 Oct 2022) Appendix D Tables D-1..D-20 into
backend/app/services/content/cnssi1253_baselines.json. Offline tooling: `pip install pdfplumber` (not a runtime dependency).
Usage: python3 scripts/parse_cnssi1253.py [pdf]
Column boundaries are the table's vertical rules (identical on every Appendix D page); row bands are the table's rows."""
import hashlib
import json
import re
import sys
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
PDF = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "reference/cnssi1253/CNSSI_1253_Final_CORRECTED_COPY_6Oct22.pdf")
OUT = ROOT / "backend/app/services/content/cnssi1253_baselines.json"
SHA = "d876741dfb78c54cf21e1f8f966475bddb9df0d3fc8e935e5350862c246d1180"
COLS = [("id", 28, 90), ("title", 90, 213), ("privacy_baseline", 213, 235), ("privacy_impl", 235, 265),
        ("c_l", 265, 284), ("c_m", 284, 303), ("c_h", 303, 323), ("i_l", 323, 342), ("i_m", 342, 361), ("i_h", 361, 381),
        ("a_l", 381, 400), ("a_m", 400, 420), ("a_h", 420, 440), ("justification", 440, 556), ("parameter_value", 556, 683),
        ("assurance", 683, 710), ("resiliency", 710, 736), ("attack", 736, 764)]
ID_RE = re.compile(r"^[A-Z]{2}-\d+(\(\d+\))?$")
MARKS = {"X", "+", "--", ""}


LEGEND = {
    "ref": "Appendix D introduction, pp. D-1 to D-2 (PDF pp. 22-23)",
    "X": "Identifies applicability of NIST SP 800-53B baselines for NSS.",
    "+": "Identifies a control needed to protect NSS and therefore added to the NSS baselines.",
    "--": "Identifies a control selected for NIST baseline (security or privacy) but not selected for an NSS baseline (security or privacy). "
          "Privacy controls selected for a NIST baseline but not selected for an NSS baseline are specific to systems that process PII and are "
          "addressed in the Privacy Overlay. Any control can still be selected during tailoring if needed.",
    "blank": "A control not selected for a baseline nor allocated to a particular security objective; no parameter value specific to NSS is provided "
             "for the control; or the control is not applicable to an Assurance, Resiliency, or ATT&CK mapping. If not indicated with an \"X\" or \"+\", "
             "the control may still be selected during the tailoring process.",
    "√": "Identifies applicability of a control to Privacy Implementation Considerations, Assurance, Resiliency, or ATT&CK.",
    "privacy_control_baseline": "Controls indicated with an \"X\" or a \"+\" in this column are required for all NSS.",
    "security_control_baselines": "Columns showing the association of a control to the security objective (confidentiality, integrity, availability) "
                                  "and at what impact level (low, moderate, high) based on inclusion of an \"X\" or a \"+\".",
    "privacy_implementation_considerations": {"1": "Close coordination between security and privacy is needed to manage privacy risks",
                                              "2": "Design choices may mitigate privacy risks", "3": "Implementation choices may create unintended privacy risks",
                                              "4": "PII should not flow through or into a system that is not authorized to process PII"},
    "parameter_value": "Contains minimum values specified for NSS; parameter values not appropriate for CNSS to define for all NSS are not included. "
                       "Parameter values apply to both privacy and security baselines.",
    "withdrawn": "Controls that are designated as \"Withdrawn\" indicate they are no longer in the NIST SP 800-53 control catalog.",
}
RULE = {
    "ref": "Section 3.2.1, Task S-1, Control Selection, p. 10 (PDF p. 14); trigraph per Section 3.1.2, p. 10 (PDF p. 14)",
    "text": ["1. Select the NSS security control baseline contained in Appendix D Tables D-1 through D-20 corresponding to the security categorization "
             "of the system (i.e., the impact levels determined for each security objective [confidentiality, integrity, and availability]).",
             "2. Include the NSS privacy control baseline contained in Appendix D Tables D-1 through D-20, which is a default for all NSS."],
    "trigraph": "For each security objective, determine the overall high water mark for information types on the system ... This results in three "
                "distinct high water marks, one for each security objective ... shown as a trigraph categorization (e.g., L-L-L, M-M-H).",
    "implemented_as": "baseline = {rows marked X or + in the C column at the system's C level} ∪ {… I column at the I level} ∪ {… A column at the A level} "
                      "∪ {rows marked X or + in the Privacy Control Baseline column}; withdrawn rows and '--' / blank cells are never selected. "
                      "No overall (single) high-water mark is used for NSS selection.",
}
FAMILY_NOTES = {
    "Table D-13": {"family": "PM", "pdf_page": 101, "doc_page": "D-80", "note": "Deployed organization-wide. Supports information security program. "
                   "Not associated with security control baselines. Independent of any system impact level."},
    "Table D-15": {"family": "PT", "pdf_page": 108, "doc_page": "D-87", "note": "Personally Identifiable Information Processing and Transparency "
                   "control are not allocated to the security control baselines."},
}


def col_of(x: float, shift: float = 0) -> str | None:
    return next((n for n, a, b in COLS if a + shift <= x < b + shift), None)


def cell_text(words) -> str:
    lines: list[list] = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if lines and abs(lines[-1][0]["top"] - w["top"]) < 3:
            lines[-1].append(w)
        else:
            lines.append([w])
    return "\n".join(" ".join(x["text"] for x in sorted(ln, key=lambda w: w["x0"])) for ln in lines).strip()


def norm(cid: str) -> str:
    m = re.match(r"^([A-Z]{2})-(\d+)(?:\((\d+)\))?$", cid)
    return f"{m.group(1).lower()}-{int(m.group(2))}" + (f".{int(m.group(3))}" if m.group(3) else "")


def main() -> None:
    raw = PDF.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SHA, "unexpected source file"
    rows, table, problems, notes = [], None, [], {}
    with pdfplumber.open(PDF) as pdf:
        for pi, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            m = re.search(r"Table (D-\d+): ([^\n]+?Family)", text.replace("\n", " ")) if "Table D-" in text else None
            if m and pi >= 20:
                table = {"table": f"Table {m.group(1)}", "family": m.group(2).strip()}
            if table is None or pi < 24:
                continue
            tabs = page.find_tables()
            if not tabs:
                continue
            doc_page = next((ln.strip() for ln in text.splitlines()[:4] + text.splitlines()[-4:][::-1] if re.fullmatch(r"D-\d+", ln.strip())), None)
            words = page.extract_words(extra_attrs=["size"])
            ls = sorted((w["x0"] + w["x1"]) / 2 for w in words if w["text"] == "L" and w["top"] < 240)
            shift = (ls[0] - 273.5) if ls else 0  # Table D-19 pages are drawn ~2 pt further left
            ys: list[float] = []  # row rules: horizontal edges across the whole ID column (x 30-89)
            for y in sorted(e["top"] for e in page.edges if e["orientation"] == "h" and e["x0"] <= 31 and e["x1"] >= 86):
                if not ys or y - ys[-1] > 2:
                    ys.append(y)
            for top, bottom in zip(ys, ys[1:]):
                ws = [w for w in words if top - 0.5 <= (w["top"] + w["bottom"]) / 2 <= bottom + 0.5 and 28 <= w["x0"] < 764]
                cells = {n: [] for n, _, _ in COLS}
                for w in ws:
                    c = col_of((w["x0"] + w["x1"]) / 2, shift)
                    if c:
                        cells[c].append(w)
                vals = {n: cell_text(v) for n, v in cells.items()}
                if vals["c_m"] == "C" or vals["title"] == "Title" or vals["c_l"] == "L":
                    continue  # header rows
                if vals["id"] in ("ID", "") and not ID_RE.match(vals["id"]):
                    if vals["id"] == "" and rows and any(vals.values()):
                        prev = rows[-1]  # row continued from the previous page
                        extra = {k: v for k, v in vals.items() if v}
                        if set(extra) - {"parameter_value", "justification", "title"}:
                            problems.append(f"p.{pi + 1}: continuation row with unexpected columns {extra}")
                        if extra.get("parameter_value"):
                            prev["parameter_value"] = f"{prev['parameter_value'] or ''}\n{extra['parameter_value']}".strip()
                        prev["continued_on_pdf_page"] = pi + 1
                    continue
                if not ID_RE.match(vals["id"]):
                    problems.append(f"p.{pi + 1}: unparsed ID {vals['id']!r}")
                    continue
                title = " ".join(vals["title"].split())
                withdrawn = "Withdrawn" in " ".join(vals.values())
                sel = {}
                for o in "cia":
                    for lv in "lmh":
                        toks = vals[f"{o}_{lv}"].split()
                        marks = [t for t in toks if t in MARKS]
                        if len(marks) != len(toks):
                            notes.setdefault(table["table"], set()).add(pi + 1)  # merged note cell across C/I/A (PM, PT families)
                        if len(marks) > 1:
                            problems.append(f"p.{pi + 1} {vals['id']}: several marks {marks} in {o}_{lv}")
                        sel[f"{o}_{lv}"] = "" if withdrawn else (marks[0] if marks else "")
                rows.append({"id": vals["id"], "control_id": norm(vals["id"]), "title": title.replace(" Withdrawn", "").strip() if withdrawn else title,
                             "withdrawn": withdrawn, "table": table["table"], "family": table["family"], "pdf_page": pi + 1, "doc_page": doc_page,
                             "privacy_baseline": vals["privacy_baseline"].replace(" ", ""), "privacy_implementation": vals["privacy_impl"].replace(" ", "").replace("\n", ""),
                             "marks": sel, "justification": None if withdrawn else (" ".join(vals["justification"].split()) or None),
                             "parameter_value": vals["parameter_value"] or None,
                             "assurance": "√" in vals["assurance"], "resiliency": "√" in vals["resiliency"], "attack": "√" in vals["attack"]})
    seen, dups = {}, []
    for r in rows:
        if r["id"] in seen:
            dups.append(r["id"])
        seen[r["id"]] = r
    out = {"source": {"title": "CNSSI No. 1253, Categorization and Control Selection for National Security Systems", "date": "2022-07-29",
                      "copy": "Corrected copy, 6 October 2022", "file": PDF.name, "sha256": SHA, "pages": 161, "catalog": "NIST SP 800-53 Revision 5",
                      "appendix": "Appendix D, Tables D-1 through D-20 (PDF pp. 25-161 / D-4 onward)"},
           "legend": LEGEND, "selection_rule": RULE, "family_notes": FAMILY_NOTES,
           "parser": "scripts/parse_cnssi1253.py (pdfplumber; table vertical rules as column boundaries)", "rows": rows,
           "parse_problems": problems, "duplicate_ids": dups, "merged_note_pages": {k: sorted(v) for k, v in notes.items()}}
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(len(rows), "rows;", len(problems), "problems;", len(dups), "dups")
    for p in problems[:60]:
        print(" ", p)


if __name__ == "__main__":
    main()
