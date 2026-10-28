#!/usr/bin/env python3
"""Before/after screenshots of the worst wrap screens, scrolled to the first finding (guided prompt dismissed).
BEFORE_BASE = build of the pre-fix commit served via a local proxy; AFTER_BASE = preview. Writes $WRAP_RAW/{before,after}-light-<w>/<page>_<w>.png"""
import asyncio
import json
import os
import sys

sys.path.insert(0, "/app/scripts")
from check_layout_overflow import EMAIL, PW, act, ensure_systems, routes  # noqa: E402
from check_wrap import MEASURE  # noqa: E402
from playwright.async_api import async_playwright  # noqa: E402
import httpx  # noqa: E402

RAW = os.environ.get("WRAP_RAW", "/root/raw/wrap")
W = "/app/docs/screenshots/wrap"
PAGES = os.environ["WRAP_PAGES"].split(",")


def size_for(p):
    b = {r: x for r in ("390", "768") for x in json.load(open(f"{W}/results-before-light-{r}.json")) if x["page"] == p}
    return "390" if b["390"]["count"] >= b["768"]["count"] else "768"


async def shoot(base, phase, anchors):
    tok = httpx.post(f"{base}/api/v1/auth/login", json={"email": EMAIL, "password": PW}, timeout=60).json()["access_token"]
    rs = {r[0]: r for r in routes(ensure_systems(tok))}
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await (await b.new_context(viewport={"width": 390, "height": 844})).new_page()
        await page.goto(base + "/login")
        await page.fill("input[type=email]", EMAIL)
        await page.fill("input[type=password]", PW)
        await page.keyboard.press("Enter")
        await page.wait_for_url(lambda u: "/login" not in u, timeout=60000)
        await page.evaluate("localStorage.setItem('ironvision.theme', 'light')")
        for name in PAGES:
            s = size_for(name)
            await page.set_viewport_size({"width": int(s), "height": 844 if s == "390" else 1024})
            _, path, sid, how = rs[name]
            await page.evaluate(f"localStorage.setItem('aegis.selected_system', '{sid}')")
            await page.goto(base + path)
            try:
                await page.wait_for_selector("[data-testid=main-content] h1, [data-testid=main-content] h2", timeout=30000)
                await page.wait_for_load_state("networkidle", timeout=20000)
                await act(page, how)
            except Exception:
                pass
            if await page.locator("[data-testid=guided-first-login-no]").count():
                await page.click("[data-testid=guided-first-login-no]")
            if phase == "before":
                items = await page.evaluate(MEASURE)
                anchors[name] = next((i["el"] for i in items if i["el"] not in ("div", "span", "td", "p", "li")), None)
            a = anchors.get(name)
            if a and await page.locator(f"[data-testid='{a}']").count():
                await page.locator(f"[data-testid='{a}']").first.scroll_into_view_if_needed()
                await page.evaluate("window.scrollBy(0, -120)")
            await page.wait_for_timeout(500)
            os.makedirs(f"{RAW}/{phase}-light-{s}", exist_ok=True)
            await page.screenshot(path=f"{RAW}/{phase}-light-{s}/{name}_{s}.png")
            print(phase, name, s, a)
        await b.close()


async def main():
    anchors = {}
    await shoot(os.environ["BEFORE_BASE"], "before", anchors)
    await shoot(os.environ["AFTER_BASE"], "after", anchors)


asyncio.run(main())
