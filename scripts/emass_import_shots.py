#!/usr/bin/env python3
"""eMASS Import Center screenshots (headless, no testing agent). Works on a fresh SYNTHETIC system it registers itself – demo systems untouched.
Rerun: SHOT_BASE=https://<preview-host> SHOT_EMAIL=demo@ironvision.ai SHOT_PASSWORD=... python3 scripts/emass_import_shots.py
Output: docs/screenshots/emass_import/*.png"""
import asyncio
import io
import os
import uuid

import httpx
import openpyxl
from playwright.async_api import async_playwright

BASE = os.environ["SHOT_BASE"].rstrip("/")
EMAIL, PW = os.environ["SHOT_EMAIL"], os.environ["SHOT_PASSWORD"]
OUT = "/app/docs/screenshots/emass_import"
TMP = "/tmp/emass_shots"


async def shot(page, name):
    await page.wait_for_timeout(400)
    await page.screenshot(path=f"{OUT}/{name}.png", full_page=False)
    print("shot", name)


def main_api():
    c = httpx.Client(base_url=BASE + "/api/v1", timeout=120)
    tok = c.post("/auth/login", json={"email": EMAIL, "password": PW}).json()["access_token"]
    c.headers["Authorization"] = f"Bearer {tok}"
    r = c.post("/systems", json={"name": "SYNTHETIC Migration Demo", "acronym": "MIG" + uuid.uuid4().hex[:3].upper(), "processes_pii": False,
                                 "baseline_key": "moderate", "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}]})
    r.raise_for_status()
    sid = r.json()["id"]
    os.makedirs(TMP, exist_ok=True)
    files = {}
    for t in ("slcm", "ppsm", "categorization"):
        files[t] = f"{TMP}/SYNTHETIC_{t}.xlsx"
        open(files[t], "wb").write(c.get(f"/emass-imports/samples/{t}").content)
    imp = c.post("/emass-imports", files={"file": ("ppsm.xlsx", open(files["ppsm"], "rb").read())}, data={"system_id": sid}).json()  # baseline PPSM → later conflicts
    c.post(f"/emass-imports/{imp['id']}/target", json={"action": "update", "system_id": sid, "report_type": "ppsm"}).raise_for_status()
    c.post(f"/emass-imports/{imp['id']}/apply").raise_for_status()
    wb = openpyxl.load_workbook(files["ppsm"])
    wb["PPSM"]["G9"] = "SYNTHETIC web front end – now also serves the public API"
    wb["PPSM"]["E10"] = "11. Enclave GW to Enclave (In); 12. Enclave to Enclave GW (Out)"
    b = io.BytesIO()
    wb.save(b)
    files["ppsm_changed"] = f"{TMP}/SYNTHETIC_ppsm_changed.xlsx"
    open(files["ppsm_changed"], "wb").write(b.getvalue())
    return sid, files


async def main():
    os.makedirs(OUT, exist_ok=True)
    sid, files = main_api()
    center = f"{BASE}/systems/{sid}/emass-import"
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
        await page.goto(BASE + "/login")
        await page.fill("input[type=email]", EMAIL)
        await page.fill("input[type=password]", PW)
        await page.keyboard.press("Enter")
        await page.wait_for_url(lambda u: "/login" not in u, timeout=30000)
        await page.goto(center)
        await page.wait_for_selector("[data-testid=import-ai-notice]", timeout=60000)
        await shot(page, "01_import_center")
        await page.set_input_files("[data-testid=import-file-input]", [files["slcm"], files["categorization"], files["ppsm_changed"]])
        await page.click("[data-testid=import-upload-btn]")
        await page.wait_for_selector("[data-testid=import-batch-row-2]", timeout=60000)
        await shot(page, "02_batch_detection")
        ppsm_href = await page.get_attribute("[data-testid=import-batch-open-2]", "href")
        await page.click("[data-testid=import-batch-open-0]")
        await page.wait_for_selector("[data-testid=emass-import-prompt]", timeout=60000)
        await shot(page, "03_detection_prompt")
        await page.click("[data-testid=import-update-this]")
        await page.wait_for_selector("[data-testid=emass-import-review]", timeout=60000)
        await shot(page, "04_preview_imported_preselected")
        for t in ("import-not-in-system", "import-invalid", "import-exceptions", "import-duplicates", "import-not-imported"):
            for d in await page.locator(f"[data-testid={t}]").all():
                await d.evaluate("e => e.open = true")
        await page.locator("[data-testid=emass-import-report]").scroll_into_view_if_needed()
        await shot(page, "05_exception_queue")
        page.once("dialog", lambda d: asyncio.ensure_future(d.accept()))
        await page.click("[data-testid=import-apply-btn]")
        await page.wait_for_selector("[data-testid=import-revert-btn]", timeout=60000)
        await page.goto(BASE + ppsm_href)
        await page.wait_for_selector("[data-testid=import-update-this]", timeout=60000)
        await page.click("[data-testid=import-update-this]")
        await page.wait_for_selector("[data-testid=emass-import-review]", timeout=60000)
        await page.locator("[data-testid=import-section-ppsm]").scroll_into_view_if_needed()
        await shot(page, "06_conflicts_current_vs_imported")
        page.once("dialog", lambda d: asyncio.ensure_future(d.accept()))
        await page.click("[data-testid=import-apply-btn]")
        await page.wait_for_selector("[data-testid=import-completion-report]", timeout=60000)
        await page.click("[data-testid=import-completion-report]")
        await page.wait_for_selector("[data-testid=migration-coverage]", timeout=60000)
        await shot(page, "07_completion_report")
        await page.goto(center)
        await page.wait_for_selector("[data-testid=ppsm-table] table", timeout=60000)
        await page.locator("[data-testid=ppsm-table]").scroll_into_view_if_needed()
        await shot(page, "08_ppsm_table")
        await page.goto(BASE + "/systems/new")
        await page.wait_for_selector("[data-testid=register-start]", timeout=60000)
        await page.click("[data-testid=register-start-copy]")
        await shot(page, "09_registration_choice")
        await b.close()
    print("system", sid)


asyncio.run(main())
