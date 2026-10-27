#!/usr/bin/env python3
"""Catalog tree screenshots + timings (headless, no testing agent).
Rerun: SHOT_BASE=https://<preview-host> SHOT_EMAIL=demo@ironvision.ai SHOT_PASSWORD=... python3 scripts/catalog_tree_shots.py
Output: docs/screenshots/catalog_tree/*.png and timings.json."""
import asyncio
import json
import os

import httpx
from playwright.async_api import async_playwright

BASE = os.environ["SHOT_BASE"].rstrip("/")
EMAIL, PW = os.environ["SHOT_EMAIL"], os.environ["SHOT_PASSWORD"]
OUT = "/app/docs/screenshots/catalog_tree"


async def shot(page, name):
    await page.screenshot(path=f"{OUT}/{name}.png", full_page=False)
    print("shot", name)


async def main():
    os.makedirs(OUT, exist_ok=True)
    tok = httpx.post(f"{BASE}/api/v1/auth/login", json={"email": EMAIL, "password": PW}, timeout=60).json()["access_token"]
    sid = httpx.get(f"{BASE}/api/v1/systems", headers={"Authorization": f"Bearer {tok}"}, timeout=60).json()[0]["id"]
    t = {}
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
        await page.goto(BASE + "/login")
        await page.fill("input[type=email]", EMAIL)
        await page.fill("input[type=password]", PW)
        await page.keyboard.press("Enter")
        await page.wait_for_url(lambda u: "/login" not in u, timeout=30000)
        await page.evaluate("Object.keys(sessionStorage).filter(k => k.startsWith('aegis.catalogTree')).forEach(k => sessionStorage.removeItem(k))")
        for i in range(3):  # initial render: navigation start → 20 families visible (incl. API fetch of the full catalog)
            await page.goto(BASE + "/catalog")
            await page.evaluate("Object.keys(sessionStorage).filter(k => k.startsWith('aegis.catalogTree')).forEach(k => sessionStorage.removeItem(k))")
            await page.wait_for_selector("[data-testid=tree-family-sr]", state="attached", timeout=60000)
            t.setdefault("initial_render_ms", []).append(await page.evaluate("Math.round(performance.now())"))
            t.setdefault("api_load_ms", []).append(await page.evaluate("window.__catalogTreeLoadMs"))
        await shot(page, "01_collapsed_families")
        await page.click("[data-testid=tree-family-toggle-ac]")
        await page.wait_for_selector("[data-testid=tree-control-ac-2]")
        await shot(page, "02_family_expanded")
        await page.click("[data-testid=tree-control-toggle-ac-2]")
        await page.wait_for_selector("[data-testid=tree-enhancement-ac-2\\.1]")
        await page.locator("[data-testid=tree-control-ac-2]").scroll_into_view_if_needed()
        await shot(page, "03_control_enhancements_expanded")
        await page.click("[data-testid=catalog-tree-withdrawn]")
        for i in range(3):  # Expand All on the full catalog incl. withdrawn (1,196 nodes as loaded)
            await page.click("[data-testid=catalog-tree-collapse-all]")
            ms = await page.evaluate("""() => new Promise(res => { const t0 = performance.now();
                document.querySelector('[data-testid=catalog-tree-expand-all]').click();
                const chk = () => document.querySelector('[data-testid="tree-enhancement-sr-12"], [data-testid="tree-control-sr-12"]') ? requestAnimationFrame(() => res(Math.round(performance.now() - t0))) : requestAnimationFrame(chk); chk(); })""")
            t.setdefault("expand_all_ms", []).append(ms)
        t["nodes_rendered_after_expand_all"] = await page.locator("[role=treeitem]").count()
        await page.click("[data-testid=catalog-tree-collapse-all]")
        await page.click("[data-testid=catalog-tree-withdrawn]")
        await page.fill("[data-testid=catalog-tree-search]", "AC-02(01)")
        await page.wait_for_selector("[data-testid=tree-enhancement-ac-2\\.1]")
        await shot(page, "04_search_result_id")
        await page.fill("[data-testid=catalog-tree-search]", "remote access")
        await page.wait_for_timeout(500)
        await shot(page, "05_search_result_keyword")
        await page.fill("[data-testid=catalog-tree-search]", "")
        await page.wait_for_timeout(400)
        await page.goto(BASE + f"/catalog?system={sid}")
        await page.wait_for_selector("[data-testid=tree-family-ac]")
        await page.select_option("[data-testid=catalog-tree-filter-implementation_status]", "implemented")
        await page.click("[data-testid=catalog-tree-expand-all]")
        await page.wait_for_timeout(400)
        await shot(page, "06_filters_system_context")
        await page.goto(BASE + "/catalog")
        await page.wait_for_selector("[data-testid=tree-family-ac]")
        await page.click("[data-testid=catalog-tree-collapse-all]")
        await page.click("[data-testid=tree-family-toggle-sc]")
        await page.click("[data-testid=tree-control-toggle-sc-7]")
        await page.locator("[data-testid=tree-enhancement-sc-7\\.5]").scroll_into_view_if_needed()
        await page.click("[data-testid=tree-open-sc-7\\.5]")
        await page.wait_for_selector("[data-testid=control-detail-drawer]")
        await page.wait_for_selector("[data-testid=control-detail-title]:not(:has-text('Loading'))")
        await shot(page, "07_details_open")
        await page.click("[data-testid=control-detail-close-btn]")
        await page.wait_for_timeout(400)
        t["state_preserved_after_close"] = (await page.locator("[data-testid=tree-enhancement-sc-7\\.5]").count() == 1
                                            and await page.get_attribute("[data-testid=tree-family-sc]", "aria-expanded") == "true")
        await shot(page, "08_details_closed_state_preserved")
        await page.goto(BASE + "/catalog")  # reload: expansion restored from session storage
        await page.wait_for_selector("[data-testid=tree-enhancement-sc-7\\.5]", timeout=20000)
        t["state_restored_after_reload"] = True
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.wait_for_timeout(400)
        t["mobile_doc_scroll_width"] = await page.evaluate("document.documentElement.scrollWidth")
        await shot(page, "09_mobile_390")
        await page.click("[data-testid=catalog-tree-collapse-all]")
        await page.click("[data-testid=tree-family-toggle-ac]")
        await shot(page, "10_mobile_390_family_expanded")
        await b.close()
    for k in ("initial_render_ms", "api_load_ms", "expand_all_ms"):
        t[k + "_median"] = sorted(t[k])[len(t[k]) // 2]
    json.dump(t, open(f"{OUT}/timings.json", "w"), indent=1)
    print(json.dumps(t))


asyncio.run(main())
