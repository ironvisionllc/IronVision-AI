"""Prepares the shared SYNTHETIC demo for the 3:45 cut (v4) – zero AI calls. Run AFTER root says go; undo with --reset.
1) stored AI policy result copied in (prep_v2.copy_policy, AC-2 left unmapped);
2) SYNTHETIC Control Information applied to LTP off-camera (history row "Control Information, applied" + the Import-management scene);
3) LTP authorization package submitted (ISSO) and endorsed (ISSM) so the AO decision is pending on camera;
4) checks that the LTP ACAS run still has an open finding without a POA&M."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

import prep_v2 as p2  # noqa: E402

CI = Path(__file__).resolve().parent / "fixtures" / "SYNTHETIC_LTP_ControlInfo.xlsx"


def h(t):
    return {"Authorization": f"Bearer {t}"}


def main():
    db = p2.SessionLocal()
    if "--reset" in sys.argv:
        from app.services.sandbox import reset_demo_account
        print(reset_demo_account(db))
        return
    org = db.execute(text("select org_id from users where email='demo@ironvision.ai'")).scalar()
    ltp = str(db.execute(text("select id from systems where org_id=:o and acronym='LTP'"), {"o": org}).scalar())
    isso_id = db.execute(text("select id from users where org_id=:o and persona_role='isso'"), {"o": org}).scalar()
    print("policy", p2.copy_policy(db, org, ltp, isso_id))
    db.commit()
    with httpx.Client(base_url=p2.BASE, timeout=180) as c:
        base = p2.tok(c)
        isso, issm = p2.tok(c, "isso", base), p2.tok(c, "issm", base)
        r = c.post(f"/systems/{ltp}/emass-imports", headers=h(isso), files={"file": (CI.name, CI.read_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        iid = r.json()["id"]
        print("ci upload", r.status_code, iid)
        print("ci accept-safe", c.put(f"/systems/{ltp}/emass-imports/{iid}/decisions", headers=h(isso), json={"bulk": "accept_safe"}).status_code)
        print("ci apply", c.post(f"/systems/{ltp}/emass-imports/{iid}/apply", headers=h(isso)).status_code)
        r = c.post(f"/systems/{ltp}/authorization/submit", headers=h(isso), json={"justification": "SYNTHETIC package for the product demo recording"})
        j = r.json()
        rid = j.get("id") or (j.get("request") or {}).get("id")
        print("package submit", r.status_code, rid, str(j)[:160])
        r = c.post(f"/reviews/{rid}/decisions", headers=h(issm), json={"action": "endorse", "rationale": "SYNTHETIC – endorsed for AO decision"})
        print("issm endorse", r.status_code, r.text[:160])
        hist = c.get("/import-center/history", headers=h(isso)).json()["items"]
        scan = next(x["id"] for x in hist if x["kind"] == "ingest" and x["file_name"] == "ltp_weekly_scan.nessus")
        run = c.get(f"/ingest-runs/{scan}", headers=h(isso)).json()
        free = [f for f in run.get("findings", []) if not f.get("poam_id") and f.get("current_state") == "open"]
        print("acas run", scan, "open findings without POA&M:", len(free))
        trs = str(db.execute(text("select id from systems where org_id=:o and acronym='TRS'"), {"o": org}).scalar())
        cur = c.get(f"/systems/{trs}/categorization", headers=h(isso)).json()
        body = {k: v for k, v in cur.items() if k in ("information_types", "mission_criticality", "system_type", "acquisition_category", "operating_environment",
                                                      "environment_detail", "processes_pii", "classified_information")}
        body.update({"mode": "cnssi1253", "nss_determination": "yes", "cia": {"c": "Moderate", "i": "High", "a": "Low"}})
        body = {k: v for k, v in body.items() if v not in (None, "")}
        r = c.put(f"/systems/{trs}/categorization", headers=h(isso), json=body)
        print("TRS CNSSI save", r.status_code, r.text[:200])
        rec = c.get(f"/systems/{trs}/categorization/records", headers=h(isso)).json()["current"]
        ao = p2.tok(c, "ao", base)
        r = c.post(f"/systems/{trs}/categorization/records/{rec['id']}/approve", headers=h(ao), json={"rationale": "SYNTHETIC – CNSSI 1253 M-H-L approved for the demo"})
        print("TRS CNSSI approve", r.status_code, r.text[:200])
    print("ai_interactions last 2h:", db.execute(text("select count(*) from ai_interactions where created_at > now() - interval '2 hours'")).scalar())


if __name__ == "__main__":
    main()
