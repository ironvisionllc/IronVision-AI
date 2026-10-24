"""Prepares SYNTHETIC demo-workspace records for the product demo recording (shared Explore-Demo sandbox tenant only).
Idempotent: creates the NSS example system once, imports the blank eMASS TR template once, pre-generates AI evidence analysis."""
import time
from pathlib import Path

import httpx

BASE = "https://aegis-rmf-demo.preview.emergentagent.com/api/v1"
BLANK = Path("/app/backend/tests/fixtures/emass/BLANK_TRExport.xlsx")


def tok(c, role=None, base=None):
    if role is None:
        return c.post("/auth/demo-login", json={}).json()["access_token"]
    return c.post("/sandbox/act-as", json={"role": role}, headers={"Authorization": f"Bearer {base}"}).json()["access_token"]


def H(t):
    return {"Authorization": f"Bearer {t}"}


def wait_job(c, t, jid, limit=300):
    for _ in range(limit // 3):
        j = c.get(f"/jobs/{jid}", headers=H(t))
        if j.status_code == 200 and j.json().get("status") in ("succeeded", "failed"):
            return j.json()["status"]
        time.sleep(3)
    return "timeout"


def main():
    with httpx.Client(base_url=BASE, timeout=120) as c:
        base = tok(c)
        isso = tok(c, "isso", base)
        ss = c.get("/systems", headers=H(isso)).json()
        ltp = next(s for s in ss if s["acronym"] == "LTP")
        teg = next((s for s in ss if s["acronym"] == "TEG"), None)
        if not teg:
            r = c.post("/systems", headers=H(isso), json={
                "name": "Tactical Edge Gateway", "acronym": "TEG", "baseline_key": "high", "categorization_mode": "cnssi1253", "nss_determination": "yes",
                "description": "SYNTHETIC national security system example for the product demo (not a real system).",
                "operating_environment": "tactical", "information_types": [{"id": "C.3.1.3"}], "processes_pii": True,
                "confidentiality_impact": "Moderate", "integrity_impact": "High", "availability_impact": "Low"})
            print("create TEG", r.status_code, r.text[:200])
            teg = r.json()
        roles = c.get(f"/systems/{ltp['id']}/roles", headers=H(isso)).json()
        issm = tok(c, "issm", base)
        for ra in roles:
            r = c.post(f"/systems/{teg['id']}/roles", headers=H(issm), json={"user_id": ra["user_id"], "role": ra["role"]})
            print("role", ra["role"], r.status_code)
        cat = c.get(f"/systems/{teg['id']}/categorization/records", headers=H(isso))
        print("cat records", cat.status_code, cat.text[:150])
        cur = cat.json().get("current") if cat.status_code == 200 else None
        if not cur:
            r = c.put(f"/systems/{teg['id']}/categorization", headers=H(isso), json={
                "mode": "cnssi1253", "nss_determination": "yes", "classified_information": "no", "processes_pii": True,
                "information_types": [{"id": "C.3.1.3", "c": "Moderate", "i": "High", "a": "Low",
                                       "rationale": "Integrity of tactical security data is mission-critical (synthetic example)."}],
                "rationale": "Mission data integrity is critical; confidentiality moderate; availability low (synthetic example)."})
            print("categorize", r.status_code, r.text[:200])
            cur = c.get(f"/systems/{teg['id']}/categorization/records", headers=H(isso)).json().get("current")
        if cur and cur.get("status") != "approved":
            ao = tok(c, "ao", base)
            r = c.post(f"/systems/{teg['id']}/categorization/records/{cur['id']}/approve", headers=H(ao),
                       json={"rationale": "Categorization M-H-L reviewed against mission impact; approved (synthetic demo)."})
            print("AO approve", r.status_code, r.text[:200])
        r = c.post(f"/systems/{teg['id']}/select/cnssi-baseline", headers=H(isso), json={"to": "M-H-L"})
        print("cnssi baseline", r.status_code, r.text[:200])
        wbs = c.get(f"/systems/{ltp['id']}/tr/workbooks", headers=H(isso)).json()
        if not wbs:
            r = c.post(f"/systems/{ltp['id']}/tr/workbooks", headers=H(isso), files={"file": ("BLANK_TRExport.xlsx", BLANK.read_bytes(),
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
            print("tr upload", r.status_code, r.text[:200])
            wbs = [r.json()]
        wb = wbs[0]
        print("wb", wb.get("id"), wb.get("status"), wb.get("row_count") or wb.get("counts"))
        if wb.get("status") not in ("ready", "generated", "reviewing", "review"):
            r = c.post(f"/tr/workbooks/{wb['id']}/generate", headers=H(isso), json={"populate": True})
            print("generate", r.status_code, r.text[:200])
            if r.status_code == 202:
                print("generate job", wait_job(c, isso, r.json()["job_id"]))
        print({"ltp": ltp["id"], "teg": teg["id"], "wb": wb["id"]})


main()
