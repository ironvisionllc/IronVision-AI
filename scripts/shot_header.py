"""Header-compaction screenshots: python3 scripts/shot_header.py before|after"""
import asyncio
import os
import sys

from playwright.async_api import async_playwright

BASE = os.environ["SHOT_BASE"]
EMAIL, PW = os.environ["SHOT_EMAIL"], os.environ["SHOT_PASSWORD"]
OUT = "/app/docs/screenshots/header-compact"
SIZES = [(1280, 800), (1440, 900), (1920, 1080), (390, 844)]
PAGES = [("controls", "/controls"), ("test-results", "/test-results")]


async def main(tag: str):
    os.makedirs(OUT, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()
        await page.goto(BASE + "/login")
        await page.fill("input[type=email]", EMAIL)
        await page.fill("input[type=password]", PW)
        await page.keyboard.press("Enter")
        await page.wait_for_url(lambda u: "/login" not in u, timeout=30000)
        for w, h in SIZES:
            await page.set_viewport_size({"width": w, "height": h})
            for name, path in PAGES:
                await page.goto(BASE + path)
                await page.wait_for_selector("[data-testid=main-content] h1", timeout=30000)
                await page.wait_for_timeout(1500)
                top = await page.evaluate("""() => {
                  const m = document.querySelector('[data-testid=main-content]');
                  const bc = m.querySelector('nav, [data-testid=breadcrumbs]') || m.querySelector('h1');
                  const h1 = m.querySelector('h1');
                  const hdr = document.querySelector('[data-testid=app-header]');
                  const act = document.querySelector('[data-testid=acting-as]');
                  const a = act ? act.getBoundingClientRect() : null;
                  return {breadcrumb: Math.round(bc.getBoundingClientRect().top), title: Math.round(h1.getBoundingClientRect().top),
                          header_h: Math.round(hdr.getBoundingClientRect().height),
                          acting_visible: !!a && a.width > 0 && a.right <= window.innerWidth && a.bottom > 0};
                }""")
                print(tag, f"{w}x{h}", name, top)
                await page.screenshot(path=f"{OUT}/{tag}_{name}_{w}x{h}.png")
        await b.close()


asyncio.run(main(sys.argv[1]))
