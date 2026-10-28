#!/usr/bin/env python3
"""Colour-contrast regression check (WCAG 2.2 AA) – every app route, light AND dark theme, 1280 and 390 wide.

Rerun:  SHOT_BASE=https://<preview-host> SHOT_EMAIL=jordan.qa7731@example.com SHOT_PASSWORD=... python3 scripts/check_contrast.py [tag]
Per route/theme/size it runs
  1. axe-core `color-contrast` (text 4.5:1, large text 3:1) on the page as loaded, and
  2. a computed-contrast pass over a sample of controls (buttons, button-styled links, tabs, switches, inputs, status dots):
     resting, :hover and keyboard :focus-visible states – text 4.5:1 (3:1 large; disabled labels 3:1 so they stay readable),
     component boundary 3:1 when the fill does not separate the control from its surroundings, focus indicator 3:1, status dots 3:1.
Options: SHOT_PAGES=a,b (subset)  CONTRAST_THEMES=dark,light  CONTRAST_SIZES=1280x800,390x844  CONTRAST_SHOTS=1 (dark 1280 screenshots).
Results: docs/screenshots/contrast/results-<tag>.json and a per-route summary on stdout."""
import asyncio
import json
import os
import sys
from collections import defaultdict

import httpx
from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(__file__))
from check_layout_overflow import BASE, EMAIL, PW, act, ensure_systems, goto_authed, routes  # noqa: E402

OUT = "/app/docs/screenshots/contrast"
RAW = os.environ.get("CONTRAST_RAW", "/tmp/contrast_raw")  # raw per-route screenshots, not committed
AXE = "/app/frontend/node_modules/axe-core/axe.min.js"
AXE_SRC = open(AXE).read()
THEMES = os.environ.get("CONTRAST_THEMES", "dark,light").split(",")
SIZES = [tuple(int(x) for x in s.split("x")) for s in os.environ.get("CONTRAST_SIZES", "1280x800,390x844").split(",")]
ONLY = set(filter(None, os.environ.get("SHOT_PAGES", "").split(",")))
SAMPLE = int(os.environ.get("CONTRAST_SAMPLE", "10"))

LIB = r"""
window.__ivc = (() => {
  const hex = (h) => { h = h.replace('#', ''); if (h.length === 3) h = [...h].map((c) => c + c).join(''); return [0, 2, 4].map((i) => parseInt(h.substr(i, 2), 16)).concat(h.length === 8 ? parseInt(h.substr(6, 2), 16) / 255 : 1); };
  const parse = (c) => { if (!c) return null; if (c[0] === '#') return hex(c); const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null;
    const p = m[1].split(/[\s,\/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const stops = (img) => (img && img !== 'none' ? (img.match(/rgba?\([^)]+\)|#[0-9a-fA-F]{3,8}\b/g) || []).map(parse) : []);
  const lin = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const lum = (c) => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const over = (top, bot, a = top[3]) => [0, 1, 2].map((i) => top[i] * a + bot[i] * (1 - a)).concat(1);
  const root = () => (document.documentElement.classList.contains('dark') ? [15, 23, 42, 1] : [248, 250, 252, 1]);
  // composite background behind el (el's own fill included unless skipSelf); gradients → worst-case stop handled by caller
  const fills = (el) => { const s = getComputedStyle(el); const g = stops(s.backgroundImage); const c = parse(s.backgroundColor);
    return g.length ? g : (c && c[3] > 0 ? [c] : []); };
  const behind = (el) => { const chain = []; for (let e = el; e; e = e.parentElement) { const f = fills(e); if (f.length) { chain.push(f[0]); if (f[0][3] >= 1) break; } }
    let b = root(); for (let i = chain.length - 1; i >= 0; i--) b = over(chain[i], b); return b; };
  const opacity = (el) => { let o = 1; for (let e = el; e; e = e.parentElement) o *= Number(getComputedStyle(e).opacity); return o; };
  const vis = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 2 && r.height > 2 && r.bottom > 0 && r.top < innerHeight && s.visibility !== 'hidden' && s.display !== 'none'; };
  const large = (s) => { const px = parseFloat(s.fontSize), w = Number(s.fontWeight) || 400; return px >= 24 || (px >= 18.66 && w >= 700); };
  const id = (el) => (el.dataset.testid || el.closest('[data-testid]')?.dataset.testid || el.tagName.toLowerCase()) + (el.className && typeof el.className === 'string' ? ' .' + el.className.split(' ').filter((c) => /^(btn|input|iv-|rounded-full)/.test(c)).join('.') : '');
  const measure = (el, state) => {
    const out = []; const s = getComputedStyle(el); const parentBg = behind(el.parentElement || document.body); const op = opacity(el);
    const own = fills(el); const mixO = (c) => (op < 1 ? over(c, parentBg, op) : c);
    const bgs = (own.length ? own.map((f) => over(f, parentBg)) : [parentBg]).map(mixO);
    const disabled = el.disabled || el.getAttribute('aria-disabled') === 'true';
    const text = (el.innerText || el.value || '').trim();
    const fg = parse(s.color);
    if (text && fg && !el.matches('.rounded-full.h-2')) {
      const need = disabled ? 3 : large(s) ? 3 : 4.5;
      const r = Math.min(...bgs.map((b) => ratio(mixO(over(fg, b)), b)));
      if (r < need) out.push({ check: disabled ? 'disabled-label' : 'text', state, ratio: +r.toFixed(2), need, el: id(el), label: text.slice(0, 40) });
    }
    if (el.matches('.rounded-full.h-2, [data-testid*=status-dot], [data-testid^=nav-step-status-]')) {
      const r = Math.min(...bgs.map((b) => ratio(b, parentBg))); if (r < 3) out.push({ check: 'status-dot', state, ratio: +r.toFixed(2), need: 3, el: id(el) });
    } else if (el.matches('.btn-secondary, .btn-outline, .input, select, input[type=text], input[type=search], input[type=email], input[type=date], textarea, [role=switch], input[type=checkbox]')) {
      const fillR = Math.min(...bgs.map((b) => ratio(b, parentBg)));
      const bw = parseFloat(s.borderTopWidth) || 0; const bc = parse(s.borderTopColor);
      const borderR = bw > 0 && bc ? ratio(mixO(over(bc, bgs[0])), parentBg) : 1;
      if (fillR < 3 && borderR < 3 && !el.matches('input[type=checkbox]')) out.push({ check: 'boundary', state, ratio: +Math.max(fillR, borderR).toFixed(2), need: 3, el: id(el) });
    }
    if (state === 'focus') {
      const ow = parseFloat(s.outlineWidth) || 0; const oc = parse(s.outlineColor);
      let r = s.outlineStyle !== 'none' && ow >= 1 && oc ? ratio(over(oc, parentBg), parentBg) : 0;
      const sh = (s.boxShadow || '').match(/rgba?\([^)]+\)/g) || []; for (const c of sh) r = Math.max(r, ratio(over(parse(c), parentBg), parentBg));
      const bc = parse(s.borderTopColor); if (bc && (parseFloat(s.borderTopWidth) || 0) > 0) r = Math.max(r, ratio(over(bc, bgs[0]), parentBg));
      if (r < 3) out.push({ check: 'focus-indicator', state, ratio: +r.toFixed(2), need: 3, el: id(el) });
    }
    return out;
  };
  const SEL = 'button, a.btn-primary, a.btn-secondary, a.btn-outline, a.btn-ghost, a.btn-destructive, [role=tab], [role=switch], .input, select, textarea, .rounded-full.h-2, [data-testid^=nav-step-status-]';
  const sample = (n) => { const seen = new Set(), pick = [];
    for (const el of document.querySelectorAll(SEL)) { if (!vis(el)) continue; const sig = (typeof el.className === 'string' ? el.className : '') + '|' + el.tagName + '|' + (el.disabled ? 'd' : '');
      if (seen.has(sig)) continue; seen.add(sig); pick.push(el); if (pick.length >= n) break; }
    pick.forEach((el, i) => el.setAttribute('data-ivc', String(i))); return pick.length; };
  return { measure, sample };
})();
"""


async def page_checks(page) -> dict:
    if not await page.evaluate("typeof axe !== 'undefined'"):
        await page.evaluate(AXE_SRC)  # evaluate (not a <script> tag) so pages with a strict CSP are checked too
    axe = await page.evaluate("""async () => { const r = await axe.run({exclude: [['[data-emergent-overlay-host]']]}, {runOnly: ['color-contrast'], resultTypes: ['violations']});
      return r.violations.flatMap(v => v.nodes.map(n => ({target: n.target.join(' '), summary: (n.any[0]||{}).message || '', html: n.html.slice(0, 120)}))); }""")
    await page.evaluate(LIB)
    n = await page.evaluate(f"__ivc.sample({SAMPLE})")
    custom = []
    for i in range(n):
        loc = page.locator(f"[data-ivc='{i}']")
        try:
            custom += await loc.evaluate("(el) => __ivc.measure(el, 'rest')", timeout=3000)
        except Exception:
            continue  # element re-rendered away (e.g. a dismissed prompt) – nothing left to measure
        try:
            await loc.hover(timeout=1500)
            await page.wait_for_timeout(160)  # transitions are 150 ms
            custom += await loc.evaluate("(el) => __ivc.measure(el, 'hover')", timeout=3000)
            if await loc.evaluate("(el) => !el.disabled && el.tabIndex >= 0 && !el.matches('.rounded-full.h-2, [data-testid^=nav-step-status-]')", timeout=3000):
                await page.keyboard.press("Shift")  # keyboard modality → programmatic focus gets :focus-visible
                await loc.focus(timeout=1500)
                await page.wait_for_timeout(160)
                custom += await loc.evaluate("(el) => __ivc.measure(el, 'focus')", timeout=3000)
        except Exception:
            pass  # element moved/covered – resting state still measured
    await page.mouse.move(0, 0)
    return {"axe": axe, "custom": custom}


async def main(tag: str) -> None:
    os.makedirs(OUT, exist_ok=True)
    shots = os.environ.get("CONTRAST_SHOTS") == "1"
    if shots:
        os.makedirs(f"{RAW}/{tag}", exist_ok=True)
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
                    await page.wait_for_timeout(400)
                    r = await page_checks(page)
                    row = {"page": name, "theme": theme, "size": f"{w}x{h}", "axe": len(r["axe"]), "custom": len(r["custom"]), "axe_nodes": r["axe"][:25], "custom_items": r["custom"][:40]}
                    results.append(row)
                    print(f"{theme:5} {w}x{h} {name:24} axe={row['axe']:3} custom={row['custom']:3}", flush=True)
                    if shots and theme == "dark" and w == 1280:
                        await page.screenshot(path=f"{RAW}/{tag}/{name}.png")
        await b.close()
    json.dump(results, open(f"{OUT}/results-{tag}.json", "w"), indent=1)
    by = defaultdict(int)
    for r in results:
        by[r["theme"]] += r["axe"] + r["custom"]
    total = sum(by.values())
    print(f"\nTOTAL violations: {total} ({', '.join(f'{k}={v}' for k, v in by.items())}) across {len(results)} route/theme/size runs")
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "run"))
