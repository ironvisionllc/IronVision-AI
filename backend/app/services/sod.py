"""Separation of duties: whoever prepared/edited/accepted an item may not approve it.
Real orgs: compare REAL people (a sandbox persona is operated by its real user – switching persona is not a different person).
Sandbox orgs (server-side Organization.is_sandbox only): a different persona of the same real user is allowed and labelled; the same persona never."""
from sqlalchemy.orm import Session

from app.models import Organization

SANDBOX_LABEL = "Sandbox: same person"
REAL_MSG = ("Separation of duties: a different person must approve – you {verb} this item. "
            "Switching to another persona does not count as a different person.")
SAME_PERSONA_MSG = ("Separation of duties: the same role that {verb} this item cannot approve it. "
                    "In this sandbox, another role (a different persona) must approve, or ask another person.")


def identity(current) -> dict:
    real = current.operator or current.user
    return {"real_user_id": str(real.id), "real_email": real.email, "persona_user_id": str(current.user.id), "persona_email": current.user.email,
            "persona_role": current.user.persona_role}


def is_sandbox(db: Session, org_id) -> bool:
    org = db.get(Organization, org_id)
    return bool(org and org.is_sandbox)


def evaluate(prior: dict | None, current, sandbox: bool, verb: str) -> tuple[str | None, dict | None]:
    """→ (blocked_reason, audit_details). No prior actor (e.g. auto-suggested row) → allowed."""
    if not prior:
        return None, None
    me = identity(current)
    if prior["real_user_id"] != me["real_user_id"]:
        return None, {"sod": "different person", "prepared_by": prior, "approved_by": me}
    if not sandbox:
        return REAL_MSG.format(verb=verb), None
    if prior["persona_user_id"] == me["persona_user_id"]:
        return SAME_PERSONA_MSG.format(verb=verb), None
    return None, {"sod": SANDBOX_LABEL, "label": SANDBOX_LABEL, "real_user": me["real_email"], "prepared_by": prior, "approved_by": me}
