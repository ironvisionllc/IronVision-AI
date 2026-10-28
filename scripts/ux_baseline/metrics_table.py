#!/usr/bin/env python3
"""Render docs/ux/METRICS.md from data/baseline_metrics.json (re-run after the redesign; pass a 2nd json to compare)."""
import json
import sys

EMASS = {  # approximate typical eMASS steps; sources listed below the table
    "register": "≈4 wizard pages (System Information, Authorization Information, Roles, Review/Submit) [1]",
    "categorize": "≈3 screens – Categorization tab, info types, submit (approx.) [2]",
    "baseline": "≈2 – Controls → baseline auto-assigned from categorization, tailor (approx.) [2]",
    "import_impl": "≈4 – Controls → Bulk Processing → Implementation Plan import → review (approx.) [1][3]",
    "update_control": "≈3 – Controls → select control → Implementation Plan tab → save (approx.) [2]",
    "evidence": "≈3 – Artifacts → Add Artifact → associate to control (approx.) [2]",
    "test_results": "≈4 – Controls → Bulk Processing → Test Result import → review (approx.) [1][3]",
    "finding": "≈3 – Controls / Assets → non-compliant test result (approx.) [2]",
    "poam": "≈4 – POA&M → Add/Edit item → milestones → save (approx.) [1]",
    "ssp": "≈2 – Reports → System Security Plan report (approx.) [2]",
    "package": "≈3 – Package → Submit → Package Approval Chain (PAC) [1]",
    "iscm": "≈3 – Controls → SLCM fields per control / bulk (approx.) [2]",
}
TWICE = {"register": "info type + PII entered here AND in Categorize", "categorize": "yes (see register)", "evidence": "source name before first upload"}


def main(path="/app/docs/ux/data/baseline_metrics.json"):
    d = json.load(open(path))
    rows = ["| Task | Clicks | Page changes | Fields | Scripted s | Next action shown | Data entered twice | Completed | eMASS reference (approx.) |",
            "|---|---|---|---|---|---|---|---|---|"]
    for r in d["results"]:
        rows.append(f"| {r['label']} | {r['clicks']} | {r['page_changes']} | {r['fields']} | {r['scripted_seconds']} | {'yes' if r['next_action_shown'] else '**no**'} | "
                    f"{TWICE.get(r['task'], 'no')} | {'yes' if r['completed'] else 'blocked: ' + str(r['blocked_at'])[:60]} | {EMASS[r['task']]} |")
    tot = {k: sum(r[k] for r in d["results"]) for k in ("clicks", "page_changes", "fields")}
    rows.append(f"| **Total (12 tasks)** | **{tot['clicks']}** | **{tot['page_changes']}** | **{tot['fields']}** | – | {sum(r['next_action_shown'] for r in d['results'])}/12 | 3 | | |")
    body = f"""# 4 · Baseline task metrics (CURRENT UI)

- **Run:** `python3 scripts/ux_baseline/tasks.py`, then `python3 scripts/ux_baseline/metrics_table.py`.
- **Setup:** {d['persona']} on the SYNTHETIC sandbox ({d['base']}), fresh system `{d['fresh_system']}` for tasks 1–7 and 12, seeded LTP for tasks 8–11.
- **Counting rules:**
  - Clicks: every click or option choice, including the file chooser and sidebar navigation.
  - Fields: text typed, options chosen or files picked.
  - Page changes: changes of URL path.
  - Scripted time: wall-clock time of the script, including network. It is not human time; use it only to compare before and after.
- **Caveat – "Next action shown":** the walk records yes when any "Next action / Next step" text is on the final screen. Today that is often the generic "Next action: Assign key roles" banner (audit #3), so a yes here overstates the guidance.
- **Package:** the LTP package was already submitted, so the submit button was absent. The package task measures the path to the package page.
- **Screenshots** at the end of each task: `screens/tasks/<task>.png`.

{chr(10).join(rows)}

**eMASS reference sources** (approximate where marked):
- [1] DCSA, *NISP eMASS Industry Operation Guide* v1.1 (registration's 4 steps, POA&M, package submission / PAC) – https://www.dcsa.mil/Portals/91/Documents/CTP/tools/NISP%20eMASS%20Industry%20Operation%20Guide%20Version%201.1.pdf
- [2] DISA eMASS User Guide (in-app Help; not public – counts estimated from [1] and [3], so approximate)
- [3] rmf.org, *eMASS Overview / Essentials* (bulk processing of the Implementation Plan and Test Results) – https://rmf.org/wp-content/uploads/2018/03/eMASS-Overview-Outline.pdf
"""
    open("/app/docs/ux/METRICS.md", "w").write(body)
    print(body)


if __name__ == "__main__":
    main(*sys.argv[1:])
