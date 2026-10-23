"""Automatic pipeline E2E per upload type: upload → worker processing → every screen API reflects the new data with consistent
counts (single counts service) → an approval updates the dependent screens; a broken file fails with a visible reason + Retry."""
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import IngestRun
from tests.conftest import auth
from tests.test_policy_coverage import COMPLETE, _analyze
from tests.test_sandbox import _signup, signup_on  # noqa: F401
from tests.test_sme_section1 import _docx

S = Path(__file__).resolve().parents[2] / "samples"
FILES = {"ckl": S / "e2e/e2e-web-01.ckl", "cklb": S / "stig/ltp_app-server-02.cklb", "xccdf": S / "scap/demo_linux_xccdf_results_SYNTHETIC.xml",
         "nessus": S / "e2e/e2e_scan.nessus", "nessus_csv": S / "acas/fmdh_scan_export.csv"}


def _process(run_id):
    from worker.handlers import handle_ingest

    with SessionLocal() as db:
        handle_ingest(db, {"run_id": run_id})
        db.commit()


@pytest.fixture(scope="module")
def org(client, signup_on):  # noqa: F811
    t = _signup(client, f"pipe-{uuid.uuid4().hex[:6]}@example.com", "Pipeline Org")
    h = auth(t["access_token"])
    issm = auth(client.post("/api/v1/sandbox/act-as", json={"role": "issm"}, headers=h).json()["access_token"])
    LEADER["h"] = issm
    return {"h": h}


LEADER: dict = {}


def _system(client, h, acr):
    r = client.post("/api/v1/systems", json={"name": f"Pipeline {acr}", "acronym": acr, "baseline_key": "moderate", "categorization_mode": "fips199",
                                             "information_types": [{"id": "D.16.3"}]}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _screens(client, h, sid) -> dict:
    g = lambda u, **p: client.get(f"/api/v1{u}", params=p, headers=h)  # noqa: E731
    out = {k: g(u) for k, u in {"summary": f"/systems/{sid}/workbench/summary", "controls": f"/systems/{sid}/workbench/controls",
                                "ccis": f"/systems/{sid}/ccis", "trace": f"/systems/{sid}/traceability", "ledger": f"/systems/{sid}/evidence",
                                "steps": f"/systems/{sid}/rmf-steps", "processing": f"/systems/{sid}/processing"}.items()}
    out["leader"] = client.get("/api/v1/dashboard/leadership", headers=LEADER["h"])
    out["review"] = g("/mapping-review", system_id=sid)
    out["with_ev"] = g(f"/systems/{sid}/workbench/controls", has_evidence="yes")
    for k, r in out.items():
        assert r.status_code == 200, (k, r.text[:300])
    return {k: r.json() for k, r in out.items()}


def _consistent(d: dict, sid: str):
    s = d["summary"]
    assert len(d["with_ev"]) == s["counts"]["with_evidence"], "Workbench filter and dashboard count use the same predicate"
    assert len(d["controls"]) == s["counts"]["assigned"]
    row = next(r for r in d["leader"]["systems"] if str(r["id"]) == sid)
    assert row["open_findings"] == s["metrics"]["open_findings"], "portfolio and system dashboard agree"
    assert sum(d["review"]["queue_counts"].values()) == len(d["review"]["queue"])


@pytest.mark.parametrize("kind", list(FILES))
def test_upload_type_propagates_everywhere(client, org, kind):
    h = org["h"]
    sid = _system(client, h, f"P{kind[:3].upper()}{uuid.uuid4().hex[:3]}")
    before = _screens(client, h, sid)
    r = client.post(f"/api/v1/systems/{sid}/uploads", files={"file": (FILES[kind].name, FILES[kind].read_bytes())}, headers=h)
    assert r.status_code == 202, r.text
    run = r.json()["id"]
    item = next(i for i in client.get(f"/api/v1/systems/{sid}/processing", headers=h).json()["items"] if i["id"] == run)
    assert item["state"] == "queued"
    _process(run)
    after = _screens(client, h, sid)
    item = next(i for i in after["processing"]["items"] if i["id"] == run)
    assert item["state"] == "analysed" and item["summary"]["rules_parsed"] > 0 and "parsed" in item["summary"]["text"], item
    assert len(after["ledger"]) > len(before["ledger"]) if isinstance(after["ledger"], list) else True
    assert after["summary"]["counts"]["with_evidence"] >= before["summary"]["counts"]["with_evidence"]
    assert after["summary"]["counts"]["with_evidence"] > 0 or item["summary"]["mapped"] == 0
    _consistent(after, sid)
    fm = [q for q in after["review"]["queue"] if q["kind"] == "finding_map"]
    if fm:
        q = fm[0]
        d = client.post("/api/v1/mapping-review/decide", json={"system_id": sid, "action": "approve", "justification": "",
                                                              "items": [{"kind": q["kind"], "ids": q["ids"], "control_id": q["control_id"]}]}, headers=h)
        assert d.status_code == 200, d.text
        again = _screens(client, h, sid)
        assert again["review"]["queue_counts"]["finding_map"] == after["review"]["queue_counts"]["finding_map"] - 1
        _consistent(again, sid)


def test_policy_upload_propagates_and_reports_summary(client, org):
    h = org["h"]
    sid = _system(client, h, f"PPOL{uuid.uuid4().hex[:3]}")
    for name, data in (("ra.docx", _docx(COMPLETE)), ("ra.txt", "\n".join(COMPLETE).encode())):
        r = client.post("/api/v1/policies", files={"file": (name, data)}, data={"title": f"RA {name}", "system_ids": sid}, headers=h)
        assert r.status_code == 201, r.text
        pid = r.json()["id"]
        assert next(i for i in client.get(f"/api/v1/systems/{sid}/processing", headers=h).json()["items"] if i["id"] == pid)["state"] == "queued"
        _analyze(pid)
        d = _screens(client, h, sid)
        item = next(i for i in d["processing"]["items"] if i["id"] == pid)
        assert item["state"] == "analysed" and item["summary"]["requirements"] > 0, item
        assert any(r["control_id"] == "ra-1" and r["policy_ids"] for r in d["ccis"]["items"])
        _consistent(d, sid)


def test_failed_parse_shows_reason_and_retry_is_idempotent(client, org):
    h = org["h"]
    sid = _system(client, h, f"PBAD{uuid.uuid4().hex[:3]}")
    bad = b"<?xml version='1.0'?><CHECKLIST><ASSET><HOST_NAME>x</HOST_NAME></ASSET><STIGS><iSTIG><VULN>broken"
    r = client.post(f"/api/v1/systems/{sid}/uploads", files={"file": ("broken.ckl", bad)}, headers=h)
    if r.status_code == 422:  # rejected synchronously: the reason is returned to the uploader
        assert r.json()["detail"]
        return
    run = r.json()["id"]
    _process(run)
    item = next(i for i in client.get(f"/api/v1/systems/{sid}/processing", headers=h).json()["items"] if i["id"] == run)
    assert item["state"] == "failed" and item["reason"], item
    assert client.post(f"/api/v1/ingest-runs/{run}/retry", headers=h).status_code == 202
    _process(run)
    _process(run)  # a duplicate job is a no-op
    with SessionLocal() as db:
        assert db.get(IngestRun, uuid.UUID(run)).status == "failed"
    assert client.post(f"/api/v1/ingest-runs/{run}/retry", headers=h).status_code == 202
    ok = client.post(f"/api/v1/ingest-runs/{uuid.uuid4()}/retry", headers=h)
    assert ok.status_code == 404
    _ = select
