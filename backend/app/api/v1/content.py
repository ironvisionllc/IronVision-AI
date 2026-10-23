from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ContentVersion
from app.schemas import ContentVersionOut
from app.security.deps import CurrentUser, get_current_user, require_permission
from app.services.content.loader import content_stats

router = APIRouter(prefix="/content", tags=["reference-content"], dependencies=[Depends(require_permission("catalog.read"))])


@router.get("/versions", response_model=list[ContentVersionOut])
def versions(db: Session = Depends(get_db), active_only: bool = True,
             current: CurrentUser = Depends(get_current_user)) -> list[ContentVersionOut]:
    from app.services import sandbox as sbx
    stmt = select(ContentVersion).order_by(ContentVersion.content_type, ContentVersion.content_key)
    if active_only:
        stmt = stmt.where(ContentVersion.is_active.is_(True))
    synth = sbx.has_demo_data(db, current.user.org_id)
    return [ContentVersionOut.model_validate(v) for v in db.scalars(stmt) if synth or not (v.meta or {}).get("synthetic")]


@router.get("/stats")
def stats(db: Session = Depends(get_db)) -> dict:
    from app.services.counts import catalog_counts
    return {**content_stats(db), "counts": catalog_counts(db)}


@router.get("/counts")
def counts(db: Session = Depends(get_db)) -> dict:
    from app.services.counts import catalog_counts
    return catalog_counts(db)
