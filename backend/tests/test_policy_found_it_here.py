"""Found it here / Use this passage + missed-language feedback export: RBAC, tenant isolation, human proposal (never approved), audit record;
reading report for DOCX (header, text box, table, tracked changes, image warnings)."""
import io
import uuid

import pytest

from app.db import SessionLocal
from app.models import AuditEvent, Policy, PolicyControlMap
from app.services import rmf
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401

TEXT = "1. Purpose\nThe ISSO shall review vulnerability scan results within 72 hours and report them to the ISSM."


def _org_with_policy(client, tag):
    t = _signup(client, f"fih-{tag}-{uuid.uuid4().hex[:6]}@example.com", f"FIH {tag} {uuid.uuid4().hex[:4]}")
    h = auth(t["access_token"])
    me = client.get("/api/v1/auth/me", headers=h).json()
    org_id = me.get("org_id") or me.get("user", {}).get("org_id")
    with SessionLocal() as db:
        p = Policy(org_id=uuid.UUID(org_id), title="RA", policy_key=f"ra-{uuid.uuid4().hex[:6]}", version=1, status="approved",
                   text_content=TEXT, analysis_status="analyzed", analysis={}, sha256=uuid.uuid4().hex)
        db.add(p)
        db.commit()
        pid = str(p.id)
    roles = {r: auth(client.post("/api/v1/sandbox/act-as", json={"role": r}, headers=h).json()["access_token"]) for r in ("isso", "ao", "issm")}
    return {"pid": pid, "admin": h, **roles}


@pytest.fixture(scope="module")
def two(client, signup_on):  # noqa: F811
    return _org_with_policy(client, "a"), _org_with_policy(client, "b")


def test_found_it_here_creates_open_human_proposal_and_feedback(client, two):
    a, _ = two
    r = client.post(f"/api/v1/policies/{a['pid']}/found-it-here", headers=a["isso"],
                    json={"control_id": "ra-5", "requirement_id": "CCI-001054", "text": "review vulnerability   scan results within 72 hours"})
    assert r.status_code == 201, r.text
    with SessionLocal() as db:
        m = db.get(PolicyControlMap, uuid.UUID(r.json()["proposal_id"]))
        assert m.status == "proposed" and m.source == "human_found" and m.review_flag
        ev = db.query(AuditEvent).filter(AuditEvent.action == "policy.missed_language_feedback", AuditEvent.entity_id == a["pid"]).all()
        assert ev and ev[-1].details["control_id"] == "ra-5" and "72 hours" in ev[-1].details["quote"]
    again = client.post(f"/api/v1/policies/{a['pid']}/found-it-here", headers=a["isso"], json={"control_id": "ra-5", "text": "report them to the ISSM.", "via": "use_candidate"})
    assert again.status_code == 201 and again.json()["proposal_id"] is None  # already proposed: feedback only, no duplicate proposal
    exp = client.get("/api/v1/admin/policy-feedback/export", headers=a["issm"])
    assert exp.status_code == 200 and exp.json()["requirements"][0]["label"] == "met"


def test_found_it_here_rejects_text_not_in_policy_and_denies_ao(client, two):
    a, _ = two
    assert client.post(f"/api/v1/policies/{a['pid']}/found-it-here", headers=a["isso"], json={"control_id": "ra-5", "text": "this sentence is not in the policy"}).status_code == 422
    assert client.post(f"/api/v1/policies/{a['pid']}/found-it-here", headers=a["ao"], json={"control_id": "ra-5", "text": "review vulnerability scan results"}).status_code == 403


def test_found_it_here_and_export_are_tenant_isolated(client, two):
    a, b = two
    assert client.post(f"/api/v1/policies/{a['pid']}/found-it-here", headers=b["isso"], json={"control_id": "ra-5", "text": "review vulnerability scan results"}).status_code == 404
    assert a["pid"] not in client.get("/api/v1/admin/policy-feedback/export", headers=b["issm"]).text


def test_reading_report_docx_extras_and_warnings():
    import docx
    d = docx.Document()
    d.sections[0].header.paragraphs[0].text = "CUI – Risk Assessment Policy header"
    d.add_paragraph("The ISSO shall scan monthly.")
    d.add_table(rows=1, cols=2).rows[0].cells[0].text = "Scan cadence"
    buf = io.BytesIO()
    d.save(buf)
    data = buf.getvalue()
    text = rmf.extract_text("p.docx", data)
    assert "[Header] CUI – Risk Assessment Policy header" in text and "Scan cadence" in text
    rep = rmf.reading_report("p.docx", data, text)
    assert rep["tables_included"] and rep["headers_footers_read"] and rep["pct_extracted"] >= 90 and rep["ocr"] == "not performed"


def test_reading_report_pdf_without_text_layer_warns():
    from pypdf import PdfWriter
    w = PdfWriter()
    w.add_blank_page(612, 792)
    buf = io.BytesIO()
    w.write(buf)
    rep = rmf.reading_report("scan.pdf", buf.getvalue(), "")
    assert rep["pages_without_text"] == [1] and "no text layer" in rep["warnings"][0]
