"""System registration: baseline + overlays + tailoring → control assignments, CCP inheritance, implementations."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (Baseline, BaselineControl, CommonControlProvider, ContentVersion, Control, ControlAssignment,
                        Implementation, Overlay, ProviderControl, System, TailoringDecision)
from app.services import audit
from app.services.content.loader import active_catalog_id

LEVEL = {"low": 1, "moderate": 2, "high": 3}


def high_water_mark(c: str | None, i: str | None, a: str | None) -> str | None:
    vals = [v.lower() for v in (c, i, a) if v]
    return max(vals, key=lambda v: LEVEL.get(v, 0)) if vals else None


def baseline_control_ids(db: Session, key: str) -> list[str]:
    return list(db.scalars(select(BaselineControl.control_id).join(Baseline, Baseline.id == BaselineControl.baseline_id)
                           .join(ContentVersion, ContentVersion.id == Baseline.profile_version_id)
                           .where(Baseline.baseline_key == key, ContentVersion.is_active.is_(True))))


def register_system(db: Session, data: dict, tailoring: list[dict], provider_ids: list[uuid.UUID] | None,
                    actor_id: uuid.UUID | None, actor_email: str | None) -> System:
    cat_id = active_catalog_id(db)
    if cat_id is None:
        raise ValueError("Reference catalog not loaded")
    system = System(**data)
    system.categorization = high_water_mark(system.confidentiality_impact, system.integrity_impact, system.availability_impact)
    db.add(system)
    db.flush()
    origin: dict[str, tuple[str, str]] = {cid: ("baseline", system.baseline_key) for cid in baseline_control_ids(db, system.baseline_key)}
    if system.include_privacy:
        for cid in baseline_control_ids(db, "privacy"):
            origin.setdefault(cid, ("baseline", "privacy"))
    for key in system.overlay_keys or []:
        ov = db.scalar(select(Overlay).where(Overlay.overlay_key == key, Overlay.is_active.is_(True)).order_by(Overlay.version.desc()))
        if ov is None:
            raise ValueError(f"Unknown overlay {key}")
        for cid in ov.controls_add:
            origin.setdefault(cid, ("overlay", f"{ov.overlay_key} v{ov.version}"))
        for cid in ov.controls_remove:
            origin.pop(cid, None)
    for t in tailoring:
        if not (t.get("justification") or "").strip():
            raise ValueError("Every tailoring decision requires a justification")
        cid = t["control_id"].lower()
        db.add(TailoringDecision(system_id=system.id, control_id=cid, action=t["action"], justification=t["justification"], decided_by=actor_id))
        if t["action"] == "remove":
            origin.pop(cid, None)
        else:
            origin[cid] = ("tailored_in", "tailoring")
    controls = {c.control_id: c.id for c in db.scalars(select(Control).where(Control.catalog_version_id == cat_id,
                                                                            Control.control_id.in_(list(origin))))}
    missing = sorted(set(origin) - set(controls))
    if missing:
        raise ValueError(f"Controls not in active catalog: {missing[:10]}")
    prov_q = select(ProviderControl, CommonControlProvider.id).join(CommonControlProvider)
    prov_q = prov_q.where(CommonControlProvider.id.in_(provider_ids)) if provider_ids is not None else prov_q.where(CommonControlProvider.org_id == system.org_id)
    inherit = {}
    for pc, pid in db.execute(prov_q):
        if pc.control_id not in inherit or pc.responsibility == "inherited":
            inherit[pc.control_id] = (pc.responsibility, pid)
    for cid, (org, detail) in origin.items():
        resp, pid = inherit.get(cid, ("system", None))
        a = ControlAssignment(id=uuid.uuid4(), system_id=system.id, control_uuid=controls[cid], control_id=cid, origin=org,
                              origin_detail=detail, responsibility=resp, provider_id=pid,
                              implementation_status="inherited" if resp == "inherited" else "planned")
        db.add(a)
        db.add(Implementation(assignment_id=a.id, version=1, narrative="", implementation_status=a.implementation_status, author_id=actor_id))
    db.flush()
    from app.services.evaluation import evaluate_system

    evaluate_system(db, system.id)
    audit.record(db, action="system.registered", actor_user_id=actor_id, actor_email=actor_email, entity_type="system",
                 entity_id=str(system.id), after={"name": system.name, "baseline": system.baseline_key, "overlays": system.overlay_keys,
                                                   "assigned_controls": len(origin), "tailoring": tailoring})
    return system
