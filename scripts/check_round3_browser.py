"""Round-3 browser checks (synthetic demo workspace): Attach evidence (.txt document) from a control's Evidence tab at 1280 light and
390 dark; policy stale-auditor badge + keyword-only labels at 390 dark; Workbench tab switching at 390 with no 4xx list requests."""
import asyncio
import json
import os
import sys

from playwright.async_api import async_playwright

BASE = os.environ.get("BASE_URL") or sys.exit("BASE_URL required")
SID = sys.argv[1]
PID = sys.argv[2]
FILE = "/tmp/attach-test.txt"


async def login(page, theme):
    await page.goto(f"{BASE}/login")
    await page.evaluate(f"localStorage.setItem('ironvision.theme', '{theme}')")
    await page.click('[data-testid="demo-login-btn"]')
    await page.wait_for_function("!location.pathname.startsWith('/login')", timeout=20000)


async def attach(page, out):
    await page.goto(f"{BASE}/systems/{SID}/controls/ac-2?tab=evidence")
    await page.wait_for_selector('[data-testid="wb-attach-evidence-btn"]', timeout=20000)
    await page.click('[data-testid="wb-attach-evidence-btn"]')
    await page.wait_for_selector('[data-testid="wb-attach-evidence-dialog"]', timeout=5000)
    name = f"attach-{out['label']}.txt"
    with open(FILE, "w") as f:
        f.write(f"Synthetic account review note {out['label']}\n")
    await page.set_input_files('[data-testid="wb-attach-evidence-input"]', files=[{"name": name, "mimeType": "text/plain", "buffer": open(FILE, "rb").read()}])
    try:
        await page.wait_for_selector('[data-testid="wb-attach-evidence-progress"]', timeout=2000)
        out["progress_seen"] = True
    except Exception:
        out["progress_seen"] = "too fast to observe (small file)"
    await page.wait_for_selector('[data-testid="wb-attach-evidence-done"], [data-testid="wb-attach-evidence-error"]', timeout=20000)
    out["error"] = await page.locator('[data-testid="wb-attach-evidence-error"]').all_inner_texts()
    out["dialog_open_after"] = await page.locator('[data-testid="wb-attach-evidence-dialog"]').count()
    out["done_text"] = (await page.locator('[data-testid="wb-attach-evidence-done"]').all_inner_texts() or [""])[0][:220]
    await page.wait_for_timeout(1500)
    out["listed_on_control"] = name in await page.inner_text("body")
    await page.screenshot(path=f"/tmp/r3_attach_{out['label']}.png")


async def policy(page, out):
    await page.goto(f"{BASE}/policy-auditor/{PID}")
    await page.wait_for_selector('[data-testid="policy-text"]', timeout=20000)
    await page.wait_for_timeout(1500)
    b = page.locator('[data-testid="policy-stale-badge"]')
    out["stale_badge"] = await b.count()
    if out["stale_badge"]:
        box = await b.bounding_box()
        out["stale_badge_in_viewport"] = bool(box and box["x"] >= 0 and box["x"] + box["width"] <= 391)
        out["stale_badge_colors"] = await b.evaluate("e => [getComputedStyle(e).color, getComputedStyle(e).backgroundColor]")
    body = await page.inner_text("body")
    out["ai_unavailable_label"] = "AI unavailable" in body or "keyword check only" in body
    out["page_overflow_px"] = await page.evaluate("document.documentElement.scrollWidth - innerWidth")
    await page.screenshot(path=f"/tmp/r3_policy_{out['label']}.png")


async def tabs(page, out, bad):
    await page.goto(f"{BASE}/systems/{SID}/controls/ac-2?tab=requirements")
    await page.wait_for_selector('[data-testid="wb-tab-select"]', timeout=20000)
    for _ in range(3):
        for k in ("implementation", "evidence", "assessment", "findings", "monitoring", "requirements"):
            await page.select_option('[data-testid="wb-tab-select"]', k)
            await page.wait_for_timeout(250)
    for cid in ("ac-3", "ac-2"):  # switch controls too (list reload with the saved filters)
        await page.goto(f"{BASE}/systems/{SID}/controls/{cid}?tab=evidence")
        await page.wait_for_selector('[data-testid="wb-tab-select"]', timeout=20000)
    await page.wait_for_timeout(1500)
    out["list_4xx"] = list(bad)


async def main():
    res = []
    async with async_playwright() as p:
        br = await p.chromium.launch()
        for label, theme, w, h in (("1280-light", "light", 1280, 800), ("390-dark", "dark", 390, 844)):
            ctx = await br.new_context(viewport={"width": w, "height": h})
            page = await ctx.new_page()
            bad = []
            page.on("response", lambda r, bad=bad: bad.append(f"{r.status} {r.url.split('/api/v1')[-1][:120]}")
                    if "/api/v1/" in r.url and r.status >= 400 and "workbench" in r.url else None)
            errs = []
            page.on("pageerror", lambda e, errs=errs: errs.append(str(e)[:200]))
            out = {"label": label}
            await login(page, theme)
            await attach(page, out)
            await policy(page, out)
            if w == 390:
                await tabs(page, out, bad)
            out["page_errors"] = errs
            res.append(out)
            await ctx.close()
        await br.close()
    print(json.dumps(res, indent=1))


asyncio.run(main())
