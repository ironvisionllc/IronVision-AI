"""Header compaction interaction check: popover keyboard/Esc, next-action bar collapse/dismiss, page scoping."""
import asyncio
import os

from playwright.async_api import async_playwright

BASE = os.environ["SHOT_BASE"]
OUT = "/app/docs/screenshots/header-compact"


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
        await page.goto(BASE + "/login")
        await page.fill("input[type=email]", os.environ["SHOT_EMAIL"])
        await page.fill("input[type=password]", os.environ["SHOT_PASSWORD"])
        await page.keyboard.press("Enter")
        await page.wait_for_url(lambda u: "/login" not in u, timeout=30000)
        await page.evaluate("Object.keys(localStorage).filter(k => k.startsWith('iv-next-bar:')).forEach(k => localStorage.removeItem(k))")
        await page.goto(BASE + "/systems")
        await page.wait_for_selector("[data-testid=rmf-bar]", timeout=30000)
        print("bar on /systems:", await page.locator("[data-testid=rmf-next-action]").inner_text())
        await page.wait_for_timeout(3800)
        await page.screenshot(path=f"{OUT}/after_systems_bar_1440x900.png")
        await page.click("[data-testid=rmf-bar-toggle]")
        print("collapsed bar text:", (await page.locator("[data-testid=rmf-bar]").inner_text()).strip())
        await page.screenshot(path=f"{OUT}/after_systems_bar_collapsed_1440x900.png")
        chip = page.locator("[data-testid=sandbox-chip]")
        await chip.focus()
        await page.keyboard.press("Enter")
        pop = page.locator("[data-testid=sandbox-popover]")
        await pop.wait_for(timeout=5000)
        print("popover role/label:", await pop.get_attribute("role"), "|", await pop.get_attribute("aria-label"), "| expanded:", await chip.get_attribute("aria-expanded"))
        print("popover focused:", await page.evaluate("document.activeElement && document.activeElement.dataset.testid"))
        print("popover text:", " / ".join(t.strip() for t in (await pop.inner_text()).split("\n") if t.strip()))
        await page.screenshot(path=f"{OUT}/after_sandbox_popover_1440x900.png")
        await page.keyboard.press("Escape")
        print("after Esc popover count:", await pop.count(), "| focus back on chip:", await page.evaluate("document.activeElement && document.activeElement.dataset.testid"))
        await chip.click()
        await page.click("[data-testid=sandbox-reset-btn]")
        print("reset confirmation modal:", await page.locator("[data-testid=sandbox-reset-modal]").count())
        await page.click("[data-testid=sandbox-reset-cancel]")
        await page.click("[data-testid=rmf-bar-dismiss]")
        await page.reload()
        await page.wait_for_selector("[data-testid=main-content] h1", timeout=30000)
        await page.wait_for_timeout(1500)
        print("bar after dismiss+reload:", await page.locator("[data-testid=rmf-bar]").count())
        for path in ("/rmf-workflow", "/test-results", "/portfolio"):
            await page.evaluate("Object.keys(localStorage).filter(k => k.startsWith('iv-next-bar:')).forEach(k => localStorage.removeItem(k))")
            await page.goto(BASE + path)
            await page.wait_for_selector("[data-testid=main-content]", timeout=30000)
            await page.wait_for_timeout(1500)
            print(f"bar on {path}:", await page.locator("[data-testid=rmf-bar]").count())
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.goto(BASE + "/test-results")
        await page.wait_for_selector("[data-testid=main-content] h1", timeout=30000)
        r = await page.evaluate("""() => { const o = document.querySelector('[data-testid=header-logout-btn]').getBoundingClientRect();
          const h = document.querySelector('[data-testid=app-header]').getBoundingClientRect(); return {logout_right: Math.round(o.right), header_h: Math.round(h.height), vw: innerWidth}; }""")
        print("mobile header:", r)
        await page.screenshot(path=f"{OUT}/after_test-results_390x844.png")
        await b.close()


asyncio.run(main())
