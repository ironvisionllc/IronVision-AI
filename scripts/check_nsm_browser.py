"""No-silent-misses UI check (synthetic demo workspace, no AI calls): reading report, Found it here → Mapping Review proposal,
candidate passage "Use this passage", at 1280 light and 390 dark. Usage: BASE_URL=… python3 scripts/check_nsm_browser.py <policy-id>"""
import asyncio
import json
import os
import sys

from playwright.async_api import async_playwright

BASE = os.environ.get("BASE_URL") or sys.exit("BASE_URL required")
PID = sys.argv[1]


async def run(br, label, theme, w, h):
    ctx = await br.new_context(viewport={"width": w, "height": h})
    page = await ctx.new_page()
    errs, bad = [], []
    page.on("pageerror", lambda e: errs.append(str(e)[:200]))
    page.on("response", lambda r: bad.append(f"{r.status} {r.url.split('/api/v1')[-1][:100]}") if "/api/v1/" in r.url and r.status >= 400 else None)
    out = {"label": label}
    await page.goto(f"{BASE}/login")
    await page.evaluate(f"localStorage.setItem('ironvision.theme', '{theme}')")
    await page.click('[data-testid="demo-login-btn"]')
    await page.wait_for_function("!location.pathname.startsWith('/login')", timeout=20000)
    await page.goto(f"{BASE}/policy-auditor/{PID}")
    await page.wait_for_selector('[data-testid="policy-reading-report"]', timeout=20000)
    out["reading"] = {k: await page.locator(f'[data-testid="reading-{k}"]').inner_text() for k in ("text-extracted", "characters-read", "tables-included", "whole-document-check")}
    out["warnings"] = await page.locator('[data-testid="reading-warnings"] li').all_inner_texts()
    # Found it here: highlight a sentence of the extracted text, grab it, link to AC-2
    await page.evaluate("""() => { const pre = document.querySelector('[data-testid="policy-text"] pre'); const t = pre.firstChild;
        const i = t.textContent.search(/[A-Z][^.\\n]{30,160}\\./); const m = t.textContent.slice(i).match(/[A-Z][^.\\n]{30,160}\\./)[0];
        const r = document.createRange(); r.setStart(t, i); r.setEnd(t, i + m.length); const s = getSelection(); s.removeAllRanges(); s.addRange(r); }""")
    await page.click('[data-testid="found-it-here-grab"]')
    await page.wait_for_selector('[data-testid="found-it-here-selection"]', timeout=5000)
    out["selection"] = (await page.locator('[data-testid="found-it-here-selection"]').inner_text())[:80]
    await page.fill('[data-testid="found-it-here-control"]', "AC-2")
    async with page.expect_response(lambda r: "found-it-here" in r.url) as resp:
        await page.click('[data-testid="found-it-here-send"]')
    r = await resp.value
    out["found_it_here_status"] = r.status
    out["found_it_here_message"] = (await r.json()).get("message")
    tog = page.locator('[data-testid="coverage-toggle-ac-2"]')
    if await tog.count():
        await tog.first.click()
        await page.wait_for_timeout(500)
    cand = page.locator('[data-testid^="use-candidate-"]')
    out["candidate_buttons"] = await cand.count()
    if out["candidate_buttons"]:
        await cand.first.scroll_into_view_if_needed()
        async with page.expect_response(lambda r: "found-it-here" in r.url) as resp2:
            await cand.first.click()
        out["use_candidate_status"] = (await resp2.value).status
    out["overflow_px"] = await page.evaluate("document.documentElement.scrollWidth - innerWidth")
    await page.screenshot(path=f"/tmp/nsm_{label}.png")
    out["page_errors"], out["http_4xx"] = errs, bad
    await ctx.close()
    return out


async def main():
    async with async_playwright() as p:
        br = await p.chromium.launch()
        res = [await run(br, "1280-light", "light", 1280, 800), await run(br, "390-dark", "dark", 390, 844)]
        await br.close()
    print(json.dumps(res, indent=1))


asyncio.run(main())
