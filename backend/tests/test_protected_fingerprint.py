"""Droplet plan 6294cf78e70166ca: demo_account FAILED "non-sandbox users/organizations/role assignments/evidence changed".
Root cause: seed_phase1 called evaluate_freshness(db) for ALL evidence → restored evidence rows got a new `state` (+ updated_at)."""
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text

from app.db import SessionLocal, engine
from app.services import sandbox as sbx
from app.tools import recovery as r

SAMPLES = Path(__file__).resolve().parents[2] / "samples"
URL = engine.url.render_as_string(hide_password=False)
PROTECTED = {
    "users": ("select u.id from users u join organizations o on o.id = u.org_id where not o.is_sandbox order by u.id limit 1",
              "update users set title = :v where id = :i", "title"),
    "organizations": ("select o.id from organizations o where not o.is_sandbox order by o.id limit 1",
                      "update organizations set name = :v where id = :i", "name"),
    "role_assignments": ("select r.id from role_assignments r join users u on u.id = r.user_id join organizations o on o.id = u.org_id "
                         "where not o.is_sandbox order by r.id limit 1", "update role_assignments set role = :v where id = :i", "role"),
    "evidence": ("select e.id from evidence e join systems s on s.id = e.system_id join organizations o on o.id = s.org_id "
                 "where not o.is_sandbox order by e.id limit 1", "update evidence set name = :v where id = :i", "name"),
}


def _changed(cmp: dict) -> list:
    return [c for c, v in cmp.items() if v["changed"]]


def test_named_structure_and_only_a_new_sandbox_org_with_records_passes():
    before = r._fingerprint(URL)
    assert set(before) == {"users", "organizations", "role_assignments", "evidence"}
    with SessionLocal() as db:
        org = sbx.create_sandbox(db, None, "FP pass check", "fp-pass@example.invalid")   # sandbox org + 8 personas + role assignments
        db.commit()
    cmp = r.fingerprint_compare(before, r._fingerprint(URL))
    assert _changed(cmp) == [] and org.is_sandbox
    for v in cmp.values():
        assert set(v) == {"before", "after", "changed"} and len(v["before"]["sha256"]) == 64 and v["before"] == v["after"]


@pytest.mark.parametrize("cat", list(PROTECTED))
def test_a_changed_protected_row_fails_and_names_the_category_with_a_safe_diff(cat):
    sel, upd, col = PROTECTED[cat]
    with engine.begin() as c:
        rid = c.execute(text(sel)).scalar()
        assert rid is not None, f"test DB has no protected {cat} row"
        tbl = upd.split()[1]
        orig = c.execute(text(f"select {col} from {tbl} where id = :i"), {"i": rid}).scalar()
    before = r._fingerprint(URL)
    try:
        with engine.begin() as c:
            c.execute(text(upd), {"v": "changed-by-test", "i": rid})
        cmp = r.fingerprint_compare(before, r._fingerprint(URL))
    finally:
        with engine.begin() as c:
            c.execute(text(upd), {"v": orig, "i": rid})
    assert _changed(cmp) == [cat]
    d = cmp[cat]["diff"]
    assert d["counts"] == {"added": 0, "removed": 0, "modified": 1}
    assert d["modified"] == {str(rid): [col]} and d["changed_columns"] == [col]
    summary = r._fp_summary(cmp)
    assert cat in summary and "changed-by-test" not in summary and "@" not in summary   # ids + column names only, no contents/emails


def _flags(monkeypatch):
    for k, v in {"FILE": "/opt/ironvision/IronVision-AI/deploy/digitalocean/.env.production", "DEPLOYMENT_KIND": "demo",
                 "ALLOW_DEMO_LOGIN": "true", "AUTH_PROVIDERS": "local,oidc", "DEMO_LAUNCHER": "yes"}.items():
        monkeypatch.setenv(f"RECOVER_PRODENV_{k}", v)


def test_fingerprint_collection_error_fails_the_step_redacted(monkeypatch):
    _flags(monkeypatch)
    calls = []

    def boom(url):
        calls.append(url)
        raise RuntimeError("connect failed postgresql://aegis:hunter2secret@db:5432/x")
    monkeypatch.setattr(r, "_fingerprint", boom)
    monkeypatch.setattr(r.subprocess, "run", lambda *a, **k: pytest.fail("provisioning must not run without a before-fingerprint"))
    out = r.demo_account_step(URL, "b", False)
    assert out["ok"] is False and "fingerprint collection failed (before)" in out["error"] and "hunter2secret" not in out["error"]

    real, n = r.__dict__["fingerprint_compare"], []   # after-collection failure: provisioning ran, the step still fails
    snap = {c: {"count": 0, "sha256": "0" * 64, "rows": {}} for c in r._FP_SCOPE}

    def second_fails(url):
        n.append(1)
        if len(n) > 1:
            raise RuntimeError("timeout postgresql://aegis:hunter2secret@db/x")
        return snap
    monkeypatch.setattr(r, "_fingerprint", second_fails)
    monkeypatch.setattr(r.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, 'DEMO-STEP-JSON {"org_id": "x"}\n', ""))
    monkeypatch.setattr(r, "demo_account_state", lambda url: None)
    monkeypatch.setattr(r, "_sandbox_orgs", lambda url: 0)
    out = r.demo_account_step(URL, "b", False)
    assert real is r.fingerprint_compare
    assert out["ok"] is False and out["protected_fingerprint"] is None and "fingerprint collection failed (after)" in out["error"]
    assert "hunter2secret" not in out["error"]


def test_droplet_state_old_global_freshness_changes_protected_evidence_new_seed_does_not(monkeypatch):
    """Droplet state: restored evidence whose stored freshness `state` predates today (legacy app stopped) and NO demo account."""
    monkeypatch.setenv("SAMPLES_DIR", str(SAMPLES))
    ev_scope = r._FP_SCOPE["evidence"][1]
    with engine.begin() as c:
        saved = c.execute(text(f"select e.id, e.collected_at, e.state, e.freshness_window_days, e.updated_at from {ev_scope}")).all()
        assert saved, "test DB has no protected evidence"
        c.execute(text(f"update evidence set collected_at = collected_at - interval '60 days' where id in (select e.id from {ev_scope})"))
        rs = "select count(*) from risk_snapshots x join organizations o on o.id = x.org_id where not o.is_sandbox"
        rs_before = c.execute(text(rs)).scalar()
    try:
        before = r._fingerprint(URL)
        with SessionLocal() as db:                       # NEW provisioning path (seed_phase1 as provision() runs it), fresh sandbox
            from app.seed_phase1 import seed_phase1
            org = sbx.create_sandbox(db, None, "FP droplet repro", "fp-repro@example.invalid")
            db.commit()
            seed_phase1(db, org, str(SAMPLES))
            db.commit()
        new = r.fingerprint_compare(before, r._fingerprint(URL))
        assert _changed(new) == [], r._fp_summary(new)     # right reason: protected rows untouched, not a narrowed scope
        with engine.connect() as c:
            assert c.execute(text(rs)).scalar() == rs_before   # no snapshots written into restored orgs either
        with SessionLocal() as db:                       # OLD code path: seed_phase1.py:191 evaluate_freshness(db) over ALL evidence
            from app.services.evaluation import evaluate_freshness
            evaluate_freshness(db)
            db.commit()
        old = r.fingerprint_compare(before, r._fingerprint(URL))
        assert _changed(old) == ["evidence"]
        assert old["evidence"]["diff"]["changed_columns"] == ["state", "updated_at"]
        assert old["evidence"]["diff"]["counts"]["modified"] > 0 and old["evidence"]["diff"]["counts"]["added"] == 0
        old_list_cmp = [[v["count"], v["sha256"]] for v in before.values()] == [[v["count"], v["sha256"]] for v in r._fingerprint(URL).values()]
        assert old_list_cmp is False                     # = the Droplet's opaque "combined fingerprint compare false"
    finally:
        with engine.begin() as c:
            for i, ca, st, w, ua in saved:
                c.execute(text("update evidence set collected_at = :ca, state = :st, freshness_window_days = :w, updated_at = :ua where id = :i"),
                          {"ca": ca, "st": st, "w": w, "ua": ua, "i": i})


def test_tool_version_bumped_so_plan_6294cf78e70166ca_is_refused():
    old = ("2026.10.19-rehearsal-v5-samples-dir", "2026.10.19-rehearsal-v6-protected-fingerprint")
    assert r.TOOL_VERSION not in old
    for v in old:   # 6294cf78e70166ca (v5) and every plan rehearsed by v6 are refused
        with pytest.raises(r.RecoveryError, match="re-run ./recover.sh run"):
            r.rehearsal_gate({"tool_version": v, "plan_hash": "6294cf78e70166ca", "passed": True}, "6294cf78e70166ca")
