#!/usr/bin/env python3
"""Import Center screenshots (headless, no testing agent) on a fresh SYNTHETIC system.
Rerun: SHOT_BASE=https://<preview-host> SHOT_EMAIL=... SHOT_PASSWORD=... python3 scripts/import_center_shots.py → docs/screenshots/import_center/"""
import asyncio
import os
import shutil
import uuid

import httpx
from playwright.async_api import async_playwright

BASE = os.environ["SHOT_BASE"].rstrip("/")
EMAIL, PW = os.environ["SHOT_EMAIL"], os.environ["SHOT_PASSWORD"]
OUT, TMP = "/app/docs/screenshots/import_center", "/tmp/ic_shots"
FX = "/app/backend/tests/fixtures/emass"


async def shot(page, name):
    await page.wait_for_timeout(400)
    await page.screenshot(path=f"{OUT}/{name}.png", full_page=False)
    print("shot", name)


def setup():
    c = httpx.Client(base_url=BASE + "/api/v1", timeout=120)
    c.headers["Authorization"] = "Bearer " + c.post("/auth/login", json={"email": EMAIL, "password": PW}).json()["access_token"]
    sid = c.post("/systems", json={"name": "SYNTHETIC Import Center Demo", "acronym": "IMP" + uuid.uuid4().hex[:3].upper(), "processes_pii": False,
                                   "baseline_key": "moderate", "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}]}).json()["id"]
    os.makedirs(TMP, exist_ok=True)
    files = [f"{TMP}/IV-eMASS-formatted-implementation-plan.xlsx", f"{TMP}/SYNTHETIC_web01.ckl", f"{TMP}/SYNTHETIC_ppsm.xlsx", f"{TMP}/notes.bin"]
    shutil.copy(f"{FX}/IV_eMASS_implementation_plan_user_edited.xlsx", files[0])
    open(files[1], "wb").write(b'<?xml version="1.0"?><CHECKLIST><ASSET><HOST_NAME>syn-web01</HOST_NAME></ASSET><STIGS><iSTIG><STIG_INFO/>'
                               b'<VULN><STATUS>Open</STATUS></VULN><VULN><STATUS>NotAFinding</STATUS></VULN></iSTIG></STIGS></CHECKLIST>')
    open(files[2], "wb").write(c.get("/emass-imports/samples/ppsm").content)
    open(files[3], "wb").write(b"\x00\x01 not a supported file")
    return sid, files


async def main():
    os.makedirs(OUT, exist_ok=True)
    sid, files = setup()
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
        await page.goto(BASE + "/login")
        await page.fill("input[type=email]", EMAIL)
        await page.fill("input[type=password]", PW)
        await page.keyboard.press("Enter")
        await page.wait_for_url(lambda u: "/login" not in u, timeout=30000)
        await page.goto(f"{BASE}/systems/{sid}/controls")
        await page.wait_for_selector("[data-testid=wb-import-emass-btn]", timeout=60000)
        await page.click("[data-testid=wb-import-emass-btn]")
        await page.wait_for_selector("[data-testid=ic-preset]", timeout=60000)
        await shot(page, "01_old_button_opens_center_preset")
        await page.set_input_files("[data-testid=ic-file-input]", files)
        await page.wait_for_selector("[data-testid=ic-file-3]", timeout=90000)
        await page.locator("[data-testid=ic-files]").scroll_into_view_if_needed()
        await shot(page, "02_multi_file_detection_routing")
        await page.click("[data-testid=ic-import-0]")
        await page.wait_for_selector("[data-testid=ic-result-0]", timeout=90000)
        await page.click("[data-testid=ic-import-1]")
        await page.wait_for_selector("[data-testid=ic-result-1]", timeout=90000)
        await shot(page, "03_routed_to_existing_pipelines")
        await page.locator("[data-testid=ic-types]").scroll_into_view_if_needed()
        await shot(page, "04_supported_types_rbac")
        await page.goto(f"{BASE}/systems/{sid}/import-center")
        await page.wait_for_selector("[data-testid^=ic-hist-]", timeout=60000)
        await page.locator("[data-testid=ic-history]").scroll_into_view_if_needed()
        await shot(page, "05_unified_history")
        await page.click("[data-testid=ic-open-0]") if await page.locator("[data-testid=ic-open-0]").count() else None
        await page.goto(f"{BASE}/systems/{sid}/import-center")
        await page.wait_for_selector("[data-testid^=ic-hist-emass-]", timeout=60000)
        await page.locator("[data-testid^=ic-hist-emass-] a").first.click()
        await page.wait_for_selector("[data-testid=import-row-summary]", timeout=60000)
        await shot(page, "06_plan_import_review_counts")
        await page.goto(BASE + "/import-center")
        await page.wait_for_selector("[data-testid=ic-system-select]", timeout=60000)
        await shot(page, "07_org_import_center")
        await b.close()
    print("system", sid)


asyncio.run(main())
