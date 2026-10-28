#!/usr/bin/env python3
"""UX audit crawl (read-only, SYNTHETIC demo sandbox): screenshot + action/field/filter counts for every major route.
Rerun: UX_BASE=https://<preview-host> python3 scripts/ux_baseline/crawl.py → docs/ux/screens/current/*.png + docs/ux/data/screens.json"""
import asyncio
import json
import os

import httpx
from playwright.async_api import async_playwright

BASE = os.environ.get("UX_BASE", "https://aegis-rmf-demo.preview.emergentagent.com").rstrip("/")
EMAIL, PW = os.environ.get("UX_EMAIL", "demo@ironvision.ai"), os.environ.get("UX_PASSWORD", "IronVisionDemo!2026")
OUT, DATA = "/app/docs/ux/screens/current", "/app/docs/ux/data"
ROUTES = [
    ("rmf_overview", "/rmf-workflow"), ("systems", "/systems"), ("register", "/systems/new"), ("system_detail", "/systems/{sid}"),
    ("prepare", "/rmf/prepare"), ("categorize", "/rmf/categorize"), ("select", "/rmf/select"), ("catalog", "/catalog"),
    ("implement", "/rmf/implement"), ("workbench", "/systems/{sid}/controls"), ("inheritance", "/inheritance"), ("inventory", "/inventory"),
    ("ccis", "/ccis"), ("policy_auditor", "/policy-auditor"), ("evidence_sources", "/evidence-sources"), ("assess", "/rmf/assess"),
    ("reviews", "/reviews"), ("test_results", "/test-results"), ("mapping_review", "/mapping-review"), ("authorize", "/rmf/authorize"),
    ("authorization", "/systems/{sid}/authorization"), ("poams", "/poams"), ("emass_sync", "/emass"), ("monitor", "/rmf/monitor"),
    ("evidence_ledger", "/evidence-ledger"), ("traceability", "/traceability"), ("import_center", "/systems/{sid}/import-center"),
    ("emass_import", "/systems/{sid}/emass-import"), ("migration_report", "/systems/{sid}/migration-report"), ("portfolio", "/portfolio"),
    ("help", "/help"), ("audit_log", "/audit-log"), ("admin", "/admin"),
]
STATS_JS = """() => {
  const main = document.querySelector('[data-testid=main-content]') || document.body;
  const vis = (e) => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const q = (s) => [...main.querySelectorAll(s)].filter(vis);
  const btn = q('button, a.btn-primary, a.btn-secondary');
  return {
    title: (main.querySelector('h1')||{}).innerText || '',
    buttons: btn.length, button_labels: [...new Set(btn.map(b => (b.innerText||b.getAttribute('aria-label')||'').trim()).filter(Boolean))].slice(0, 80),
    links: q('a').length, inputs: q('input:not([type=checkbox]):not([type=radio]):not([type=hidden]), textarea').length,
    selects: q('select, [role=combobox]').length, checkboxes: q('input[type=checkbox], [role=switch]').length,
    tables: q('table').length, panels: q('section, [data-testid$=-panel]').length,
    headings: q('h2, h3').map(h => h.innerText.trim()).slice(0, 40),
    nav_items: document.querySelectorAll('nav a').length,
    scroll_height: document.documentElement.scrollHeight,
  };
}"""


def system_id() -> str:
    c = httpx.Client(base_url=BASE + "/api/v1", timeout=60)
    c.headers["Authorization"] = "Bearer " + c.post("/auth/login", json={"email": EMAIL, "password": PW}).json()["access_token"]
    systems = c.get("/systems").json()
    return next((s for s in systems if s.get("acronym") == "LTP"), systems[0])["id"]


async def login(page):
    await page.goto(BASE + "/login")
    await page.fill("input[type=email]", EMAIL)
    await page.fill("input[type=password]", PW)
    await page.keyboard.press("Enter")
    await page.wait_for_url(lambda u: "/login" not in u, timeout=60000)


async def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(DATA, exist_ok=True)
    sid = system_id()
    res = {}
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
        await login(page)
        await page.evaluate(f"localStorage.setItem('aegis.selected_system', '{sid}')")
        for name, path in ROUTES:
            try:
                await page.goto(BASE + path.format(sid=sid), wait_until="networkidle", timeout=60000)
                await page.wait_for_timeout(800)
                await page.screenshot(path=f"{OUT}/{name}.png")
                res[name] = {"path": path, **await page.evaluate(STATS_JS)}
                print("ok", name, res[name]["buttons"], res[name]["inputs"] + res[name]["selects"])
            except Exception as e:  # keep crawling; record the failure
                res[name] = {"path": path, "error": str(e)[:200]}
                print("ERR", name, e)
        await b.close()
    json.dump({"system_id": sid, "base": BASE, "screens": res}, open(f"{DATA}/screens.json", "w"), indent=1)


if __name__ == "__main__":
    asyncio.run(main())
