#!/usr/bin/env python3
"""Wrap / squeeze: per-route before/after counts + light-mode before/after side-by-sides of the worst 6 screens.
Inputs: docs/screenshots/wrap/results-{before,after}-{dark,light}-{1280,768,390}.json and raw shots in $WRAP_RAW.
Outputs: docs/ux/WRAP.md, docs/ux/screens/wrap/*.png, frontend/public/ux-proposal-assets/wrap/*.png + summary.json"""
import json
import os
import shutil
from collections import defaultdict

from PIL import Image, ImageDraw, ImageFont

W = "/app/docs/screenshots/wrap"
RAW = os.environ.get("WRAP_RAW", "/tmp/wrap_raw")
RUNS = [f"{t}-{s}" for t in ("dark", "light") for s in ("1280", "768", "390")]
OUT, PUB = "/app/docs/ux/screens/wrap", "/app/frontend/public/ux-proposal-assets/wrap"


def load(phase):
    per, checks = defaultdict(dict), defaultdict(lambda: defaultdict(int))
    for run in RUNS:
        for r in json.load(open(f"{W}/results-{phase}-{run}.json")):
            per[r["page"]][run] = r["count"]
            for k, v in r["by_check"].items():
                checks[run][k] += v
    return per, checks


(b, bc), (a, ac) = load("before"), load("after")
score = {p: sum(v.get(f"light-{s}", 0) for s in ("390", "768")) for p, v in b.items()}
worst = sorted(score, key=lambda p: -score[p])[:6]
rows = ["| Route | " + " | ".join(RUNS) + " |", "|---|" + "---|" * len(RUNS)]
for p in sorted(b):
    rows.append(f"| {p} | " + " | ".join(f"{b[p].get(r, 0)} → **{a.get(p, {}).get(r, 0)}**" for r in RUNS) + " |")
tb = {r: sum(v.get(r, 0) for v in b.values()) for r in RUNS}
ta = {r: sum(v.get(r, 0) for v in a.values()) for r in RUNS}
rows.append("| **Total** | " + " | ".join(f"{tb[r]} → **{ta[r]}**" for r in RUNS) + " |")
crow = ["| Check | " + " | ".join(RUNS) + " |", "|---|" + "---|" * len(RUNS)]
for k in ("label-wrap", "clipped", "squeezed"):
    crow.append(f"| {k} | " + " | ".join(f"{bc[r].get(k, 0)} → **{ac[r].get(k, 0)}**" for r in RUNS) + " |")

os.makedirs(OUT, exist_ok=True)
font = ImageFont.load_default()
for p in worst:
    s = "390" if b[p].get("light-390", 0) >= b[p].get("light-768", 0) else "768"
    l, r = Image.open(f"{RAW}/before-light-{s}/{p}_{s}.png"), Image.open(f"{RAW}/after-light-{s}/{p}_{s}.png")
    w, h = l.size
    img = Image.new("RGB", (w * 2 + 24, h + 40), "#f8fafc")
    img.paste(l, (0, 40))
    img.paste(r, (w + 24, 40))
    d = ImageDraw.Draw(img)
    d.text((10, 12), f"BEFORE {p} @{s}px – {b[p]['light-' + s]} findings", fill="#b42318", font=font)
    d.text((w + 34, 12), f"AFTER {p} @{s}px – {a[p]['light-' + s]} findings", fill="#067647", font=font)
    img.save(f"{OUT}/{p}.png")
shutil.copytree(OUT, PUB, dirs_exist_ok=True)
json.dump({"worst": worst, "before": tb, "after": ta}, open(f"{PUB}/summary.json", "w"), indent=1)
open("/app/docs/ux/WRAP.md", "w").write(
    "# Wrapped labels and squeezed text – before / after\n\nChecked by `scripts/check_wrap.py` on every route of the layout checker at 1280, 768 and 390 wide, "
    "dark and light: **label-wrap** (button, button link, tab, chip/badge, status label or menu item on more than one line), **clipped** (visible "
    "button cut by a non-scrolling container, outside the viewport, or truncated label) and **squeezed** (text block or table cell under ~12 characters "
    "wide wrapping onto 3+ lines). `scripts/check_layout_overflow.py` still guards against horizontal page overflow.\n\n"
    "## Root cause\n\n- `overflow-wrap: anywhere` on `td`, `dd`, `code` and `.font-mono` (added by the earlier clipping fix) also shrinks the *min-content* "
    "width, so auto-layout tables and flex items squeezed columns to one word – or one character – per line instead of scrolling.\n"
    "- Buttons, tabs and chips had no `white-space: nowrap` / `flex-shrink: 0`, so `min-w-0` flex rows compressed their labels into stacks.\n"
    "- Toolbars were single non-wrapping rows.\n\n"
    "## Fix (shared CSS / components)\n\n`overflow-wrap: break-word` (breaks only words that cannot fit); nowrap + no-shrink for `.btn`, tabs, menu items, "
    "switches, chips, badges and status labels; table cells get minimum widths (9ch IDs/dates/statuses on one line, 14–24ch text) and every table "
    "scrolls horizontally inside `TableScroll` (or itself when unwrapped); `ActionBar` in `PageHeader`/`Panel` wraps whole buttons and on phones keeps "
    "the first action with the rest in a labelled **More ▾** menu (still in the DOM, one click away).\n\n"
    "Note on the *before* numbers: the dark runs were taken live before the fix with the first version of the checker (it still counted buttons in "
    "horizontally-scrolling tables as `clipped` and multi-line tree rows as wrapped labels). The light runs were re-measured with the final checker on a "
    "build of the pre-fix commit `c107f4f` served against the same backend, so light before/after use identical rules.\n\n"
    "## By check\n\n" + "\n".join(crow) + "\n\n## By route\n\n" + "\n".join(rows) +
    "\n\n## Worst 6 screens (light, narrow) – before / after\n\n" + "\n".join(f"![{p}](screens/wrap/{p}.png)" for p in worst) + "\n")
print("worst:", worst)
print(rows[-1])
print("\n".join(crow))
