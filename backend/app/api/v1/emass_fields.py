"""eMASS Implementation Plan + Risk Assessment per control, AI/rule suggestions, bulk set, exports (xlsx, validation, MOCKED payload)."""
import json
import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.records import assignment_for, enforce, get_system
from app.db import get_db
from app.security.deps import CurrentUser, has_permission, require_permission
from app.services import audit
from app.services import emass_fields as ef

router = APIRouter(tags=["emass-fields"])
L2000 = Field(None, max_length=2000)


class Assist(BaseModel):
    source: Literal["ai", "rules"] | None = None
    fields: list[str] = []
    interaction_id: uuid.UUID | None = None


class PlanIn(BaseModel):
    implementation_status: Literal["Planned", "Implemented", "Inherited", "Not Applicable", "Manually Inherited"]
    control_designation: Literal["Common", "System-Specific", "Hybrid"] | None = None
    estimated_completion_date: date | None = None
    responsible_entities: str | None = L2000
    slcm_criticality: str | None = L2000
    slcm_frequency: Literal[tuple(ef.FREQUENCIES)] | None = None  # type: ignore[valid-type]
    slcm_method: Literal["Automated", "Semi-Automated", "Manual", "Undetermined"] | None = None
    slcm_reporting: str | None = L2000
    slcm_tracking: str | None = L2000
    slcm_comments: str | None = Field(None, max_length=4000)
    na_justification: str | None = L2000
    common_control_provider: Literal["DoD", "Component", "Enclave"] | None = None
    assist: Assist = Assist()


Level = Literal["Very Low", "Low", "Moderate", "High", "Very High"]


class RiskIn(BaseModel):
    severity: Level | None = None
    relevance_of_threat: Level | None = None
    likelihood: Level | None = None
    impact: Level | None = None
    residual_risk_level: Level | None = None
    impact_description: str | None = L2000
    vulnerability_summary: str | None = L2000
    recommendations: str | None = L2000
    mitigations: str | None = L2000
    assist: Assist = Assist()


def _can_edit(current: CurrentUser, system_id) -> bool:
    return has_permission(current.assignments, "implementation.write", current.user.org_id, system_id)


def _check_interaction(db: Session, a: Assist) -> None:
    from app.models import AIInteraction
    if a.source == "ai" and a.fields and (not a.interaction_id or not db.get(AIInteraction, a.interaction_id)):
        raise HTTPException(422, "AI-assisted values must include the interaction_id returned by Suggest values")


@router.get("/systems/{system_id}/workbench/controls/{control_id}/emass")
def get_fields(system_id: uuid.UUID, control_id: str, request: Request, db: Session = Depends(get_db),
               current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    enforce(request, current, "system.read", system_id)
    return ef.view(db, assignment_for(db, system_id, control_id), _can_edit(current, system_id))


@router.put("/systems/{system_id}/workbench/controls/{control_id}/emass/plan")
def put_plan(system_id: uuid.UUID, control_id: str, body: PlanIn, request: Request, db: Session = Depends(get_db),
             current: CurrentUser = Depends(require_permission("implementation.write"))) -> dict:
    enforce(request, current, "implementation.write", system_id)
    _check_interaction(db, body.assist)
    a = assignment_for(db, system_id, control_id)
    res = ef.save_plan(db, a, body.implementation_status, body.model_dump(exclude={"implementation_status", "assist"}), current,
                       body.assist.model_dump(), audit.request_meta(request))
    if res["status_changed"]:
        from app.services.evaluation import evaluate_system
        db.flush()
        evaluate_system(db, system_id)
    db.commit()
    return {**res, "emass": ef.view(db, a, True)}


@router.put("/systems/{system_id}/workbench/controls/{control_id}/emass/risk")
def put_risk(system_id: uuid.UUID, control_id: str, body: RiskIn, request: Request, db: Session = Depends(get_db),
             current: CurrentUser = Depends(require_permission("implementation.write"))) -> dict:
    enforce(request, current, "implementation.write", system_id)
    _check_interaction(db, body.assist)
    a = assignment_for(db, system_id, control_id)
    res = ef.save_risk(db, a, body.model_dump(exclude={"assist"}), current, body.assist.model_dump(), audit.request_meta(request))
    db.commit()
    return {**res, "emass": ef.view(db, a, True)}


class SuggestIn(BaseModel):
    implementation_status: Literal["Planned", "Implemented", "Inherited", "Not Applicable", "Manually Inherited"] | None = None
    mode: Literal["auto", "rules"] = "auto"


PLAN_GROUP = [k for k in ef.PLAN_FIELDS]


async def _ai(svc, ctx: dict, status: str, fields: list[str], user_id) -> tuple[list[dict], uuid.UUID]:
    res = await svc.run("control.emass_fields_suggest", "1.0.0",
                        {"context": json.dumps(ctx, default=str), "status": status, "fields": ", ".join(fields),
                         "enums": json.dumps({k: v for k, v in ef.ENUMS.items() if k in fields})}, actor_user_id=user_id)
    return [s.model_dump() for s in res.output.suggestions], res.interaction_id


@router.post("/systems/{system_id}/workbench/controls/{control_id}/emass/suggest")
async def suggest(system_id: uuid.UUID, control_id: str, body: SuggestIn, request: Request, db: Session = Depends(get_db),
                  current: CurrentUser = Depends(require_permission("implementation.write"))) -> dict:
    """Suggestions only – nothing is saved. AI when configured and enabled, deterministic rules otherwise (or on AI failure)."""
    from app.services.ai.service import get_ai_service
    from app.services.rmf import AI_DEFAULTS, get_setting

    enforce(request, current, "implementation.write", system_id)
    s = get_system(db, system_id)
    a = assignment_for(db, system_id, control_id)
    status = body.implementation_status or ef.emass_status(a, ef.fields_for(db, a))
    if status == "Inherited":
        return {"source": "none", "suggestions": [], "rejected": [], "note": "Inherited controls take their values from the providing system – nothing to suggest"}
    ctx = ef.grounding(db, s, a)
    fields = [k for k in ef.REQUIRED[status]] + [k for k in ef.PLAN_FIELDS if k not in ef.REQUIRED[status] and status in ("Planned", "Implemented")
                                                  and k in ("control_designation", "estimated_completion_date", "responsible_entities")] + ef.RISK_FIELDS
    fields = list(dict.fromkeys(fields))
    svc = get_ai_service()
    enabled = get_setting(db, current.user.org_id, "ai", AI_DEFAULTS)["use_cases"].get("control.emass_fields_suggest", True)
    note, items, iid, src = None, [], None, "rules"
    if body.mode == "auto" and svc.configured and enabled:
        from app.services.ai.service import AIOutputTruncatedError
        try:
            try:
                items, iid = await _ai(svc, ctx, status, fields, current.user.id)
            except AIOutputTruncatedError:
                half = [k for k in fields if k in ef.PLAN_FIELDS], [k for k in fields if k in ef.RISK_FIELDS]
                items, iid = await _ai(svc, ctx, status, half[0], current.user.id)
                more, iid = await _ai(svc, ctx, status, half[1], current.user.id)
                items += more
            src = "ai"
        except Exception as exc:  # noqa: BLE001 – any AI failure falls back to the deterministic rules
            note = f"AI unavailable ({type(exc).__name__}: {str(exc)[:160]}) – deterministic suggestions shown instead"
    elif body.mode == "auto":
        note = "AI is not configured or this use case is disabled – deterministic suggestions shown (no AI)"
    if src == "rules":
        items = ef.rule_suggestions(ctx, status)
    ok, rejected = ef.clean_suggestions([i for i in items if i.get("field") in fields], status)
    audit.record_now(action="ai.emass_fields_suggest" if src == "ai" else "emass.rule_suggest", actor_user_id=current.user.id, actor_email=current.user.email,
                     entity_type="control_assignment", entity_id=str(a.id),
                     details={"status": status, "source": src, "interaction_id": str(iid) if iid else None,
                              "fields": [i["field"] for i in ok], "rejected": [i.get("field") for i in rejected], "saved": False})
    return {"source": src, "label": "AI SUGGESTIONS – not saved; accept per field, then Save" if src == "ai" else "Rule-based suggestions (no AI) – not saved",
            "interaction_id": str(iid) if iid else None, "status": status, "suggestions": ok, "rejected": rejected, "note": note,
            "grounding": {"evidence": len(ctx["evidence"]), "open_findings": len(ctx["open_findings"]), "open_poams": len(ctx["open_poams"]),
                          "policies": ctx["policies"], "inheritance": bool(ctx["inheritance"])}}


class BulkIn(BaseModel):
    control_ids: list[str] = Field(min_length=1, max_length=2000)
    fields: dict
    confirm: bool = False


@router.post("/systems/{system_id}/workbench/emass/bulk")
def bulk_set(system_id: uuid.UUID, body: BulkIn, request: Request, db: Session = Depends(get_db),
             current: CurrentUser = Depends(require_permission("implementation.write"))) -> dict:
    enforce(request, current, "implementation.write", system_id)
    if not body.confirm:
        raise HTTPException(422, "Bulk changes need explicit confirmation (confirm=true)")
    if "estimated_completion_date" in body.fields and body.fields["estimated_completion_date"]:
        try:
            body.fields["estimated_completion_date"] = date.fromisoformat(str(body.fields["estimated_completion_date"]))
        except ValueError as exc:
            raise HTTPException(422, "Estimated Completion Date must be YYYY-MM-DD") from exc
    res = ef.bulk(db, get_system(db, system_id), body.control_ids, body.fields, current, audit.request_meta(request))
    db.commit()
    return res


@router.get("/systems/{system_id}/emass/implementation-plan.xlsx")
def plan_xlsx(system_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))):
    enforce(request, current, "system.read", system_id)
    s = get_system(db, system_id)
    audit.record_now(action="emass.plan_exported", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="system", entity_id=str(s.id))
    return Response(ef.xlsx(db, s), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{s.acronym or "system"}-eMASS-formatted-implementation-plan.xlsx"',
                             "X-Compatibility": "eMASS-formatted, compatibility pending human verification"})


@router.get("/systems/{system_id}/emass/implementation-plan/validation")
def plan_validation(system_id: uuid.UUID, request: Request, fmt: str | None = None, db: Session = Depends(get_db),
                    current: CurrentUser = Depends(require_permission("system.read"))):
    enforce(request, current, "system.read", system_id)
    s = get_system(db, system_id)
    rep = ef.validation_report(db, s)
    if fmt == "csv":
        import csv
        import io
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["control", "implementation_status", "missing_required_fields", "narrative_over_2000_chars"])
        for it in rep["items"]:
            w.writerow([it["control"], it["implementation_status"], "; ".join(it["missing"]), "yes" if it["narrative_over_limit"] else ""])
        return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{s.acronym}-emass-validation.csv"'})
    return rep


@router.get("/systems/{system_id}/emass/controls-payload")
def controls_payload(system_id: uuid.UUID, request: Request, control_id: str | None = None, db: Session = Depends(get_db),
                     current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    enforce(request, current, "system.read", system_id)
    s = get_system(db, system_id)
    rs = [r for r in ef.rows(db, s) if not control_id or r["control_id"] == control_id.lower()]
    return {"mock": True, "label": "MOCKED eMASS sync payload – eMASS API field names; no real eMASS is contacted",
            "endpoint": "PUT /api/systems/{systemId}/controls", "systemId": s.emass_id, "body": [ef.api_payload(r) for r in rs],
            "excluded_fields": {"vulnerability_summary": "no eMASS API field (UI only)"}}
