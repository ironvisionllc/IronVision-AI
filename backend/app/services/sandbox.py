"""Private sandbox tenants: provisioning (same idempotent seed pipeline, real ingestion), persona identities for
separation of duties, reset, inactivity expiry/purge. Persona mode is a DEMO feature – never for production SoD."""
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models import AuthIdentity, AuthSession, Evidence, Organization, RoleAssignment, System, User
from app.services import audit

log = logging.getLogger("aegis.sandbox")
PERSONAS = [
    ("isso", "Alex Rivera", "ISSO persona"), ("issm", "Morgan Lee", "ISSM persona"), ("sca", "Dana Brooks", "SCA persona"),
    ("ao", "Col. Taylor", "AO persona"), ("system_owner", "Jordan Patel", "System Owner persona"), ("devsecops", "Riley Chen", "DevSecOps persona"),
    ("leadership_viewer", "Casey Morgan", "Leadership persona"), ("privacy_official", "Sam Ortiz", "Privacy Official persona"), ("platform_admin", "Avery Brooks", "Admin persona"),
]
ROLES = [p[0] for p in PERSONAS]
SANDBOX_SOURCE = "sandbox"
DEMO_EMAIL = "demo@ironvision.ai"


def now() -> datetime:
    return datetime.now(timezone.utc)


def inactivity_days() -> int:
    return int(os.environ.get("SANDBOX_INACTIVITY_DAYS", "30"))


REQUIRED_SAMPLES = ("stig/mpp_mpp-app-01.ckl", "acas/ltp_weekly_scan.nessus", "acas/fmdh_scan_export.csv", "policies/access_control_policy.txt")
REQUIRED_SAMPLE_GLOBS = ("stig/ltp_*",)  # every file seed_phase1/seed_phase3 read for the demo sandbox


class SamplesMissing(RuntimeError):
    pass


def samples_dir() -> str:
    """SAMPLES_DIR only (compose: SAMPLES_DIR=/samples + ./samples:/samples:ro). No computed fallback: it pointed to /app/samples
    in the recovery image and /srv/samples in the backend image – neither exists."""
    sd = os.environ.get("SAMPLES_DIR")
    if not sd:
        raise SamplesMissing("SAMPLES_DIR is not set – the demo sandbox needs the sample files "
                             "(compose: SAMPLES_DIR=/samples and ./samples:/samples:ro)")
    return sd


def check_samples(sd: str | None = None) -> dict:
    """Precheck BEFORE any DB write: every required sample file exists, else SamplesMissing naming each missing path."""
    from pathlib import Path
    root = Path(sd or samples_dir())
    missing = [str(root / f) for f in REQUIRED_SAMPLES if not (root / f).is_file()]
    missing += [str(root / g) for g in REQUIRED_SAMPLE_GLOBS if not any(p.is_file() for p in root.glob(g))]
    if missing:
        raise SamplesMissing(f"demo sandbox sample files missing (SAMPLES_DIR={root}): {', '.join(missing)}")
    return {"samples_dir": str(root), "files": sorted(str(p.relative_to(root)) for g in (*REQUIRED_SAMPLES, *REQUIRED_SAMPLE_GLOBS)
                                                      for p in root.glob(g))}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "sandbox"


def create_sandbox(db: Session, owner: User | None, org_name: str | None, email: str) -> Organization:
    base = (org_name or email.split("@")[0]).strip()[:120]
    sfx = uuid.uuid4().hex[:6]
    org = Organization(name=f"{base} Sandbox – SYNTHETIC ({sfx})", slug=f"sbx-{_slug(base)}-{sfx}", is_synthetic=True, source=SANDBOX_SOURCE,
                       is_sandbox=True, sandbox_personas=True, last_activity_at=now(), sandbox_status="queued", sandbox_progress={"step": "queued", "pct": 0})
    db.add(org)
    db.flush()
    ensure_personas(db, org, owner)
    return org


def create_owner(db: Session, email: str, name: str, org_name: str | None) -> tuple[User, Organization]:
    """New clean sandbox tenant + its owner (self sign-up and Keycloak self-registration). Caller enqueues/runs provisioning."""
    org = create_sandbox(db, None, org_name or name, email)
    u = User(org_id=org.id, email=email, display_name=name.strip()[:200], title="Sandbox owner", source=SANDBOX_SOURCE)
    db.add(u)
    db.flush()
    org.owner_user_id = u.id
    for p in db.scalars(select(User).where(User.org_id == org.id, User.persona_role.is_not(None))):
        p.operator_id = u.id
    return u, org


def ensure_personas(db: Session, org: Organization, owner: User | None) -> dict[str, User]:
    out = {}
    for role, name, label in PERSONAS:
        email = f"{role.replace('_', '.')}.{org.slug}@persona.ironvision.invalid"
        u = db.scalar(select(User).where(User.email == email))
        if u is None:
            u = User(org_id=org.id, email=email, display_name=f"{name} ({label})", title=f"{label} – sandbox persona (SYNTHETIC)",
                     source=SANDBOX_SOURCE, persona_role=role, operator_id=owner.id if owner else None)
            db.add(u)
            db.flush()
            db.add(RoleAssignment(user_id=u.id, role=role, scope_type="org", scope_id=org.id, source=SANDBOX_SOURCE))
        out[role] = u
    db.flush()
    return out


def persona(db: Session, org_id, role: str) -> User | None:
    return db.scalar(select(User).where(User.org_id == org_id, User.persona_role == role))


def is_demo(db: Session, org: Organization) -> bool:
    owner = db.get(User, org.owner_user_id) if org.owner_user_id else None
    return bool(owner and owner.email == DEMO_EMAIL)


def provision(db: Session, org_id) -> dict:
    """Demo account: the same idempotent seed pipeline as the demo (real ingestion of the sample files).
    Every other sign-up: a CLEAN tenant – tenant configuration only (decision rules, CAT/match rules), no systems or records."""
    from app.seed_phase1 import seed_phase1, seed_tenant_config

    org = db.get(Organization, org_id)
    demo = is_demo(db, org)
    sd = check_samples()["samples_dir"] if demo else None   # before the first write: never a half-provisioned demo sandbox
    org.sandbox_status, org.sandbox_progress = "provisioning", {"step": "Registering systems and ingesting sample scans…" if demo else "Preparing your workspace…", "pct": 20}
    db.commit()
    t0 = now()
    if demo:
        seed_phase1(db, org, sd)
    else:
        seed_tenant_config(db, org)
    org.sandbox_status, org.sandbox_progress = "ready", {"step": "ready", "pct": 100, "seconds": round((now() - t0).total_seconds(), 1),
                                                         "ready_at": now().isoformat(), "mode": "demo" if demo else "clean"}
    db.commit()
    return {"org_id": str(org.id), **org.sandbox_progress}


def _clear_records(db: Session, org: Organization) -> dict:
    """Delete every tenant record (systems cascade to assets/findings/evidence/POA&M links/reviews…); keeps users, personas,
    org-level role assignments and tenant configuration (decision rules, CAT/match rules)."""
    from app.models import (AppSetting, CommonControlProvider, ContentUpdate, EmassChange, EmassSyncRun, Notification, Poam, Policy,
                            RiskSnapshot)

    objects = _purge_data(db, org)
    sys_ids = list(db.scalars(select(System.id).where(System.org_id == org.id)))
    user_ids = select(User.id).where(User.org_id == org.id)
    for m in (Policy, ContentUpdate, EmassSyncRun, EmassChange, RiskSnapshot, Poam, CommonControlProvider):
        db.execute(delete(m).where(m.org_id == org.id))
    db.execute(delete(AppSetting).where(AppSetting.org_id == org.id, AppSetting.key.in_(("emass", "emass_mock_failures", "demo_data"))))
    db.execute(delete(Notification).where(Notification.user_id.in_(user_ids)))
    db.execute(delete(RoleAssignment).where(RoleAssignment.scope_type == "system", RoleAssignment.scope_id.in_(sys_ids)))
    db.execute(delete(System).where(System.id.in_(sys_ids)))
    db.execute(update(User).where(User.org_id == org.id).values(onboarding=None, acting_role=None))
    db.flush()
    return {"systems": len(sys_ids), "objects_deleted": objects}


def clear_workspace(db: Session, org: Organization, actor: User | None, action: str = "sandbox.workspace_cleared") -> dict:
    if not org.is_sandbox or is_demo(db, org):
        raise PermissionError("Clear workspace applies to non-demo sandbox tenants only")
    res = _clear_records(db, org)
    from app.seed_phase1 import seed_tenant_config

    seed_tenant_config(db, org)
    org.sandbox_status, org.sandbox_progress = "ready", {"step": "ready", "pct": 100, "ready_at": now().isoformat(), "mode": "clean"}
    audit.record(db, action=action, actor_user_id=actor.id if actor else None, actor_email=actor.email if actor else "system",
                 entity_type="organization", entity_id=str(org.id), details=res)
    return res


def convert_signups_to_clean(db: Session) -> list[dict]:
    """One-off migration: existing non-demo sign-up tenants lose their seeded copies (accounts kept)."""
    out = []
    for org in db.scalars(select(Organization).where(Organization.is_sandbox.is_(True), Organization.sandbox_status != "purged")):
        if is_demo(db, org):
            continue
        out.append({"org": org.name, **clear_workspace(db, org, None, "sandbox.converted_to_clean")})
    db.commit()
    return out



def _purge_data(db: Session, org: Organization) -> int:
    from app.services.storage import get_storage

    sys_ids = list(db.scalars(select(System.id).where(System.org_id == org.id)))
    keys = list(db.scalars(select(Evidence.storage_key).where(Evidence.system_id.in_(sys_ids)))) if sys_ids else []
    store, n = get_storage(), 0
    shared = set(db.scalars(select(Evidence.storage_key).where(Evidence.storage_key.in_(keys), Evidence.system_id.not_in(sys_ids)))) if keys else set()
    for k in set(keys) - shared:
        try:
            store.delete(k)
            n += 1
        except Exception:  # noqa: BLE001 – object may already be gone
            pass
    return n


def reset(db: Session, org: Organization, actor: User | None) -> None:
    from app.seed_phase1 import reset_demo

    if not org.is_sandbox:
        raise PermissionError("Only sandbox tenants can be reset")
    sd = check_samples()["samples_dir"]   # before purging anything
    _purge_data(db, org)
    org.sandbox_status, org.sandbox_progress = "provisioning", {"step": "Resetting sandbox…", "pct": 10}
    reset_demo(db, org, sd)
    org.sandbox_status, org.sandbox_progress = "ready", {"step": "ready", "pct": 100, "ready_at": now().isoformat()}
    audit.record(db, action="sandbox.reset", actor_user_id=actor.id if actor else None, actor_email=actor.email if actor else "scheduler",
                 entity_type="organization", entity_id=str(org.id))


def purge_refusal(db: Session, org: Organization) -> str | None:
    """Only self-service sandbox tenants are purge-eligible. Restored/customer data can never be touched by expiry/purge."""
    if not org.is_sandbox:
        return "not a sandbox tenant"
    if org.protected:
        return "tenant is protected"
    if org.source != SANDBOX_SOURCE:
        return f"tenant source is {org.source!r}, not a self-service sandbox"
    owner = db.get(User, org.owner_user_id) if org.owner_user_id else None
    if owner is None or owner.email == DEMO_EMAIL:
        return "shared demo tenant or tenant without a self-service owner"
    real = db.scalar(select(func.count()).select_from(RoleAssignment).join(User, User.id == RoleAssignment.user_id)
                     .where(User.org_id == org.id, User.persona_role.is_(None)))
    if real:
        return f"{real} role assignment(s) outside sandbox persona mode"
    return None


def purge(db: Session, org: Organization, reason: str) -> dict:
    """Delete tenant data, evidence objects and user accounts. Platform audit keeps only tenant id + counts (no content)."""
    why = purge_refusal(db, org)
    if why:
        raise PermissionError(f"Purge refused for tenant {org.id}: {why}")
    from app.models import Notification, Poam

    objects = _purge_data(db, org)
    sys_ids = list(db.scalars(select(System.id).where(System.org_id == org.id)))
    user_ids = list(db.scalars(select(User.id).where(User.org_id == org.id)))
    from app.models import CommonControlProvider, ContentUpdate, EmassSyncRun, Policy, RiskSnapshot
    for m in (Policy, ContentUpdate, EmassSyncRun, RiskSnapshot, CommonControlProvider):
        db.execute(delete(m).where(m.org_id == org.id))
    from app.seed_phase4 import reset_phase4
    reset_phase4(db, org)
    db.execute(delete(Notification).where(Notification.user_id.in_(user_ids)))
    db.execute(delete(Poam).where(Poam.org_id == org.id))
    db.execute(delete(RoleAssignment).where(RoleAssignment.user_id.in_(user_ids)))
    db.execute(delete(System).where(System.id.in_(sys_ids)))
    db.execute(delete(AuthSession).where(AuthSession.user_id.in_(user_ids)))
    oidc_ids = [tuple(s.rsplit("|", 1)) for s in db.scalars(select(AuthIdentity.subject).where(
        AuthIdentity.user_id.in_(user_ids), AuthIdentity.provider == "oidc"))]
    db.execute(delete(AuthIdentity).where(AuthIdentity.user_id.in_(user_ids)))
    for u in db.scalars(select(User).where(User.id.in_(user_ids))):
        u.is_active, u.email, u.display_name, u.title, u.operator_id = False, f"{u.id}@purged.invalid", "(purged sandbox user)", None, None
    org.sandbox_status, org.name, org.slug = "purged", f"purged-{org.id}", f"purged-{org.id}"
    from app.security.registration import offboard
    res = {"tenant_id": str(org.id), "systems": len(sys_ids), "users": len(user_ids), "objects_deleted": objects, "reason": reason,
           "keycloak_users": offboard(oidc_ids)}
    audit.record(db, action="platform.sandbox_purged", actor_email="scheduler", entity_type="tenant", entity_id=str(org.id), details=res)
    db.flush()
    return res


def expiry_info(org: Organization) -> dict | None:
    if not org.is_sandbox or not org.last_activity_at or org.protected:  # permanent (protected) sandboxes never expire – no countdown
        return None
    idle = (now() - org.last_activity_at).days
    n = inactivity_days()
    return {"inactivity_days": n, "idle_days": idle, "expires_in_days": max(n - idle, 0), "warn": idle >= n - 7,
            "message": f"Sandboxes are deleted after {n} days without activity."}


def run_expiry(db: Session) -> dict:
    n, cutoff = inactivity_days(), now() - timedelta(days=inactivity_days())
    purged = []
    for org in db.scalars(select(Organization).where(Organization.is_sandbox.is_(True), Organization.sandbox_status != "purged",
                                                     Organization.last_activity_at < cutoff)):
        why = purge_refusal(db, org)
        if why:
            if not (why.startswith("shared demo")):
                audit.record(db, action="sandbox.purge_refused", entity_type="organization", entity_id=str(org.id), outcome="denied",
                             details={"reason": why})
            continue
        purged.append(purge(db, org, f"inactive > {n} days"))
    for org in db.scalars(select(Organization).where(Organization.is_sandbox.is_(True), Organization.sandbox_status == "ready")):
        info = expiry_info(org)
        if info and info["idle_days"] in (n - 7, n - 1):
            from app.models import Notification
            if org.owner_user_id:
                db.add(Notification(user_id=org.owner_user_id, kind="sandbox_expiry", severity="warning", title="Sandbox expiry warning",
                                    body=f"Your sandbox will be deleted in {info['expires_in_days']} day(s) unless you sign in."))
    db.commit()
    return {"purged": len(purged)}


def reset_demo_account(db: Session) -> dict:
    u = db.scalar(select(User).where(User.email == DEMO_EMAIL))
    if not u:
        return {"skipped": "no demo account"}
    reset(db, db.get(Organization, u.org_id), None)
    db.commit()
    return {"reset": True}


def seed_demo_account(db: Session, password: str | None) -> Organization:
    """password=None (Keycloak demo deployment): no local password identity – the launcher signs in via the identity mapping."""
    from app.security.passwords import hash_password, verify_password

    u = db.scalar(select(User).where(User.email == DEMO_EMAIL))
    if u is None:
        org = create_sandbox(db, None, "IronVision Demo", DEMO_EMAIL)
        u = User(org_id=org.id, email=DEMO_EMAIL, display_name="IronVision Demo User", title="Shared demo account (SYNTHETIC)", source=SANDBOX_SOURCE)
        db.add(u)
        db.flush()
        org.owner_user_id = u.id
        db.execute(update(User).where(User.org_id == org.id, User.persona_role.is_not(None)).values(operator_id=u.id))
    org = db.get(Organization, u.org_id)
    ident = db.scalar(select(AuthIdentity).where(AuthIdentity.provider == "dev_password", AuthIdentity.subject == DEMO_EMAIL))
    if password is None:
        pass
    elif ident is None:
        db.add(AuthIdentity(user_id=u.id, provider="dev_password", subject=DEMO_EMAIL, secret_hash=hash_password(password)))
    elif not verify_password(password, ident.secret_hash or ""):
        ident.secret_hash = hash_password(password)
    db.flush()
    return org


DEMO_DATA_KEY = "demo_data"


def has_demo_data(db: Session, org_id) -> bool:
    """Synthetic sample content is visible only to the shared demo tenant, non-sandbox tenants (unchanged) and sandboxes that
    explicitly loaded demo data."""
    from app.models import AppSetting
    org = db.get(Organization, org_id)
    if org is None or not org.is_sandbox or is_demo(db, org):
        return True
    return db.scalar(select(AppSetting.id).where(AppSetting.org_id == org_id, AppSetting.key == DEMO_DATA_KEY)) is not None


def load_demo_data(db: Session, org: Organization, actor: User) -> dict:
    """Idempotent: the same synthetic seed pipeline as the demo account, into THIS sandbox only. Removed by Clear my workspace."""
    from app.services.rmf import set_setting
    from app.seed_phase1 import seed_phase1

    if not org.is_sandbox or is_demo(db, org):
        raise PermissionError("Load demo data applies to private sandbox workspaces only")
    if has_demo_data(db, org.id):
        return {"loaded": True, "already_loaded": True}
    if db.scalar(select(System.id).where(System.org_id == org.id).limit(1)):
        raise ValueError("Your workspace already has systems – clear it first (Clear my workspace), then load the demo data")
    sd = check_samples()["samples_dir"]
    seed_phase1(db, org, sd)
    n = db.scalar(select(func.count()).select_from(System).where(System.org_id == org.id))
    set_setting(db, org.id, DEMO_DATA_KEY, {"loaded_at": now().isoformat(), "by": actor.email, "synthetic": True, "systems": n})
    audit.record(db, action="sandbox.demo_data_loaded", actor_user_id=actor.id, actor_email=actor.email, entity_type="organization",
                 entity_id=str(org.id), details={"systems": n, "synthetic": True})
    return {"loaded": True, "already_loaded": False, "systems": n}
