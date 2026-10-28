#!/usr/bin/env python3
"""docs/ux/METRICS_AFTER.md – the 12 scripted tasks, baseline (old UI) vs after (R1–R7), from data/{baseline,after}_metrics.json."""
import json
import os

D = "/app/docs/ux/data"
b = {r["task"]: r for r in json.load(open(f"{D}/baseline_metrics.json"))["results"]}
a = json.load(open(f"{D}/after_metrics.json"))["results"]
NOTES = open(f"{os.path.dirname(D)}/METRICS_NOTES.md").read() if os.path.exists(f"{os.path.dirname(D)}/METRICS_NOTES.md") else ""  # hand-written explanations
yn = lambda v: "yes" if v else "no"  # noqa: E731
rows = ["| Task | Clicks | Page changes | Fields | Next action shown | Completed |", "|---|---|---|---|---|---|"]
for r in a:
    o = b[r["task"]]
    rows.append(f"| {r['label']} | {o['clicks']} → **{r['clicks']}** | {o['page_changes']} → **{r['page_changes']}** | {o['fields']} → **{r['fields']}** | "
                f"{yn(o['next_action_shown'])} → **{yn(r['next_action_shown'])}** | {yn(r['completed'])}{'' if r['completed'] else ' – ' + str(r['blocked_at'])[:60]} |")
t = lambda rs, k: sum(x[k] for x in rs)  # noqa: E731
rows.append(f"| **Total** | {t(b.values(), 'clicks')} → **{t(a, 'clicks')}** | {t(b.values(), 'page_changes')} → **{t(a, 'page_changes')}** | "
            f"{t(b.values(), 'fields')} → **{t(a, 'fields')}** | {sum(x['next_action_shown'] for x in b.values())}/12 → **{sum(x['next_action_shown'] for x in a)}/12** | "
            f"{sum(x['completed'] for x in a)}/12 |")
open("/app/docs/ux/METRICS_AFTER.md", "w").write(
    "# Task metrics after the redesign (R1–R7)\n\nSame 12 scripted tasks, ISSO persona, synthetic sandbox, fresh `UXB*` system per walk "
    "(archived automatically at the end). Rerun: `UX_PHASE=after python3 scripts/ux_baseline/tasks.py && python3 scripts/ux_baseline/compare.py`.\n\n"
    "Selector changes made for the new layout are commented in `tasks.py` (step header navigation, Workbench tabs, one-off evidence upload). "
    "The evidence walk now uploads a valid SARIF file (the baseline file was rejected as unsupported in both runs).\n\n" + "\n".join(rows) + "\n" + NOTES)
print("\n".join(rows))
