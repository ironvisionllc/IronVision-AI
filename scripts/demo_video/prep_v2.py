"""Prepares the shared SYNTHETIC demo workspace for the recording – zero AI calls.
1) copies an existing stored AI-analyzed SYNTHETIC policy result (AC raven fixture) into the demo org;
2) uploads the blank eMASS TR template to LTP, generates rows deterministically and creates one export.
Undo everything afterwards with: python3 prep_v2.py --reset   (re-seeds the shared demo, same as the nightly reset)."""
import json
import os
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, "/app/backend")
import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import SessionLocal  # noqa: E402

BASE = "https://aegis-rmf-demo.preview.emergentagent.com/api/v1"
SRC_POLICY = os.environ.get("SRC_POLICY", "0dfbe304-325d-4478-ae5a-1848a79ddc24")  # SYNTHETIC ac_raven bench result (stored AI analysis)
TITLE = "AC Policy – Raven Logistics (SYNTHETIC, AI-analyzed)"
SKIP_MAPS = {"ac-2"}  # left unmapped so "Use this passage" creates a NEW human proposal that Mapping Review then approves
XX1 = __import__("re").compile(r"^[a-z]{2}-1$")
BLANK = Path("/app/backend/tests/fixtures/emass/BLANK_TRExport.xlsx")


def rows(db, sql, **kw):
    return [dict(r._mapping) for r in db.execute(text(sql), kw)]


def insert(db, table, row):
    cols = list(row)
    types = {r["column_name"]: r["data_type"] for r in rows(db, "select column_name, data_type from information_schema.columns where table_name=:t", t=table)}
    vals = {k: (json.dumps(v, default=str) if types.get(k) == "jsonb" and v is not None else v) for k, v in row.items()}
    ph = [f"cast(:{c} as jsonb)" if types.get(c) == "jsonb" else f":{c}" for c in cols]
    db.execute(text(f"insert into {table} ({', '.join(cols)}) values ({', '.join(ph)})"), vals)


def copy_policy(db, org, ltp, isso):
    if rows(db, "select id from policies where org_id=:o and title=:t", o=org, t=TITLE):
        return "exists"
    p = rows(db, "select * from policies where id=:i", i=SRC_POLICY)[0]
    new = uuid.uuid4()
    p.update(id=new, org_id=org, system_ids=[ltp], evidence_ids=[], title=TITLE, supersedes_id=None, is_synthetic=True)
    if not (p.get("analysis") or {}).get("reading"):  # bench copies have no stored original: same stats from the source fixture
        from app.services import rmf
        fx = Path("/app/backend/tests/fixtures/policies/ac_policy_raven_demo.docx")
        p["analysis"] = {**(p.get("analysis") or {}), "reading": rmf.reading_report(fx.name, fx.read_bytes(), p["text_content"] or "")}
        p["file_name"] = p.get("file_name") or fx.name
    insert(db, "policies", p)
    for m in rows(db, "select * from policy_control_maps where policy_id=:i", i=SRC_POLICY):
        if m["control_id"] in SKIP_MAPS:
            continue
        m.update(id=uuid.uuid4(), org_id=org, policy_id=new, decided_by=isso if m.get("decided_by") else None)
        insert(db, "policy_control_maps", m)
    for c in rows(db, "select * from policy_requirement_coverage where policy_id=:i", i=SRC_POLICY):
        if c["source"] != "ai" and not XX1.match(c["control_id"]):  # AI-refined rows only: keyword-only leftovers of the older run would flag the result stale
            continue
        c.update(id=uuid.uuid4(), org_id=org, policy_id=new)
        insert(db, "policy_requirement_coverage", c)
    for f in rows(db, "select * from policy_findings where policy_id=:i", i=SRC_POLICY):
        f.update(id=uuid.uuid4(), policy_id=new, system_id=ltp, observed_evidence_id=None, reviewer_id=None, finding_id=None, ai_interaction_id=None)
        if "org_id" in f:
            f["org_id"] = org
        insert(db, "policy_findings", f)
    return str(new)


def tok(c, role=None, base=None):
    if role is None:
        r = c.post("/auth/login", json={"email": "demo@ironvision.ai", "password": os.environ.get("DEMO_PASSWORD", "IronVisionDemo!2026")})
        return r.json()["access_token"]
    return c.post("/sandbox/act-as", json={"role": role}, headers={"Authorization": f"Bearer {base}"}).json()["access_token"]


def tr(ltp):
    with httpx.Client(base_url=BASE, timeout=180) as c:
        isso = tok(c, "isso", tok(c))
        h = {"Authorization": f"Bearer {isso}"}
        wbs = c.get(f"/systems/{ltp}/tr/workbooks", headers=h).json()
        if not wbs:
            r = c.post(f"/systems/{ltp}/tr/workbooks", headers=h, files={"file": ("BLANK_TRExport.xlsx", BLANK.read_bytes(),
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
            print("tr upload", r.status_code, r.text[:160])
            wbs = [r.json()]
        wb = wbs[0]
        if wb.get("status") != "generated":
            r = c.post(f"/tr/workbooks/{wb['id']}/generate", headers=h, json={"populate": True})
            print("generate", r.status_code, r.text[:160])
            for _ in range(60):
                time.sleep(3)
                wb = next(w for w in c.get(f"/systems/{ltp}/tr/workbooks", headers=h).json() if w["id"] == wb["id"])
                if wb["status"] in ("generated", "failed"):
                    break
        print("wb", wb["id"], wb["status"])
        r = c.post(f"/tr/workbooks/{wb['id']}/export", headers=h)
        print("export", r.status_code, r.text[:200])


def main():
    db = SessionLocal()
    if "--reset" in sys.argv:
        from app.services.sandbox import reset_demo_account
        print(reset_demo_account(db))
        return
    org = db.execute(text("select org_id from users where email='demo@ironvision.ai'")).scalar()
    ltp = db.execute(text("select id from systems where org_id=:o and acronym='LTP'"), {"o": org}).scalar()
    isso = db.execute(text("select id from users where org_id=:o and persona_role='isso'"), {"o": org}).scalar()
    print("policy", copy_policy(db, org, ltp, isso))
    db.commit()
    tr(str(ltp))


main()
