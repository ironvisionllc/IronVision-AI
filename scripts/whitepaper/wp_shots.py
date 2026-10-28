#!/usr/bin/env python3
"""Whitepaper screenshots (25) from the shared SYNTHETIC demo – no AI calls, read-only except persona switch.
Run: python3 scripts/whitepaper/wp_shots.py → docs/screenshots/wp-2026-10/"""
import asyncio
import os
import sys

from playwright.async_api import async_playwright

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "demo_video"))
from record_demo import BASE, lookup  # noqa: E402

OUT = "/app/docs/screenshots/wp-2026-10"


def stig_run():
    import httpx
    c = httpx.Client(base_url=BASE + "/api/v1", timeout=60)
    r = c.post("/auth/demo-login", json={})
    if r.status_code == 429:
        r = c.post("/auth/login", json={"email": "demo@ironvision.ai", "password": os.environ.get("DEMO_PASSWORD", "IronVisionDemo!2026")})
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    hist = c.get("/import-center/history", headers=h).json()["items"]
    return next((x["id"] for x in hist if x["kind"] == "ingest" and x["file_name"].endswith((".ckl", ".cklb"))), None)


async def main():
    os.makedirs(OUT, exist_ok=True)
    ids, stig = lookup(), stig_run()
    L, P = ids["LTP"], ids["POLICY"]
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        page = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()

        async def shot(name, path=None, wait="main", action=None):
            try:
                if path:
                    await page.goto(BASE + path)
                await page.wait_for_selector(wait, timeout=45000)
                await page.wait_for_load_state("networkidle", timeout=20000)
                if action:
                    await action()
                await page.wait_for_timeout(900)
                await page.screenshot(path=f"{OUT}/{name}.png")
                print("ok", name, flush=True)
            except Exception as e:  # keep going; report misses
                print("MISS", name, str(e)[:120], flush=True)

        await shot("01_login", "/login", '[data-testid="demo-login-btn"]')
        await page.click('[data-testid="demo-login-btn"]')
        await page.wait_for_url(lambda u: "/login" not in u, timeout=60000)
        await page.locator('[data-testid="acting-as-select"]').select_option("isso")
        await page.wait_for_timeout(2500)
        await page.goto(f"{BASE}/systems/{L}")
        await page.wait_for_timeout(2000)

        async def open_roles():
            await page.click('[data-testid="acting-as"]')
        await shot("02_role_switcher", None, '[data-testid="acting-as"]', open_roles)
        await page.keyboard.press("Escape")
        await shot("03_rmf_overview", "/rmf-workflow")
        await shot("04_dashboard", "/dashboard")
        await shot("05_categorize", "/rmf/categorize")
        await shot("07_prepare", "/rmf/prepare")
        await shot("08_select", "/rmf/select")
        await shot("09_control_ac2", f"/systems/{L}/controls/ac-2")
        await shot("10_workbench", f"/systems/{L}/controls")
        await shot("11_inventory", "/inventory")
        await shot("12_policy_mappings", f"/policy-auditor/{P}", '[data-testid="policy-detail-page"]')
        await shot("13_stig_run", f"/ingest-runs/{stig}" if stig else "/evidence-sources")
        await shot("14_sca_workspace", "/assess/workspace")
        await shot("15_test_results", "/test-results")
        await shot("16_mapping_review", "/mapping-review")
        await shot("17_authorize", f"/systems/{L}/authorization")
        await shot("18_poam", "/poams")
        await shot("19_evidence_ledger", "/evidence-ledger")
        await shot("20_evidence_sources", "/evidence-sources")
        await shot("21_emass_hub", "/emass")
        await shot("22_import_center", f"/systems/{L}/import-center")
        await shot("23_manage_imported", f"/import-center/manage/ingest/{ids['SCAN']}", '[data-testid="manage-import-page"]')

        async def expand():
            await page.click('[data-testid="coverage-toggle-ac-2"]')
            await page.wait_for_timeout(1200)
            await page.locator('[data-testid="coverage-toggle-ac-2"]').scroll_into_view_if_needed()
        await shot("24_policy_coverage", f"/policy-auditor/{P}", '[data-testid="coverage-toggle-ac-2"]', expand)

        async def reading():
            await page.locator('[data-testid="policy-reading-report"]').scroll_into_view_if_needed()
        await shot("25_reading_report", None, '[data-testid="policy-reading-report"]', reading)
        await page.locator('[data-testid="acting-as-select"]').select_option("issm")
        await page.wait_for_timeout(2500)
        await shot("06_portfolio", "/portfolio")
        await b.close()


asyncio.run(main())
