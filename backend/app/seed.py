"""Idempotent synthetic demo seed: one org, 8 users (one per role), org-scoped role assignments."""
import logging
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import AuthIdentity, ContentVersion, Organization, RoleAssignment, User
from app.security.passwords import hash_password, verify_password
from app.check_env import DOCUMENTED_DEMO_PASSWORD
from app.services import jobs

log = logging.getLogger("aegis.seed")

ORG_NAME = "IronVision Demo Tenant – SYNTHETIC"
ORG_SLUG = "ironvision-demo"
DEMO_DOMAIN = "aegisrmf.demo"

DEMO_USERS = [
    ("system_owner", "Sam Owens", "System Owner (synthetic)"),
    ("isso", "Isabel Soto", "ISSO (synthetic)"),
    ("issm", "Marcus Hale", "ISSM (synthetic)"),
    ("sca", "Priya Anand", "Security Control Assessor (synthetic)"),
    ("ao", "Gen. Alex Ortega", "Authorizing Official (synthetic)"),
    ("devsecops", "Dana Kim", "DevSecOps Engineer (synthetic)"),
    ("leadership_viewer", "Lee Whitfield", "Leadership Viewer (synthetic)"),
    ("platform_admin", "Pat Admin", "Platform Administrator (synthetic)"),
]
SEED_SOURCE = "seed:phase0-demo"


def demo_email(role: str) -> str:
    return f"{role.replace('_', '.')}@{DEMO_DOMAIN}" if role != "isso" else f"isso@{DEMO_DOMAIN}"


def seed_demo(db: Session, password: str) -> Organization:
    org = db.scalar(select(Organization).where(Organization.slug == ORG_SLUG))
    if org is None:
        org = Organization(name=ORG_NAME, slug=ORG_SLUG, is_synthetic=True, source=SEED_SOURCE)
        db.add(org)
        db.flush()
    for role, name, title in DEMO_USERS:
        email = demo_email(role)
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(org_id=org.id, email=email, display_name=name, title=title, source=SEED_SOURCE)
            db.add(user)
            db.flush()
        ident = db.scalar(select(AuthIdentity).where(AuthIdentity.provider == "dev_password", AuthIdentity.subject == email))
        if ident is None:
            db.add(AuthIdentity(user_id=user.id, provider="dev_password", subject=email, secret_hash=hash_password(password)))
        elif not ident.secret_hash or not verify_password(password, ident.secret_hash):
            ident.secret_hash = hash_password(password)
        ra = db.scalar(select(RoleAssignment).where(RoleAssignment.user_id == user.id, RoleAssignment.role == role,
                                                    RoleAssignment.scope_type == "org", RoleAssignment.scope_id == org.id))
        if ra is None:
            db.add(RoleAssignment(user_id=user.id, role=role, scope_type="org", scope_id=org.id, source=SEED_SOURCE))
    db.flush()
    ensure_reference_content(db, org)
    return org


def ensure_reference_content(db: Session, org: Organization | None = None) -> None:
    """Reference content (NIST/CCI/KEV/STIG) is loaded for every deployment; synthetic Phase 1+ data only with a demo org."""
    has_catalog = db.scalar(select(ContentVersion.id).where(ContentVersion.content_type == "oscal_catalog").limit(1))
    if not has_catalog and not jobs.has_pending(db, jobs.JOB_CONTENT_LOAD):
        jobs.enqueue(db, jobs.JOB_CONTENT_LOAD, {"force": False, "reason": "initial seed"})
        log.info("Enqueued initial reference content load job")
    elif has_catalog and org is not None and os.environ.get("SAMPLES_DIR"):
        from app.seed_phase1 import seed_phase1

        seed_phase1(db, org, os.environ["SAMPLES_DIR"])


def retire_role_accounts(db: Session) -> None:
    """The 8 per-role demo accounts are pytest/acceptance fixtures only; deactivate any left in a demo/prod database."""
    for u in db.scalars(select(User).where(User.email.like(f"%@{DEMO_DOMAIN}"), User.is_active.is_(True))):
        u.is_active = False
    db.flush()


def demo_password() -> str:
    """STAGING_DEMO_PASSWORD overrides DEMO_USER_PASSWORD; outside development the publicly documented password is refused."""
    s = get_settings()
    pw = os.environ.get("STAGING_DEMO_PASSWORD") or s.demo_user_password
    if not pw:
        raise RuntimeError("DEMO_USER_PASSWORD (or STAGING_DEMO_PASSWORD) must be set to seed demo users")
    if s.environment != "development" and pw == DOCUMENTED_DEMO_PASSWORD:
        raise RuntimeError(f"Refusing to seed demo users with the publicly documented password in APP_ENV={s.environment}")
    return pw


def run() -> None:
    from app.check_env import production_guard

    production_guard()
    s = get_settings()
    with SessionLocal() as db:
        if s.seed_demo_data:
            from app.services import sandbox as sbx

            ensure_reference_content(db)
            pw = os.environ.get("STAGING_DEMO_PASSWORD") or s.demo_password or demo_password()
            org = sbx.seed_demo_account(db, pw)
            db.commit()
            if org.sandbox_status != "ready" and db.scalar(select(ContentVersion.id).where(ContentVersion.content_type == "oscal_catalog").limit(1)):
                sbx.provision(db, org.id)
            retire_role_accounts(db)
            log.info("Demo seed complete (single demo account %s with a private sandbox)", sbx.DEMO_EMAIL)
        else:
            ensure_reference_content(db)
            log.info("SEED_DEMO_DATA is off: reference content only, no demo accounts")
        db.commit()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
