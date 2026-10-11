"""Idempotent synthetic demo seed: one org, 8 users (one per role), org-scoped role assignments."""
import logging
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import AuthIdentity, ContentVersion, Organization, RoleAssignment, User
from app.security.passwords import hash_password, verify_password
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
    has_catalog = db.scalar(select(ContentVersion.id).where(ContentVersion.content_type == "oscal_catalog").limit(1))
    if not has_catalog and not jobs.has_pending(db, jobs.JOB_CONTENT_LOAD):
        jobs.enqueue(db, jobs.JOB_CONTENT_LOAD, {"force": False, "reason": "initial seed"})
        log.info("Enqueued initial reference content load job")
    elif has_catalog and os.environ.get("SAMPLES_DIR"):
        from app.seed_phase1 import seed_phase1

        seed_phase1(db, org, os.environ["SAMPLES_DIR"])
    return org


def run() -> None:
    s = get_settings()
    if not s.demo_user_password:
        raise RuntimeError("DEMO_USER_PASSWORD must be set to seed demo users")
    with SessionLocal() as db:
        seed_demo(db, s.demo_user_password)
        db.commit()
    log.info("Demo seed complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
