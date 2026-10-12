"""Operator CLI.  python -m app.cli create-admin --email admin@agency.gov --name "Jane Admin" [--org "Agency Name"] [--password-stdin]
Bootstraps the first production platform administrator without any demo accounts. With OIDC (production default) no password is
stored: the admin signs in through the IdP and is matched by email. --password-stdin creates a dev_password identity and is only
allowed when dev_password is enabled (non-production)."""
import argparse
import re
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuthIdentity, Organization, RoleAssignment, User
from app.security.passwords import hash_password
from app.security.sessions import enabled_providers
from app.services import audit

SOURCE = "cli:create-admin"


def create_admin(email: str, name: str, org_name: str, password: str | None = None) -> tuple[User, bool]:
    email = email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValueError("invalid email")
    if password is not None and "dev_password" not in enabled_providers():
        raise ValueError("--password-stdin requires dev_password in AUTH_PROVIDERS (not allowed in production)")
    with SessionLocal() as db:
        org = db.scalar(select(Organization).where(Organization.name == org_name))
        if org is None:
            slug = re.sub(r"[^a-z0-9]+", "-", org_name.lower()).strip("-")[:90] or "org"
            org = Organization(name=org_name, slug=slug, is_synthetic=False, source=SOURCE)
            db.add(org)
            db.flush()
        user = db.scalar(select(User).where(User.email == email))
        created = user is None
        if created:
            user = User(org_id=org.id, email=email, display_name=name, title="Platform Administrator", source=SOURCE)
            db.add(user)
            db.flush()
        if not db.scalar(select(RoleAssignment.id).where(RoleAssignment.user_id == user.id, RoleAssignment.role == "platform_admin",
                                                         RoleAssignment.scope_type == "org", RoleAssignment.scope_id == user.org_id)):
            db.add(RoleAssignment(user_id=user.id, role="platform_admin", scope_type="org", scope_id=user.org_id, source=SOURCE))
        if password:
            ident = db.scalar(select(AuthIdentity).where(AuthIdentity.provider == "dev_password", AuthIdentity.subject == email))
            if ident is None:
                db.add(AuthIdentity(user_id=user.id, provider="dev_password", subject=email, secret_hash=hash_password(password)))
            else:
                ident.secret_hash = hash_password(password)
        audit.record(db, action="admin.bootstrap", outcome="success", actor_email=SOURCE, entity_type="user", entity_id=str(user.id),
                     details={"email": email, "org": org_name, "created": created, "password_identity": bool(password)})
        db.commit()
        return user, created


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-admin", help="create (or promote) a platform administrator")
    c.add_argument("--email", required=True)
    c.add_argument("--name", required=True)
    c.add_argument("--org", default="IronVision AI")
    c.add_argument("--password-stdin", action="store_true", help="read a dev_password secret from stdin (non-production only)")
    a = ap.parse_args(argv)
    pw = sys.stdin.readline().rstrip("\n") if a.password_stdin else None
    if a.password_stdin and len(pw or "") < 12:
        print("password must be at least 12 characters", file=sys.stderr)
        return 2
    try:
        user, created = create_admin(a.email, a.name, a.org, pw)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"{'created' if created else 'updated'} platform_admin {user.email} (id {user.id}) in org {a.org!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
