#!/usr/bin/env python3
"""Self-test for check_wrap.py: on the Workbench at 390 px the current markup must give 0 findings and the pre-fix markup (re-created in the page) must be caught (row-wrap + tab-scroll).
Rerun: SHOT_BASE=... SHOT_EMAIL=... SHOT_PASSWORD=... python3 scripts/check_wrap_selftest.py"""
import asyncio, sys
sys.path.insert(0, "/app/scripts")
from check_wrap import MEASURE
from playwright.async_api import async_playwright
B = "https://aegis-rmf-demo.preview.emergentagent.com"
# old markup (before the fix): no min-w-0 on the row button, status as text next to the ID, tabs in a horizontal scroller
OLD = """() => { for (const b of document.querySelectorAll('button[data-testid^=queue-item-]')) { b.classList.remove('min-w-0'); const l1 = b.firstElementChild; l1.classList.remove('whitespace-nowrap','min-w-0'); l1.className += ' justify-between';
  const st = l1.querySelector('[data-testid^=queue-status-]'); st.classList.remove('max-sm:sr-only','truncate','min-w-0'); st.style.whiteSpace='normal'; b.lastElementChild.classList.remove('truncate'); }
  const t = document.querySelector('[data-testid=wb-tabs]'); if (t) { t.classList.remove('hidden','flex-wrap'); t.style.display='flex'; t.style.overflowX='auto'; } }"""
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await (await b.new_context(viewport={"width": 390, "height": 844})).new_page()
        await pg.goto(B + "/login"); await pg.fill("input[type=email]", "demo@ironvision.ai"); await pg.fill("input[type=password]", "IronVisionDemo!2026"); await pg.keyboard.press("Enter")
        await pg.wait_for_url(lambda u: "/login" not in u, timeout=60000)
        await pg.goto(B + "/controls"); await pg.wait_for_selector("[data-testid^=queue-item-]", timeout=30000)
        await pg.click("button[data-testid^=queue-item-]"); await pg.wait_for_selector("[data-testid=wb-tab-select]", timeout=30000); await pg.wait_for_timeout(1500)
        new = await pg.evaluate(MEASURE); print("current markup:", len(new), new[:3])
        await pg.evaluate(OLD); await pg.wait_for_timeout(300)
        old = await pg.evaluate(MEASURE); print("old markup:", len(old), sorted({o['check'] for o in old}), old[:3])
        await b.close()
asyncio.run(main())
