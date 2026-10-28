#!/usr/bin/env python3
"""Night-mode contrast: per-route before/after violation table + dark-mode before/after side-by-sides of the worst 6 screens.
Inputs: docs/screenshots/contrast/results-{before,after}-{dark,light}-{1280,390}.json and the dark 1280 screenshots.
Outputs: docs/ux/CONTRAST.md, docs/ux/screens/contrast/*.png, frontend/public/ux-proposal-assets/contrast/*.png"""
import json
import os
import shutil
from collections import defaultdict

from PIL import Image, ImageDraw, ImageFont

C = "/app/docs/screenshots/contrast"
SHOTS = os.environ.get("CONTRAST_RAW", "/tmp/contrast_raw")
RUNS = ["dark-1280", "dark-390", "light-1280", "light-390"]
OUT, PUB = "/app/docs/ux/screens/contrast", "/app/frontend/public/ux-proposal-assets/contrast"


def load(phase):
    per = defaultdict(dict)
    for run in RUNS:
        for r in json.load(open(f"{C}/results-{phase}-{run}.json")):
            per[r["page"]][run] = r["axe"] + r["custom"]
    return per


b, a = load("before"), load("after")
worst = [p for p, _ in sorted(b.items(), key=lambda x: -x[1].get("dark-1280", 0))[:6]]
rows = ["| Route | " + " | ".join(f"{r} before → after" for r in RUNS) + " |", "|---|" + "---|" * len(RUNS)]
tot_b, tot_a = defaultdict(int), defaultdict(int)
for p in sorted(b):
    cells = []
    for r in RUNS:
        x, y = b[p].get(r, 0), a.get(p, {}).get(r, 0)
        tot_b[r] += x
        tot_a[r] += y
        cells.append(f"{x} → **{y}**")
    rows.append(f"| {p} | " + " | ".join(cells) + " |")
rows.append("| **Total** | " + " | ".join(f"{tot_b[r]} → **{tot_a[r]}**" for r in RUNS) + " |")

os.makedirs(OUT, exist_ok=True)
font = ImageFont.load_default()
for p in worst:
    if not (os.path.exists(f"{SHOTS}/before-dark-1280/{p}.png") and os.path.exists(f"{SHOTS}/after-dark-1280/{p}.png")):
        print("raw screenshots missing – keeping the existing side-by-side for", p)
        continue
    l, r = Image.open(f"{SHOTS}/before-dark-1280/{p}.png"), Image.open(f"{SHOTS}/after-dark-1280/{p}.png")
    w, h = l.size
    img = Image.new("RGB", (w * 2 + 24, h + 40), "#0b1220")
    img.paste(l, (0, 40))
    img.paste(r, (w + 24, 40))
    d = ImageDraw.Draw(img)
    d.text((12, 12), f"BEFORE – {p} (dark) – {b[p]['dark-1280']} violations", fill="#fca5a5", font=font)
    d.text((w + 36, 12), f"AFTER – {p} (dark) – {a[p]['dark-1280']} violations", fill="#86efac", font=font)
    img.thumbnail((2200, 2200))
    img.save(f"{OUT}/{p}.png")
shutil.copytree(OUT, PUB, dirs_exist_ok=True)
json.dump({"worst": worst, "before": {r: tot_b[r] for r in RUNS}, "after": {r: tot_a[r] for r in RUNS},
           "per_route": {p: {"before": b[p], "after": a.get(p, {})} for p in b}}, open(f"{PUB}/summary.json", "w"), indent=1)
open("/app/docs/ux/CONTRAST.md", "w").write(
    "# Night-mode contrast – before / after\n\nWCAG 2.2 AA: text 4.5:1 (3:1 large), non-text UI, borders and focus indicators 3:1, disabled labels 3:1.\n"
    "Checked by `scripts/check_contrast.py` (axe-core `color-contrast` + computed contrast of resting, hover and keyboard-focus states of a sample "
    "of buttons, button links, tabs, switches, inputs and status dots) on every route of the layout checker, dark and light, 1280 and 390 wide.\n\n"
    "## Root cause\n\n- Dark theme inverts palette shades 400–950 into light colours; white or dark-slate text on those solid fills "
    "(role pill, toasts, badges) dropped to 1.1–2:1.\n- `bg-white` is not a theme variable – white panels stayed white in dark mode under light text.\n"
    "- Control borders (`--iv-border-strong`) were 1.4:1 (light) and 1.9–2.4:1 (dark); the primary fill (#2597B2) gave white text 3.4:1, destructive 3.8:1.\n"
    "- Disabled and dimmed items used 45–60 % opacity (labels ≈2:1); `outline-none` utilities removed focus rings; status dots 1.5–2.5:1.\n\n"
    "## Fix (tokens / variants – applies everywhere)\n\n`--iv-control-border`, `--iv-outline-border`, `--iv-placeholder`, `--iv-disabled-*`, darker `--iv-grad-brand` and "
    "`--iv-grad-danger`; one dark-ink rule for light fills in dark mode; dark `bg-white`; light-mode 700 shade under white text on mid fills; "
    "`.iv-dimmed` instead of opacity; dashed disabled buttons with readable labels (reason tooltips unchanged); `:focus-visible` ring cannot be removed; "
    "status-dot shades 3:1.\n\n## Violations by route (axe + computed)\n\n" + "\n".join(rows) +
    "\n\n## Worst 6 screens (dark, 1280) – before / after\n\n" + "\n".join(f"![{p}](screens/contrast/{p}.png)" for p in worst) + "\n")
print("worst:", worst)
print(rows[-1])
