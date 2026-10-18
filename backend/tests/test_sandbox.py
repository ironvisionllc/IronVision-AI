"""Wave 8: self sign-up, private sandbox tenants, persona role switcher with separation of duties."""
import os
import uuid

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Organization, Poam, System, User
from tests.conftest import auth

PW = "Sandbox!Pass-2026x"


@pytest.fixture(scope="module")
def signup_on():
    from app.config import get_settings
    os.environ["ALLOW_SIGNUP"], os.environ["SIGNUP_MIN_SECONDS"], os.environ["SIGNUP_RATE_LIMIT"] = "true", "0", "100/3600"
    get_settings.cache_clear()
    yield
    os.environ.pop("ALLOW_SIGNUP", None)
    os.environ.pop("SIGNUP_MIN_SECONDS", None)
    os.environ.pop("SIGNUP_RATE_LIMIT", None)
    get_settings.cache_clear()


def tok(client) -> str:
    return client.get("/api/v1/auth/signup/start").json()["form_token"]


def _signup(client, email, org):
    r = client.post("/api/v1/auth/signup", json={"name": "Jane Tester", "email": email, "password": PW, "organization": org, "form_token": tok(client)})
    assert r.status_code == 201, r.text
    from app.services.sandbox import provision
    with SessionLocal() as db:
        provision(db, uuid.UUID(r.json()["org_id"]))
    t = client.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()
    return t


@pytest.fixture(scope="module")
def two_sandboxes(client, signup_on):
    a = _signup(client, f"a-{uuid.uuid4().hex[:6]}@example.com", "Org A")
    b = _signup(client, f"b-{uuid.uuid4().hex[:6]}@example.com", "Org B")
    return a, b


def test_signup_disabled_by_default_and_validation(client):
    from app.config import get_settings
    os.environ["ALLOW_SIGNUP"] = "false"
    get_settings.cache_clear()
    assert client.post("/api/v1/auth/signup", json={"name": "X Y", "email": "x@example.com", "password": PW}).status_code == 404


def test_signup_rules(client, signup_on):
    r = client.post("/api/v1/auth/signup", json={"name": "X Y", "email": "weak@example.com", "password": "short", "form_token": tok(client)})
    assert r.status_code == 422 and "12 characters" in r.json()["detail"], r.text
    bot = client.post("/api/v1/auth/signup", json={"name": "X Y", "email": "bot@example.com", "password": PW, "iv_hp_fax_only": "x", "form_token": tok(client)})
    assert bot.status_code == 400 and "rejected" not in bot.json()["detail"].lower()
    assert client.post("/api/v1/auth/signup", json={"name": "X Y", "email": "bot2@example.com", "password": PW}).status_code == 400  # no form token
    # legacy autofill target "website" is ignored (not a trap any more)
    ok = client.post("/api/v1/auth/signup", json={"name": "X Y", "email": f"auto-{uuid.uuid4().hex[:6]}@example.com", "password": PW,
                                                  "website": "https://autofilled.example", "form_token": tok(client)})
    assert ok.status_code == 201, ok.text
    from app.models import AuditEvent
    with SessionLocal() as db:
        reasons = {(e.details or {}).get("reason") for e in db.scalars(select(AuditEvent).where(AuditEvent.action == "auth.signup", AuditEvent.outcome == "denied"))}
    assert {"password_policy", "bot_trap_field_filled", "missing_or_invalid_form_token"} <= reasons


def test_signup_too_fast_and_duplicate_message(client, signup_on, monkeypatch):
    email = f"dup-{uuid.uuid4().hex[:6]}@example.com"
    assert client.post("/api/v1/auth/signup", json={"name": "X Y", "email": email, "password": PW, "form_token": tok(client)}).status_code == 201
    d = client.post("/api/v1/auth/signup", json={"name": "X Y", "email": email, "password": PW, "form_token": tok(client)})
    assert d.status_code == 409 and "sign in instead" in d.json()["detail"]
    monkeypatch.setenv("SIGNUP_MIN_SECONDS", "30")
    assert client.post("/api/v1/auth/signup", json={"name": "X Y", "email": "fast@example.com", "password": PW, "form_token": tok(client)}).status_code == 400


def test_login_lands_on_isso_persona_with_operator(client, two_sandboxes):
    a, _ = two_sandboxes
    assert a["user"]["persona_role"] == "isso" and a["user"]["is_sandbox"] is True
    st = client.get("/api/v1/sandbox/status", headers=auth(a["access_token"])).json()
    assert st["status"] == "ready" and st["acting_role"] == "isso" and st["operator"]["email"].startswith("a-")


def _register(client, h, name="Clean Test System"):
    r = client.post("/api/v1/systems", json={"name": name, "acronym": "CTS", "baseline_key": "low"}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_signup_is_clean_and_isolated(client, token, two_sandboxes):
    a, b = two_sandboxes
    ha, hb = auth(a["access_token"]), auth(b["access_token"])
    assert client.get("/api/v1/systems", headers=ha).json() == [] and client.get("/api/v1/systems", headers=hb).json() == []
    with SessionLocal() as db:
        from app.models import CommonControlProvider, DecisionRule, Policy, RiskSnapshot
        org = db.get(Organization, db.scalar(select(User.org_id).where(User.email == a["user"]["email"])))
        for m in (Poam, Policy, RiskSnapshot, CommonControlProvider):
            assert not db.scalar(select(m.id).where(m.org_id == org.id).limit(1)), m.__name__
        assert db.scalar(select(DecisionRule.id).where(DecisionRule.org_id == org.id).limit(1))  # tenant config is still seeded
    st = client.get("/api/v1/sandbox/status", headers=ha).json()
    assert st["workspace"] == "clean" and st["reset_label"] == "Clear my workspace"
    assert [s["key"] for s in st["onboarding"]][:2] == ["register_system", "add_source"] and not any(s["done"] for s in st["onboarding"])
    sid = _register(client, ha)
    assert next(s for s in client.get("/api/v1/sandbox/status", headers=ha).json()["onboarding"] if s["key"] == "register_system")["done"]
    assert client.get(f"/api/v1/systems/{sid}", headers=hb).status_code in (403, 404)
    demo = {s["id"] for s in client.get("/api/v1/systems", headers=auth(token("isso@aegisrmf.demo"))).json()}
    assert sid not in demo


def test_empty_workspace_endpoints_are_200_and_zeroed(client, signup_on):
    t = _signup(client, f"e-{uuid.uuid4().hex[:6]}@example.com", "Empty Org")
    h = auth(t["access_token"])
    for path in ("/systems", "/poams", "/reviews", "/notifications", "/sandbox/status", "/content/stats", "/policies",
                 "/emass/status", "/search?q=ac", "/content-updates", "/decision-rules", "/freshness-policies"):
        r = client.get(f"/api/v1{path}", headers=h)
        assert r.status_code == 200, (path, r.status_code, r.text[:200])
    lead = client.post("/api/v1/sandbox/act-as", json={"role": "leadership_viewer"}, headers=h).json()
    r = client.get("/api/v1/dashboard/leadership", headers=auth(lead["access_token"]))
    assert r.status_code == 200, r.text[:300]
    assert "NaN" not in r.text
    z = client.get("/api/v1/sandbox/samples.zip", headers=h)
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip"
    import io
    import zipfile
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert any(n.endswith(".ckl") for n in names) and any(n.endswith(".nessus") for n in names) and not any("e2e" in n for n in names)
    assert client.get("/api/v1/sandbox/samples.zip").status_code == 401
    assert client.get("/api/v1/systems", headers=h).json() == []  # downloading samples loads nothing


def test_persona_sod_and_operated_by(client, two_sandboxes):
    a, _ = two_sandboxes
    isso = auth(a["access_token"])
    sid = _register(client, isso, "SoD Test System")
    p = client.post("/api/v1/poams", json={"system_id": sid, "weakness": "Manual weakness for SoD test", "control_ids": ["ac-2"],
                                           "due_date": "2027-01-31"}, headers=isso)
    assert p.status_code == 201, p.text
    r = client.post(f"/api/v1/poams/{p.json()['id']}/request-extension", json={"justification": "Vendor patch delayed by a quarter",
                                                                              "kind": "deadline_extension", "new_due_date": "2027-04-30"}, headers=isso)
    assert r.status_code == 201, r.text
    rid = next(x["id"] for x in client.get("/api/v1/reviews", headers=isso).json()["items"] if x.get("poam_id") == p.json()["id"])
    assert client.post(f"/api/v1/reviews/{rid}/decisions", json={"action": "approve", "rationale": "self approval attempt"}, headers=isso).status_code == 403
    issm = client.post("/api/v1/sandbox/act-as", json={"role": "issm"}, headers=isso).json()
    assert issm["user"]["persona_role"] == "issm"
    ok = client.post(f"/api/v1/reviews/{rid}/decisions", json={"action": "approve", "rationale": "Approved by ISSM persona"}, headers=auth(issm["access_token"]))
    assert ok.status_code == 200, ok.text
    from app.models import AuditEvent
    with SessionLocal() as db:
        ev = db.scalar(select(AuditEvent).where(AuditEvent.entity_id == rid).order_by(AuditEvent.seq.desc()))
        assert ev.details and ev.details.get("operated_by", "").startswith("a-")


def test_clear_workspace_keeps_account(client, signup_on):
    em = f"c-{uuid.uuid4().hex[:6]}@example.com"
    t = _signup(client, em, "Clear Org")
    h = auth(t["access_token"])
    _register(client, h, "To Be Cleared")
    r = client.post("/api/v1/sandbox/reset", headers=h)
    assert r.status_code == 200 and r.json()["mode"] == "workspace_cleared"
    assert client.get("/api/v1/systems", headers=h).json() == []
    assert client.post("/api/v1/auth/login", json={"email": em, "password": PW}).status_code == 200
    from app.models import AuditEvent
    with SessionLocal() as db:
        assert db.scalar(select(AuditEvent.id).where(AuditEvent.action == "sandbox.workspace_cleared", AuditEvent.actor_email == em))


def test_demo_account_has_four_systems_and_conversion(client, signup_on):
    from app.services import sandbox as sbx
    with SessionLocal() as db:
        org = sbx.seed_demo_account(db, PW)
        db.commit()
        sbx.provision(db, org.id)
        assert len(db.scalars(select(System.id).where(System.org_id == org.id)).all()) == 4
        # a legacy seeded sign-up tenant is converted to clean; demo is untouched
        legacy = sbx.create_sandbox(db, None, "Legacy", "legacy@example.com")
        u = User(org_id=legacy.id, email=f"legacy-{uuid.uuid4().hex[:6]}@example.com", display_name="Legacy", source="sandbox")
        db.add(u)
        db.flush()
        legacy.owner_user_id = u.id
        from app.seed_phase1 import seed_phase1
        seed_phase1(db, legacy, sbx.samples_dir())
        legacy.sandbox_status = "ready"
        db.commit()
        assert db.scalar(select(System.id).where(System.org_id == legacy.id).limit(1))
        out = sbx.convert_signups_to_clean(db)
        assert any(o["org"] == legacy.name and o["systems"] == 4 for o in out)
        assert not db.scalar(select(System.id).where(System.org_id == legacy.id).limit(1))
        assert len(db.scalars(select(System.id).where(System.org_id == org.id)).all()) == 4
        assert db.get(User, u.id).is_active
        with pytest.raises(PermissionError):
            sbx.clear_workspace(db, org, None)


def test_act_as_refused_outside_sandbox(client, token):
    assert client.post("/api/v1/sandbox/act-as", json={"role": "ao"}, headers=auth(token("isso@aegisrmf.demo"))).status_code == 403


def test_expiry_purges_only_sandboxes(client, two_sandboxes):
    from datetime import datetime, timedelta, timezone

    from app.services import sandbox as sbx
    _, b = two_sandboxes
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.email.like("b-%@example.com")))
        org = db.get(Organization, u.org_id)
        org.last_activity_at = datetime.now(timezone.utc) - timedelta(days=sbx.inactivity_days() + 1)
        demo = db.scalar(select(Organization).where(Organization.is_sandbox.is_(False)))
        demo.last_activity_at = datetime.now(timezone.utc) - timedelta(days=400)
        db.commit()
        assert sbx.run_expiry(db)["purged"] >= 1
        db.refresh(org)
        assert org.sandbox_status == "purged" and not db.get(User, u.id).is_active
        with pytest.raises(PermissionError):
            sbx.purge(db, demo, "test")
    assert client.post("/api/v1/auth/login", json={"email": u.email, "password": PW}).status_code == 401


def test_audit_log_and_workflow_are_tenant_scoped_and_honest(client, signup_on):
    a = _signup(client, f"al-{uuid.uuid4().hex[:6]}@example.com", "Audit A")
    b = _signup(client, f"bl-{uuid.uuid4().hex[:6]}@example.com", "Audit B")
    ha, hb = auth(a["access_token"]), auth(b["access_token"])
    _register(client, hb, "Tenant B Secret System")
    sid = _register(client, ha, "Tenant A System")
    issm = auth(client.post("/api/v1/sandbox/act-as", json={"role": "issm"}, headers=ha).json()["access_token"])
    log = client.get("/api/v1/audit-log?page_size=200&include_system=true", headers=issm).json()
    emails = {i["actor_email"] for i in log["items"]}
    assert emails and all(e.startswith("al-") or "sbx-audit-a" in e for e in emails), emails
    assert "Tenant B Secret System" not in str(log["items"])
    stages = {s["stage"]: s["state"] for s in client.get(f"/api/v1/systems/{sid}/rmf-workflow", headers=ha).json()}
    assert all(stages[k] == "not_configured" for k in ("Ongoing: POA&M", "Ongoing: Attestations", "Ongoing: Reviews", "Ongoing: Policy audit"))
    assert stages["7. Monitor"] == "not_configured"


def test_demo_login_gated_audited_and_passwordless(client, monkeypatch):
    from app.config import get_settings
    from app.services import sandbox as sbx
    with SessionLocal() as db:
        sbx.seed_demo_account(db, PW)
        db.commit()
        org = db.get(Organization, db.scalar(select(User.org_id).where(User.email == sbx.DEMO_EMAIL)))
        if org.sandbox_status != "ready":
            sbx.provision(db, org.id)
    monkeypatch.delenv("ALLOW_DEMO_LOGIN", raising=False)
    get_settings.cache_clear()
    assert client.post("/api/v1/auth/demo-login").status_code == 404
    assert client.get("/api/v1/auth/provider").json()["demo_login_enabled"] is False
    monkeypatch.setenv("ALLOW_DEMO_LOGIN", "true")
    get_settings.cache_clear()
    try:
        assert client.get("/api/v1/auth/provider").json()["demo_login_enabled"] is True
        r = client.post("/api/v1/auth/demo-login")
        assert r.status_code == 200, r.text
        assert r.json()["user"]["persona_role"] == "isso"
        st = client.get("/api/v1/sandbox/status", headers=auth(r.json()["access_token"])).json()
        assert st["operator"]["email"] == sbx.DEMO_EMAIL and st["is_demo"] is True
        admin = client.post("/api/v1/sandbox/act-as", json={"role": "platform_admin"}, headers=auth(r.json()["access_token"])).json()
        inv = client.post("/api/v1/admin/users", json={"email": "x@y.demo", "display_name": "X Y", "role": "isso"}, headers=auth(admin["access_token"]))
        assert inv.status_code == 403
        from app.models import AuditEvent
        with SessionLocal() as db:
            ev = db.scalar(select(AuditEvent).where(AuditEvent.action == "auth.demo_login", AuditEvent.outcome == "success").order_by(AuditEvent.seq.desc()))
            assert ev and ev.ip and (ev.details or {}).get("client_ip")
        monkeypatch.setenv("DEMO_LOGIN_RATE_LIMIT", "1/3600")
        assert client.post("/api/v1/auth/demo-login").status_code == 429
    finally:
        monkeypatch.delenv("ALLOW_DEMO_LOGIN", raising=False)
        get_settings.cache_clear()


def test_check_env_refuses_demo_login_in_production():
    from app.check_env import validate
    errs, _ = validate({"APP_ENV": "production", "ALLOW_DEMO_LOGIN": "true"})
    assert any("ALLOW_DEMO_LOGIN" in e for e in errs)
    errs, _ = validate({"APP_ENV": "production", "ALLOW_DEMO_LOGIN": "true", "ALLOW_DEMO_LOGIN_IN_PRODUCTION": "true"})
    assert any("DEPLOYMENT_KIND=demo" in e for e in errs)  # the old override no longer works
    errs, _ = validate({"APP_ENV": "production", "ALLOW_DEMO_LOGIN": "true", "DEPLOYMENT_KIND": "customer"})
    assert any("never on a customer deployment" in e for e in errs)
    errs, warns = validate({"APP_ENV": "production", "ALLOW_DEMO_LOGIN": "true", "DEPLOYMENT_KIND": "demo"})
    assert not any("ALLOW_DEMO_LOGIN" in e for e in errs) and any("ALLOW_DEMO_LOGIN" in w for w in warns)
    errs, _ = validate({"APP_ENV": "production", "ALLOW_DEMO_LOGIN": "true", "DEPLOYMENT_KIND": "demo", "AUTH_PROVIDERS": "oidc"})
    assert any("KEYCLOAK_DEMO_LAUNCHER_CLIENT_SECRET is required" in e for e in errs)


def test_demo_login_keycloak_mode_needs_the_exact_issuer_mapping(client, monkeypatch):
    """Explore Demo (Option B launcher): 403 without a mapping, 403 when only another issuer's mapping exists, 200 + session +
    role switch with the exact <OIDC_ISSUER>|<sub> mapping. The endpoint is not relaxed for any case."""
    from sqlalchemy import delete

    from app.config import get_settings
    from app.models import AuthIdentity
    from app.security import demo_launcher
    from app.services import identity_map
    from app.services import sandbox as sbx
    iss, other, sub = "http://scratch-kc.test/realms/ironvision-demo", "https://auth.other.test/realms/ironvision-demo", str(uuid.uuid4())
    for k, v in {"ALLOW_DEMO_LOGIN": "true", "AUTH_PROVIDERS": "oidc", "OIDC_ISSUER": iss, "KEYCLOAK_DEMO_LAUNCHER_CLIENT_SECRET": "x",
                 "KEYCLOAK_DEMO_PASSWORD": "x", "KEYCLOAK_DEMO_USERNAME": "launcher", "DEMO_LOGIN_RATE_LIMIT": "1000/60"}.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    monkeypatch.setattr(demo_launcher, "login", lambda: {"subject": f"{iss}|{sub}", "email": sbx.DEMO_EMAIL})

    def oidc_identities(db, demo):
        db.execute(delete(AuthIdentity).where(AuthIdentity.user_id == demo.id, AuthIdentity.provider == "oidc"))
        db.commit()
    try:
        with SessionLocal() as db:
            org = sbx.seed_demo_account(db, None)
            db.commit()
            if org.sandbox_status != "ready":
                sbx.provision(db, org.id)
            demo = db.scalar(select(User).where(User.email == sbx.DEMO_EMAIL))
            oidc_identities(db, demo)
        r = client.post("/api/v1/auth/demo-login")
        assert r.status_code == 403 and "not mapped" in r.text                       # mapping absent
        with SessionLocal() as db:
            demo = db.scalar(select(User).where(User.email == sbx.DEMO_EMAIL))
            identity_map.map_identity(db, user=demo, issuer=other, sub=sub, reason="test: other issuer", actor="pytest", username="launcher")
            db.commit()
        r = client.post("/api/v1/auth/demo-login")
        assert r.status_code == 403 and "not mapped" in r.text                       # another issuer's mapping grants nothing
        with SessionLocal() as db:
            demo = db.scalar(select(User).where(User.email == sbx.DEMO_EMAIL))
            oidc_identities(db, demo)
            identity_map.map_identity(db, user=demo, issuer=iss, sub=sub, reason="test: exact issuer", actor="pytest", username="launcher")
            db.commit()
        r = client.post("/api/v1/auth/demo-login")
        assert r.status_code == 200, r.text                                           # exact mapping → session
        tok = r.json()["access_token"]
        assert client.get("/api/v1/sandbox/status", headers=auth(tok)).json()["operator"]["email"] == sbx.DEMO_EMAIL
        sw = client.post("/api/v1/sandbox/act-as", json={"role": "issm"}, headers=auth(tok))
        assert sw.status_code == 200 and sw.json()["access_token"]                    # role switch
    finally:
        with SessionLocal() as db:
            demo = db.scalar(select(User).where(User.email == sbx.DEMO_EMAIL))
            if demo:
                oidc_identities(db, demo)
        for k in ("ALLOW_DEMO_LOGIN", "KEYCLOAK_DEMO_LAUNCHER_CLIENT_SECRET"):
            monkeypatch.delenv(k, raising=False)
        get_settings.cache_clear()
