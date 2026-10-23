"""Self sign-up + private sandbox tenants + persona role switcher (sandbox tenants only)."""
import os
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.auth import _issue, build_user_out
from app.config import get_settings
from app.db import get_db
from app.models import AuthIdentity, Organization, RoleAssignment, User
from app.security import sessions
from app.security.deps import CurrentUser, get_current_user, self_scoped
from app.security.passwords import hash_password
from app.services import audit, jobs
from app.services import sandbox as sbx

router = APIRouter(tags=["sandbox"])
ONBOARDING = [("upload_scan", "Upload a scan", "/evidence-sources"), ("create_poam", "Create a POA&M", "/poams"),
              ("switch_issm", "Switch to the ISSM persona", None), ("approve_closure", "Approve a closure", "/reviews"),
              ("view_leadership", "View Leadership (switch to ISSM, AO or Leadership first)", "/portfolio")]
ONBOARDING_CLEAN = [("register_system", "Register a system", "/systems/new"),
                    ("add_source", "Add an evidence source or upload a scan", "/evidence-sources"),
                    ("create_poam", "Create a POA&M", "/poams"), ("approve_closure", "Switch to ISSM and approve a closure", "/reviews"),
                    ("view_leadership", "View Leadership (switch to ISSM, AO or Leadership first)", "/portfolio")]
EVENTS = {"register_system": ("system.registered",), "add_source": ("source.created", "ingest.received"), "upload_scan": ("ingest.received",),
          "create_poam": ("poam.created",), "approve_closure": ("review.effect.poam_closure",), "view_leadership": ("leadership.viewed",)}
SAMPLE_DIRS = ("stig", "acas", "scap", "sarif", "policies")


class SignupIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=1, max_length=200)
    organization: str | None = Field(None, max_length=120)
    iv_hp_fax_only: str | None = None  # bot trap: hidden, unusual name so browser/password-manager autofill ignores it
    form_token: str | None = None  # from GET /auth/signup/start (minimum time-to-submit)


BOT_MSG = "Sign-up could not be completed. Please reload the page and try again."


def _min_seconds() -> float:
    return float(os.environ.get("SIGNUP_MIN_SECONDS", "2"))


def _sign(ts: str) -> str:
    import hashlib
    import hmac

    return hmac.new(get_settings().jwt_secret.encode(), f"signup:{ts}".encode(), hashlib.sha256).hexdigest()[:32]


def form_token_problem(token: str | None) -> str | None:
    import hmac
    import time

    ts, _, sig = (token or "").rpartition(".")
    if not ts or not hmac.compare_digest(sig, _sign(ts)):
        return "missing_or_invalid_form_token"
    try:
        age = time.time() - float(ts)
    except ValueError:
        return "missing_or_invalid_form_token"
    if age < _min_seconds():
        return f"submitted_too_fast ({age:.1f}s)"
    if age > 6 * 3600:
        return "form_token_expired"
    return None


@router.get("/auth/signup/start")
def signup_start() -> dict:
    import time

    ts = f"{time.time():.3f}"
    return {"form_token": f"{ts}.{_sign(ts)}", "min_seconds": _min_seconds()}


def signup_limit() -> tuple[int, int]:
    n, _, w = os.environ.get("SIGNUP_RATE_LIMIT", "5/3600").partition("/")
    return int(n), int(w or 3600)


def signup_exempt(ip: str | None) -> bool:
    """SIGNUP_RATE_LIMIT_EXEMPT_CIDRS: exact test/egress addresses only (empty by default; check_env warns in production)."""
    import ipaddress

    try:
        addr = ipaddress.ip_address(ip or "")
    except ValueError:
        return False
    nets = [x.strip() for x in os.environ.get("SIGNUP_RATE_LIMIT_EXEMPT_CIDRS", "").split(",") if x.strip()]
    return any(addr in ipaddress.ip_network(n, strict=False) for n in nets)


def signups_from(db: Session, ip: str | None, window: int) -> tuple[int, int]:
    """(successful sign-ups from this IP in the window, seconds until the oldest one ages out). Rejected attempts don't count."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func

    from app.models import AuditEvent
    since = datetime.now(timezone.utc) - timedelta(seconds=window)
    n, oldest = db.execute(select(func.count(), func.min(AuditEvent.occurred_at)).where(
        AuditEvent.action == "auth.signup", AuditEvent.outcome == "success", AuditEvent.ip == ip, AuditEvent.occurred_at > since)).one()
    return n, int((oldest - since).total_seconds()) + 1 if oldest else 0


def password_problems(pw: str, email: str) -> list[str]:
    p = []
    if len(pw) < 12:
        p.append("at least 12 characters")
    for rx, label in ((r"[a-z]", "a lowercase letter"), (r"[A-Z]", "an uppercase letter"), (r"\d", "a digit"), (r"[^A-Za-z0-9]", "a symbol")):
        if not re.search(rx, pw):
            p.append(label)
    if email.split("@")[0].lower() in pw.lower() and len(email.split("@")[0]) >= 3:
        p.append("must not contain your email name")
    return p


@router.post("/auth/signup", status_code=201)
def signup(body: SignupIn, request: Request, db: Session = Depends(get_db)) -> dict:
    s = get_settings()
    if not s.allow_signup:
        raise HTTPException(404, "Self sign-up is disabled")
    if "dev_password" not in sessions.enabled_providers():
        raise HTTPException(404, "Self sign-up requires local password accounts (AUTH_PROVIDERS)")
    meta = audit.request_meta(request)
    chain = {"peer": request.client.host if request.client else None, "x_forwarded_for": (request.headers.get("x-forwarded-for") or "")[:300]}

    def deny(reason: str, status: int, msg: str):
        audit.record_now(action="auth.signup", outcome="denied", actor_email=body.email[:320], details={"reason": reason, **chain}, **meta)
        raise HTTPException(status, msg)

    limit, window = signup_limit()
    n, wait = signups_from(db, meta.get("ip"), window)
    if not signup_exempt(meta.get("ip")) and n >= limit:
        mins = max(1, -(-wait // 60))
        audit.record_now(action="auth.signup", outcome="denied", actor_email=body.email[:320], details={"reason": "rate_limited", **chain}, **meta)
        raise HTTPException(429, f"Too many sign-ups from this network ({limit} per {window // 60} min). Try again in {mins} minute{'s' if mins != 1 else ''}.",
                            headers={"Retry-After": str(wait)})
    if body.iv_hp_fax_only:
        deny("bot_trap_field_filled", 400, BOT_MSG)
    if problem := form_token_problem(body.form_token):
        deny(problem, 400, BOT_MSG)
    email = body.email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or email.endswith(".invalid"):
        deny("invalid_email", 422, "Enter a valid email address (name@example.com).")
    if probs := password_problems(body.password, email):
        deny("password_policy", 422, "Password needs " + ", ".join(probs) + ".")
    if db.scalar(select(User.id).where(User.email == email)):
        deny("email_exists", 409, "This email is already registered – sign in instead.")
    u, org = sbx.create_owner(db, email, body.name, body.organization)
    db.add(AuthIdentity(user_id=u.id, provider="dev_password", subject=email, secret_hash=hash_password(body.password)))
    job = jobs.enqueue(db, "sandbox.provision", {"org_id": str(org.id)}, requested_by=u.id)
    audit.record(db, action="auth.signup", actor_user_id=u.id, actor_email=email, entity_type="organization", entity_id=str(org.id),
                 details={"sandbox": True, "job_id": str(job.id), **chain}, **meta)
    db.commit()
    return {"ok": True, "org_id": str(org.id), "job_id": str(job.id), "message": "Account created. Sign in to open your sandbox."}


def _real(current: CurrentUser) -> User:
    return current.operator or current.user


def _sandbox_org(db: Session, current: CurrentUser) -> Organization:
    org = db.get(Organization, _real(current).org_id)
    if org is None or not org.is_sandbox or not org.sandbox_personas:
        raise HTTPException(403, "Persona switching is only available in sandbox tenants (strict real-identity SoD applies here)")
    return org


@router.get("/sandbox/status")
def sandbox_status(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    real = _real(current)
    org = db.get(Organization, real.org_id)
    if not org.is_sandbox:
        return {"sandbox": False}
    steps = {**(real.onboarding or {}), **onboarding_events(db, org)}
    demo = sbx.is_demo(db, org)
    return {"sandbox": True, "is_demo": demo, "workspace": "demo" if demo else "clean",
            "demo_data_loaded": sbx.has_demo_data(db, org.id),
            "reset_label": "Reset demo data" if demo else "Clear my workspace",
            "reset_confirm": ("Re-seed the 4 synthetic demo systems? Your changes in the demo are discarded." if demo else
                              "Delete ALL your systems, evidence, findings, POA&Ms, policies and reviews? Your account and reference content are kept."), "status": org.sandbox_status, "progress": org.sandbox_progress, "org_name": org.name,
            "operator": {"email": real.email, "name": real.display_name}, "acting_role": current.user.persona_role,
            "acting_as": current.user.display_name if current.user.persona_role else None,
            "personas": [{"role": r, "name": f"{n} ({l})"} for r, n, l in sbx.PERSONAS],
            "expiry": None if demo else sbx.expiry_info(org),
            "onboarding": [{"key": k, "label": label, "link": link, "done": bool(steps.get(k))} for k, label, link in (ONBOARDING if demo else ONBOARDING_CLEAN)],
            "onboarding_dismissed": bool(steps.get("dismissed")),
            "label": "Sandbox persona mode – simulated identities for demo separation of duties; not acceptable for production SoD"}


def onboarding_events(db: Session, org: Organization) -> dict:
    """Checklist ticks derived from real audit events in this sandbox after it became ready (seed activity excluded)."""
    from datetime import datetime

    from app.models import AuditEvent
    ready = (org.sandbox_progress or {}).get("ready_at")
    if not ready:
        return {}
    uids = list(db.scalars(select(User.id).where(User.org_id == org.id)))
    wanted = sorted({a for v in EVENTS.values() for a in v})
    q = select(AuditEvent.action).where(AuditEvent.actor_user_id.in_(uids), AuditEvent.occurred_at > datetime.fromisoformat(ready),
                                        AuditEvent.action.in_(wanted)).distinct()
    acts = set(db.scalars(q))
    return {k: True for k, v in EVENTS.items() if acts & set(v)}


class ActAs(BaseModel):
    role: str


@router.post("/sandbox/act-as")
def act_as(body: ActAs, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(self_scoped)):
    org = _sandbox_org(db, current)
    if org.sandbox_status != "ready":
        raise HTTPException(409, "Sandbox is still being prepared")
    real = _real(current)
    p = sbx.persona(db, org.id, body.role)
    if p is None or p.operator_id != real.id:
        raise HTTPException(422, f"Unknown persona role {body.role}")
    real.acting_role = body.role
    steps = dict(real.onboarding or {})
    if body.role == "issm":
        steps["switch_issm"] = True
    real.onboarding = steps
    audit.record(db, action="sandbox.act_as", actor_user_id=real.id, actor_email=real.email, entity_type="user", entity_id=str(p.id),
                 details={"role": body.role, "persona": p.display_name})
    db.commit()
    from app.models import AuthSession
    cur = db.get(AuthSession, uuid.UUID(request.state.sid))  # keep the IdP id_token_hint so persona sessions still end the SSO session
    return _issue(db, p, current.auth_provider, request, operator=real, id_token_hint=cur.id_token_hint if cur else None)


@router.post("/sandbox/demo-data")
def load_demo_data(db: Session = Depends(get_db), current: CurrentUser = Depends(self_scoped)) -> dict:
    org = _sandbox_org(db, current)
    try:
        r = sbx.load_demo_data(db, org, _real(current))
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    db.commit()
    return r


@router.post("/sandbox/reset")
def reset_sandbox(db: Session = Depends(get_db), current: CurrentUser = Depends(self_scoped)) -> dict:
    org = _sandbox_org(db, current)
    if sbx.is_demo(db, org):
        sbx.reset(db, org, _real(current))
        mode = "demo_reseeded"
    else:
        sbx.clear_workspace(db, org, _real(current))
        mode = "workspace_cleared"
    db.commit()
    return {"ok": True, "status": org.sandbox_status, "mode": mode}


@router.get("/sandbox/samples.zip")
def sample_files(current: CurrentUser = Depends(get_current_user)):
    """Download the synthetic sample STIG/ACAS/SCAP/SARIF/policy files (files only – nothing is loaded into the workspace)."""
    import io
    import zipfile
    from pathlib import Path

    from fastapi.responses import Response

    try:
        root = Path(sbx.samples_dir()).resolve()
    except sbx.SamplesMissing as exc:
        raise HTTPException(503, str(exc)) from exc
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for d in SAMPLE_DIRS:
            base = (root / d).resolve()
            if base.parent != root or not base.is_dir():
                continue
            for f in sorted(base.iterdir()):
                if f.is_file() and not f.is_symlink() and f.resolve().parent == base and f.stat().st_size <= 10 * 1024 * 1024:
                    z.write(f, f"ironvision-samples-SYNTHETIC/{d}/{f.name}")
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="ironvision-samples-SYNTHETIC.zip"'})


class StepIn(BaseModel):
    step: str = Field(pattern="^(dismissed)$")


@router.post("/sandbox/onboarding")
def onboarding_step(body: StepIn, db: Session = Depends(get_db), current: CurrentUser = Depends(self_scoped)) -> dict:
    real = _real(current)
    real.onboarding = {**(real.onboarding or {}), body.step: True}
    db.commit()
    return {"ok": True}


_ = (RoleAssignment, build_user_out, uuid)
