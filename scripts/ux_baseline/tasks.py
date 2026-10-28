#!/usr/bin/env python3
"""Baseline task metrics on the CURRENT UI (SYNTHETIC demo sandbox, ISSO persona). Re-run unchanged after the redesign to compare.
Counts per task: clicks, page changes (pathname), manual fields (fill/select/upload), scripted time, next action shown, blocked step.
Rerun: UX_BASE=https://<preview-host> python3 scripts/ux_baseline/tasks.py → docs/ux/data/baseline_metrics.json + docs/ux/screens/tasks/*.png
Tasks 1–7 and 12 run on a fresh SYNTHETIC system registered in task 1; tasks 8–11 on the seeded LTP system (it has findings and a package)."""
import asyncio
import json
import os
import re
import time
import uuid

import httpx
from playwright.async_api import async_playwright

BASE = os.environ.get("UX_BASE", "https://aegis-rmf-demo.preview.emergentagent.com").rstrip("/")
EMAIL, PW = os.environ.get("UX_EMAIL", "demo@ironvision.ai"), os.environ.get("UX_PASSWORD", "IronVisionDemo!2026")
FX = "/app/backend/tests/fixtures/emass"
PHASE = os.environ.get("UX_PHASE", "baseline")
OUT, SHOTS = "/app/docs/ux/data", "/app/docs/ux/screens/tasks" + ("" if PHASE == "baseline" else f"_{PHASE}")
NEXT_RX = re.compile(r"next action|next step|next:|what's next|continue to", re.I)
ACRONYM = "UXB" + uuid.uuid4().hex[:3].upper()


class Meter:
    """Wraps the page; every user action is counted. opt=True → skipped (not counted) when the element is absent."""

    def __init__(self, page):
        self.page, self.clicks, self.fields, self.paths, self.notes = page, 0, 0, [], []

    def _path(self):
        p = re.sub(r"^https?://[^/]+", "", self.page.url).split("?")[0]
        if not self.paths or self.paths[-1] != p:
            self.paths.append(p)

    async def _el(self, sel, opt, timeout=15000):
        loc = self.page.locator(sel).first
        try:
            await loc.wait_for(state="visible", timeout=6000 if opt else timeout)
            return loc
        except Exception:
            if opt:
                self.notes.append(f"skipped (absent): {sel}")
                return None
            raise RuntimeError(f"not found: {sel}")

    async def click(self, sel, opt=False):
        if (loc := await self._el(sel, opt)) is None:
            return False
        await loc.click()
        self.clicks += 1
        await self.page.wait_for_timeout(700)
        self._path()
        return True

    async def fill(self, sel, val, opt=False):
        if (loc := await self._el(sel, opt)) is None:
            return False
        await loc.fill(val)
        self.fields += 1
        return True

    async def select(self, sel, opt=False, **kw):
        if (loc := await self._el(sel, opt)) is None:
            return False
        await loc.select_option(**kw)
        self.fields += 1
        self.clicks += 1
        await self.page.wait_for_timeout(500)
        return True

    async def upload(self, sel, files, opt=False):
        loc = self.page.locator(sel).first
        try:
            await loc.wait_for(state="attached", timeout=15000)
        except Exception:
            if opt:
                return False
            raise RuntimeError(f"not found: {sel}")
        await loc.set_input_files(files)
        self.fields += 1
        self.clicks += 1  # the file chooser
        await self.page.wait_for_timeout(1500)
        return True

    async def nav(self, label):
        """Sidebar navigation by its visible label. 'step/Label' = RMF-step layout: open the step first when its pages are collapsed."""
        step, _, label = label.rpartition("/")
        sel = f"aside a:has-text('{label}'), nav a:has-text('{label}')"
        if step and not await self.page.locator(sel).first.is_visible():
            await self.click(f"[data-testid=nav-step-{step}]")  # the step header opens the step's main page
            href = await self.page.locator(sel).first.get_attribute("href")
            if href and self.page.url.split("?")[0].endswith(href):
                return True
        return await self.click(sel)

    async def system(self, sid):
        await self.select("aside select", value=sid)


def api():
    c = httpx.Client(base_url=BASE + "/api/v1", timeout=120)
    c.headers["Authorization"] = "Bearer " + c.post("/auth/login", json={"email": EMAIL, "password": PW}).json()["access_token"]
    return c


# ---------- the 12 tasks ----------
async def t_register(m, ctx):
    await m.nav("Systems")
    await m.click("[data-testid=register-system-btn]")
    if not await m.page.locator("[data-testid=reg-name]").count():
        await m.click("button:has-text('scratch'), button:has-text('Start from'), a:has-text('scratch')", opt=True)
    await m.fill("[data-testid=reg-name]", f"SYNTHETIC UX Baseline {ACRONYM}")
    await m.fill("[data-testid=reg-acronym]", ACRONYM)
    await m.fill("[data-testid=info-type-search]", "inventory")  # registration requires an information type (entered again in Categorize)
    await m.click("[data-testid^=info-type-add-]")
    await m.click("[data-testid=pii-no]")
    await m.click("[data-testid=register-submit-btn]")
    await m.page.wait_for_timeout(2500)
    err = m.page.locator("[data-testid=register-error]")
    if await err.count() and await err.is_visible():
        raise RuntimeError("register error: " + (await err.inner_text())[:200])
    ctx["sid"] = next(s["id"] for s in ctx["api"].get("/systems").json() if s.get("acronym") == ACRONYM)


async def t_categorize(m, ctx):
    await m.system(ctx["sid"])
    await m.nav("categorize/Information types")
    await m.fill("[data-testid=info-type-search]", "logistics")
    await m.click("[data-testid^=info-type-add-]")
    await m.fill("[data-testid=cat-rationale]", "SYNTHETIC baseline-measurement categorization", opt=True)
    await m.click("[data-testid=categorize-save]")


async def t_baseline(m, ctx):
    await m.nav("select/Baseline, tailoring")
    await m.click("button:has-text('Initial baseline')", opt=True)
    await m.select("[data-testid=select-baseline-key]", value="moderate")
    await m.click("[data-testid=select-apply-baseline]")
    await m.click("[data-testid=select-baseline-preview] button:has-text('Apply')")


async def t_import_impl(m, ctx):
    await m.nav("Import Center")
    await m.select("[data-testid=ic-system-select]", opt=True, value=ctx["sid"])
    await m.upload("[data-testid=ic-file-input]", [f"{FX}/IV_eMASS_implementation_plan_user_edited.xlsx"])
    await m.click("[data-testid=ic-import-0]")
    await m.click("[data-testid=ic-open-0]")
    await m.click("[data-testid=import-apply-btn]")


async def t_update_control(m, ctx):
    await m.nav("implement/Control Workbench")
    if not await m.click("[data-testid^=queue-open-]", opt=True):  # fresh system: empty work queue → pick from the control list
        if not await m.page.locator("[data-testid^=queue-item-]").count():  # old layout: list hidden until "All controls"
            await m.click("[data-testid=show-all-toggle]")
        await m.click("[data-testid^=queue-item-] button, [data-testid^=queue-item-] a, [data-testid^=queue-item-]")
    await m.select("[data-testid=wb-impl-status]", value="partially_implemented")
    await m.click("[data-testid=wb-status-save]", opt=True)
    await m.fill("textarea[data-testid*=narrative], [data-testid=implementation-panel] textarea", "SYNTHETIC: accounts are reviewed quarterly by the ISSO.", opt=True)
    await m.click("[data-testid=wb-narrative-save]", opt=True)


async def t_evidence(m, ctx):
    p = "/tmp/SYNTHETIC_ux_evidence.json"
    open(p, "w").write(json.dumps({"tool": "SYNTHETIC", "control": "AC-2", "result": "pass"}))
    await m.nav("implement/Evidence – add")
    await m.click("[data-testid=add-source-btn]", opt=True)
    if await m.page.locator("[data-testid=upload-btn][disabled]").count() and await m.page.locator("[data-testid=upload-source-select] option").count() <= 1:  # old layout: a source had to be created first
        await m.click("[data-testid=create-file-source-btn]")
        await m.fill("[data-testid=file-source-name]", "SYNTHETIC manual uploads")
        await m.click("[data-testid=file-source-save]")
        await m.select("[data-testid=upload-source-select]", opt=True, index=1)
    await m.upload("[data-testid=upload-file-input]", [p])
    await m.click("[data-testid=upload-btn]")


async def t_test_results(m, ctx):
    await m.nav("assess/Test results")
    await m.click("[data-testid=tr-upload-input]")  # the old button now opens the Import Center pre-set to Test Results
    await m.upload("[data-testid=ic-file-input]", [f"{FX}/SYNTHETIC_TRExport.xlsx"])
    await m.click("[data-testid=ic-import-0]")


async def t_finding(m, ctx):
    await m.system(ctx["ltp"])
    await m.nav("implement/Control Workbench")
    if not await m.click("text=Open findings", opt=True):  # new layout: the control's Findings tab
        await m.click("[data-testid^=queue-item-]")
        await m.click("[data-testid=wb-tab-findings]")
    else:
        await m.click("[data-testid^=queue-open-]")
    await m.click("[data-testid^=wb-finding-link-], main a[href^='/findings/']")


async def t_poam(m, ctx):
    if await m.click("[data-testid^=add-to-poam-]", opt=True):  # finding not yet on a POA&M → create
        if await m.page.locator("[data-testid=poam-match-notice]").count():  # matching open POA&M → link (the recommended path)
            await m.click("[data-testid=poam-match-notice] button:has-text('Link to existing')")
            return
        await m.fill("[data-testid=poam-form-weakness]", "SYNTHETIC weakness for baseline measurement")
        await m.fill("[data-testid=poam-form-plan]", "SYNTHETIC remediation plan")
        await m.click("[data-testid=poam-form-submit]")
        return
    await m.nav("authorize/POA&M")  # already linked → update the POA&M
    await m.click("[data-testid=poam-table] a")
    await m.click("[data-testid=poam-edit-btn]")
    await m.fill("[data-testid=poam-detail-page] textarea", "SYNTHETIC updated remediation plan", opt=True)
    await m.click("[data-testid=poam-edit-save]")


async def t_ssp(m, ctx):
    await m.nav("authorize/Package & documents")
    await m.click("[data-testid=doc-ssp-check]")
    await m.click("[data-testid=doc-ssp-docx]")


async def t_package(m, ctx):
    await m.nav("Systems")
    await m.click(f"a[href='/systems/{ctx['ltp']}']", opt=True)
    await m.click("[data-testid=open-authorization-btn], a:has-text('Authorization package'), button:has-text('Authorization package')")
    await m.click("[data-testid=submit-package-btn]", opt=True)


async def t_iscm(m, ctx):
    await m.system(ctx["sid"])
    await m.nav("select/Baseline, tailoring")
    await m.fill("[data-testid=iscm-narrative]", "SYNTHETIC monitoring strategy for baseline measurement")
    await m.select("[data-testid=iscm-default-slcm_frequency], [data-testid$=slcm_frequency]", opt=True, index=1)
    await m.click("[data-testid=iscm-save]")
    await m.click("[data-testid=iscm-submit]", opt=True)


TASKS = [("register", "Register a system", t_register), ("categorize", "Categorize", t_categorize), ("baseline", "Select a baseline", t_baseline),
         ("import_impl", "Import implementation info (Implementation Plan)", t_import_impl), ("update_control", "Update a control", t_update_control),
         ("evidence", "Attach evidence", t_evidence), ("test_results", "Import test results", t_test_results), ("finding", "Review a finding", t_finding),
         ("poam", "Create/update a POA&M (from the finding)", t_poam), ("ssp", "Generate an SSP", t_ssp),
         ("package", "Prepare an authorization package", t_package), ("iscm", "Configure continuous monitoring", t_iscm)]


async def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(SHOTS, exist_ok=True)
    c = api()
    ctx = {"api": c, "ltp": next(s for s in c.get("/systems").json() if s.get("acronym") == "LTP")["id"]}
    results = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await (await b.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)).new_page()
        page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
        await page.goto(BASE + "/login")
        await page.fill("input[type=email]", EMAIL)
        await page.fill("input[type=password]", PW)
        await page.keyboard.press("Enter")
        await page.wait_for_url(lambda u: "/login" not in u, timeout=60000)
        await page.wait_for_timeout(1500)
        for key, label, fn in TASKS:
            m = Meter(page)
            m._path()
            t0, err = time.perf_counter(), None
            try:
                await fn(m, ctx)
                await page.wait_for_timeout(1200)
            except Exception as e:
                err = str(e)[:240]
            body = await page.locator("[data-testid=main-content]").inner_text() if await page.locator("[data-testid=main-content]").count() else ""
            await page.screenshot(path=f"{SHOTS}/{key}.png")
            r = {"task": key, "label": label, "clicks": m.clicks, "page_changes": max(len(m.paths) - 1, 0), "fields": m.fields,
                 "scripted_seconds": round(time.perf_counter() - t0, 1), "next_action_shown": bool(NEXT_RX.search(body)),
                 "completed": err is None, "blocked_at": err, "notes": m.notes, "paths": m.paths}
            results.append(r)
            print(json.dumps({k: r[k] for k in ("task", "clicks", "page_changes", "fields", "scripted_seconds", "next_action_shown", "completed", "blocked_at")}))
        await b.close()
    if ctx.get("sid"):
        c.post(f"/systems/{ctx['sid']}/archive", json={"reason": "SYNTHETIC UX baseline-measurement system – cleanup after the walk"})
    json.dump({"base": BASE, "persona": "ISSO (demo sandbox)", "phase": PHASE, "fresh_system": ACRONYM, "results": results}, open(f"{OUT}/{PHASE}_metrics.json", "w"), indent=1)


if __name__ == "__main__":
    asyncio.run(main())
