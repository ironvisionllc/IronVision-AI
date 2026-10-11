from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RoleAssignment, User


def user_labels(db: Session, ids) -> dict[str, dict]:
    """{user_id: {"name", "email", "roles"}}; roles = org-scope roles (system-scope listed with acronym-less 'system:' prefix)."""
    ids = {i for i in ids if i}
    if not ids:
        return {}
    out = {str(u.id): {"name": u.display_name, "email": u.email, "roles": []} for u in db.scalars(select(User).where(User.id.in_(ids)))}
    for ra in db.scalars(select(RoleAssignment).where(RoleAssignment.user_id.in_(ids))):
        r = out[str(ra.user_id)]["roles"]
        if ra.role not in r:
            r.append(ra.role)
    return out


def attach(db: Session, rows: list[dict], id_key: str, prefix: str) -> list[dict]:
    labels = user_labels(db, [r.get(id_key) for r in rows])
    for r in rows:
        lab = labels.get(str(r.get(id_key)), {})
        r[f"{prefix}_name"], r[f"{prefix}_roles"] = lab.get("name"), lab.get("roles", [])
        r[prefix] = {"name": lab.get("name"), "roles": lab.get("roles", []), "email": lab.get("email")} if lab else None
    return rows
