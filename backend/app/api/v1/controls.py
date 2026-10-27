from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Baseline, BaselineControl, Cci, CciControlMap, ContentVersion, Control, ControlObjective
from app.schemas import CciMapOut, ControlDetail, ControlList, ControlSummary, FamilyOut, ObjectiveOut
from app.security.deps import require_permission
from app.services.content.loader import active_catalog_id

router = APIRouter(prefix="/controls", tags=["controls"], dependencies=[Depends(require_permission("catalog.read"))])


def _baselines_for(db: Session, control_uuids: list) -> dict:
    out = defaultdict(list)
    if not control_uuids:
        return out
    rows = db.execute(
        select(BaselineControl.control_uuid, Baseline.baseline_key)
        .join(Baseline, Baseline.id == BaselineControl.baseline_id)
        .join(ContentVersion, ContentVersion.id == Baseline.profile_version_id)
        .where(BaselineControl.control_uuid.in_(control_uuids), ContentVersion.is_active.is_(True))
    ).all()
    order = {"low": 0, "moderate": 1, "high": 2, "privacy": 3}
    for cu, key in rows:
        out[cu].append(key)
    for k in out:
        out[k].sort(key=lambda b: order.get(b, 9))
    return out


@router.get("", response_model=ControlList)
def list_controls(
    db: Session = Depends(get_db),
    q: str | None = Query(None, max_length=100),
    family: str | None = Query(None, max_length=10),
    baseline: str | None = Query(None, pattern="^(low|moderate|high|privacy)$"),
    include_withdrawn: bool = False,
    enhancements: bool = True,
    limit: int = Query(100, ge=1, le=2000),
    offset: int = Query(0, ge=0),
) -> ControlList:
    cat_id = active_catalog_id(db)
    if cat_id is None:
        return ControlList(total=0, limit=limit, offset=offset, catalog_version_id=None, items=[])
    stmt = select(Control).where(Control.catalog_version_id == cat_id)
    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.where(or_(Control.control_id.ilike(term), Control.label.ilike(term), Control.title.ilike(term)))
    if family:
        stmt = stmt.where(Control.family_id == family.lower())
    if not include_withdrawn:
        stmt = stmt.where(Control.is_withdrawn.is_(False))
    if not enhancements:
        stmt = stmt.where(Control.is_enhancement.is_(False))
    if baseline:
        sub = (select(BaselineControl.control_uuid).join(Baseline, Baseline.id == BaselineControl.baseline_id)
               .join(ContentVersion, ContentVersion.id == Baseline.profile_version_id)
               .where(Baseline.baseline_key == baseline, ContentVersion.is_active.is_(True)))
        stmt = stmt.where(Control.id.in_(sub))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = list(db.scalars(stmt.order_by(Control.sort_id).limit(limit).offset(offset)))
    bl = _baselines_for(db, [r.id for r in rows])
    items = [ControlSummary.model_validate(r).model_copy(update={"baselines": bl.get(r.id, [])}) for r in rows]
    return ControlList(total=total, limit=limit, offset=offset, catalog_version_id=cat_id, items=items)


@router.get("/families", response_model=list[FamilyOut])
def families(db: Session = Depends(get_db)) -> list[FamilyOut]:
    cat_id = active_catalog_id(db)
    rows = db.execute(
        select(Control.family_id, Control.family_title, func.count())
        .where(Control.catalog_version_id == cat_id, Control.is_withdrawn.is_(False))
        .group_by(Control.family_id, Control.family_title).order_by(Control.family_id)
    ).all()
    return [FamilyOut(family_id=f, family_title=t, count=c) for f, t, c in rows]


@router.get("/cci-index")
def cci_index(db: Session = Depends(get_db)) -> dict:
    """Read-only CCI → control ids of the active catalog (catalog tree search by CCI); fetched lazily, no per-control details."""
    cat_id = active_catalog_id(db)
    out: dict[str, list[str]] = {}
    for cci, cid in db.execute(select(CciControlMap.cci_id, Control.control_id).join(Control, Control.id == CciControlMap.control_uuid)
                               .where(Control.catalog_version_id == cat_id).distinct()):
        out.setdefault(cci, []).append(cid)
    return out


@router.get("/{control_id}", response_model=ControlDetail)
def get_control(control_id: str, db: Session = Depends(get_db)) -> ControlDetail:
    cat_id = active_catalog_id(db)
    ctrl = db.scalar(select(Control).where(Control.catalog_version_id == cat_id, Control.control_id == control_id.lower()))
    if ctrl is None:
        raise HTTPException(404, f"Control {control_id} not found in active catalog")
    objectives = db.scalars(select(ControlObjective).where(ControlObjective.control_uuid == ctrl.id)
                            .order_by(ControlObjective.sort_order))
    cci_rows = db.execute(
        select(CciControlMap, Cci.definition).join(Cci, Cci.id == CciControlMap.cci_uuid)
        .where(CciControlMap.control_uuid == ctrl.id).order_by(CciControlMap.cci_id)
    ).all()
    enh = db.execute(select(Control.control_id, Control.label, Control.title, Control.is_withdrawn)
                     .where(Control.parent_id == ctrl.id).order_by(Control.sort_id)).all()
    summary = ControlSummary.model_validate(ctrl).model_copy(update={"baselines": _baselines_for(db, [ctrl.id]).get(ctrl.id, [])})
    return ControlDetail(
        **summary.model_dump(), statement=ctrl.statement, parameters=ctrl.parameters, guidance=ctrl.guidance,
        assessment_methods=ctrl.assessment_methods, links=ctrl.links,
        objectives=[ObjectiveOut.model_validate(o) for o in objectives],
        ccis=[CciMapOut(cci_id=m.cci_id, definition=d, reference_index=m.reference_index, statement_part=m.statement_part,
                        review_status=m.review_status, version=m.version, effective_date=m.effective_date, source=m.source)
              for m, d in cci_rows],
        enhancements=[{"control_id": c, "label": lbl, "title": t, "is_withdrawn": w} for c, lbl, t, w in enh],
        source=ctrl.source, provenance=ctrl.provenance,
    )
