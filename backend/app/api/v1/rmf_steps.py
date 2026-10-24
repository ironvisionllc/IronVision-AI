"""RMF 7-step API: step status + next action, Prepare roles, Categorize (FIPS 199 / CNSSI 1253), Select (baseline/overlays/tailoring)."""
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.records import get_system, to_dict
from app.db import get_db
from app.models import Overlay, TailoringDecision, User
from app.security.deps import CurrentUser, get_current_user, require_permission
from app.services import audit
from app.services import rmf_steps as rs
from app.services.counts import system_counts

router = APIRouter(tags=["rmf-steps"])


def _err(fn, *a):
    try:
        return fn(*a)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("/reference/rmf")
def rmf_reference(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    users = db.scalars(select(User).where(User.org_id == current.user.org_id).order_by(User.display_name))
    return {"key_roles": [{"key": k, "label": l, "help": h, "required": r, "registration": k not in rs.NOT_AT_REGISTRATION} for k, l, h, r in rs.KEY_ROLES],
            "users": [{"id": str(u.id), "display_name": u.display_name, "email": u.email} for u in users],
            "emass_note": rs.EMASS,
            "mission_criticality": [{"value": v, "label": l, "help": h} for v, l, h in rs.MISSION_CRITICALITY],
            "system_types": [{"value": v, "help": h} for v, h in rs.SYSTEM_TYPES],
            "acquisition_categories": [{"value": v, "help": h} for v, h in rs.ACQUISITION_CATEGORIES],
            "authorization_types": [{"value": v, "help": h} for v, h in rs.AUTHORIZATION_TYPES],
            "environments": [{"value": v, "label": l, "cloud": c} for v, l, c in rs.ENVIRONMENTS]}


@router.get("/reference/role-matrix")
def role_matrix(_: CurrentUser = Depends(get_current_user)) -> dict:
    from app.security.rbac import PERMISSIONS, ROLE_PERMISSIONS, ROLES

    return {"roles": [{"key": k, "label": v} for k, v in ROLES.items()],
            "actions": [{"permission": p, "action": rs.ACTION_LABELS.get(p, d), "description": d,
                         "roles": [r for r in ROLES if p in ROLE_PERMISSIONS.get(r, set())]} for p, d in PERMISSIONS.items()]}


@router.get("/reference/info-types")
def info_types(_: CurrentUser = Depends(get_current_user)) -> dict:
    return rs.info_type_catalog()


class CategorizeIn(BaseModel):
    mode: str = Field("fips199", pattern="^(fips199|cnssi1253)$")
    information_types: list[dict] = []
    cia: dict | None = None


@router.post("/reference/categorize")
def categorize_preview(body: CategorizeIn, _: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    return rs.categorize(body.mode, body.information_types, body.cia)


@router.get("/systems/{system_id}/rmf-steps")
def rmf_steps(system_id: uuid.UUID, db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    return rs.steps(db, get_system(db, system_id))


class RolesIn(BaseModel):
    roles: dict


@router.get("/systems/{system_id}/prepare")
def prepare_view(system_id: uuid.UUID, db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    return {"roles": rs.role_holders(db, get_system(db, system_id))}


@router.put("/systems/{system_id}/prepare")
def prepare_save(system_id: uuid.UUID, body: RolesIn, db: Session = Depends(get_db),
                 current: CurrentUser = Depends(require_permission("system.write"))) -> dict:
    out = _err(rs.save_roles, db, get_system(db, system_id), body.roles, current.user)
    db.commit()
    return {"roles": out}


class CategorizationIn(CategorizeIn):
    nss_determination: str | None = Field(None, pattern="^(yes|no|unsure)$", description="Is this a National Security System? (44 U.S.C. §3552; SP 800-59)")
    classified_information: str | None = Field(None, pattern="^(yes|no|unknown)$", description="Does the system, by intent and design, process classified information?")
    rationale: str | None = Field(None, max_length=4000)
    mission_criticality: str | None = Field(None, max_length=50)
    system_type: str | None = Field(None, max_length=80)
    acquisition_category: str | None = Field(None, max_length=40)
    authorization_type: str | None = Field(None, max_length=50)
    operating_environment: str | None = Field(None, max_length=100)
    environment_detail: dict | None = None
    processes_pii: bool | None = None
    pta: dict | None = None


def apply_categorization(s, body: CategorizationIn) -> dict:
    calc = rs.categorize(body.mode, body.information_types, body.cia)
    if calc["errors"]:
        raise ValueError("; ".join(calc["errors"]))
    if not calc["rows"]:
        raise ValueError("Pick at least one information type from the SP 800-60 catalog")
    s.categorization_mode = body.mode
    s.information_types = [{k: r[k] for k in ("id", "name", "c", "i", "a", "rationale", "adjusted")} for r in calc["rows"]]
    s.confidentiality_impact, s.integrity_impact, s.availability_impact = calc["c"], calc["i"], calc["a"]
    from app.services.rmf_accuracy import validate_environment

    validate_environment(body.operating_environment or s.operating_environment, body.environment_detail if body.environment_detail is not None else s.environment_detail,
                         body.mode, body.classified_information or (s.applicability_flags or {}).get("classified_information"))
    s.categorization = (calc["overall"] or calc["baseline"] or "").lower() or None
    s.categorization_detail = {"steps": calc["steps"], "security_category": calc["security_category"], "baseline": calc["baseline"],
                               "baseline_selection": calc.get("baseline_selection")}
    if body.nss_determination:
        s.nss_determination = body.nss_determination
    if body.classified_information:
        s.applicability_flags = {**(s.applicability_flags or {}), "classified_information": body.classified_information}
    for f in ("mission_criticality", "system_type", "acquisition_category", "authorization_type", "operating_environment", "environment_detail",
              "processes_pii", "pta"):
        v = getattr(body, f)
        if v is not None:
            setattr(s, f, v)
    return calc


@router.get("/systems/{system_id}/categorization")
def categorization_view(system_id: uuid.UUID, db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    s = get_system(db, system_id)
    keep = ("categorization_mode", "information_types", "confidentiality_impact", "integrity_impact", "availability_impact", "categorization",
            "categorization_detail", "mission_criticality", "system_type", "acquisition_category", "authorization_type", "operating_environment",
            "environment_detail", "processes_pii", "pta", "baseline_key", "include_privacy", "nss_determination", "applicability_flags")
    out = {k: getattr(s, k) for k in keep}
    from app.services import cnssi1253

    return {**out, "privacy_prompt": cnssi1253.privacy_prompt(db, s)}


@router.put("/systems/{system_id}/categorization")
def categorization_save(system_id: uuid.UUID, body: CategorizationIn, db: Session = Depends(get_db),
                        current: CurrentUser = Depends(require_permission("system.write"))) -> dict:
    s = get_system(db, system_id)
    before = {"categorization": s.categorization, "c": s.confidentiality_impact, "i": s.integrity_impact, "a": s.availability_impact}
    from app.services import rmf_accuracy as ra

    approved = ra.latest(db, s.id, "approved")
    keep = {f: getattr(s, f) for f in ("categorization_mode", "information_types", "confidentiality_impact", "integrity_impact", "availability_impact",
                                       "categorization", "categorization_detail")}
    calc = _err(apply_categorization, s, body)
    rec = ra.record(db, s, calc, body.mode, body.nss_determination or s.nss_determination, body.rationale, current.user.email)
    calc = {**calc, "revision": rec.revision, "record_status": rec.status}
    if approved and rec.status == "pending_reapproval":  # an approved categorization is not overwritten until re-approved
        for f, v in keep.items():
            setattr(s, f, v)
    audit.record(db, action="system.categorized", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="system",
                 entity_id=str(s.id), before=before, after={"mode": body.mode, "c": calc["c"], "i": calc["i"], "a": calc["a"],
                                                            "information_types": [r["id"] for r in calc["rows"]], "processes_pii": s.processes_pii})
    db.commit()
    needs = []
    if calc["baseline"] and rs.LEVEL.get(calc["baseline"], 0) > rs.LEVEL.get(s.baseline_key or "", 0):
        needs.append(f"raise the baseline from {s.baseline_key} to {calc['baseline']}")
    if s.processes_pii and not s.include_privacy:
        needs.append("apply the privacy baseline")
    return {"calculation": calc, "select_actions": needs}


@router.get("/systems/{system_id}/select")
def select_view(system_id: uuid.UUID, db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    s = get_system(db, system_id)
    rs.ensure_overlays(db)
    db.commit()
    ovs = {}
    from app.services.sandbox import has_demo_data

    demo = has_demo_data(db, s.org_id)
    for o in db.scalars(select(Overlay).where(Overlay.is_active.is_(True), Overlay.group_key.is_(None)).order_by(Overlay.overlay_key, Overlay.created_at)):
        if o.is_synthetic and not demo and o.overlay_key not in (s.overlay_keys or []):
            continue
        if o.structure_only and o.overlay_key.split("-")[1] in ("privacy", "classified", "space"):
            continue
        ovs[o.overlay_key] = o
    from app.services.overlays import OVERLAY_META, groups_view
    from app.services.rmf_accuracy import overlay_availability, review_flags

    groups = groups_view(db, s)
    for g in groups:
        g["available"], g["unavailable_reason"] = overlay_availability(s, g["group"])
        g["meta"] = OVERLAY_META.get(g["group"])
    groups = [g for g in groups if g["available"] or any(v.get("applied") for v in g.get("variants", [])) or g["group"] in ("privacy", "classified")]

    return {"baseline_key": s.baseline_key, "framework": s.categorization_mode, "review_flags": review_flags(s),
            "cnssi": _cnssi_view(db, s), "privacy_prompt": _privacy_prompt(db, s),
            "classified_information": (s.applicability_flags or {}).get("classified_information"), "recommended_baseline": (s.categorization or "").lower() or None, "include_privacy": s.include_privacy,
            "processes_pii": s.processes_pii, "overlay_keys": s.overlay_keys or [], "counts": system_counts(db, s),
            "overlay_groups": groups,
            "overlays": [{"key": o.overlay_key, "title": o.title, "version": o.version, "structure_only": o.structure_only, "description": o.description,
                          "add": len(o.controls_add), "remove": len(o.controls_remove), "synthetic": o.is_synthetic,
                          "applied": o.overlay_key in (s.overlay_keys or [])} for o in ovs.values()],
            "tailoring": [to_dict(t) for t in db.scalars(select(TailoringDecision).where(TailoringDecision.system_id == s.id, TailoringDecision.overlay_key.is_(None))
                                                         .order_by(TailoringDecision.created_at.desc()))]}


@router.get("/systems/{system_id}/select/overlays/{overlay_key}")
def select_overlay_controls(system_id: uuid.UUID, overlay_key: str, db: Session = Depends(get_db),
                            _: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    from app.services.overlays import overlay_controls

    return _err(overlay_controls, db, get_system(db, system_id), overlay_key)


class BaselineIn(BaseModel):
    baseline_key: str = Field(pattern="^(low|moderate|high)$")
    include_privacy: bool = False


def _privacy_prompt(db: Session, s) -> dict | None:
    from app.services import cnssi1253

    return cnssi1253.privacy_prompt(db, s)


def _cnssi_view(db: Session, s) -> dict | None:
    from app.services import cnssi1253

    if s.categorization_mode != "cnssi1253":
        return None
    src = cnssi1253.data()["source"]
    tri = cnssi1253.system_trigraph(s)
    gaps = [r["control_id"] for r in cnssi1253.rows() if r.get("not_in_catalog")]
    unc = cnssi1253.uncovered_catalog_ids(db)
    st = cnssi1253.approval_state(db, s)
    applied = cnssi1253.applied(s)
    return {"trigraph": tri, "applied": applied, "proposal": cnssi1253.proposal(db, s), "approval": st,
            "categorization_status": (f"Approved (revision {st['approved_revision']})" if applied and st["approved_trigraph"] == applied
                                      else "Pending categorization approval"),
            "source": f"{src['title']}, {src['date']} ({src['copy']}), SHA-256 {src['sha256'][:12]}…",
            "rule": cnssi1253.data()["selection_rule"],
            "sme_review": [f"SME review required: {len(unc)} Rev 5 catalog controls are not in the CNSSI 1253 (2022) tables, so they are not selected – "
                           + ", ".join(unc)] if unc else [],
            "not_in_catalog": gaps}


class CnssiAcceptIn(BaseModel):
    to: str = Field(pattern="^[LMH]-[LMH]-[LMH]$")


class AdoptItem(BaseModel):
    control_id: str = Field(max_length=50)
    parameter_id: str = Field(max_length=100)


class AdoptIn(BaseModel):
    items: list[AdoptItem] = []
    control_id: str | None = Field(None, max_length=50)  # bulk: every mapped CNSSI value of this control
    family: str | None = Field(None, pattern="^[a-z]{2}$")  # bulk: every mapped CNSSI value of this family's assigned controls
    confirm_conflicts: bool = False


@router.post("/systems/{system_id}/parameters/cnssi-adopt")
def adopt_cnssi_values(system_id: uuid.UUID, body: AdoptIn, db: Session = Depends(get_db),
                       current: CurrentUser = Depends(require_permission("system.write"))):
    from fastapi.responses import JSONResponse

    from app.models import ControlAssignment
    from app.services import cnssi_params

    s = get_system(db, system_id)
    items = [(i.control_id.lower(), i.parameter_id) for i in body.items]
    if body.control_id or body.family:
        m = cnssi_params.mapping(db)
        have = set(db.scalars(select(ControlAssignment.control_id).where(ControlAssignment.system_id == s.id)))
        ids = [body.control_id.lower()] if body.control_id else sorted(c for c in have if c.split("-")[0] == body.family)
        items += [(c, p) for c in ids if c in have for p in (m.get(c) or {}).get("odps", {})]
    if not items:
        raise HTTPException(422, "No CNSSI 1253 values to adopt for this selection")
    try:
        out = cnssi_params.adopt(db, s, items, body.confirm_conflicts, current.user)
    except cnssi_params.Conflict as c:
        return JSONResponse(status_code=409, content={"detail": "Confirm the conflicts to replace them", "conflicts": c.items})
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    db.commit()
    return out


@router.post("/systems/{system_id}/parameters/cnssi-adopt/{event_id}/undo")
def undo_cnssi_values(system_id: uuid.UUID, event_id: uuid.UUID, db: Session = Depends(get_db),
                      current: CurrentUser = Depends(require_permission("system.write"))) -> dict:
    from app.services import cnssi_params

    out = _err(cnssi_params.undo, db, get_system(db, system_id), event_id, current.user)
    db.commit()
    return out


@router.post("/systems/{system_id}/select/cnssi-baseline")
def accept_cnssi_baseline(system_id: uuid.UUID, body: CnssiAcceptIn, db: Session = Depends(get_db),
                          current: CurrentUser = Depends(require_permission("system.write"))) -> dict:
    from app.services import cnssi1253

    s = get_system(db, system_id)
    p = cnssi1253.proposal(db, s)
    if p and p["to"] == body.to and p["blocked_reason"]:  # audited refusal: categorization change not yet approved
        audit.record(db, action="system.cnssi_baseline_accept_blocked", actor_user_id=current.user.id, actor_email=current.user.email,
                     entity_type="system", entity_id=str(s.id), after={"to": p["to"], "kind": p["kind"], "reason": p["blocked_reason"]})
        db.commit()
        raise HTTPException(422, p["blocked_reason"])
    out = _err(cnssi1253.accept, db, s, current.user, body.to)
    db.commit()
    return {**out, "counts": system_counts(db, s)}


@router.post("/systems/{system_id}/select/baseline")
def select_baseline(system_id: uuid.UUID, body: BaselineIn, db: Session = Depends(get_db),
                    current: CurrentUser = Depends(require_permission("system.write"))) -> dict:
    s = get_system(db, system_id)
    out = _err(rs.apply_baseline, db, s, body.baseline_key, body.include_privacy, current.user)
    db.commit()
    return {**out, "counts": system_counts(db, s)}


class OverlayIn(BaseModel):
    overlay_key: str = Field(max_length=100)
    apply: bool


@router.post("/systems/{system_id}/select/overlay")
def select_overlay(system_id: uuid.UUID, body: OverlayIn, db: Session = Depends(get_db),
                   current: CurrentUser = Depends(require_permission("system.write"))) -> dict:
    s = get_system(db, system_id)
    out = _err(rs.set_overlay, db, s, body.overlay_key, body.apply, current.user)
    db.commit()
    return {**out, "counts": system_counts(db, s)}


class TailorIn(BaseModel):
    action: str = Field(pattern="^(add|remove)$")
    control_ids: list[str] = Field(min_length=1, max_length=1500)
    justification: str = Field("", max_length=4000)


@router.post("/systems/{system_id}/select/tailor")
def select_tailor(system_id: uuid.UUID, body: TailorIn, db: Session = Depends(get_db),
                  current: CurrentUser = Depends(require_permission("system.write"))) -> dict:
    s = get_system(db, system_id)
    out = _err(rs.tailor, db, s, body.action, body.control_ids, body.justification, current.user)
    db.commit()
    return {**out, "counts": system_counts(db, s)}


@router.post("/overlays/{overlay_key}/import", status_code=201)
async def overlay_import(overlay_key: str, version: str = Form(..., min_length=1, max_length=20), file: UploadFile = File(...),
                         db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("admin.content.load"))) -> dict:
    ov = _err(rs.import_overlay_csv, db, overlay_key, version, await file.read(), current.user)
    db.commit()
    return {"overlay_key": ov.overlay_key, "version": ov.version, "add": len(ov.controls_add), "remove": len(ov.controls_remove)}


@router.post("/overlays/import-reference", status_code=201)
async def overlay_import_reference(file: UploadFile = File(...), db: Session = Depends(get_db),
                                   current: CurrentUser = Depends(require_permission("admin.content.load"))) -> dict:
    import json

    from app.services.overlays import load_reference, record_import

    try:
        data = json.loads((await file.read()).decode("utf-8-sig"))
        if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get("overlays"), dict):
            raise ValueError("Expected the derived overlay data file (schema 1) produced by scripts/cnssi1253/parse_overlays.py")
        created = load_reference(db, data, current.user.email)
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(status_code=422, detail=f"Could not import: {e}") from e
    record_import(db, current.user, created, file.filename or "upload")
    db.commit()
    return {"created": created, "message": f"{len(created)} overlay variant(s) loaded" if created else "Already loaded – no new versions"}


@router.get("/systems/{system_id}/authorize")
def authorize_view(system_id: uuid.UUID, db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    s = get_system(db, system_id)
    return {"checklist": rs.authorization_checklist(db, s), "authorization_status": s.authorization_status,
            "authorization_type": s.authorization_type, "authorization_expiration": s.authorization_expiration}


@router.get("/systems/{system_id}/traceability")
def traceability(system_id: uuid.UUID, mapped_only: bool = False, policy: str | None = None, fmt: str | None = None, db: Session = Depends(get_db),
                 _: CurrentUser = Depends(require_permission("system.read"))):
    """Policy → control → CCI → statement → evidence → findings → POA&M per assigned control; optional mapped-only / per-policy filter."""
    from app.services import policy_coverage as pc

    s = get_system(db, system_id)
    idx = pc.index(db, s)
    titles = {str(p.id): p.title for p in pc.applicable_policies(db, s)}
    want = {x for x in (policy or "").split(",") if x} or None
    rows = []
    for r in rs.traceability(db, s):
        e = idx.get(r["control_id"])
        if (mapped_only and not (e and (e["mapped"] or e["proposed"]))) or (want and not pc.matches(e, None, want, None)):
            continue
        cc = [c for c in (e or {}).get("rows", []) if c.requirement_type == "cci"]
        r["policies"] = [{"id": i, "title": titles.get(i), "status": "mapped" if i in e["mapped"] else "proposed"} for i in sorted((e["mapped"] | e["proposed"]) if e else [])]
        r["ccis"] = {"total": len({c.requirement_id for c in cc}), "met": len({c.requirement_id for c in cc if pc.effective(c) == "met"})}
        rows.append(r)
    if fmt == "csv":
        import csv
        import io

        from fastapi.responses import Response

        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["policy", "control_id", "ccis_met", "ccis_total", "origin", "implementation_status", "statement", "evidence", "open_findings"])
        for r in rows:
            w.writerow(["; ".join(p["title"] or "" for p in r["policies"]), r["control_id"].upper(), r["ccis"]["met"], r["ccis"]["total"], r.get("origin"),
                        r.get("implementation_status"), r.get("statement"), r.get("evidence"), r.get("open_findings")])
        return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{s.acronym or "system"}-traceability.csv"'})
    return rows
