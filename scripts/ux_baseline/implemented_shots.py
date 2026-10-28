#!/usr/bin/env python3
"""Screenshots of the implemented redesign (synthetic sandbox) → frontend/public/ux-proposal-assets/implemented/*.png + docs/ux/screens/implemented/."""
import asyncio
import os
import shutil

from playwright.async_api import async_playwright

BASE = os.environ.get("UX_BASE", "https://aegis-rmf-demo.preview.emergentagent.com").rstrip("/")
EMAIL, PW = os.environ.get("UX_EMAIL", "demo@ironvision.ai"), os.environ.get("UX_PASSWORD", "IronVisionDemo!2026")
OUT = "/app/frontend/public/ux-proposal-assets/implemented"
DOCS = "/app/docs/ux/screens/implemented"


async def main():
    os.makedirs(OUT, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
        await page.goto(BASE + "/login")
        await page.fill("input[type=email]", EMAIL)
        await page.fill("input[type=password]", PW)
        await page.keyboard.press("Enter")
        await page.wait_for_url(lambda u: "/login" not in u, timeout=60000)
        await page.evaluate("Object.keys(localStorage).filter(k => k.startsWith('iv.guided.')).forEach(k => localStorage.setItem(k, 'off'))")

        async def shot(name, path, wait=None, after=None):
            await page.goto(BASE + path)
            await page.wait_for_load_state("networkidle")
            if wait:
                await page.wait_for_selector(wait, timeout=30000)
            if after:
                await after()
            await page.wait_for_timeout(1200)
            if await page.locator("[data-testid=guided-first-login-no]").count():
                await page.click("[data-testid=guided-first-login-no]")
            await page.screenshot(path=f"{OUT}/{name}.png")
            print("shot", name)

        async def persona(role):
            await page.goto(BASE + "/my-work")
            await page.wait_for_selector("[data-testid=acting-as-select]")
            await page.select_option("[data-testid=acting-as-select]", value=role)
            await page.wait_for_timeout(2500)

        await shot("dashboard", "/dashboard", "[data-testid=dashboard-page]")
        await shot("navigation", "/rmf/select", "[data-testid=nav-step-select]")
        for role in ("isso", "sca", "issm", "ao"):
            await persona(role)
            await shot(f"mywork_{role}", "/my-work", "[data-testid=my-work-page]")
        await persona("isso")

        async def open_control():
            await page.click("button[data-testid^=queue-item-]")
            await page.wait_for_selector("[data-testid=wb-tabs]")
        await shot("workbench", "/controls", "button[data-testid^=queue-item-]", open_control)
        await shot("import_center", "/import-center")
        await shot("mapping_review", "/mapping-review")
        await shot("sca_workspace", "/assess/workspace")

        async def ssp_check():
            if await page.locator("[data-testid=doc-ssp-check]").count():
                await page.click("[data-testid=doc-ssp-check]")
                await page.wait_for_timeout(2500)
        await shot("generate_ssp", "/rmf/authorize", None, ssp_check)
        await shot("guided_off", "/rmf/categorize")
        await page.evaluate("Object.keys(localStorage).filter(k => k.startsWith('iv.guided.')).forEach(k => localStorage.setItem(k, 'on'))")
        await shot("guided_on", "/rmf/categorize", "[data-testid=guided-panel]")
        await page.evaluate("Object.keys(localStorage).filter(k => k.startsWith('iv.guided.')).forEach(k => localStorage.setItem(k, 'off'))")
        await b.close()
    shutil.copytree(OUT, DOCS, dirs_exist_ok=True)


asyncio.run(main())
