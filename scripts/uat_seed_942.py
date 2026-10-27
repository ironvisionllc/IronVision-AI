#!/usr/bin/env python3
"""UAT fast fixture (SYNTHETIC, preview only): a fresh sandbox tenant with demo data, topped up to EXACTLY N open review items
(default 942) with proposed policy mappings – no AI analysis. Two of them (policy "SYN-FAIL") are injectable: --inject moves that
policy's owner org to a second sandbox so the decision fails ("Policy mapping not found"); --restore moves it back.
Usage: python scripts/uat_seed_942.py seed [N]  |  inject <state.json>  |  restore <state.json>"""
import json
import sys
import time
import uuid

import httpx

sys.path.insert(0, "/app/backend")
from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import ControlAssignment, Job, Policy, PolicyControlMap, System, User  # noqa: E402

API = "http://localhost:8001/api/v1"
PW = "Uat-Synthetic-942!x"


def signup(c: httpx.Client, label: str) -> dict:
    email = f"uat942-{label}-{uuid.uuid4().hex[:6]}@example.com"
    tok = c.get(f"{API}/auth/signup/start").json()["form_token"]
    time.sleep(2.2)
    r = c.post(f"{API}/auth/signup", json={"name": f"UAT {label}", "email": email, "password": PW, "organization": f"UAT 942 {label} SYNTHETIC",
                                            "form_token": tok})
    r.raise_for_status()
    for _ in range(60):
        t = c.post(f"{API}/auth/login", json={"email": email, "password": PW})
        if t.status_code == 200 and c.get(f"{API}/sandbox/status", headers={"Authorization": f"Bearer {t.json()['access_token']}"}).status_code == 200:
            return {"email": email, "org_id": r.json()["org_id"], "token": t.json()["access_token"]}
        time.sleep(1)
    raise SystemExit("sign-up provisioning did not finish")


def open_items(c, h, sid) -> list:
    q = c.get(f"{API}/mapping-review", params={"system_id": sid}, headers=h).json()["queue"]
    return [x for x in q if not x.get("awaiting_sca")]


def seed(n: int) -> None:
    c = httpx.Client(timeout=120)
    a, b = signup(c, "a"), signup(c, "b")
    h = {"Authorization": f"Bearer {a['token']}"}
    c.post(f"{API}/sandbox/demo-data", headers=h).raise_for_status()
    with SessionLocal() as db:  # let the demo-data analysis jobs finish so the open count is stable
        users = list(db.scalars(select(User.id).where(User.org_id == uuid.UUID(a["org_id"]))))
        for _ in range(600):
            if not db.scalar(select(Job.id).where(Job.requested_by.in_(users), Job.status.in_(("queued", "running"))).limit(1)):
                break
            time.sleep(1)
            db.expire_all()
        sid = str(db.scalar(select(System.id).where(System.org_id == uuid.UUID(a["org_id"]), System.acronym == "LTP")))
    isso = c.post(f"{API}/sandbox/act-as", json={"role": "isso"}, headers=h).json()["access_token"]
    hi = {"Authorization": f"Bearer {isso}"}
    have = len(open_items(c, hi, sid))
    need = n - have
    with SessionLocal() as db:
        s = db.get(System, uuid.UUID(sid))
        ctl = sorted(db.scalars(select(ControlAssignment.control_id).where(ControlAssignment.system_id == s.id)))
        taken = {m for m in db.scalars(select(PolicyControlMap.control_id).join(Policy, Policy.id == PolicyControlMap.policy_id)
                                       .where(PolicyControlMap.org_id == s.org_id, PolicyControlMap.valid_to.is_(None)))}
        free = [x for x in ctl if x not in taken]
        fail = Policy(org_id=s.org_id, policy_key="SYN-FAIL", title="SYNTHETIC injectable-failure policy", version=1, status="current",
                      text_content="SYNTHETIC", analysis_status="analyzed")
        db.add(fail)
        db.flush()
        rest, i = need - 2, 0
        while rest > 0:
            p = Policy(org_id=s.org_id, policy_key=f"SYN-942-{i:02d}", title=f"SYNTHETIC UAT policy {i:02d}", version=1, status="current",
                       text_content="SYNTHETIC", analysis_status="analyzed")
            db.add(p)
            db.flush()
            for cid in ctl[:min(rest, 40)]:
                db.add(PolicyControlMap(policy_id=p.id, org_id=s.org_id, control_id=cid, status="proposed", source="statement_language",
                                        confidence="High", basis="SYNTHETIC UAT 942 fixture", snippets=["SYNTHETIC"]))
            rest -= min(rest, 40)
            i += 1
        for cid in free[:2] or ctl[:2]:
            db.add(PolicyControlMap(policy_id=fail.id, org_id=s.org_id, control_id=cid, status="proposed", source="statement_language",
                                    confidence="High", basis="SYNTHETIC injectable failure", snippets=["SYNTHETIC"]))
        db.commit()
        fail_id = str(fail.id)
    total = len(open_items(c, hi, sid))
    st = {"email": a["email"], "password": PW, "org_a": a["org_id"], "org_b": b["org_id"], "system_id": sid, "fail_policy": fail_id,
          "demo_open": have, "seeded": need, "open_total": total, "policies": i + 1}
    json.dump(st, open("/tmp/uat942.json", "w"), indent=1)
    print(json.dumps(st))


def move(state: str, to_key: str) -> None:
    st = json.load(open(state))
    with SessionLocal() as db:
        db.get(Policy, uuid.UUID(st["fail_policy"])).org_id = uuid.UUID(st[to_key])
        db.commit()
    print(f"SYN-FAIL policy owner → {to_key}")


def topup(state: str, n: int) -> None:
    """Extra SYNTHETIC proposed mappings so the injected-failure run goes through the server bulk job (>50 items)."""
    st = json.load(open(state))
    with SessionLocal() as db:
        s = db.get(System, uuid.UUID(st["system_id"]))
        ctl = sorted(db.scalars(select(ControlAssignment.control_id).where(ControlAssignment.system_id == s.id)))
        p = Policy(org_id=s.org_id, policy_key=f"SYN-TOPUP-{uuid.uuid4().hex[:4]}", title="SYNTHETIC UAT retry-run policy", version=1, status="current",
                   text_content="SYNTHETIC", analysis_status="analyzed")
        db.add(p)
        db.flush()
        for cid in ctl[:n]:
            db.add(PolicyControlMap(policy_id=p.id, org_id=s.org_id, control_id=cid, status="proposed", source="statement_language",
                                    confidence="High", basis="SYNTHETIC UAT retry-run fixture", snippets=["SYNTHETIC"]))
        db.commit()
    print(f"added {n} proposed mappings")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "topup":
        topup(sys.argv[2], int(sys.argv[3]))
    elif cmd == "seed":
        seed(int(sys.argv[2]) if len(sys.argv) > 2 else 942)
    else:
        move(sys.argv[2], "org_b" if cmd == "inject" else "org_a")
