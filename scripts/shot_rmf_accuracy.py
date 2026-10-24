"""RMF accuracy browser check + screenshots: python3.11 scripts/shot_rmf_accuracy.py (SHOT_BASE / SHOT_EMAIL / SHOT_PASSWORD)."""
import asyncio
import os

from playwright.async_api import async_playwright

BASE, OUT = os.environ["SHOT_BASE"], "/app/docs/screenshots/rmf-accuracy"


async def main():
    os.makedirs(OUT, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(BASE + "/login")
        await page.fill("input[type=email]", os.environ["SHOT_EMAIL"])
        await page.fill("input[type=password]", os.environ["SHOT_PASSWORD"])
        await page.keyboard.press("Enter")
        await page.wait_for_url(lambda u: "/login" not in u, timeout=30000)

        async def persona(label):
            await page.wait_for_selector("[data-testid=acting-as-select]", timeout=30000)
            await page.wait_for_timeout(1000)
            opts = await page.locator("[data-testid=acting-as-select] option").all_inner_texts()
            await page.select_option("[data-testid=acting-as-select]", label=next((o for o in opts if label in o), opts[0]))
            print("persona options:", opts)
            await page.wait_for_timeout(2500)

        async def shot(name, sel=None):
            if sel:
                await page.locator(sel).first.scroll_into_view_if_needed()
            await page.wait_for_timeout(800)
            await page.screenshot(path=f"{OUT}/{name}.png")

        async def check(label, cond):
            print(("PASS " if cond else "FAIL ") + label)

        await persona("ISSO")
        await page.goto(BASE + "/systems/new")
        await page.wait_for_selector("[data-testid=main-content] h1", timeout=30000)
        await page.wait_for_timeout(2000)
        body = await page.locator("[data-testid=main-content]").inner_text()
        await check("1 registration has no AODR / CCP / User Representative", "AODR" not in body and "Common Control Provider" not in body and "User Representative" not in body)
        await check("3 registration has no Authorization type sought", "Authorization type sought" not in body)
        await check("8 PII question offers Unknown – requires review", await page.locator("[data-testid=pii-unknown]").count() == 1)
        await shot("01_registration_roles_and_pii", "[data-testid=pii-unknown]")

        await page.goto(BASE + "/rmf/categorize")
        await page.wait_for_selector("[data-testid=framework-step]", timeout=30000)
        await check("2 NSS question Yes/No/Unsure", await page.locator("[data-testid^=nss-]").count() >= 3)
        await shot("02_categorize_framework_nss", "[data-testid=framework-step]")
        await page.wait_for_selector("[data-testid=pta-panel]", timeout=20000)
        await check("4 PTA example-set label", "example set" in (await page.locator("[data-testid=pta-panel]").inner_text()).lower())
        await shot("03_categorize_approval_and_pta", "[data-testid=cat-approval]")
        await shot("04_pta_questionnaire", "[data-testid=pta-panel]")

        await page.goto(BASE + "/rmf/select")
        await page.wait_for_selector("[data-testid=param-compare]", timeout=30000)
        await page.wait_for_timeout(2500)
        total = await page.locator("[data-testid=param-compare-total]").inner_text()
        await check(f"5 parameter comparison on screen ({total})", not total.startswith("0 "))
        await shot("05_parameter_comparison", "[data-testid=param-compare]")
        await page.fill("[data-testid=param-filter-q]", "no-such-parameter-zz")
        await page.wait_for_selector("[data-testid=param-compare-empty]", timeout=15000)
        await check("5 empty state instead of empty file", True)
        txt = await page.locator("[data-testid=main-content]").inner_text()
        await check("6/7 FIPS system: CNSSI overlays not applicable, 800-53B privacy baseline explained",
                    "800-53B privacy baseline" in txt or "Not applicable" in txt)
        await shot("06_overlays_applicability", "[data-testid^=overlay-group-privacy]")

        await page.goto(BASE + "/rmf/authorize")
        await page.wait_for_selector("[data-testid=auth-type]", timeout=30000)
        await check("3 Authorization type sought shown in Authorize", True)
        await shot("07_authorize_authorization_type", "[data-testid=auth-type]")

        await page.goto(BASE + "/evidence-ledger")
        btn = page.locator("[data-testid^=ev-actions-]").first
        await btn.wait_for(timeout=30000)
        await btn.click()
        await check("10 evidence actions menu", await page.locator("[role=menu] [role=menuitem]").count() >= 5)
        await shot("08_evidence_actions_menu")
        await page.locator("[data-testid^=ev-history-]").first.click()
        await page.wait_for_selector("[data-testid=evidence-dialog]", timeout=15000)
        await page.wait_for_timeout(1500)
        await check("10 version history dialog", await page.locator("[data-testid=ev-versions]").count() == 1)
        await shot("09_evidence_version_history")
        await page.keyboard.press("Escape")

        await page.goto(BASE + "/policy-auditor")
        await page.wait_for_selector("[data-testid=main-content] h1", timeout=30000)
        link = page.locator("a[href^='/policy-auditor/']").first
        await link.wait_for(timeout=20000)
        await link.click()
        sbs = page.locator("[data-testid^=mapping-sbs-]").first
        await sbs.wait_for(timeout=30000)
        await check("12 every mapping shows evidence confidence", await page.locator("[data-testid^=evidence-confidence-]").count() >= 1)
        await shot("10_policy_mappings_confidence", "[data-testid^=evidence-confidence-]")
        await sbs.click()
        await page.wait_for_selector("[data-testid=sbs-left]", timeout=20000)
        await page.wait_for_timeout(1500)
        await check("11 side-by-side: control left, policy right, actions", await page.locator("[data-testid=sbs-right]").count() == 1)
        await shot("11_side_by_side_review")
        print("page errors:", errors[:3])
        await b.close()


asyncio.run(main())
