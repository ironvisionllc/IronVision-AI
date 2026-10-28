#!/usr/bin/env python3
"""Wrap / squeeze regression check – every app route at 1280, 768 and 390 wide, dark and light theme.

Rerun:  SHOT_BASE=https://<preview-host> SHOT_EMAIL=jordan.qa7731@example.com SHOT_PASSWORD=... python3 scripts/check_wrap.py [tag]
Fails a route when
  label-wrap   a button, button-styled link, tab, chip/badge, status label or menu item renders its label on more than one line
  clipped      a visible button is cut off by a non-scrolling container, lies outside the viewport, or its label is truncated
  squeezed     a text block or table cell is under ~12 characters wide while wrapping onto 3+ lines
Runs next to scripts/check_layout_overflow.py (no horizontal page overflow) – same routes, login and fixtures.
Options: SHOT_PAGES=a,b  WRAP_THEMES=dark,light  WRAP_SIZES=1280x800,768x1024,390x844  WRAP_SHOTS=1 (light-theme screenshots → $WRAP_RAW)
Results: docs/screenshots/wrap/results-<tag>.json"""
import asyncio
import json
import os
import sys
from collections import defaultdict

import httpx
from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(__file__))
from check_layout_overflow import BASE, EMAIL, PW, act, ensure_systems, goto_authed, routes  # noqa: E402

OUT = "/app/docs/screenshots/wrap"
RAW = os.environ.get("WRAP_RAW", "/tmp/wrap_raw")
THEMES = os.environ.get("WRAP_THEMES", "dark,light").split(",")
SIZES = [tuple(int(x) for x in s.split("x")) for s in os.environ.get("WRAP_SIZES", "1280x800,768x1024,390x844").split(",")]
ONLY = set(filter(None, os.environ.get("SHOT_PAGES", "").split(",")))

MEASURE = r"""() => {
  const W = innerWidth, H = innerHeight, out = [];
  const vis = (el) => { const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none' && !el.closest('[aria-hidden=true], [hidden], details:not([open]) > :not(summary)'); };
  const id = (el) => (el.closest('[data-testid]')?.dataset.testid || el.tagName.toLowerCase());
  const lines = (el) => {  // number of visual lines of el's own text (text nodes only – icons are ignored)
    const rs = []; const tw = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    for (let n = tw.nextNode(); n; n = tw.nextNode()) { if (!n.textContent.trim()) continue; const rg = document.createRange(); rg.selectNodeContents(n);
      rs.push(...[...rg.getClientRects()].filter((r) => r.width > 0.5 && r.height > 4)); }
    const lh = parseFloat(getComputedStyle(el).lineHeight) || parseFloat(getComputedStyle(el).fontSize) * 1.4;
    const tops = []; for (const r of rs) { const c = r.top + r.height / 2; if (!tops.some((t) => Math.abs(t - c) < lh * 0.6)) tops.push(c); }
    return tops.length;
  };
  const LABELS = 'button:not(:has(.block)), a[class*="btn"], [role=tab], [role=menuitem], [data-testid*="chip"], [data-testid*="badge"], [data-testid*="status"]:not(td):not(div), .rounded-full.px-2, .rounded-full.px-2\\.5, span.rounded.px-1\\.5, span.rounded.px-2';
  const chipLike = (el) => { const s = getComputedStyle(el); return (s.backgroundColor !== 'rgba(0, 0, 0, 0)' && s.backgroundColor !== 'transparent') || parseFloat(s.borderTopWidth) > 0; };
  for (const el of document.querySelectorAll(LABELS)) {
    if (!vis(el) || !(el.innerText || '').trim()) continue;
    if (el.matches('[data-testid*="status"]:not(button):not([role=tab])') && !chipLike(el)) continue;  // plain status values (text) are not chips
    if (el.closest('table') && el.tagName === 'TD') continue;
    const text = el.innerText.trim();
    if (text.includes('\n')) continue;  // multi-line content by design (tree rows, cards) – not a label
    if (text.length > 40 || el.querySelector('div, p, ul, table')) continue;  // card-like links/buttons with paragraphs are not labels
    const r = el.getBoundingClientRect();
    if (lines(el) > 1) out.push({ check: 'label-wrap', el: id(el), text: text.slice(0, 40), w: Math.round(r.width) });
    if (el.matches('button, a[class*="btn"], [role=tab]')) {
      const inScroll = (() => { for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) if (/auto|scroll/.test(getComputedStyle(p).overflowX)) return true; return false; })();
      if (!inScroll && (r.right > W + 1 || r.left < -1)) out.push({ check: 'clipped', why: 'outside viewport', el: id(el), text: text.slice(0, 40) });
      else if (el.scrollWidth > el.clientWidth + 2 && getComputedStyle(el).overflowX !== 'visible') out.push({ check: 'clipped', why: 'label truncated', el: id(el), text: text.slice(0, 40) });
      else for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
        const s = getComputedStyle(p); if (s.overflowX === 'visible' && s.overflowY === 'visible') continue;
        const scrolls = /auto|scroll/.test(s.overflowX + s.overflowY); const pr = p.getBoundingClientRect();
        if (!scrolls && (r.right > pr.right + 1 || r.left < pr.left - 1)) { out.push({ check: 'clipped', why: 'cut by container', el: id(el), text: text.slice(0, 40) }); }
        break;
      }
    }
  }
  const BLOCKS = 'p, td, th, dd, dt, li, label, h1, h2, h3, h4, [data-testid] > span, div';
  for (const el of document.querySelectorAll(BLOCKS)) {
    if (!vis(el)) continue;
    const own = [...el.childNodes].filter((n) => n.nodeType === 3 && n.textContent.trim().length > 2).map((n) => n.textContent.trim()).join(' ');
    if (own.length < 14) continue;
    const s = getComputedStyle(el), fs = parseFloat(s.fontSize), r = el.getBoundingClientRect();
    const cw = r.width - parseFloat(s.paddingLeft) - parseFloat(s.paddingRight);
    if (cw >= fs * 0.55 * 12) continue;
    const lh = parseFloat(s.lineHeight) || fs * 1.4, h = r.height - parseFloat(s.paddingTop) - parseFloat(s.paddingBottom);
    if (Math.round(h / lh) >= 3) out.push({ check: 'squeezed', el: id(el), text: own.slice(0, 40), w: Math.round(cw) });
  }
  const seen = new Set(); return out.filter((o) => { const k = o.check + o.el + o.text; if (seen.has(k)) return false; seen.add(k); return true; });
}"""


async def main(tag: str) -> None:
    os.makedirs(OUT, exist_ok=True)
    shots = os.environ.get("WRAP_SHOTS") == "1"
    tok = httpx.post(f"{BASE}/api/v1/auth/login", json={"email": EMAIL, "password": PW}, timeout=60).json()["access_token"]
    rs, results = routes(ensure_systems(tok)), []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await (await b.new_context(viewport={"width": 1280, "height": 800})).new_page()
        await page.goto(BASE + "/login")
        await page.fill("input[type=email]", EMAIL)
        await page.fill("input[type=password]", PW)
        await page.keyboard.press("Enter")
        await page.wait_for_url(lambda u: "/login" not in u, timeout=30000)
        await page.evaluate("Object.keys(localStorage).filter(k => k.startsWith('iv.guided.')).forEach(k => localStorage.setItem(k, 'off'))")
        for theme in THEMES:
            await page.evaluate(f"localStorage.setItem('ironvision.theme', '{theme}')")
            for w, h in SIZES:
                await page.set_viewport_size({"width": w, "height": h})
                for name, path, sid, how in rs:
                    if ONLY and name not in ONLY:
                        continue
                    await page.evaluate(f"localStorage.setItem('aegis.selected_system', '{sid}')")
                    if not await goto_authed(page, BASE + path):  # a session that expired mid-run must not measure the login page
                        raise SystemExit(f"not signed in at {path}")
                    try:
                        await page.wait_for_selector("[data-testid=main-content] h1, [data-testid=main-content] h2", timeout=20000)
                        await page.wait_for_load_state("networkidle", timeout=15000)
                        await act(page, how)
                    except Exception:
                        pass
                    await page.wait_for_timeout(300)
                    items = await page.evaluate(MEASURE)
                    cnt = defaultdict(int)
                    for i in items:
                        cnt[i["check"]] += 1
                    results.append({"page": name, "theme": theme, "size": f"{w}x{h}", "count": len(items), "by_check": dict(cnt), "items": items[:40]})
                    print(f"{theme:5} {w}x{h} {name:24} {len(items):3} {dict(cnt)}", flush=True)
                    if shots and theme == "light":
                        os.makedirs(f"{RAW}/{tag}", exist_ok=True)
                        await page.screenshot(path=f"{RAW}/{tag}/{name}_{w}.png")
        await b.close()
    json.dump(results, open(f"{OUT}/results-{tag}.json", "w"), indent=1)
    total = sum(r["count"] for r in results)
    print(f"\nTOTAL wrap/clip/squeeze findings: {total} across {len(results)} route/theme/size runs")
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "run"))
