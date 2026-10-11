from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ContentVersion
from app.schemas import ContentVersionOut
from app.security.deps import require_permission
from app.services.content.loader import content_stats

router = APIRouter(prefix="/content", tags=["reference-content"], dependencies=[Depends(require_permission("catalog.read"))])


@router.get("/versions", response_model=list[ContentVersionOut])
def versions(db: Session = Depends(get_db), active_only: bool = True) -> list[ContentVersionOut]:
    stmt = select(ContentVersion).order_by(ContentVersion.content_type, ContentVersion.content_key)
    if active_only:
        stmt = stmt.where(ContentVersion.is_active.is_(True))
    return [ContentVersionOut.model_validate(v) for v in db.scalars(stmt)]


@router.get("/stats")
def stats(db: Session = Depends(get_db)) -> dict:
    return content_stats(db)
