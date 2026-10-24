"""Records the silent IronVision AI product demo (CDP screencast → virtual timeline; loads/waits are cut out).
Run: python3 scripts/demo_video/record_demo.py  → /tmp/demo_rec/frames/*.jpg + timeline.json, then assemble.py builds the MP4."""
import asyncio
import base64
import json
import math
import sys
import time
from pathlib import Path

from playwright.async_api import async_playwright

BASE = "https://aegis-rmf-demo.preview.emergentagent.com"
LTP, TEG = "53ce70f2-6c09-4c0e-a7e5-03770d64e81a", "279595b1-7f99-4d22-9487-f95502906c68"
TR_ROW = 41
ZOOM = 1.25
OUT = Path("/tmp/demo_rec")
CARDS = Path(__file__).resolve().parent / "cards"

CURSOR_JS = """
(() => {
  if (location.protocol !== 'file:') document.addEventListener('DOMContentLoaded', () => { document.documentElement.style.zoom = '%(z)s'; });
  const mk = () => {
    if (location.protocol === 'file:' || document.getElementById('__cur')) return;
    const z = location.protocol === 'file:' ? 1 : %(z)s;
    const c = document.createElement('div'); c.id = '__cur';
    c.style.cssText = 'position:fixed;left:0;top:0;width:30px;height:30px;z-index:2147483647;pointer-events:none;transition:none;zoom:' + (1 / z);
    c.innerHTML = '<svg width="30" height="30" viewBox="0 0 24 24"><path d="M3 2 L3 19 L7.5 14.8 L10.6 21.5 L13.3 20.3 L10.3 13.8 L16.5 13.8 Z" fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    const r = document.createElement('div'); r.id = '__rip';
    r.style.cssText = 'position:fixed;width:44px;height:44px;margin:-22px 0 0 -22px;border-radius:50%%;border:3px solid #2597B2;opacity:0;z-index:2147483646;pointer-events:none;zoom:' + (1 / z);
    document.documentElement.appendChild(r); document.documentElement.appendChild(c);
    window.__cur = (x, y) => { c.style.transform = `translate(${x}px, ${y}px)`; r.style.left = x + 'px'; r.style.top = y + 'px'; };
    window.__rip = () => { r.animate([{opacity: .9, transform: 'scale(.4)'}, {opacity: 0, transform: 'scale(1.5)'}], {duration: 520, easing: 'ease-out'}); };
    window.__cur(window.__cx || 960, window.__cy || 540);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mk); else mk();
  new MutationObserver(() => mk()).observe(document, {childList: true, subtree: true});
})();
""" % {"z": ZOOM}


class Rec:
    def __init__(self):
        self.frames, self.intervals, self.on, self.vt0, self.scenes, self.events = [], [], False, 0.0, [], []
        self.cx, self.cy = 960, 540

    def vt(self):
        return self.vt0 + (time.time() - self.intervals[-1][0] if self.on else 0)

    def start(self):
        if not self.on:
            self.intervals.append([time.time(), None, self.vt0])
            self.on = True

    def stop(self):
        if self.on:
            self.intervals[-1][1] = time.time()
            self.vt0 += self.intervals[-1][1] - self.intervals[-1][0]
            self.on = False

    def frame(self, ts, data):
        for s, e, v in reversed(self.intervals):
            if ts >= s and (e is None or ts <= e):
                self.frames.append((v + ts - s, data))
                return


R = Rec()


async def main():
    OUT.mkdir(exist_ok=True)
    (OUT / "frames").mkdir(exist_ok=True)
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1920, "height": 1080})
        await ctx.add_init_script(CURSOR_JS)
        page = await ctx.new_page()
        cdp = await ctx.new_cdp_session(page)

        def on_frame(f):
            R.frame(f["metadata"]["timestamp"], f["data"])
            asyncio.ensure_future(cdp.send("Page.screencastFrameAck", {"sessionId": f["sessionId"]}))
        cdp.on("Page.screencastFrame", on_frame)
        await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 90, "maxWidth": 1920, "maxHeight": 1080})
        A = Actions(page)
        try:
            await run_scenes(A, page)
        except Exception as e:
            R.stop()
            await page.screenshot(path=str(OUT / "error.png"))
            print("ERROR", repr(e), "at vt", round(R.vt0, 1), flush=True)
            raise
        finally:
            R.stop()
            await cdp.send("Page.stopScreencast")
            await asyncio.sleep(0.5)
            meta = []
            for i, (t, d) in enumerate(sorted(R.frames, key=lambda x: x[0])):
                p = OUT / "frames" / f"{i:06d}.jpg"
                p.write_bytes(base64.b64decode(d))
                meta.append([round(t, 4), p.name])
            (OUT / "timeline.json").write_text(json.dumps({"frames": meta, "scenes": R.scenes, "events": R.events, "end": round(R.vt0, 3)}, indent=0))
            print("frames", len(meta), "end", round(R.vt0, 2), flush=True)
            await b.close()


class Actions:
    def __init__(self, page):
        self.p = page
        self.R = R

    async def hold(self, s):
        R.start()
        await asyncio.sleep(s)

    async def settle(self, sel=None, extra=0.8):
        R.stop()
        try:
            await self.p.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        if sel:
            await self.p.wait_for_selector(sel, state="visible", timeout=30000)
        await asyncio.sleep(extra)
        R.start()
        await self.p.evaluate("([x, y]) => { window.__cx = x; window.__cy = y; window.__cur && window.__cur(x + 1, y); }", [R.cx, R.cy])
        await asyncio.sleep(0.06)
        await self.p.evaluate("([x, y]) => { window.__cur && window.__cur(x, y); }", [R.cx, R.cy])

    def ev(self, what):
        R.events.append([round(R.vt(), 2), what])

    async def go(self, path, sel=None):
        self.ev("open " + (path if path.startswith("/") else path.rsplit("/", 1)[-1]))
        R.stop()
        await self.p.goto(BASE + path if path.startswith("/") else path)
        await self.settle(sel)

    async def move(self, x, y, dur=0.8):
        R.start()
        x0, y0 = R.cx, R.cy
        n = max(8, int(dur * 40))
        for i in range(1, n + 1):
            t = i / n
            e = 0.5 - math.cos(math.pi * t) / 2
            x1, y1 = x0 + (x - x0) * e, y0 + (y - y0) * e
            await self.p.mouse.move(x1, y1)
            await self.p.evaluate("([x, y]) => { window.__cx = x; window.__cy = y; window.__cur && window.__cur(x, y); }", [x1, y1])
            await asyncio.sleep(dur / n)
        R.cx, R.cy = x, y

    async def box(self, sel):
        loc = self.p.locator(sel).first
        R.stop()
        await loc.wait_for(state="visible", timeout=10000)
        await loc.evaluate("e => { const r = e.getBoundingClientRect(); if (r.top < 80 || r.bottom > innerHeight - 20) e.scrollIntoView({block: 'center'}); }")
        await asyncio.sleep(0.3)
        bb = await loc.bounding_box()
        R.start()
        return loc, bb

    async def point(self, sel, dur=0.8, dx=0.5, dy=0.5):
        try:
            loc, bb = await asyncio.wait_for(self.box(sel), 12)
        except Exception as e:
            print("  point failed:", sel, str(e)[:120], flush=True)
            self.R.start()
            return self.p.locator(sel).first
        await self.move(bb["x"] + bb["width"] * dx, bb["y"] + bb["height"] * dy, dur)
        return loc

    async def click(self, sel, dur=0.8, then=None, wait=0.4):
        loc = await self.point(sel, dur)
        self.ev("click " + sel)
        await self.p.evaluate("window.__rip && window.__rip()")
        await asyncio.sleep(0.15)
        await loc.click()
        if then:
            await self.settle(then)
        else:
            await asyncio.sleep(wait)
        return loc

    async def scroll(self, dy, dur=1.2):
        R.start()
        n = max(6, int(dur * 30))
        for _ in range(n):
            await self.p.mouse.wheel(0, dy / n)
            await asyncio.sleep(dur / n)

    async def type(self, sel, text, delay=0.06):
        loc = await self.click(sel, 0.6)
        await loc.type(text, delay=int(delay * 1000))

    async def persona(self, role):
        self.ev("persona " + role)
        R.stop()
        await self.p.locator('[data-testid="acting-as-select"]').select_option(role)
        await asyncio.sleep(2.0)
        await self.settle()

    async def system(self, sid, reload_sel=None):
        await self.point('[data-testid="system-selector-select"]', 0.7)
        R.stop()
        await self.p.locator('[data-testid="system-selector-select"]').select_option(sid)
        await self.settle(reload_sel, 1.2)

    def mark(self, n, name):
        R.scenes.append({"scene": n, "name": name, "start": round(R.vt(), 2)})
        print(f"scene {n} {name} @ {R.vt():.1f}", flush=True)

    async def pad_to(self, t):
        now = R.vt()
        if now < t:
            await self.hold(t - now)
        else:
            print(f"  overrun: {now:.1f} > {t}", flush=True)


async def run_scenes(A: Actions, page):
    from scenes import SCENES
    for fn in SCENES:
        await fn(A, page)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    asyncio.run(main())
