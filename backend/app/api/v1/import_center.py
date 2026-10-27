"""Import Center – ONE place for every system data import. Detection + routing only: each file is sent (by the client) to the
existing pipeline endpoint, and its existing review screen is used. One history across all pipelines, with retry for failed imports."""
import re
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.records import get_system, visible_systems
from app.db import get_db
from app.models import EmassImport, IngestRun, InventoryImport, Policy, System, TrWorkbook
from app.security.deps import CurrentUser, enforce, require_permission
from app.security.rbac import has_permission
from app.services import audit, jobs

router = APIRouter(tags=["import-center"])
MAX_BYTES = 20 * 1024 * 1024

# key → label (eMASS / RMF wording), RMF step, where the data goes, permission, pipeline endpoint, review screen
TYPES: dict[str, dict] = {
    "policy": {"label": "Policy / procedure document", "step": "Implement", "dest": "Policy Auditor → Mapping Review", "perm": "implementation.write",
               "endpoint": "POST /policies", "review": "/policy-auditor/{id}"},
    "ckl": {"label": "STIG Checklist (CKL)", "step": "Assess", "dest": "Evidence processing → STIG results", "perm": "ingest.upload",
            "endpoint": "POST /systems/{system_id}/uploads", "review": "/ingest-runs/{id}"},
    "cklb": {"label": "STIG Checklist (CKLB)", "step": "Assess", "dest": "Evidence processing → STIG results", "perm": "ingest.upload",
             "endpoint": "POST /systems/{system_id}/uploads", "review": "/ingest-runs/{id}"},
    "xccdf": {"label": "SCAP / XCCDF results (incl. ARF)", "step": "Assess", "dest": "Evidence processing → SCAP results", "perm": "ingest.upload",
              "endpoint": "POST /systems/{system_id}/uploads", "review": "/ingest-runs/{id}"},
    "nessus_xml": {"label": "Nessus / ACAS scan (.nessus)", "step": "Assess", "dest": "Evidence processing → vulnerability findings", "perm": "ingest.upload",
                   "endpoint": "POST /systems/{system_id}/uploads", "review": "/ingest-runs/{id}"},
    "nessus_csv": {"label": "ACAS / Nessus CSV export", "step": "Assess", "dest": "Evidence processing → vulnerability findings", "perm": "ingest.upload",
                   "endpoint": "POST /systems/{system_id}/uploads", "review": "/ingest-runs/{id}"},
    "sarif": {"label": "SARIF code scan", "step": "Assess", "dest": "Evidence processing → code findings", "perm": "ingest.upload",
              "endpoint": "POST /systems/{system_id}/uploads", "review": "/ingest-runs/{id}"},
    "test_results": {"label": "eMASS Test Result Import template", "step": "Assess", "dest": "Assess → Test Results workbook", "perm": "ingest.upload",
                     "endpoint": "POST /systems/{system_id}/tr/workbooks", "review": "/test-results"},
    "test_plan": {"label": "Test Plan (eMASS Test Result Import layout)", "step": "Assess", "dest": "Assess → Test Plan", "perm": "ingest.upload",
                  "endpoint": "POST /systems/{system_id}/tr/test-plan/preview", "review": "/test-results"},
    "control_information": {"label": "eMASS Control Information / Implementation Plan", "step": "Implement", "dest": "Control Workbench → eMASS fields review",
                            "perm": "implementation.write", "endpoint": "POST /systems/{system_id}/emass-imports", "review": "/systems/{system_id}/emass-import/{id}"},
    "system_details": {"label": "eMASS System Details", "step": "Prepare", "dest": "System registration / Prepare (review)", "perm": "system.write",
                       "endpoint": "POST /emass-imports", "review": "/systems/{system_id}/emass-import/{id}"},
    "categorization": {"label": "eMASS Categorization", "step": "Categorize", "dest": "Categorize proposal (review)", "perm": "system.write",
                       "endpoint": "POST /emass-imports", "review": "/systems/{system_id}/emass-import/{id}"},
    "slcm": {"label": "eMASS SLCM worksheet", "step": "Select", "dest": "Select S-5 / Monitor – per-control SLCM (review)", "perm": "implementation.write",
             "endpoint": "POST /emass-imports", "review": "/systems/{system_id}/emass-import/{id}"},
    "ppsm": {"label": "eMASS PPSM Boundaries", "step": "Prepare", "dest": "System boundary – PPSM (review)", "perm": "system.write",
             "endpoint": "POST /emass-imports", "review": "/systems/{system_id}/emass-import/{id}"},
    "poam": {"label": "eMASS POA&M", "step": "Assess / Authorize", "dest": "POA&M (review)", "perm": "poam.manage",
             "endpoint": "POST /emass-imports", "review": "/systems/{system_id}/emass-import/{id}"},
    "hwsw": {"label": "eMASS Hardware/Software List", "step": "Prepare", "dest": "System boundary → HW/SW Inventory", "perm": "system.write",
             "endpoint": "POST /systems/{system_id}/inventory/imports", "review": "/inventory"},
}
SUPPORTED = ("Supported: policy documents (.pdf/.docx/.txt), STIG CKL/CKLB, SCAP XCCDF/ARF results, Nessus (.nessus) and ACAS CSV, SARIF, "
             "and eMASS workbooks (Control Information / our Implementation Plan export, System Details, Categorization, SLCM, PPSM, POA&M, "
             "Hardware/Software List, Test Result Import template / Test Plan). Reference data (catalog content, overlays) is imported in Admin.")


def _count_rows(sheets, typ: str) -> int | None:
    from app.services import emass_reports as er
    return er.record_count(sheets, typ)


def detect_file(name: str, data: bytes) -> dict:
    """→ {type, confidence, record_count, candidates, message}. Uses the existing detectors (ingest.detect_format, emass_reports.detect)."""
    from app.services import emass_reports as er
    from app.services.ingest.parsers import ParseError, detect_format
    low = (name or "").lower()
    if not data:
        return {"type": None, "confidence": "none", "message": f"{name}: empty file. {SUPPORTED}"}
    if len(data) > MAX_BYTES:
        return {"type": None, "confidence": "none", "message": f"{name}: larger than 20 MB. {SUPPORTED}"}
    is_pdf = data.lstrip()[:5] == b"%PDF-"
    is_zip = data[:4] == b"PK\x03\x04"
    if is_pdf or (is_zip and b"word/" in data[:300_000]) or low.endswith((".txt", ".md")):
        return {"type": "policy", "confidence": "high" if (is_pdf or is_zip) else "medium", "record_count": None, "candidates": ["policy"]}
    if is_zip or low.endswith((".xlsx", ".xlsm")) or (low.endswith(".csv") and b"Plugin ID" not in data[:4000]):
        try:
            sheets = er.read_sheets(data, name)
        except HTTPException as exc:
            return {"type": None, "confidence": "none", "message": f"{name}: {exc.detail}. {SUPPORTED}"}
        d = er.detect(sheets)
        typ = d.get("type")
        if not typ or d.get("confidence") == "none":
            return {"type": None, "confidence": "none", "message": f"{name}: spreadsheet, but no supported eMASS layout was recognised. {SUPPORTED}"}
        cands = list(dict.fromkeys([typ, *(d.get("candidates") or [])]))
        if typ == "test_results":
            cands.append("test_plan")
        return {"type": typ, "confidence": d.get("confidence"), "record_count": _count_rows(sheets, typ), "candidates": cands,
                "ambiguous": d.get("ambiguous", False), "sheets": d.get("sheets")}
    try:
        fmt = detect_format(name, data)
    except ParseError as exc:
        return {"type": None, "confidence": "none", "message": f"{exc} {SUPPORTED}"}
    n = {"ckl": data.count(b"<VULN>"), "xccdf": len(re.findall(rb"<(?:\w+:)?rule-result\b", data)),
         "nessus_xml": data.count(b"<ReportItem "), "nessus_csv": max(data.count(b"\n") - 1, 0)}.get(fmt)
    return {"type": fmt, "confidence": "high", "record_count": n, "candidates": [fmt]}


def _types_for(current: CurrentUser, system_id) -> list[dict]:
    out = []
    for k, t in TYPES.items():
        ok = system_id is not None and has_permission(current.assignments, t["perm"], current.user.org_id, system_id) if k != "policy" else \
            has_permission(current.assignments, t["perm"], current.user.org_id, system_id)
        out.append({"key": k, **{x: t[x] for x in ("label", "step", "dest", "endpoint")}, "allowed": bool(ok),
                    "reason": None if ok else (f"Your role lacks “{t['perm']}” for this system" if system_id else "Choose a target system first")})
    return out


@router.get("/import-center/types")
def types(system_id: uuid.UUID | None = None, request: Request = None, db: Session = Depends(get_db),
          current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    if system_id:
        enforce(request, current, "system.read", system_id)
        get_system(db, system_id)
    return {"types": _types_for(current, system_id), "supported": SUPPORTED, "reference_data_note": "Reference data imports (catalog content, overlay data) are in Admin."}


@router.post("/import-center/detect")
async def detect(request: Request, file: UploadFile = File(...), system_id: uuid.UUID | None = Form(None), db: Session = Depends(get_db),
                 current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    """Detection only – nothing is stored. The client then sends the file to the type's existing pipeline endpoint."""
    if system_id:
        enforce(request, current, "system.read", system_id)
        get_system(db, system_id)
    data = await file.read()
    d = detect_file(file.filename or "upload", data)
    t = TYPES.get(d.get("type") or "")
    allowed = {x["key"]: x for x in _types_for(current, system_id)}
    return {"file_name": file.filename, "size_bytes": len(data), **d, **({k: t[k] for k in ("label", "step", "dest", "endpoint")} if t else {}),
            "allowed": allowed.get(d.get("type") or "", {}).get("allowed", False), "reason": allowed.get(d.get("type") or "", {}).get("reason"),
            "candidate_labels": {c: TYPES[c]["label"] for c in d.get("candidates") or [] if c in TYPES}}


def _st(s: str | None) -> str:
    s = (s or "").lower()
    return ("queued" if s in ("queued", "received", "not_analyzed") else "processing" if s in ("processing", "running", "generating", "analyzing", "detecting")
            else "needs review" if s in ("review", "detected", "mapped", "needs_review", "ready") else "applied" if s in ("applied", "imported", "analyzed", "processed", "generated", "completed", "current")
            else "failed" if s in ("failed", "error", "rejected") else "reverted" if s == "reverted" else "discarded" if s == "discarded" else s)


def history_rows(db: Session, org_id, sids: list, system_scoped: bool = False) -> list[dict]:
    from app.services import emass_reports as er
    names = {s.id: s.acronym or s.name for s in db.scalars(select(System).where(System.id.in_(sids)))}
    rows = []
    ssids = {str(x) for x in sids}
    for i in db.scalars(select(EmassImport).where(EmassImport.org_id == org_id, (EmassImport.system_id.in_(sids)) | (EmassImport.system_id.is_(None))).limit(500)):
        ctx_sid = (i.detected or {}).get("context_system_id")
        if i.system_id is None and system_scoped and ctx_sid not in ssids:
            continue  # system tab: only uploads made in this system's context
        i_sid = i.system_id or (uuid.UUID(ctx_sid) if ctx_sid in ssids else None)
        rows.append({"kind": "emass", "id": str(i.id), "type": i.report_type, "label": f"eMASS {er.TYPES.get(i.report_type, i.report_type)}", "file_name": i.file_name,
                     "sha256": i.sha256, "user": i.uploaded_by_email, "at": i.created_at, "status": _st(i.status), "raw_status": i.status, "system_id": i_sid,
                     "counts": i.counts or {}, "link": f"/systems/{i_sid}/emass-import/{i.id}" if i_sid else f"/emass-import/{i.id}"})
    for r in db.scalars(select(IngestRun).where(IngestRun.system_id.in_(sids)).limit(500)):
        rows.append({"kind": "ingest", "id": str(r.id), "type": r.file_format, "label": TYPES.get(r.file_format or "", {}).get("label", r.file_format or "Evidence upload"),
                     "file_name": r.file_name, "sha256": r.sha256, "user": None, "at": r.received_at, "status": _st(r.status), "raw_status": r.status,
                     "system_id": r.system_id, "counts": {"records": r.total, "mapped": r.mapped, "unmapped": r.unmapped}, "error": "; ".join(r.errors or [])[:300] or None,
                     "link": f"/ingest-runs/{r.id}"})
    for w in db.scalars(select(TrWorkbook).where(TrWorkbook.org_id == org_id, TrWorkbook.system_id.in_(sids)).limit(500)):
        rows.append({"kind": "tr", "id": str(w.id), "type": "test_results", "label": TYPES["test_results"]["label"], "file_name": w.file_name, "sha256": w.sha256,
                     "user": w.uploaded_by, "at": w.created_at, "status": _st(w.status), "raw_status": w.status, "system_id": w.system_id, "counts": w.counts or {},
                     "error": w.error, "link": "/test-results"})
    for m in db.scalars(select(InventoryImport).where(InventoryImport.org_id == org_id, InventoryImport.system_id.in_(sids)).limit(500)):
        rows.append({"kind": "inventory", "id": str(m.id), "type": "hwsw", "label": TYPES["hwsw"]["label"], "file_name": m.file_name, "sha256": m.sha256,
                     "user": m.uploaded_by, "at": m.created_at, "status": _st(m.status), "raw_status": m.status, "system_id": m.system_id, "counts": m.counts or {},
                     "error": m.error, "link": "/inventory"})
    ssid = {str(x) for x in sids}
    for p in db.scalars(select(Policy).where(Policy.org_id == org_id, Policy.file_name.is_not(None)).limit(500)):
        ps = [x for x in (p.system_ids or []) if str(x) in ssid]
        if p.system_ids and not ps:
            continue
        rows.append({"kind": "policy", "id": str(p.id), "type": "policy", "label": TYPES["policy"]["label"], "file_name": p.file_name, "sha256": p.sha256,
                     "user": None, "at": p.created_at, "status": _st(p.analysis_status), "raw_status": p.analysis_status, "system_id": ps[0] if ps else None,
                     "counts": {"version": p.version}, "link": f"/policy-auditor/{p.id}"})
    for r in rows:
        r["system"] = names.get(uuid.UUID(str(r["system_id"]))) if r["system_id"] else None
        r["system_id"] = str(r["system_id"]) if r["system_id"] else None
        r["at"] = r["at"].isoformat() if r["at"] else None
        r["retry"] = r["status"] == "failed" and r["kind"] in RETRY
    return sorted(rows, key=lambda r: r["at"] or "", reverse=True)


@router.get("/import-center/history")
def history(system_id: uuid.UUID | None = None, request: Request = None, db: Session = Depends(get_db),
            current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    """Every import of every type for the system (or every system the user can see in the organization)."""
    if system_id:
        enforce(request, current, "system.read", system_id)
        sids = [get_system(db, system_id).id]
    else:
        sids = [s.id for s in visible_systems(db, current)]
    return {"items": history_rows(db, current.user.org_id, sids, system_scoped=bool(system_id))}


RETRY = {"ingest": (IngestRun, "ingest.process", "run_id", "status", "queued", "ingest.upload"),
         "tr": (TrWorkbook, "tr.detect", "workbook_id", "status", "queued", "ingest.upload"),
         "inventory": (InventoryImport, "inventory.import", "import_id", "status", "queued", "system.write"),
         "policy": (Policy, "policy.analyze", "policy_id", "analysis_status", "queued", "implementation.write")}


@router.post("/import-center/retry/{kind}/{item_id}")
def retry(kind: str, item_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    """Re-queue a FAILED import on its existing pipeline job (the stored original is re-processed; nothing is re-uploaded)."""
    if kind not in RETRY:
        raise HTTPException(404, "This import type cannot be retried here")
    model, job_type, key, col, new, perm = RETRY[kind]
    obj = db.get(model, item_id)
    sid = None
    if obj is not None:
        sid = obj.system_id if hasattr(obj, "system_id") else ((obj.system_ids or [None])[0])
        org = obj.org_id if hasattr(obj, "org_id") else db.get(System, obj.system_id).org_id
        if org != current.user.org_id:
            obj = None
    if obj is None:
        raise HTTPException(404, "Import not found")
    if sid:
        enforce(request, current, perm, uuid.UUID(str(sid)))
    if _st(getattr(obj, col)) != "failed":
        raise HTTPException(409, "Only a failed import can be retried")
    setattr(obj, col, new)
    payload = {key: str(obj.id)}
    if kind == "inventory":
        payload["actor_email"] = current.user.email
    job = jobs.enqueue(db, job_type, payload, requested_by=current.user.id)
    audit.record(db, action="import.retried", actor_user_id=current.user.id, actor_email=current.user.email, entity_type=kind, entity_id=str(obj.id),
                 details={"job_id": str(job.id), "job_type": job_type}, **audit.request_meta(request))
    db.commit()
    return {"id": str(obj.id), "kind": kind, "status": "queued", "job_id": str(job.id)}
