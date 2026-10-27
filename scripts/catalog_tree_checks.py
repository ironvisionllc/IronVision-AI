#!/usr/bin/env python3
"""Catalog tree automated checks on the demo LTP system (headless, no testing agent).
1 filters (baseline origin, assessment status, applicability, implementation) == Workbench API sets
2 clearing a search restores a NON-EMPTY prior expansion  3 Tab lands in the tree; ArrowLeft collapses / moves to parent
4 tap expand/collapse at 390 px.  Rerun: SHOT_BASE=https://<preview-host> python3 scripts/catalog_tree_checks.py
Output: docs/screenshots/catalog_tree/checks.json"""
import asyncio
import json
import os

import httpx
from playwright.async_api import async_playwright

BASE = os.environ["SHOT_BASE"].rstrip("/")
OUT = "/app/docs/screenshots/catalog_tree"
IDS = """() => [...document.querySelectorAll('[data-testid^="tree-control-"],[data-testid^="tree-enhancement-"]')]
  .filter(e => e.dataset.filterMatch !== 'false').map(e => e.dataset.testid).filter(t => !t.startsWith('tree-control-toggle-')).map(t => t.replace(/^tree-(control|enhancement)-/, ''))"""


CLEAR = "Object.keys(sessionStorage).filter(k => k.startsWith('aegis.catalogTree')).forEach(k => sessionStorage.removeItem(k))"


async def tree_ids(page, sid, key, value):
    await page.evaluate(CLEAR)  # each filter alone (saved filters would otherwise combine)
    await page.goto(f"{BASE}/catalog?system={sid}")
    try:
        await page.wait_for_selector("[data-testid=catalog-tree-summary]", state="attached", timeout=60000)
        await page.wait_for_function("document.querySelectorAll('[role=treeitem]').length > 0 || document.querySelector('[data-testid=catalog-tree-empty]')", timeout=60000)
    except Exception:
        await page.screenshot(path="/tmp/tree_fail.png")
        print("FAIL at", page.url, (await page.inner_text("body"))[:400])
        raise
    await page.select_option(f"[data-testid=catalog-tree-filter-{key}]", value)
    await page.click("[data-testid=catalog-tree-expand-all]")
    await page.wait_for_timeout(500)
    return set(await page.evaluate(IDS))


async def main():
    r = {}
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
        await page.goto(BASE + "/login")
        await page.click("[data-testid=demo-login-btn]")
        await page.wait_for_url(lambda u: "/login" not in u, timeout=30000)
        tok = await page.evaluate("Object.entries(sessionStorage).find(([k, v]) => /token/i.test(k) && !/refresh/i.test(k))[1]")
        api = httpx.Client(base_url=BASE + "/api/v1", headers={"Authorization": f"Bearer {tok}"}, timeout=60)
        sid = next(s["id"] for s in api.get("/systems").json() if s.get("acronym") == "LTP")
        rows = api.get(f"/systems/{sid}/workbench/controls", params={"limit": 5000}).json()

        def wb(**f):
            return {x["control_id"] for x in api.get(f"/systems/{sid}/workbench/controls", params={**f, "limit": 5000}).json()}
        expect = {
            ("baseline", "baseline"): wb(origin="baseline"), ("baseline", "overlay"): wb(origin="overlay"),
            ("assessment_status", "satisfied"): wb(assessment_status="satisfied"), ("assessment_status", "not_assessed"): wb(assessment_status="not_assessed"),
            ("assessment_status", "other_than_satisfied"): wb(assessment_status="other_than_satisfied"),
            ("implementation_status", "implemented"): wb(implementation_status="implemented"),
            ("applicability", "not_applicable"): wb(implementation_status="not_applicable"),
            ("applicability", "inherited"): (wb(responsibility="inherited") | wb(implementation_status="inherited")) - wb(implementation_status="not_applicable"),
        }
        expect[("applicability", "applicable")] = {x["control_id"] for x in rows} - expect[("applicability", "not_applicable")] - expect[("applicability", "inherited")]
        r["filters"] = {}
        for (k, v), want in expect.items():
            got = await tree_ids(page, sid, k, v)
            r["filters"][f"{k}={v}"] = {"tree": len(got), "workbench_api": len(want), "equal": got == want,
                                       "only_tree": sorted(got - want)[:5], "only_api": sorted(want - got)[:5]}
        # 2: non-empty prior expansion restored after clearing a search
        await page.goto(BASE + "/catalog")
        await page.wait_for_selector("[data-testid=tree-family-sc]", state="attached", timeout=60000)
        await page.click("[data-testid=catalog-tree-collapse-all]")
        await page.click("[data-testid=tree-family-toggle-sc]")
        await page.click("[data-testid=tree-control-toggle-sc-7]")
        await page.fill("[data-testid=catalog-tree-search]", "AC-2(1)")
        await page.wait_for_selector("[data-testid=tree-enhancement-ac-2\\.1]")
        await page.fill("[data-testid=catalog-tree-search]", "")
        await page.wait_for_timeout(600)
        r["search_restore"] = {"sc_open": await page.get_attribute("[data-testid=tree-family-sc]", "aria-expanded") == "true",
                               "sc7_open": await page.get_attribute("[data-testid=tree-control-sc-7]", "aria-expanded") == "true",
                               "ac_closed": await page.get_attribute("[data-testid=tree-family-ac]", "aria-expanded") == "false"}
        # 3: Tab into the tree; ArrowLeft collapses / moves to parent
        await page.click("[data-testid=catalog-tree-collapse-all]")
        await page.focus("[data-testid=catalog-tree-collapse-all]")
        for _ in range(8):
            await page.keyboard.press("Tab")
            if await page.evaluate("document.activeElement?.getAttribute('role')") == "treeitem":
                break
        first = await page.evaluate("document.activeElement?.dataset.testid")
        await page.keyboard.press("ArrowRight")
        opened = await page.get_attribute(f"[data-testid={first}]", "aria-expanded")
        await page.keyboard.press("ArrowDown")
        child = await page.evaluate("document.activeElement?.dataset.testid")
        await page.keyboard.press("ArrowLeft")
        parent = await page.evaluate("document.activeElement?.dataset.testid")
        await page.keyboard.press("ArrowLeft")
        closed = await page.get_attribute(f"[data-testid={first}]", "aria-expanded")
        r["keyboard"] = {"tab_lands_on": first, "arrow_right_expands": opened == "true", "arrow_down_to_child": child,
                         "arrow_left_to_parent": parent, "arrow_left_collapses": closed == "false"}
        # 4: tap at 390 px
        m = await (await b.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)).new_page()
        await m.goto(BASE + "/login")
        await m.tap("[data-testid=demo-login-btn]")
        await m.wait_for_url(lambda u: "/login" not in u, timeout=30000)
        await m.goto(BASE + "/catalog")
        await m.wait_for_selector("[data-testid=tree-family-toggle-ac]", state="attached", timeout=60000)
        await m.tap("[data-testid=catalog-tree-collapse-all]")
        await m.tap("[data-testid=tree-family-toggle-ac]")
        e1 = await m.get_attribute("[data-testid=tree-family-ac]", "aria-expanded")
        await m.tap("[data-testid=tree-control-toggle-ac-2]")
        e2 = await m.locator("[data-testid=tree-enhancement-ac-2\\.1]").count()
        await m.screenshot(path=f"{OUT}/11_mobile_tap_expanded.png")
        await m.tap("[data-testid=tree-family-toggle-ac]")
        e3 = await m.get_attribute("[data-testid=tree-family-ac]", "aria-expanded")
        r["mobile_tap"] = {"family_expands": e1 == "true", "control_expands": e2 == 1, "family_collapses": e3 == "false",
                           "doc_width": await m.evaluate("document.documentElement.scrollWidth")}
        await b.close()
    r["all_pass"] = (all(v["equal"] for v in r["filters"].values()) and all(r["search_restore"].values())
                     and r["keyboard"]["arrow_right_expands"] and r["keyboard"]["arrow_left_collapses"]
                     and r["keyboard"]["arrow_left_to_parent"] == r["keyboard"]["tab_lands_on"] and str(r["keyboard"]["tab_lands_on"]).startswith("tree-family-")
                     and all(v for k, v in r["mobile_tap"].items() if k != "doc_width") and r["mobile_tap"]["doc_width"] <= 390)
    json.dump(r, open(f"{OUT}/checks.json", "w"), indent=1)
    print(json.dumps(r))


asyncio.run(main())
