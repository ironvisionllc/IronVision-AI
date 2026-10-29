"""Continuous Monitoring Strategy (SP 800-37 Rev 2 Task S-5, defined in Select) and SLCM due list (Monitor). Feeds the eMASS SLCM fields."""
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.records import assignment_for, enforce, get_system
from app.db import get_db
from app.security.deps import CurrentUser, require_permission
from app.services import audit, iscm

router = APIRouter(tags=["iscm"])


class ProfileIn(BaseModel):
    name: str = Field(..., max_length=120)
    match_type: Literal["family", "control_list", "designation"]
    match_value: str = Field(..., max_length=2000)
    values: dict = {}


class StrategyIn(BaseModel):
    narrative: str | None = Field(None, max_length=20000)
    scope: str | None = Field(None, max_length=4000)
    defaults: dict = {}
    profiles: list[ProfileIn] = []
    reporting: list[dict] = []
    review_activities: list[dict] = []
    evidence_requirements: list[dict] = []


class IscmDecisionIn(BaseModel):
    approve: bool
    comment: str = Field("", max_length=2000)


class PromoteIn(BaseModel):
    field: Literal[tuple(iscm.SLCM)]  # type: ignore[valid-type]
    value: str = Field(..., max_length=4000)
    target: Literal["system_default", "family_profile"]
    families: list[str] = []


class ResetIn(BaseModel):
    fields: list[str]


@router.get("/systems/{system_id}/iscm")
def get_strategy(system_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    return iscm.view(db, get_system(db, system_id))


@router.put("/systems/{system_id}/iscm")
def put_strategy(system_id: uuid.UUID, body: StrategyIn, request: Request, db: Session = Depends(get_db),
                 current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    enforce(request, current, "system.write", system_id)
    s = get_system(db, system_id)
    iscm.save(db, s, body.model_dump(), current)
    db.commit()
    return iscm.view(db, s)


@router.post("/systems/{system_id}/iscm/submit")
def submit_strategy(system_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                    current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    enforce(request, current, "system.write", system_id)
    s = get_system(db, system_id)
    iscm.submit(db, s, current)
    db.commit()
    return iscm.view(db, s)


@router.post("/systems/{system_id}/iscm/withdraw")
def withdraw_strategy(system_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                      current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    enforce(request, current, "system.write", system_id)
    s = get_system(db, system_id)
    iscm.withdraw(db, s, current)
    db.commit()
    return iscm.view(db, s)


@router.post("/systems/{system_id}/iscm/decision")
def decide_strategy(system_id: uuid.UUID, body: IscmDecisionIn, db: Session = Depends(get_db),
                    current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    s = get_system(db, system_id)
    iscm.decide(db, s, current, body.approve, body.comment)
    db.commit()
    return iscm.view(db, s)


@router.get("/systems/{system_id}/iscm/promote-preview")
def promote_preview(system_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    return {"items": iscm.promote_preview(db, get_system(db, system_id)),
            "note": "Reviewed action: promoting changes the draft strategy only; it takes effect when the ISSM approves it."}


@router.post("/systems/{system_id}/iscm/promote")
def promote(system_id: uuid.UUID, body: PromoteIn, request: Request, db: Session = Depends(get_db),
            current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    enforce(request, current, "system.write", system_id)
    s = get_system(db, system_id)
    v = iscm.view(db, s)["strategy"] or {"defaults": {}, "profiles": []}
    body_in = {k: v.get(k) for k in ("narrative", "scope", "reporting", "review_activities", "evidence_requirements")}
    profiles = [{k: p[k] for k in ("name", "match_type", "match_value", "values")} for p in v["profiles"]]
    defaults = dict(v["defaults"] or {})
    if body.target == "system_default":
        defaults[body.field] = body.value
    else:
        if not body.families:
            raise HTTPException(422, "Choose at least one control family")
        fams = ",".join(f.lower() for f in body.families)
        p = next((p for p in profiles if p["match_type"] == "family" and p["match_value"] == fams), None)
        if p is None:
            p = {"name": "/".join(f.upper() for f in body.families), "match_type": "family", "match_value": fams, "values": {}}
            profiles.append(p)
        p["values"] = {**p["values"], body.field: body.value}
    iscm.save(db, s, {**body_in, "defaults": defaults, "profiles": profiles}, current)
    audit.record(db, action="iscm.common_value_promoted", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="system",
                 entity_id=str(s.id), after=body.model_dump(), details={"takes_effect": "after ISSM approval"}, **audit.request_meta(request))
    db.commit()
    return iscm.view(db, s)


@router.get("/systems/{system_id}/iscm/due")
def slcm_due(system_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    items = iscm.due(db, get_system(db, system_id))
    return {"items": items, "counts": {k: sum(1 for i in items if i["status"] == k) for k in ("overdue", "never_monitored", "due_soon", "on_track", "no_frequency")}}


@router.post("/systems/{system_id}/workbench/controls/{control_id}/emass/slcm-reset")
def slcm_reset(system_id: uuid.UUID, control_id: str, body: ResetIn, request: Request, db: Session = Depends(get_db),
               current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    """Reset to strategy: clears the per-control SLCM override so the approved Continuous Monitoring Strategy value applies."""
    enforce(request, current, "implementation.write", system_id)
    a = assignment_for(db, system_id, control_id)
    done = iscm.reset_fields(db, a, body.fields, current, audit.request_meta(request))
    db.commit()
    return {"reset": done}
