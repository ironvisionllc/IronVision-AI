#!/usr/bin/env python3
"""Layout overflow regression check: every app route at several viewport sizes must not overflow horizontally.

Rerun:  SHOT_BASE=https://<preview-host> SHOT_EMAIL=jordan.qa7731@example.com SHOT_PASSWORD=... python3 scripts/check_layout_overflow.py [tag]
A page fails if document.scrollWidth > innerWidth, if the main column has hidden horizontal overflow, or if any visible element's
right edge passes the main column / viewport without being inside its own scroll (or intentional clip) container.
Results: docs/screenshots/layout-overflow/results-<tag>.json (+ screenshots of Select and Admin at 1280 and 1440)."""
import asyncio
import json
import os
import sys

import httpx
from playwright.async_api import async_playwright

BASE = os.environ["SHOT_BASE"].rstrip("/")
EMAIL, PW = os.environ["SHOT_EMAIL"], os.environ["SHOT_PASSWORD"]
OUT = "/app/docs/screenshots/layout-overflow"
SIZES = [(1280, 800), (1440, 900), (1920, 1080)]
MOBILE = (390, 844)
if os.environ.get("SHOT_SIZES"):  # e.g. SHOT_SIZES=768x1024,1280x800,1440x900 (390 = MOBILE, always run for MOBILE_PAGES)
    SIZES = [tuple(int(x) for x in s.split("x")) for s in os.environ["SHOT_SIZES"].split(",")]
ONLY = set(filter(None, os.environ.get("SHOT_PAGES", "").split(",")))  # optional subset of page names
MOBILE_PAGES = {"dashboard", "my-work", "sca-workspace", "import-center", "catalog", "catalog-tree", "catalog-tree-system", "select", "admin", "workbench", "parameter-comparison", "mapping-review", "policy-detail", "test-results", "audit-log"}
SHOTS = {"select", "admin"}

MEASURE = """() => {
  const W = window.innerWidth, main = document.querySelector('[data-testid=main-content]');
  const mr = main ? Math.min(main.getBoundingClientRect().right, W) : W;
  const contained = (el) => { for (let p = el.parentElement; p && p !== main && p !== document.body; p = p.parentElement) {
      const s = getComputedStyle(p); if (s.overflowX !== 'visible') return true; } return false; };
  const bad = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height || getComputedStyle(el).position === 'fixed') continue;
    const inMain = main && main.contains(el) && el !== main;
    const edge = inMain ? mr : W;
    if (r.right > edge + 1 && !contained(el)) {
      if (bad.length && bad[bad.length - 1].el.contains(el)) continue;
      bad.push({el, d: {tag: el.tagName.toLowerCase(), testid: el.closest('[data-testid]')?.dataset.testid || null,
        cls: (el.className && el.className.baseVal === undefined ? String(el.className) : '').slice(0, 80), right: Math.round(r.right), edge: Math.round(edge)}});
    }
  }
  return {doc: document.documentElement.scrollWidth, W, main_hidden: main ? main.scrollWidth - main.clientWidth : 0, offenders: bad.slice(0, 8).map(b => b.d)};
}"""


def ensure_systems(token: str) -> dict:
    h = {"Authorization": f"Bearer {token}"}
    with httpx.Client(base_url=BASE + "/api/v1", headers=h, timeout=60) as c:
        ss = c.get("/systems").json()
        nss = next((s for s in ss if s.get("categorization_mode") == "cnssi1253"), None)
        if not nss:  # layout fixture: an NSS system (CNSSI 1253, M-H-L) next to the existing FIPS system
            nss = c.post("/systems", json={"name": "ZZ Layout NSS (fixture)", "acronym": "ZZLAY", "baseline_key": "high", "categorization_mode": "cnssi1253",
                                           "nss_determination": "yes", "information_types": [{"id": "D.16.3"}], "processes_pii": True,
                                           "confidentiality_impact": "Moderate", "integrity_impact": "High", "availability_impact": "Low"}).json()
        fips = next((s for s in ss if s.get("categorization_mode") != "cnssi1253"), None)
        pols = c.get("/policies").json()
        pols = pols.get("policies", []) if isinstance(pols, dict) else pols
    return {"nss": nss["id"], "fips": fips["id"] if fips else nss["id"], "policy": (pols[0]["id"] if pols else None)}


def routes(ids: dict) -> list[tuple[str, str, str, str | None]]:
    n, f, p = ids["nss"], ids["fips"], ids["policy"]
    r = [("rmf-workflow", "/rmf-workflow", f, None), ("systems", "/systems", f, None), ("system-detail", f"/systems/{n}", n, None),
         ("portfolio", "/portfolio", f, None), ("prepare", "/rmf/prepare", n, None), ("categorize", "/rmf/categorize", n, None),
         ("categorize-fips", "/rmf/categorize", f, None), ("select", "/rmf/select", n, "overlays"), ("select-fips", "/rmf/select", f, "overlays"),
         ("parameter-comparison", "/rmf/select", n, "params"), ("catalog", "/catalog", n, None), ("catalog-tree", "/catalog?control=ac-2.1", n, "close-drawer"),
         ("catalog-tree-system", f"/catalog?system={n}", n, "tree-expand"), ("implement", "/rmf/implement", n, None),
         ("workbench", "/controls", n, "list"), ("control-detail", f"/systems/{n}/controls/ac-2", n, None), ("control-detail-fips", f"/systems/{f}/controls/ac-2", f, None),
         ("inheritance", "/inheritance", f, None), ("inventory", "/inventory", f, None), ("ccis", "/ccis", f, None),
         ("policy-auditor", "/policy-auditor", f, None), ("evidence-sources", "/evidence-sources", f, None), ("assess", "/rmf/assess", f, None),
         ("reviews", "/reviews", f, None), ("test-results", "/test-results", f, None), ("mapping-review", "/mapping-review", f, "queue-sbs"),
         ("authorize", "/rmf/authorize", n, None), ("authorization-package", f"/systems/{n}/authorization", n, None), ("poam", "/poams", f, None),
         ("emass", "/emass", f, None), ("monitor", "/rmf/monitor", f, None), ("evidence-ledger", "/evidence-ledger", f, None),
         ("traceability", "/traceability", f, None), ("help", "/help", f, None), ("audit-log", "/audit-log", f, None), ("admin", "/admin", f, None),
         ("docs", "/docs-center", f, None), ("notifications", "/settings/notifications", f, None),
         ("dashboard", "/dashboard", n, None), ("my-work", "/my-work", n, None), ("sca-workspace", "/assess/workspace", f, None),
         ("import-center", "/import-center", f, None)]
    if p:
        r += [("policy-detail", f"/policy-auditor/{p}", f, None), ("policy-side-by-side", f"/policy-auditor/{p}", f, "mapping-sbs")]
    return r


async def act(page, how: str | None) -> None:
    if how == "list":  # the control list renders after the summary – measure the rows, not the empty frame
        await page.wait_for_selector("[data-testid^=queue-item-]", timeout=20000)
    if how == "close-drawer":
        await page.wait_for_selector("[data-testid=tree-enhancement-ac-2\\.1]", timeout=20000)
        await page.keyboard.press("Escape")
    elif how == "tree-expand":
        await page.click("[data-testid=catalog-tree-expand-all]")
        await page.wait_for_selector("[data-testid=tree-enhancement-ac-2\\.1]", timeout=20000)
    elif how == "overlays":
        for b in await page.locator("[data-testid$=-details]").all():
            await b.click()
    elif how == "params":
        await page.locator("[data-testid=param-compare]").scroll_into_view_if_needed()
    elif how in ("mapping-sbs", "queue-sbs"):
        b = page.locator(f"[data-testid^={how}-]").first
        if await b.count():
            await b.click()
            await page.wait_for_selector("[data-testid=sbs-review], [role=dialog]", timeout=15000)
    if how:
        await page.wait_for_timeout(800)


async def ui_login(page) -> None:
    await page.goto(BASE + "/login")
    await page.fill("input[type=email]", EMAIL)
    await page.fill("input[type=password]", PW)
    await page.keyboard.press("Enter")
    await page.wait_for_url(lambda u: "/login" not in u, timeout=30000)


async def goto_authed(page, url: str) -> bool:
    """Navigate; if the session expired (redirect to /login) sign in again and retry once. False = still not signed in."""
    await page.goto(url)
    await page.wait_for_load_state("domcontentloaded")
    if "/login" in page.url and "/login" not in url:
        await ui_login(page)
        await page.goto(url)
    if await page.locator("[data-testid=guided-first-login-no]").count():  # first-login Guided Mode prompt would cover content
        try:
            await page.click("[data-testid=guided-first-login-no]", timeout=3000)
        except Exception:
            pass
    return "/login" not in page.url or "/login" in url


async def main(tag: str) -> None:
    os.makedirs(OUT, exist_ok=True)
    tok = httpx.post(f"{BASE}/api/v1/auth/login", json={"email": EMAIL, "password": PW}, timeout=60).json()["access_token"]
    ids = ensure_systems(tok)
    rs, results = routes(ids), []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
        await page.goto(BASE + "/login")
        await page.fill("input[type=email]", EMAIL)
        await page.fill("input[type=password]", PW)
        await page.keyboard.press("Enter")
        await page.wait_for_url(lambda u: "/login" not in u, timeout=30000)
        for w, h in SIZES + [MOBILE]:
            await page.set_viewport_size({"width": w, "height": h})
            for name, path, sid, how in rs:
                if ((w, h) == MOBILE and name not in MOBILE_PAGES) or (ONLY and name not in ONLY):
                    continue
                await page.evaluate(f"localStorage.setItem('aegis.selected_system', '{sid}')")
                if not await goto_authed(page, BASE + path):
                    raise SystemExit(f"not signed in at {path} – results would measure the login page")
                try:
                    await page.wait_for_selector("[data-testid=main-content] h1, [data-testid=main-content] h2", timeout=20000)
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                err = None
                try:
                    await act(page, how)
                except Exception as e:  # interaction target missing is reported, not fatal
                    err = f"{type(e).__name__}: {str(e)[:120]}"
                m = await page.evaluate(MEASURE)
                ok = m["doc"] <= m["W"] and m["main_hidden"] <= 1 and not m["offenders"]
                results.append({"page": name, "size": f"{w}x{h}", "ok": ok, "doc_scroll": m["doc"], "viewport": m["W"],
                                "main_hidden_overflow": m["main_hidden"], "offenders": m["offenders"], "interaction_error": err})
                print(f"{'PASS' if ok else 'FAIL'} {w}x{h} {name}{'' if ok else ' ' + json.dumps(m['offenders'][:2])[:200]}")
                if name in SHOTS and w in (1280, 1440):
                    await page.screenshot(path=f"{OUT}/{tag}_{name}_{w}.png", full_page=False)
        await b.close()
    json.dump(results, open(f"{OUT}/results-{tag}.json", "w"), indent=1)
    bad = [r for r in results if not r["ok"]]
    print(f"\n{len(results) - len(bad)}/{len(results)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "run"))
