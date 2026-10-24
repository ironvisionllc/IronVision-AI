"""SME section 1: fresh sign-up starts empty (DB-level), Load demo data, one source of truth for counts, policy→control mapping
(parser + manual map/reject + workbench), parameter export, workbench filters, has-evidence, status save, evidence formats."""
import csv
import io
import json
import uuid

import pytest
from sqlalchemy import inspect as sa_inspect, select, text

from app.db import SessionLocal
from app.models import ControlAssignment, Organization, System, User
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401  (fixture)

# Tenant-scoped rows a brand-new sign-up legitimately has: its users/personas + tenant CONFIG (no operational/demo data).
ALLOWED = {"users", "decision_rules", "cat_rules", "poam_match_rules", "dedup_rules", "audit_events", "notification_prefs", "app_settings"}

RA_POLICY = [
    "Risk Assessment Policy (synthetic)",
    "1. Purpose. This Risk Assessment policy establishes the purpose of risk assessment for the organization and implements RA-1a.1.",
    "2. Scope. This policy applies to all organizational systems, personnel and contractors.",
    "3. Roles and responsibilities. The ISSM coordinates risk assessment; system owners are accountable. Management commitment is affirmed.",
    "4. Coordination among organizational entities and compliance with applicable laws, executive orders and directives is required.",
    "5. Procedures. Risk assessment procedures (RA-1 a.2) facilitate implementation of this policy and the associated controls.",
    "6. Review. The official designated in RA-1b reviews and updates this risk assessment policy annually.",
]


def _docx(lines):
    import docx
    d = docx.Document()
    for ln in lines:
        d.add_paragraph(ln)
    b = io.BytesIO()
    d.save(b)
    return b.getvalue()


def _pdf(lines):
    esc = [ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for ln in lines]
    stream = "BT /F1 9 Tf 40 800 Td 12 TL " + " ".join(f"({x}) Tj T*" for x in esc) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode()
    x = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
    return out + f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n".encode()


@pytest.fixture(scope="module")
def fresh(client, signup_on):  # noqa: F811
    t = _signup(client, f"sme-{uuid.uuid4().hex[:6]}@example.com", "SME Fresh Org")
    with SessionLocal() as db:
        org_id = db.scalar(select(User.org_id).where(User.email == t["user"]["email"]))
    return {"h": auth(t["access_token"]), "org_id": org_id}


def _tenant_counts(org_id) -> dict:
    with SessionLocal() as db:
        insp = sa_inspect(db.get_bind())
        out = {}
        for tbl in insp.get_table_names():
            cols = {c["name"] for c in insp.get_columns(tbl)}
            if tbl == "organizations":
                continue
            if "org_id" in cols:
                n = db.execute(text(f'SELECT count(*) FROM "{tbl}" WHERE org_id = :o'), {"o": org_id}).scalar()
            elif "system_id" in cols:
                n = db.execute(text(f'SELECT count(*) FROM "{tbl}" t JOIN systems s ON s.id = t.system_id WHERE s.org_id = :o'), {"o": org_id}).scalar()
            else:
                continue
            if n:
                out[tbl] = n
        return out


def test_fresh_signup_is_empty_db_level_and_no_synthetic_content(client, fresh):
    counts = _tenant_counts(fresh["org_id"])
    assert set(counts) <= ALLOWED, {k: v for k, v in counts.items() if k not in ALLOWED}
    with SessionLocal() as db:
        from app.models import AppSetting
        keys = set(db.scalars(select(AppSetting.key).where(AppSetting.org_id == fresh["org_id"])))
        assert "demo_data" not in keys
    cu = client.get("/api/v1/content-updates", headers=fresh["h"]).json()
    for t in cu["types"]:
        assert t["available"] == [] and not t.get("superseded"), t["content_type"]
        assert not any((v.get("meta") or {}).get("synthetic") for v in t["installed"]), t["content_type"]
    assert cu["history"] == []
    vers = client.get("/api/v1/content/versions", headers=fresh["h"]).json()
    assert vers and not any((v.get("meta") or {}).get("synthetic") for v in vers)
    assert {v["content_type"] for v in vers} >= {"oscal_catalog", "cci_list"}   # reference catalogs stay available
    with SessionLocal() as db:
        from app.models import ContentVersion
        synth = db.scalar(select(ContentVersion.id).where(ContentVersion.meta["synthetic"].astext == "true").limit(1))
    if synth:
        assert client.post(f"/api/v1/content-updates/{synth}/preview", headers=fresh["h"]).status_code == 404
    st = client.get("/api/v1/sandbox/status", headers=fresh["h"]).json()
    assert st["demo_data_loaded"] is False


def test_load_demo_data_idempotent_and_cleared(client, signup_on):  # noqa: F811
    t = _signup(client, f"ld-{uuid.uuid4().hex[:6]}@example.com", "Load Demo Org")
    h = auth(t["access_token"])
    r = client.post("/api/v1/sandbox/demo-data", headers=h)
    assert r.status_code == 200 and r.json()["already_loaded"] is False and r.json()["systems"] > 0, r.text
    n = len(client.get("/api/v1/systems", headers=h).json())
    again = client.post("/api/v1/sandbox/demo-data", headers=h).json()
    assert again["already_loaded"] is True and len(client.get("/api/v1/systems", headers=h).json()) == n
    assert client.get("/api/v1/sandbox/status", headers=h).json()["demo_data_loaded"] is True
    assert any(x["installed"] for x in client.get("/api/v1/content-updates", headers=h).json()["types"] if x["content_type"] == "stig_benchmark")
    assert client.post("/api/v1/sandbox/reset", headers=h).status_code == 200
    assert client.get("/api/v1/systems", headers=h).json() == []
    assert client.get("/api/v1/sandbox/status", headers=h).json()["demo_data_loaded"] is False


def test_demo_tenant_cannot_load_demo_data(client, token):
    assert client.post("/api/v1/sandbox/demo-data", headers=auth(token("isso@aegisrmf.demo"))).status_code in (403, 404)


def _demo_system(client, token):
    h = auth(token("isso@aegisrmf.demo"))
    return h, client.get("/api/v1/systems", headers=h).json()[0]["id"]


def test_counts_single_source_of_truth(client, token):
    from app.services.counts import catalog_counts, system_counts
    h, sid = _demo_system(client, token)
    with SessionLocal() as db:
        cc = catalog_counts(db)
        sc = system_counts(db, db.get(System, uuid.UUID(sid)))
    assert cc["base_controls"] + cc["enhancements"] == cc["rev5_total"] and cc["rev5_total"] - cc["withdrawn"] == cc["selectable"]
    assert client.get("/api/v1/content/counts", headers=h).json() == cc
    st = client.get("/api/v1/content/stats", headers=h).json()
    assert st["counts"] == cc and st["controls_total"] == cc["rev5_total"] and st["base_controls"] == cc["base_controls"]
    assert client.get("/api/v1/controls", params={"limit": 1}, headers=h).json()["total"] == cc["selectable"]
    assert client.get("/api/v1/controls", params={"limit": 1, "include_withdrawn": True}, headers=h).json()["total"] == cc["rev5_total"]
    for b, n in cc["baselines"].items():
        assert client.get("/api/v1/controls", params={"limit": 1, "baseline": b}, headers=h).json()["total"] == n, b
        assert cc["labels"]["baselines"][b].startswith(f"{n:,} in the ")
    s = client.get(f"/api/v1/systems/{sid}/workbench/summary", headers=h).json()
    assert s["counts"] == sc and s["total_assigned"] == sc["assigned"] and s["with_evidence"] == sc["with_evidence"]
    assert sc["baseline"] - sc["removed"] + sc["overlay_added"] + sc["tailored_in"] == sc["assigned"]
    assert len(client.get(f"/api/v1/systems/{sid}/workbench/controls", headers=h).json()) == sc["assigned"]
    rmf = client.get(f"/api/v1/systems/{sid}/rmf", headers=h)
    if rmf.status_code == 200:
        assert sc["labels"]["assigned"] in rmf.text


def test_has_evidence_filter_matches_counts(client, token):
    h, sid = _demo_system(client, token)
    s = client.get(f"/api/v1/systems/{sid}/workbench/summary", headers=h).json()
    url = f"/api/v1/systems/{sid}/workbench/controls"
    yes = client.get(url, params={"has_evidence": "yes"}, headers=h).json()
    no = client.get(url, params={"has_evidence": "no"}, headers=h).json()
    cur = client.get(url, params={"evidence": "current"}, headers=h).json()
    assert len(yes) == s["with_evidence"] and len(yes) + len(no) == s["total_assigned"] and len(cur) == s["with_current_evidence"]
    assert all(a["evidence_freshness_status"] != "no_evidence" for a in yes)


FILTER_VALUES = {"implementation_status": ["planned", "partially_implemented", "implemented", "inherited", "not_applicable"],
                 "assessment_status": ["not_assessed", "satisfied", "other_than_satisfied"], "responsibility": ["system", "shared", "inherited"],
                 "origin": ["baseline", "overlay", "tailored_in"], "monitoring_status": ["passing", "failing", "no_data", "inherited"]}


def test_every_workbench_filter_value_matches_db(client, token):
    h, sid = _demo_system(client, token)
    url = f"/api/v1/systems/{sid}/workbench/controls"
    with SessionLocal() as db:
        rows = list(db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == uuid.UUID(sid))))
    for col, vals in FILTER_VALUES.items():
        for v in vals:
            got = {a["control_id"] for a in client.get(url, params={col: v}, headers=h).json()}
            assert got == {a.control_id for a in rows if getattr(a, col) == v}, (col, v)
    fam = {a["control_id"] for a in client.get(url, params={"family": "AC"}, headers=h).json()}
    assert fam and all(c.startswith("ac-") for c in fam) and fam == {a.control_id for a in rows if a.control_id.startswith("ac-")}
    both = client.get(url, params={"family": "ac", "implementation_status": "planned"}, headers=h).json()
    assert all(a["control_id"].startswith("ac-") and a["implementation_status"] == "planned" for a in both)


def test_status_save_then_filter_and_last_changed(client, token):
    h, sid = _demo_system(client, token)
    url = f"/api/v1/systems/{sid}/workbench/controls"
    cid = client.get(url, params={"implementation_status": "planned"}, headers=h).json()[0]["control_id"]
    r = client.put(f"{url}/{cid}/status", json={"implementation_status": "partially_implemented"}, headers=h)
    assert r.status_code == 200 and r.json()["status_last_changed"]["action"] == "implementation.status_changed", r.text
    assert cid in {a["control_id"] for a in client.get(url, params={"implementation_status": "partially_implemented"}, headers=h).json()}
    assert cid not in {a["control_id"] for a in client.get(url, params={"implementation_status": "planned"}, headers=h).json()}
    d = client.get(f"{url}/{cid}", headers=h).json()
    assert d["assignment"]["implementation_status"] == "partially_implemented" and d["status_last_changed"]["email"] == "isso@aegisrmf.demo"
    assert client.put(f"{url}/{cid}/status", json={"implementation_status": "bogus"}, headers=h).status_code == 422
    assert client.put(f"{url}/{cid}/status", json={"implementation_status": "planned"}, headers=h).status_code == 200


@pytest.mark.parametrize("kind", ["docx", "pdf"])
def test_ra_policy_maps_to_ra1_not_ac17(client, fresh, kind):
    from worker.handlers import handle_policy_analyze
    data = _docx(RA_POLICY) if kind == "docx" else _pdf(RA_POLICY)
    r = client.post("/api/v1/policies", files={"file": (f"ra-policy.{kind}", data)}, data={"title": f"RA Policy {kind}"}, headers=fresh["h"])
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    with SessionLocal() as db:
        handle_policy_analyze(db, {"policy_id": pid})
        db.commit()
    d = client.get(f"/api/v1/policies/{pid}", headers=fresh["h"]).json()
    maps = d["control_mappings"]
    assert maps and maps[0]["control_id"] == "ra-1" and maps[0]["confidence"] == "High", maps[:3]
    assert "explicit_id" in maps[0]["source"] and "statement_language" in maps[0]["source"] and maps[0]["snippets"]
    assert {"RA-1a.1"} <= set(maps[0]["parts"])
    assert not any(m["control_id"].startswith("ac-17") for m in maps)
    assert not any(f["control_id"] and f["control_id"].startswith("ac-17") for f in d["findings"])


def test_parser_id_forms():
    from app.services.policy_mapping import CID_RX
    got = [m.group(0) for m in CID_RX.finditer("RA-1, RA-1a, RA-1a.1, RA-1.a, AC-2(1), AC-2 (1) and SC-7(4)(a)")]
    assert got[:6] == ["RA-1", "RA-1a", "RA-1a.1", "RA-1.a", "AC-2(1)", "AC-2 (1)"]


def test_manual_map_reject_history_workbench_and_export(client, token):
    h, sid = _demo_system(client, token)
    r = client.post("/api/v1/policies", files={"file": ("ra.docx", _docx(RA_POLICY))}, data={"title": "RA Map Test", "system_ids": sid}, headers=h)
    pid = r.json()["id"]
    assert client.post(f"/api/v1/policies/{pid}/control-mappings", json={"control_ids": ["zz-99"]}, headers=h).status_code == 422
    assert client.post(f"/api/v1/policies/{pid}/control-mappings", json={"control_ids": ["ac-2", "ra-1"]}, headers=h).json()["mapped"] == ["ac-2", "ra-1"]
    assert client.post(f"/api/v1/policies/{pid}/control-mappings/reject", json={"control_id": "ac-2", "justification": "short"}, headers=h).status_code == 422
    assert client.post(f"/api/v1/policies/{pid}/control-mappings/reject", json={"control_id": "ac-2", "justification": "Not an access control policy"}, headers=h).status_code == 200
    d = client.get(f"/api/v1/policies/{pid}", headers=h).json()
    cur = {m["control_id"]: m for m in d["control_mappings"]}
    assert cur["ra-1"]["status"] == "mapped" and cur["ra-1"]["decider_name"] and cur["ac-2"]["status"] == "rejected"
    assert len([x for x in d["mapping_history"] if x["control_id"] == "ac-2"]) == 2      # versioned, not overwritten
    w = client.get(f"/api/v1/systems/{sid}/workbench/controls/ra-1", headers=h).json()
    pm = [m for m in w["policy_mappings"] if m["policy_id"] == pid]
    assert pm and pm[0]["status"] == "mapped" and pm[0]["decided_at"]
    assert not [m for m in client.get(f"/api/v1/systems/{sid}/workbench/controls/ac-2", headers=h).json()["policy_mappings"] if m["policy_id"] == pid]
    with SessionLocal() as db:
        from app.models import AuditEvent
        acts = set(db.scalars(select(AuditEvent.action).where(AuditEvent.entity_id == pid)))
    assert {"policy.control_mapped", "policy.control_mapping_rejected"} <= acts
    other = _other_tenant_token(client)
    if other:
        assert client.post(f"/api/v1/policies/{pid}/control-mappings", json={"control_ids": ["ra-1"]}, headers=other).status_code in (403, 404)
    csvr = client.get(f"/api/v1/policies/{pid}/parameters.csv", headers=h)
    rows = list(csv.reader(io.StringIO(csvr.text.lstrip("\ufeff"))))
    assert rows[0][:4] == ["System", "Control ID", "Enhancement", "Parameter ID"] and len(rows) > 1
    assert any(r[1] == "RA-1" and r[5] for r in rows[1:]), "the policy's RA-1 parameter value is in the comparison"


def _other_tenant_token(client):
    r = client.post("/api/v1/auth/login", json={"email": "isso.b@tenantb.demo", "password": "Demo!Pass-2026x"})
    return auth(r.json()["access_token"]) if r.status_code == 200 else None


def test_export_parameters_for_policy_values(client, token):
    h, sid = _demo_system(client, token)
    pols = client.get("/api/v1/policies", headers=h).json()
    items = pols if isinstance(pols, list) else next(v for v in pols.values() if isinstance(v, list))
    pid = next(p["id"] for p in items if p.get("analysis_status") == "analyzed" and p.get("title", "").startswith("Access"))
    rows = list(csv.reader(io.StringIO(client.get(f"/api/v1/policies/{pid}/parameters.csv", headers=h).text.lstrip("\ufeff"))))
    assert rows[0][0] == "System" and any(r[5] for r in rows[1:]), rows[:4]


# ---- evidence formats: synthetic fixtures, detection by content ----
CKL = b'<?xml version="1.0"?><CHECKLIST><ASSET><HOST_NAME>h1</HOST_NAME></ASSET><STIGS><iSTIG><STIG_INFO/></iSTIG></STIGS></CHECKLIST>'
CKLB = json.dumps({"title": "synthetic", "target_data": {"host_name": "h1"}, "stigs": [{"stig_name": "Synthetic STIG", "rules": []}]}).encode()
XCCDF_NS = 'xmlns="http://checklists.nist.gov/xccdf/1.2"'


def _xccdf_results(pad: int) -> bytes:
    rules = "".join(f'<Rule id="xccdf_mil.disa.stig_rule_SV-{i}r1_rule" severity="medium"><title>Synthetic rule {i}</title></Rule>' for i in range(pad))
    tr = ('<TestResult id="xccdf_scc_testresult"><target>host-1</target>'
          '<rule-result idref="xccdf_mil.disa.stig_rule_SV-1r1_rule" severity="medium"><result>fail</result></rule-result></TestResult>')
    return f'<?xml version="1.0"?><Benchmark {XCCDF_NS} id="synthetic">{rules}{tr}</Benchmark>'.encode()


@pytest.mark.parametrize("name,data,fmt", [
    ("x.ckl", CKL, "ckl"), ("x.cklb", CKLB, "cklb"), ("renamed.json", CKLB, "cklb"),
    ("scc_XCCDF-Results.xml", _xccdf_results(12000), "xccdf"),                   # > 2 MB, TestResult after the rules (SCC/DISA layout)
    ("arf.xml", b'<?xml version="1.0"?><arf:asset-report-collection xmlns:arf="urn:x"><TestResult/></arf:asset-report-collection>', "xccdf"),
    ("scan.nessus", b'<?xml version="1.0" ?><NessusClientData_v2><Report name="r"/></NessusClientData_v2>', "nessus_xml"),
    ("acas.csv", b'"Plugin","Plugin Name","Severity","IP Address","DNS Name"\n"19506","Info","Info","10.0.0.1","h"\n', "nessus_csv"),
    ("nessus.csv", b"Plugin ID,CVE,CVSS,Risk,Host,Protocol,Port,Name\n1,,,None,h,tcp,0,x\n", "nessus_csv"),
])
def test_detect_by_content(name, data, fmt):
    from app.services.ingest.parsers import detect_format
    assert len(data) < 2_000_000 or b"TestResult" not in data[:2_000_000]
    assert detect_format(name, data) == fmt


@pytest.mark.parametrize("name,data,why", [
    ("bench.xml", f'<?xml version="1.0"?><Benchmark {XCCDF_NS}><Rule id="r"/></Benchmark>'.encode(), "no <TestResult>"),
    ("other.xml", b'<?xml version="1.0"?><!-- c --><inventory><x/></inventory>', "root element is <inventory>"),
    ("policy.pdf", b"%PDF-1.4\n...", "policy document (PDF)"),
    ("data.json", b'{"foo": 1}', "neither CKLB"),
    ("hosts.csv", b"name,ip\nh,1\n", "no 'Plugin ID' column"),
])
def test_rejections_say_why_and_list_supported(name, data, why):
    from app.services.ingest.parsers import ParseError, detect_format
    with pytest.raises(ParseError) as e:
        detect_format(name, data)
    assert why in str(e.value) and ".cklb" in str(e.value) and "Nessus/ACAS" in str(e.value)
