"""Auto-save helpers: close my editing sessions (leaving a page/record) and the per-user registration draft (not a system until Register)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import UserDraft
from app.security.deps import CurrentUser, require_permission, self_scoped
from app.services import autosave

router = APIRouter(tags=["autosave"])
KINDS = {"registration": "system.register"}


class CloseIn(BaseModel):
    entity_type: str | None = Field(None, max_length=50)
    entity_id: str | None = Field(None, max_length=100)


@router.post("/autosave/close")
def close_sessions(body: CloseIn, db: Session = Depends(get_db), current: CurrentUser = Depends(self_scoped)) -> dict:
    n = autosave.close_for(db, current.user.id, "left_record", body.entity_type, body.entity_id)
    db.commit()
    return {"closed": n}


def _kind(kind: str, current: CurrentUser) -> None:
    from app.security.rbac import has_permission

    if kind not in KINDS:
        raise HTTPException(404, "Unknown draft kind")
    if not has_permission(current.assignments, KINDS[kind], current.user.org_id):
        raise HTTPException(403, f"Needs the {KINDS[kind]} permission")


def _get(db: Session, current: CurrentUser, kind: str) -> UserDraft | None:
    return db.scalar(select(UserDraft).where(UserDraft.user_id == current.user.id, UserDraft.org_id == current.user.org_id, UserDraft.kind == kind))


def _out(d: UserDraft | None) -> dict:
    return {"data": d.data if d else None, "updated_at": d.updated_at.isoformat() if d else None}


@router.get("/drafts/{kind}")
def get_draft(kind: str, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    _kind(kind, current)
    return _out(_get(db, current, kind))


class DraftIn(BaseModel):
    data: dict


@router.put("/drafts/{kind}")
def put_draft(kind: str, body: DraftIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    """Stores the draft only – nothing is registered, audited as a record or visible to anyone else."""
    _kind(kind, current)
    if len(str(body.data)) > 200_000:
        raise HTTPException(413, "Draft too large")
    d = _get(db, current, kind)
    if d is None:
        d = UserDraft(user_id=current.user.id, org_id=current.user.org_id, kind=kind, data=body.data)
        db.add(d)
    else:
        d.data = body.data
    db.commit()
    db.refresh(d)
    return _out(d)


@router.delete("/drafts/{kind}", status_code=204)
def delete_draft(kind: str, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))) -> None:
    _kind(kind, current)
    d = _get(db, current, kind)
    if d is not None:
        db.delete(d)
        db.commit()
