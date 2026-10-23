"""Official CNSSI 1253 overlays: parse accuracy against the PDFs (hand-verified samples with page numbers), totals, and the
Select-step behaviour (apply adds/removes + parameter values, remove reverses exactly, variant exclusivity, counts reconcile)."""
import json
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401

REF = Path(__file__).resolve().parents[1] / "app" / "services" / "content" / "cnssi1253_overlays.json"
PDFS = Path("/app/reference/cnssi1253")
RESTRICTED = PDFS / "derived" / "cnssi1253_restricted_overlays.json"
FOUO_SAMPLES = PDFS / "derived" / "fouo_verification.json"

# (source id, variant, flags, PDF page of the summary table) – read by hand from the PDF summary tables.
SAMPLES = {
    "classified": [("AC-1", "classified", "+GR", 5), ("AC-3(2)", "classified", "+R", 5), ("AC-11", "classified", "+VR", 5), ("AC-16(5)", "classified", "+GR", 5),
                   ("AT-2", "classified", "+GVR", 6), ("AU-6(5)", "classified", "+GVR", 6), ("CA-3", "classified", "+GVR", 6), ("IR-9", "classified", "+GVR", 7),
                   ("MP-6", "classified", "+VR", 7), ("PE-22", "classified", "+VR", 7), ("SC-7(26)", "classified", "+VR", 8), ("SC-28", "classified", "+GVR", 8),
                   ("SR-12", "classified", "+VR", 9)],
    "privacy": [("AC-1", "acct", "BASELINE", 15), ("AC-2", "acct", "+GVR", 15), ("AC-2", "high", "+GVR", 15), ("AC-2(1)", "moderate", "+R", 15),
                ("AC-2(6)", "enhancing", "*R", 15), ("AC-2(8)", "low", "--", 15), ("AC-2(9)", "acct", "+VR", 15), ("AC-3(9)", "low", "+R", 15),
                ("AC-3(9)", "moderate", "+VR", 15), ("AC-4(8)", "enhancing", "*VR", 16), ("AC-6(1)", "high", "+GR", 16), ("AC-8", "moderate", "BASELINE", 16),
                ("AC-16", "high", "+GVR", 16), ("AC-11", "low", "+VR", 16)],
    "space": [("AC-2", "space", "--", 7), ("AC-2(1)", "space", "--", 7), ("AC-3(2)", "space", "+G", 7), ("AC-3(3)", "space", "+G", 7), ("AC-3(13)", "space", "+G", 7),
              ("AC-4(2)", "space", "+G", 8), ("AC-4(4)", "space", "--", 8), ("AC-5", "space", "--", 8), ("AC-7", "space", "--", 8), ("AC-11(1)", "space", "--", 8),
              ("AC-16(6)", "space", "--", 8), ("AC-20(2)", "space", "--", 8)],
}
ABSENT = {"privacy": [("AC-2(1)", "low")]}


def _n(raw):
    m = re.match(r"([A-Z]{2})-(\d+)(?:\((\d+)\))?$", raw)
    return f"{m[1].lower()}-{int(m[2])}" + (f".{int(m[3])}" if m[3] else "")


def _page_text(pdf: Path, page: int) -> str | None:
    if not pdf.exists() or not shutil.which("pdftotext"):
        return None
    return subprocess.run(["pdftotext", "-layout", "-f", str(page), "-l", str(page), str(pdf), "-"], capture_output=True, text=True).stdout


def _check(data, samples, absent):
    for key, rows in samples.items():
        ov = data[key]
        by = {c["control_id"]: c for c in ov["controls"]}
        for sid, var, flags, page in rows:
            c = by[_n(sid)]
            assert c["by_variant"][var]["flags"] == flags, (key, sid, var)
            assert c["summary_page"] == page, (key, sid)
            txt = _page_text(PDFS / ov["document"]["file"], page)
            if txt is not None:
                assert sid.split("(")[0] in txt and (("CNSS Privacy Baseline" in txt) if flags == "BASELINE" else flags in txt), (key, sid, page)
        for sid, var in absent.get(key, []):
            assert var not in by[_n(sid)]["by_variant"], (key, sid, var)


def test_reference_is_versioned_sourced_and_public_only():
    d = json.loads(REF.read_text())
    assert set(d["overlays"]) == {"privacy", "classified", "space"}, "FOUO overlays must not ship in the public reference file"
    for k, ov in d["overlays"].items():
        doc = ov["document"]
        assert doc["public_release_ok"] and re.fullmatch(r"[0-9a-f]{64}", doc["sha256"]) and doc["date"] and doc["file"].endswith(".pdf")
        assert not doc["marking"].startswith("UNCLASSIFIED//FOUO") and not ov["ambiguous"] and not ov["flagged_ids"]
        assert all(c["in_rev5"] and re.fullmatch(r"[a-z]{2}-\d+(\.\d+)?", c["control_id"]) for c in ov["controls"])
        pdf = PDFS / doc["file"]
        if pdf.exists():
            import hashlib

            assert hashlib.sha256(pdf.read_bytes()).hexdigest() == doc["sha256"]


def test_hand_verified_samples_match_pdf():
    _check(json.loads(REF.read_text())["overlays"], SAMPLES, ABSENT)


@pytest.mark.skipif(not (RESTRICTED.exists() and FOUO_SAMPLES.exists()), reason="FOUO-derived data is kept out of git")
def test_fouo_overlays_hand_verified_samples():
    data = json.loads(RESTRICTED.read_text())["overlays"]
    v = json.loads(FOUO_SAMPLES.read_text())
    samples = {}
    for k, rows in v["samples"].items():
        by = {c["control_id"]: c for c in data[k]["controls"]}
        samples[k] = [(sid, var, flags, by[_n(sid)]["summary_page"]) for sid, var, flags in rows]
    _check(data, samples, {k: [tuple(x) for x in r] for k, r in v["absent"].items()})
    assert all(not ov["ambiguous"] and not ov["flagged_ids"] and "FOUO" in ov["document"]["marking"] for ov in data.values())


def test_totals_against_document_tables():
    d = json.loads(REF.read_text())["overlays"]
    assert len(d["classified"]["controls"]) == 108          # Table 1, pp. 5–9, counted by hand
    sp = d["space"]["controls"]
    assert (len(sp), sum(c["by_variant"]["space"]["action"] == "add" for c in sp), sum(c["by_variant"]["space"]["action"] == "remove" for c in sp)) == (345, 83, 262)
    order = ["acct", "low", "moderate", "high"]
    for c in d["privacy"]["controls"]:     # Section 3.2: each control set layers on the one below
        adds = [c["by_variant"].get(v, {}).get("action") == "add" for v in order]
        assert all(not adds[i] or adds[i + 1] for i in range(3)), c["source_id"]
    pdf = PDFS / d["space"]["document"]["file"]
    if pdf.exists() and shutil.which("pdftotext"):
        t = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout
        assert "There are 306 controls in the CNSSI 1253 H/H/H baseline that are not specifically identified in" in t
        a = t[t.index("Table 3 - Space Platform Overlay Applicable Baseline Controls"):]
        ids = set(re.findall(r"^\s{0,3}([A-Z]{2}-\d+(?:\(\d+\))?)\s", a, re.M)) | {f"{p}{s}" for p, s in re.findall(r"^\s{0,3}([A-Z]{2}-)\s+.*\n\s{0,3}(\d+\(\d+\))", a, re.M)}
        assert len(ids) == 306 and not ids & {c["source_id"] for c in sp}


@pytest.fixture(scope="module")
def ws(client, signup_on):  # noqa: F811
    t = _signup(client, f"ov-{uuid.uuid4().hex[:6]}@example.com", "Overlay Org")
    h = auth(t["access_token"])
    r = client.post("/api/v1/systems", json={"name": "Overlay System", "acronym": "OVS", "baseline_key": "moderate", "categorization_mode": "fips199",
                                             "information_types": [{"id": "D.16.3"}]}, headers=h)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert client.post(f"/api/v1/systems/{sid}/select/baseline", headers=h, json={"baseline_key": "moderate", "include_privacy": True}).status_code == 200
    return {"h": h, "sid": sid}


def _assigned(client, ws):
    return {r["control_id"]: r.get("origin") for r in client.get(f"/api/v1/systems/{ws['sid']}/traceability", headers=ws["h"]).json()}


def _ov(client, ws, key, on):
    return client.post(f"/api/v1/systems/{ws['sid']}/select/overlay", headers=ws["h"], json={"overlay_key": key, "apply": on})


def _reconciles(c):
    assert c["assigned"] == c["baseline"] + c["overlay_added"] - c["overlay_removed"] - c["tailored_out"] + c["tailored_in"]
    assert f"= {c['assigned']:,} assigned" in c["labels"]["reconciliation"] and "removed by overlays" in c["labels"]["reconciliation"]


def test_select_lists_groups_with_applicability_and_restricted_note(client, ws):
    g = {x["group"]: x for x in client.get(f"/api/v1/systems/{ws['sid']}/select", headers=ws["h"]).json()["overlay_groups"]}
    assert [v["variant"] for v in g["privacy"]["variants"]] == ["acct", "low", "moderate", "high"] and "audit logs" in g["privacy"]["question"]
    assert "classified information" in g["classified"]["question"] and g["classified"]["document"]["sha256"]
    for k in ("intelligence", "cds"):
        assert g[k]["restricted"] and (g[k]["loaded"] or "FOUO" in g[k]["note"])


def test_apply_classified_adds_sets_params_and_remove_reverses_exactly(client, ws):
    before = _assigned(client, ws)
    r = _ov(client, ws, "cnssi-classified", True)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["added"] and out["parameters_set"] > 0 and not out["removed"]
    _reconciles(out["counts"])
    assert out["counts"]["overlay_added"] == len(out["added"])
    det = client.get(f"/api/v1/systems/{ws['sid']}/select/overlays/cnssi-classified", headers=ws["h"]).json()
    row = next(c for c in det["controls"] if c["control_id"] == "ac-11")
    assert row["label"].startswith("Added by Classified System Overlay (CNSSI 1253 App. E Att. 5, p. 12)")
    assert any("15 minutes" in f["text"] for f in row["fields"] if "Parameter" in f["label"])
    new = next(c for c in det["controls"] if c["control_id"] == out["added"][0])
    assert new["added_by_this"] and new["assigned"]
    csv_r = client.get(f"/api/v1/systems/{ws['sid']}/parameters.csv", headers=ws["h"])
    assert csv_r.status_code == 200 and "attachment; filename=" in csv_r.headers["content-disposition"]
    lines = csv_r.text.splitlines()
    assert lines[0].startswith("row_type,source") and any(ln.startswith("overlay_parameter") and ",AC-11," in ln for ln in lines)
    wb = client.get(f"/api/v1/systems/{ws['sid']}/workbench/controls/ac-11", headers=ws["h"]).json()
    assert any(n["key"] == "cnssi-classified" and "p. 12" in n["cite"] for n in wb["overlay_notes"])
    back = _ov(client, ws, "cnssi-classified", False).json()
    assert sorted(back["removed"]) == sorted(out["added"])
    assert _assigned(client, ws) == before
    _reconciles(back["counts"])


def test_space_removals_are_recorded_and_restored(client, ws):
    before = _assigned(client, ws)
    out = _ov(client, ws, "cnssi-space", True).json()
    assert out["removed"] and set(out["removed"]) <= set(before)
    c = out["counts"]
    _reconciles(c)
    assert c["overlay_removed"] == len(set(out["removed"]) & {k for k, o in before.items() if o == "baseline"})
    sel = client.get(f"/api/v1/systems/{ws['sid']}/select", headers=ws["h"]).json()
    assert not any(t.get("overlay_key") for t in sel["tailoring"]), "overlay removals are not manual tailoring"
    det = client.get(f"/api/v1/systems/{ws['sid']}/select/overlays/cnssi-space", headers=ws["h"]).json()
    rm = next(x for x in det["controls"] if x["control_id"] == out["removed"][0])
    assert rm["removed_by_overlay"] and rm["label"].startswith("Removed by Space Platform Overlay (CNSSI 1253F Att. 2, p.")
    back = _ov(client, ws, "cnssi-space", False).json()
    assert sorted(back["restored"]) == sorted(out["removed"]) and _assigned(client, ws) == before


def test_privacy_variants_are_exclusive_and_shared_additions_survive(client, ws):
    before = _assigned(client, ws)
    assert _ov(client, ws, "cnssi-privacy-low", True).status_code == 200
    mod = _ov(client, ws, "cnssi-privacy-moderate", True).json()
    keys = client.get(f"/api/v1/systems/{ws['sid']}/select", headers=ws["h"]).json()["overlay_keys"]
    assert "cnssi-privacy-moderate" in keys and "cnssi-privacy-low" not in keys
    _reconciles(mod["counts"])
    assert _ov(client, ws, "cnssi-classified", True).status_code == 200
    _ov(client, ws, "cnssi-privacy-moderate", False)
    _ov(client, ws, "cnssi-classified", False)
    assert _assigned(client, ws) == before
    assert _ov(client, ws, "cnssi-classified", False).status_code == 422


def test_restricted_import_needs_admin_and_schema(client, ws):
    files = {"file": ("x.json", b'{"schema": 1, "overlays": {}}', "application/json")}
    assert client.post("/api/v1/overlays/import-reference", headers=ws["h"], files=files).status_code == 403


@pytest.mark.skipif(not RESTRICTED.exists(), reason="FOUO-derived data is kept out of git")
def test_restricted_reference_loads_in_rolled_back_transaction():
    from app.db import SessionLocal
    from app.models import Overlay
    from app.services.overlays import load_reference

    with SessionLocal() as db:
        created = load_reference(db, json.loads(RESTRICTED.read_text()))
        assert {"cnssi-intelligence-int-a", "cnssi-intelligence-int-c", "cnssi-cds-access", "cnssi-cds-transfer"} <= set(created) or not created
        rows = db.query(Overlay).filter(Overlay.overlay_key == "cnssi-cds-transfer", Overlay.is_active.is_(True)).all()
        assert rows and rows[0].details["ac-3.9"]["action"] == "add" and "ac-3.9" not in (db.query(Overlay).filter(
            Overlay.overlay_key == "cnssi-cds-access", Overlay.is_active.is_(True)).one().details or {})
        db.rollback()
