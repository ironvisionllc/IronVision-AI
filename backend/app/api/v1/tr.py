"""eMASS Test Result (TR) template import, mapping, generation, SCA review and export (RMF step 5 · Assess)."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.v1.records import get_system
from app.db import get_db
from app.models import Cci, Control, TrAnalysis, TrExport, TrRow, TrWorkbook
from app.security.deps import CurrentUser, get_current_user, require_object_permission, require_permission
from app.services import audit, jobs, sod
from app.services.tr import service as trs

router = APIRouter(tags=["test-results"])
SCA_ONLY = "Only an assessor (SCA role) can approve or set a Compliance Status. Your role can prepare and review Test Results but not make the determination."


def _wb(db: Session, wid: uuid.UUID, current: CurrentUser) -> TrWorkbook:
    wb = db.get(TrWorkbook, wid)
    if wb is None or wb.org_id != current.user.org_id:
        raise HTTPException(404, "Test Result workbook not found")
    return wb


def _can(db: Session, current: CurrentUser, perm: str, system_id) -> bool:
    from app.security.rbac import has_permission

    return has_permission(current.assignments, perm, current.user.org_id, system_id)


def _real(current: CurrentUser):
    """Real person behind the request (a sandbox persona is operated by its real user)."""
    return current.operator.id if current.operator else current.user.id


def _out(wb: TrWorkbook) -> dict:
    return {"id": str(wb.id), "system_id": str(wb.system_id), "file_name": wb.file_name, "version": wb.version, "sha256": wb.sha256, "status": wb.status,
            "error": wb.error, "counts": wb.counts or {}, "definition": wb.definition, "detection": wb.detection, "uploaded_by": wb.uploaded_by,
            "created_at": wb.created_at.isoformat(), "generated_at": wb.generated_at.isoformat() if wb.generated_at else None}


def _row(r: TrRow, current: CurrentUser | None = None, sandbox: bool = False) -> dict:
    return {"id": str(r.id), "row": r.row_number, "added": r.added, "control_acronym": r.control_acronym, "ap_acronym": r.ap_acronym, "cci_id": r.cci_id,
            "control_id": r.control_id, "match_status": r.match_status, "match_reason": r.match_reason, "proposed": r.proposed or {}, "sources": r.sources or [],
            "flags": r.flags or [], "state": r.state, "final": r.final, "decided_by": r.decided_by, "justification": r.justification,
            "decided_at": r.decided_at.isoformat() if r.decided_at else None, "last_exported_at": r.last_exported_at.isoformat() if r.last_exported_at else None,
            "prepared_by": r.prepared_by, "sod_lock": sod.evaluate(r.prepared_by, current, sandbox, "edited or prepared")[0] if current else None}


@router.post("/systems/{system_id}/tr/workbooks", status_code=201)
async def upload(system_id: uuid.UUID, request: Request, file: UploadFile = File(...), db: Session = Depends(get_db),
                 current: CurrentUser = Depends(require_permission("ingest.upload"))) -> dict:
    s = get_system(db, system_id)
    data = await file.read()
    if not (file.filename or "").lower().endswith((".xlsx", ".xlsm")) or data[:2] != b"PK":
        raise HTTPException(422, "Upload the eMASS Test Result Import Template as an .xlsx workbook")
    wb = trs.import_workbook(db, s, file.filename, data, current.user)
    audit.record(db, action="tr.workbook_uploaded", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="tr_workbook",
                 entity_id=str(wb.id), after={"file_name": wb.file_name, "sha256": wb.sha256, "version": wb.version}, **audit.request_meta(request))
    db.commit()
    return _out(wb)


def _plan_perm(current: CurrentUser, system_id: uuid.UUID) -> None:
    if not _can(None, current, "ingest.upload", system_id):
        from app.security.rbac import ROLE_PERMISSIONS, ROLES
        raise HTTPException(403, {"code": "missing_permission", "permission": "ingest.upload",
                                  "message": "Importing a Test Plan needs the ingest.upload permission – your role can view Test Results but not import them",
                                  "roles": [r for r in ROLES if "ingest.upload" in ROLE_PERMISSIONS.get(r, set())]})


@router.post("/systems/{system_id}/tr/test-plan/preview")
async def test_plan_preview(system_id: uuid.UUID, file: UploadFile = File(...), db: Session = Depends(get_db),
                            current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    """Import Test Plan – step 1: recognise the format, validate columns and rows, list accepted/rejected rows. Nothing is saved."""
    from app.services.tr import test_plan

    _plan_perm(current, system_id)
    p = test_plan.preview(db, get_system(db, system_id), file.filename or "", await file.read(test_plan.MAX_BYTES + 1))
    p.pop("_xlsx")
    return p


@router.post("/systems/{system_id}/tr/test-plan/import", status_code=201)
async def test_plan_import(system_id: uuid.UUID, request: Request, file: UploadFile = File(...), db: Session = Depends(get_db),
                           current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    """Import Test Plan – step 2: create a Test Results workbook from the accepted rows (results stay blank until the SCA approves)."""
    from app.services.tr import test_plan

    _plan_perm(current, system_id)
    wb, p = test_plan.import_accepted(db, get_system(db, system_id), file.filename or "", await file.read(test_plan.MAX_BYTES + 1), current.user)
    audit.record(db, action="tr.test_plan_imported", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="tr_workbook",
                 entity_id=str(wb.id), after={"file_name": wb.file_name, "sha256": wb.sha256, "accepted": p["counts"]["accepted"],
                                              "rejected_rows": [r["row"] for r in p["rejected"]]}, **audit.request_meta(request))
    db.commit()
    return {**_out(wb), "preview": {k: v for k, v in p.items() if k != "_xlsx"}}


@router.get("/systems/{system_id}/tr/workbooks")
def list_workbooks(system_id: uuid.UUID, db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("system.read"))) -> list[dict]:
    s = get_system(db, system_id)
    return [_out(w) for w in db.scalars(select(TrWorkbook).where(TrWorkbook.system_id == s.id).order_by(TrWorkbook.created_at.desc()))]


@router.get("/tr/workbooks/{wid}")
def workbook(wid: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    wb = _wb(db, wid, current)
    added = db.scalars(select(TrRow.added).where(TrRow.workbook_id == wb.id).distinct()).all()
    return {**_out(wb), "export_mode": "blank" if added == [True] else "prepopulated", "can_approve": _can(db, current, "assessment.perform", wb.system_id),
            "exports": [{"id": str(e.id), "version": e.version, "file_name": e.file_name, "sha256": e.sha256, "exported_by": e.exported_by, "counts": e.counts,
                         "created_at": e.created_at.isoformat(), "template_version": e.template_version, "validation_ok": (e.verification or {}).get("ok"),
                         "mode": (e.verification or {}).get("mode", "prepopulated"), "mode_label": (e.verification or {}).get("mode_label"),
                         "changed_cells": len((e.verification or {}).get("changed_cells", [])),
                         "sandbox_same_person_rows": (e.verification or {}).get("sandbox_same_person_rows", 0)}
                        for e in db.scalars(select(TrExport).where(TrExport.workbook_id == wb.id).order_by(TrExport.version.desc()))]}


@router.get("/tr/workbooks/{wid}/rows")
def rows(wid: uuid.UUID, state: str | None = None, match: str | None = None, family: str | None = None, q: str | None = None, page: int = 1, size: int = 50,
         db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    wb = _wb(db, wid, current)
    st = select(TrRow).where(TrRow.workbook_id == wb.id)
    if state:
        st = st.where(TrRow.state.in_(state.split(",")))
    if match:
        st = st.where(TrRow.match_status.in_(match.split(",")))
    if family:
        st = st.where(TrRow.control_id.ilike(f"{family.lower()}-%"))
    if q:
        st = st.where(or_(TrRow.ap_acronym.ilike(f"%{q}%"), TrRow.cci_id.ilike(f"%{q}%"), TrRow.control_id.ilike(f"%{q}%")))
    items = list(db.scalars(st.order_by(TrRow.row_number)))
    size = min(max(size, 10), 500)
    sandbox = sod.is_sandbox(db, wb.org_id)
    return {"total": len(items), "items": [_row(r, current, sandbox) for r in items[(page - 1) * size: page * size]], "counts": wb.counts}


class MappingIn(BaseModel):
    roles: dict[str, str]


@router.put("/tr/workbooks/{wid}/mapping")
def set_mapping(wid: uuid.UUID, body: MappingIn, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_object_permission("ingest.upload", "TrWorkbook", "wid"))) -> dict:
    wb = _wb(db, wid, current)
    if not _can(db, current, "ingest.upload", wb.system_id):
        raise HTTPException(403, "Your role cannot change Test Result column mappings")
    cols = {c["col"] for c in wb.detection["columns"]}
    bad = [c for c in body.roles.values() if c not in cols]
    if bad or set(body.roles.values()) & set(wb.detection.get("readonly_cols", [])) & {body.roles.get(r) for r in ("compliance_status", "date_tested", "tested_by", "test_results")}:
        raise HTTPException(422, "Result columns must be existing columns outside the read-only “Provided by eMASS” sections")
    trs.detect_and_match(db, wb, body.roles)
    audit.record(db, action="tr.mapping_changed", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="tr_workbook", entity_id=str(wb.id),
                 after={"roles": body.roles}, **audit.request_meta(request))
    db.commit()
    return _out(wb)


class ResolveIn(BaseModel):
    control_id: str
    cci_id: str | None = None


@router.post("/tr/workbooks/{wid}/rows/{rid}/resolve")
def resolve(wid: uuid.UUID, rid: uuid.UUID, body: ResolveIn, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_object_permission("ingest.upload", "TrWorkbook", "wid"))) -> dict:
    wb = _wb(db, wid, current)
    if not _can(db, current, "ingest.upload", wb.system_id):
        raise HTTPException(403, "Your role cannot resolve Test Result row mappings")
    r = db.get(TrRow, rid)
    if r is None or r.workbook_id != wb.id:
        raise HTTPException(404, "Row not found")
    before = {"control_id": r.control_id, "cci_id": r.cci_id, "match_status": r.match_status}
    r.control_id, r.cci_id = body.control_id.lower(), trs.norm_cci(body.cci_id) or r.cci_id
    r.match_status, r.match_reason = "resolved", f"Confirmed manually by {current.user.email}"
    r.flags = [f for f in (r.flags or []) if f != "needs_mapping_review"]
    trs.refresh_counts(db, wb)
    audit.record(db, action="tr.row_resolved", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="tr_row", entity_id=str(r.id),
                 before=before, after={"control_id": r.control_id, "cci_id": r.cci_id}, **audit.request_meta(request))
    db.commit()
    return _row(r)


class TemplateIn(BaseModel):
    name: str


@router.post("/tr/workbooks/{wid}/template")
def save_template(wid: uuid.UUID, body: TemplateIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require_object_permission("ingest.upload", "TrWorkbook", "wid"))) -> dict:
    wb = _wb(db, wid, current)
    t = trs.save_template(db, wb, body.name, current.user)
    db.commit()
    return {"id": str(t.id), "name": t.name, "version": t.version}


class GenerateIn(BaseModel):
    populate: bool = False


@router.post("/tr/workbooks/{wid}/generate", status_code=202)
def generate(wid: uuid.UUID, body: GenerateIn, db: Session = Depends(get_db), current: CurrentUser = Depends(require_object_permission("ingest.upload", "TrWorkbook", "wid"))) -> dict:
    wb = _wb(db, wid, current)
    if not _can(db, current, "ingest.upload", wb.system_id):
        raise HTTPException(403, "Your role cannot generate Test Results")
    wb.status = "generating"
    job = jobs.enqueue(db, "tr.generate", {"workbook_id": str(wb.id), "populate": body.populate}, requested_by=current.user.id)
    db.commit()
    return {"ok": True, "job_id": str(job.id)}


class TesterIn(BaseModel):
    tested_by: str = ""
    date_tested: date | None = None


class DecideIn(BaseModel):
    action: str = Field(description="`approve` (SCA only) or `edit`")
    row_ids: list[uuid.UUID]
    justification: str = ""
    use_suggestion: bool = Field(False, description="approve: use the evidence suggestion as the SCA's Compliance Status")
    status: str | None = Field(None, description="approve: the SCA's Compliance Status (must be in the template vocabulary)")
    values: dict | None = Field(None, description="edit: {\"test_results\": str, \"compliance_status\": str (SCA only)}. "
                                                   "approve: only {\"test_results\": str} – the SCA's final Test Results text, saved with the approval")
    tested_by: str = Field("", description="approve: actual tester for the batch (required unless per_row)")
    date_tested: date | None = Field(None, description="approve: actual test date for the batch, not in the future (required unless per_row)")
    per_row: dict[str, TesterIn] = Field({}, description="approve: row_id → {tested_by, date_tested}")


def _testers(body: DecideIn, limit: int) -> dict:
    out = {}
    for rid in map(str, body.row_ids):
        t = body.per_row.get(rid) or TesterIn(tested_by=body.tested_by, date_tested=body.date_tested)
        if not t.tested_by.strip() or t.date_tested is None:
            raise HTTPException(422, "Enter both “Date tested” and “Tested by” for every row you approve – they are the actual tester and test date, "
                                     "not the approver or today")
        if t.date_tested > date.today():
            raise HTTPException(422, "“Date tested” cannot be in the future")
        if len(t.tested_by.strip()) > limit:
            raise HTTPException(422, f"“Tested by” exceeds the template's {limit}-character limit")
        out[rid] = {"tested_by": t.tested_by, "date_tested": t.date_tested}
    return out


@router.post("/tr/workbooks/{wid}/decide")
def decide(wid: uuid.UUID, body: DecideIn, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_object_permission("system.read", "TrWorkbook", "wid"))) -> dict:
    wb = _wb(db, wid, current)
    sets_status = body.action == "approve" or bool((body.values or {}).get("compliance_status"))
    if sets_status and not _can(db, current, "assessment.perform", wb.system_id):
        raise HTTPException(403, SCA_ONLY)
    if not sets_status and not (_can(db, current, "assessment.perform", wb.system_id) or _can(db, current, "implementation.write", wb.system_id)):
        raise HTTPException(403, "Your role cannot edit Test Results")
    if len(body.justification.strip()) < 5 and (body.action == "edit" or len(body.row_ids) > 1):
        raise HTTPException(422, "Add a justification (at least 5 characters) – it is kept in the audit log")
    rs = list(db.scalars(select(TrRow).where(TrRow.workbook_id == wb.id, TrRow.id.in_(body.row_ids))))
    meta = audit.request_meta(request)
    if body.action == "approve":
        extra = set(body.values or {}) - {"test_results"}
        if extra:
            raise HTTPException(422, f"On approve only values.test_results can be sent (got {', '.join(sorted(extra))}); set the Compliance Status with `status`")
        text = (body.values or {}).get("test_results")
        if text is not None and len(text) > ((wb.definition.get("limits") or {}).get("test_results") or 4000):
            raise HTTPException(422, "Test Results exceed the template's character limit")
        before = {r.id: r.state for r in rs}
        testers = _testers(body, (wb.definition.get("limits") or {}).get("tested_by") or 150)
        sandbox = sod.is_sandbox(db, wb.org_id)
        ok, blocked, details = [], [], {}
        for r in rs:
            why, det = sod.evaluate(r.prepared_by, current, sandbox, "edited or prepared")
            if why:
                blocked.append({"row": r.row_number, "reason": why})
            else:
                ok.append(r)
                details[str(r.id)] = det
        if blocked and not ok:
            raise HTTPException(403, blocked[0]["reason"])
        res = trs.approve(db, wb, ok, current.user, body.justification, body.use_suggestion, body.status, testers, text, details)
        res["skipped"] = blocked + res["skipped"]
        for r in ok:
            if r.row_number in res["approved"]:
                audit.record(db, action="tr.row_approved", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="tr_row", entity_id=str(r.id),
                             before={"state": before[r.id]}, after={**r.final, "justification": body.justification, "workbook_id": str(wb.id),
                                                                    "approver": current.user.email, "approver_real_user": str(_real(current)),
                                                                    "tester": r.final["tested_by"], "test_date": r.final["date_tested"]},
                             details=details.get(str(r.id)), **meta)
    elif body.action == "edit":
        try:
            for r in rs:
                b = dict(r.final or {})
                trs.edit(db, wb, r, body.values or {}, current.user, body.justification)
                r.prepared_by = sod.identity(current)
                audit.record(db, action="tr.row_edited", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="tr_row", entity_id=str(r.id),
                             before=b, after={**r.final, "justification": body.justification}, **meta)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        res = {"edited": [r.row_number for r in rs], "skipped": []}
    else:
        raise HTTPException(422, "action must be approve or edit")
    db.commit()
    counts = trs.refresh_counts(db, wb)   # after the commit, so they reflect this action
    db.commit()
    return {**res, "counts": counts}


@router.post("/tr/workbooks/{wid}/export")
def export(wid: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_object_permission("system.read", "TrWorkbook", "wid"))) -> dict:
    wb = _wb(db, wid, current)
    if not _can(db, current, "system.read", wb.system_id):
        raise HTTPException(403, "Your role cannot export Test Results")
    try:
        e = trs.export(db, wb, current.user)
    except ValueError as ex:
        raise HTTPException(409, str(ex)) from ex
    audit.record(db, action="tr.exported", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="tr_export", entity_id=str(e.id),
                 after={"workbook_id": str(wb.id), "version": e.version, "sha256": e.sha256, "counts": e.counts, "template_version": e.template_version,
                        "evidence_ids": e.evidence_ids, "changed_cells": len(e.verification["changed_cells"])}, **audit.request_meta(request))
    db.commit()
    return {"id": str(e.id), "version": e.version, "file_name": e.file_name, "sha256": e.sha256, "counts": e.counts, "verification": e.verification}


def _export(db, eid, current) -> TrExport:
    e = db.get(TrExport, eid)
    if e is None or db.get(TrWorkbook, e.workbook_id).org_id != current.user.org_id:
        raise HTTPException(404, "Export not found")
    return e


@router.get("/tr/exports/{eid}/download")
def download(eid: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> Response:
    from app.services.storage.base import get_storage

    e = _export(db, eid, current)
    return Response(get_storage().get(e.storage_key), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{e.file_name}"'})


@router.get("/tr/exports/{eid}/validation-report")
def validation_report(eid: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> Response:
    import json

    e = _export(db, eid, current)
    rep = {"export": e.file_name, "version": e.version, "sha256": e.sha256, "exported_by": e.exported_by, "exported_at": e.created_at.isoformat(), **e.verification,
           "human_required": ["Open the file in Microsoft Excel – no repair prompt", "Import into eMASS (Assessment → Test Result Import)", "Spot-check 3 rows in eMASS"]}
    return Response(json.dumps(rep, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{e.file_name.replace(".xlsx", "")}_validation_report.json"'})


@router.get("/tr/lookup")
def lookup(q: str, db: Session = Depends(get_db), _: CurrentUser = Depends(get_current_user)) -> dict:
    ql = q.strip().lower()
    ctl = list(db.scalars(select(Control.control_id).where(Control.control_id.ilike(f"{ql}%")).distinct().limit(15)))
    ccis = list(db.execute(select(Cci.cci_id, Cci.definition).where(Cci.cci_id.ilike(f"%{ql}%")).limit(15)))
    return {"controls": ctl, "ccis": [{"cci_id": c, "definition": (d or "")[:140]} for c, d in ccis]}


class AnalyzeIn(BaseModel):
    row_ids: list[uuid.UUID] = []
    all_matched: bool = False


@router.post("/tr/workbooks/{wid}/analyze", status_code=202)
def analyze(wid: uuid.UUID, body: AnalyzeIn, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_object_permission("system.read", "TrWorkbook", "wid"))) -> dict:
    """Evidence analysis as a worker job: one row (on demand) or in bulk. Read-only for the row; nothing is written to Test Results."""
    wb = _wb(db, wid, current)
    if not any(_can(db, current, p, wb.system_id) for p in ("assessment.perform", "implementation.write", "ingest.upload")):
        raise HTTPException(403, "Your role cannot run evidence analysis")
    q = select(TrRow.id).where(TrRow.workbook_id == wb.id, TrRow.match_status.notin_(("ambiguous", "unmatched")))
    ids = [str(i) for i in db.scalars(q if body.all_matched else q.where(TrRow.id.in_(body.row_ids)))]
    if not ids:
        raise HTTPException(422, "No mapped rows selected – resolve the control/CCI mapping first")
    job = jobs.enqueue(db, "tr.analyze", {"workbook_id": str(wb.id), "row_ids": ids, "actor_id": str(current.user.id)}, requested_by=current.user.id)
    audit.record(db, action="tr.analysis_requested", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="tr_workbook",
                 entity_id=str(wb.id), after={"rows": len(ids), "job_id": str(job.id)}, **audit.request_meta(request))
    db.commit()
    return {"ok": True, "job_id": str(job.id), "rows": len(ids)}


def _row_of(db, wb, rid) -> TrRow:
    r = db.get(TrRow, rid)
    if r is None or r.workbook_id != wb.id:
        raise HTTPException(404, "Row not found")
    return r


@router.get("/tr/workbooks/{wid}/rows/{rid}/analysis")
def get_analysis(wid: uuid.UUID, rid: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    from app.services.tr import analysis

    wb = _wb(db, wid, current)
    r = _row_of(db, wb, rid)
    hist = list(db.scalars(select(TrAnalysis).where(TrAnalysis.row_id == r.id).order_by(TrAnalysis.created_at.desc())))
    return {"latest": analysis.out(hist[0]) if hist else None, "history": len(hist)}


class UseAnalysisIn(BaseModel):
    model_config = ConfigDict(extra="forbid")   # compliance_status / tested_by / date_tested are rejected (422)
    analysis_id: uuid.UUID
    text: str
    justification: str = ""


@router.post("/tr/workbooks/{wid}/rows/{rid}/use-analysis")
def use_analysis(wid: uuid.UUID, rid: uuid.UUID, body: UseAnalysisIn, request: Request, db: Session = Depends(get_db),
                 current: CurrentUser = Depends(require_object_permission("system.read", "TrWorkbook", "wid"))) -> dict:
    """Assessor clicks “Use this text”: only Test Results changes, attributed as AI-assisted. An approved row needs SCA re-approval."""
    wb = _wb(db, wid, current)
    if not (_can(db, current, "assessment.perform", wb.system_id) or _can(db, current, "implementation.write", wb.system_id)):
        raise HTTPException(403, "Your role cannot edit Test Results")
    r = _row_of(db, wb, rid)
    a = db.get(TrAnalysis, body.analysis_id)
    if a is None or a.row_id != r.id:
        raise HTTPException(404, "Analysis not found for this row")
    text = body.text.strip()
    if not text or len(text) > ((wb.definition.get("limits") or {}).get("test_results") or 4000):
        raise HTTPException(422, "Test Results text is empty or exceeds the template's character limit")
    before = {"final": dict(r.final or {}), "state": r.state}
    r.final = {**(r.final or {}), "test_results": text,
               "ai_assisted": {"analysis_id": str(a.id), "mode": a.mode, "provider": a.provider, "model": a.model, "prompt_version": a.prompt_version,
                               "edited_by_user": text != (a.output.get("explanation") or "").strip(), "applied_by": current.user.email}}
    r.state, r.decided_by, r.decided_at = "edited", current.user.email, trs.now()
    r.prepared_by = sod.identity(current)
    r.justification = body.justification or "Applied evidence-analysis text"
    trs.refresh_counts(db, wb)
    audit.record(db, action="tr.ai_text_applied", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="tr_row", entity_id=str(r.id),
                 before=before, after={"final": r.final, "state": r.state}, **audit.request_meta(request))
    db.commit()
    return _row(r)
