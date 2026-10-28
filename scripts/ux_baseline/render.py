#!/usr/bin/env python3
"""Render the static mockups to PNG and compose before/after side-by-sides (current screenshot | mockup).
Run after crawl.py and mockups.py: python3 scripts/ux_baseline/render.py"""
import asyncio
from pathlib import Path

from PIL import Image, ImageDraw
from playwright.async_api import async_playwright

M, CUR = Path("/app/docs/ux/mockups"), Path("/app/docs/ux/screens/current")
PNG, BA = M / "png", Path("/app/docs/ux/before_after")
PAIRS = {"dashboard": "system_detail", "navigation": "select", "workbench": "workbench", "import_center": "import_center",
         "mapping_review": "mapping_review", "assessment": "assess"}


async def render():
    PNG.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
        for f in sorted(M.glob("*.html")):
            await page.goto(f.as_uri())
            await page.wait_for_timeout(300)
            await page.screenshot(path=str(PNG / f"{f.stem}.png"), full_page=True)
            print("png", f.stem)
        await b.close()


def side_by_side():
    BA.mkdir(parents=True, exist_ok=True)
    for after, before in PAIRS.items():
        a, b = Image.open(CUR / f"{before}.png").convert("RGB"), Image.open(PNG / f"{after}.png").convert("RGB")
        h = 900
        a, b = a.crop((0, 0, a.width, min(a.height, h))), b.crop((0, 0, b.width, min(b.height, h)))
        out = Image.new("RGB", (a.width + b.width + 30, h + 40), "white")
        out.paste(a, (0, 40))
        out.paste(b, (a.width + 30, 40))
        d = ImageDraw.Draw(out)
        d.text((10, 12), f"BEFORE – current UI ({before})", fill="black")
        d.text((a.width + 40, 12), f"AFTER – proposed mockup ({after}, non-functional)", fill="black")
        out = out.resize((out.width // 2, out.height // 2))
        out.save(BA / f"{after}.png")
        print("before/after", after)


if __name__ == "__main__":
    asyncio.run(render())
    side_by_side()
