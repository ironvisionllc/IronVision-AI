"""Route-level authorization guard: every mutating route declares a permission (or self-scope) dependency."""
from fastapi.routing import APIRoute
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import Finding, Poam, System
from tests.conftest import auth

PUBLIC = {("POST", "/api/v1/auth/login"), ("POST", "/api/v1/auth/refresh"), ("POST", "/api/v1/auth/mtls/login"),
          ("POST", "/api/v1/auth/logout"), ("POST", "/api/v1/auth/signup")}
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def _walk(routes, prefix=""):
    for r in routes:
        if isinstance(r, APIRoute):
            yield prefix + r.path, r
        elif hasattr(r, "original_router"):
            ctx = getattr(r, "include_context", None)
            yield from _walk(r.original_router.routes, prefix + (getattr(ctx, "prefix", "") or ""))
        elif hasattr(r, "routes") and not hasattr(r, "app"):
            yield from _walk(r.routes, prefix)


def _calls(dep):
    for s in dep.dependencies:
        yield s.call
        yield from _calls(s)


def test_every_mutating_route_has_permission_dependency():
    seen, missing = 0, []
    for path, r in _walk(app.routes):
        for m in r.methods & MUTATING:
            seen += 1
            if (m, path) in PUBLIC:
                continue
            if not any(getattr(c, "permission", None) or getattr(c, "self_scoped", False) for c in _calls(r.dependant)):
                missing.append(f"{m} {path}")
    assert seen > 50, f"route enumeration broken ({seen} mutating routes found)"
    assert not missing, "mutating routes without a permission dependency: " + ", ".join(sorted(missing))


def _finding(acr="LTP") -> Finding:
    with SessionLocal() as db:
        sid = db.scalar(select(System.id).where(System.acronym == acr))
        return db.scalar(select(Finding).where(Finding.system_id == sid, Finding.mapping_status == "unmapped", Finding.current_state == "open",
                                               Finding.disposition.is_(None)).limit(1))


def test_direct_disposition_goes_through_decision_rule(client, token):
    isso, issm = auth(token("isso@aegisrmf.demo")), auth(token("issm@aegisrmf.demo"))
    f = _finding()
    r = client.post(f"/api/v1/findings/{f.id}/disposition", json={"disposition": "not_applicable", "justification": "Not in this boundary"}, headers=isso)
    assert r.status_code == 200 and r.json()["applied"] is False and r.json()["pending_request"], r.text
    with SessionLocal() as db:
        assert db.get(Finding, f.id).disposition is None and db.get(Finding, f.id).mapping_status == "unmapped"
    assert client.post(f"/api/v1/reviews/{r.json()['request_id']}/decisions", json={"action": "approve", "rationale": "Requester cannot self approve"},
                       headers=isso).status_code == 403
    assert client.post(f"/api/v1/reviews/{r.json()['request_id']}/decisions", json={"action": "approve", "rationale": "Confirmed outside boundary"},
                       headers=issm).status_code == 200
    with SessionLocal() as db:
        assert db.get(Finding, f.id).disposition == "not_applicable"


def test_disposition_requires_permission_and_tenant(client, token):
    viewer = auth(token("leadership.viewer@aegisrmf.demo"))
    f = _finding()
    assert client.post(f"/api/v1/findings/{f.id}/disposition", json={"disposition": "informational", "justification": "Viewer should not do this"},
                       headers=viewer).status_code == 403
    assert client.post("/api/v1/findings/00000000-0000-0000-0000-000000000000/disposition",
                       json={"disposition": "informational", "justification": "Unknown finding id"}, headers=viewer).status_code == 404


def test_informational_rule_action_is_pending_until_approved(client, token):
    isso = auth(token("isso@aegisrmf.demo"))
    f = _finding()
    r = client.post("/api/v1/mapping-review/rule-action", json={"system_id": str(f.system_id), "finding_ids": [str(f.id)], "action": "informational",
                                                                "justification": "Informational banner check"}, headers=isso).json()
    assert r["updated"] == 0 and r["pending_request"]
    with SessionLocal() as db:
        assert db.get(Finding, f.id).disposition is None


def test_poam_status_cannot_bypass_pending_review(client, token):
    isso = auth(token("isso@aegisrmf.demo"))
    with SessionLocal() as db:
        p = db.scalar(select(Poam).where(Poam.status.in_(("new", "in_progress")), Poam.due_date.is_not(None)).limit(1))
        p.status = "closure_review"
        db.commit()
        pid, due = str(p.id), p.due_date
    try:
        assert client.patch(f"/api/v1/poams/{pid}", json={"status": "in_progress"}, headers=isso).status_code == 409
    finally:
        with SessionLocal() as db:
            db.get(Poam, p.id).status = "in_progress"
            db.commit()
    later = due.replace(year=due.year + 1).isoformat()
    assert client.patch(f"/api/v1/poams/{pid}", json={"due_date": later}, headers=isso).status_code == 409


def test_signup_exempt_cidrs(monkeypatch):
    from app.api.v1.sandbox import signup_exempt
    from app.check_env import validate

    monkeypatch.setenv("SIGNUP_RATE_LIMIT_EXEMPT_CIDRS", "127.0.0.0/8,203.0.113.7/32")
    assert signup_exempt("127.0.0.1") and signup_exempt("203.0.113.7")
    assert not signup_exempt("203.0.113.8") and not signup_exempt("8.8.8.8") and not signup_exempt(None)
    monkeypatch.setenv("SIGNUP_RATE_LIMIT_EXEMPT_CIDRS", "")
    assert not signup_exempt("127.0.0.1")
    _, warns = validate({"APP_ENV": "production", "SIGNUP_RATE_LIMIT_EXEMPT_CIDRS": "203.0.113.7/32"})
    assert any("SIGNUP_RATE_LIMIT_EXEMPT_CIDRS" in w for w in warns)


def test_missing_permission_detail_is_structured(client, token):
    r = client.get("/api/v1/dashboard/leadership", headers=auth(token("isso@aegisrmf.demo")))
    assert r.status_code == 403
    d = r.json()["detail"]
    assert d["code"] == "missing_permission" and d["permission"] == "portfolio.read"
    assert {"issm", "ao", "leadership_viewer"} <= set(d["roles"]) and "isso" not in d["roles"]
    assert d["message"] == "Missing permission: portfolio.read"
