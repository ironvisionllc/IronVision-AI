from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AuditEvent, Job
from app.schemas import AuditEventOut, ContentLoadRequest, JobOut
from app.security.deps import CurrentUser, require_permission
from app.services import audit, jobs

router = APIRouter(tags=["admin"])


@router.post("/admin/content/load", response_model=JobOut, status_code=202)
def trigger_content_load(body: ContentLoadRequest, request: Request, db: Session = Depends(get_db),
                         current: CurrentUser = Depends(require_permission("admin.content.load"))) -> JobOut:
    job = jobs.enqueue(db, jobs.JOB_CONTENT_LOAD, {"force": body.force}, requested_by=current.user.id)
    audit.record(db, action="content.load_requested", actor_user_id=current.user.id, actor_email=current.user.email,
                 entity_type="job", entity_id=str(job.id), details={"force": body.force}, **audit.request_meta(request))
    db.commit()
    db.refresh(job)
    return JobOut.model_validate(job)


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(db: Session = Depends(get_db), limit: int = Query(20, ge=1, le=100),
              _: CurrentUser = Depends(require_permission("admin.health.read"))) -> list[JobOut]:
    return [JobOut.model_validate(j) for j in db.scalars(select(Job).order_by(Job.created_at.desc()).limit(limit))]


@router.get("/audit-events", response_model=list[AuditEventOut])
def list_audit(db: Session = Depends(get_db), limit: int = Query(50, ge=1, le=500),
               action: str | None = Query(None, max_length=100), outcome: str | None = Query(None, max_length=30),
               _: CurrentUser = Depends(require_permission("audit.read"))) -> list[AuditEventOut]:
    stmt = select(AuditEvent).order_by(AuditEvent.seq.desc()).limit(limit)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if outcome:
        stmt = stmt.where(AuditEvent.outcome == outcome)
    from app.services.people import user_labels

    events = list(db.scalars(stmt))
    labels = user_labels(db, [e.actor_user_id for e in events])
    out = []
    for e in events:
        o = AuditEventOut.model_validate(e)
        lab = labels.get(str(e.actor_user_id), {})
        o.actor_name, o.actor_roles = lab.get("name"), lab.get("roles", [])
        out.append(o)
    return out


@router.get("/audit-events/verify")
def verify_audit(db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("audit.read"))) -> dict:
    return audit.verify_chain(db)


@router.get("/admin/identity-mappings")
def identity_mappings(db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("admin.users.manage"))) -> list[dict]:
    """Read-only: OIDC identity mappings for the caller's organization (created only by the operator CLI)."""
    from app.services import identity_map
    return identity_map.list_mappings(db, current.user.org_id)
