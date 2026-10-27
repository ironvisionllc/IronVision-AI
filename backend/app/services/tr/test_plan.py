"""Import Test Plan (eMASS Test Results / Assessment Procedures): synchronous preview + import of accepted rows into a TR workbook.
Reuses the TR parser (xlsx.detect), CCI/AP matching (service.match) and the shared eMASS report detection; nothing is saved by preview."""
import csv
import io

from fastapi import HTTPException
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ControlAssignment, System, TrRow, TrWorkbook
from app.services import emass_reports as er
from app.services.tr import service as trs
from app.services.tr import xlsx

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 10_000
REQUIRED = {"ap_acronym": "AP Acronym", "cci": "CCI"}
LABELS = {"control_acronym": "Control Acronym", "ap_acronym": "AP Acronym", "cci": "CCI", "cci_definition": "CCI Definition",
          "assessment_procedures": "Assessment Procedures", "compliance_status": "Compliance Status", "date_tested": "Date Tested",
          "tested_by": "Tested By", "test_results": "Test Results"}


def _csv_to_xlsx(data: bytes) -> bytes:
    try:
        rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise HTTPException(422, "Could not read the CSV file (UTF-8, comma-separated expected)") from exc
    if len(rows) > MAX_ROWS + 40:
        raise HTTPException(422, f"More than {MAX_ROWS:,} rows – split the file")
    wb = Workbook()
    ws = wb.active
    ws.title = "Template"
    for r, vals in enumerate(rows, start=1):
        for c, v in enumerate(vals, start=1):
            if v != "":
                cell = ws.cell(r, c, v)
                cell.data_type = "s"  # never a formula
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def normalise(file_name: str, data: bytes) -> tuple[str, bytes, str]:
    """→ (stored file name, xlsx bytes, format label). Rejects unsupported formats with a clear message."""
    low = (file_name or "").lower()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File is larger than 10 MB")
    if low.endswith(".csv"):
        return file_name.rsplit(".", 1)[0] + " (from CSV).xlsx", _csv_to_xlsx(data), "CSV (same columns as the eMASS Test Result Import template)"
    if low.endswith((".xlsx", ".xlsm")):
        if data[:2] != b"PK":
            raise HTTPException(422, "The file is not a valid Excel workbook (.xlsx/.xlsm)")
        return file_name, data, "eMASS Test Result Import template (.xlsx)"
    ext = "." + low.rsplit(".", 1)[-1] if "." in low else "(no extension)"
    raise HTTPException(422, f"Unsupported format {ext} – upload the eMASS Test Result Import template (.xlsx/.xlsm) or a CSV with the same columns "
                             "(AP Acronym, CCI, optional Control Acronym / Assessment Procedures)")


def preview(db: Session, s: System, file_name: str, data: bytes) -> dict:
    name, xdata, fmt = normalise(file_name, data)
    sheets = er.read_sheets(xdata, "x.xlsx")
    det_type = er.detect(sheets)
    if det_type["type"] not in (None, "test_results") and "test_results" not in det_type["candidates"]:
        raise HTTPException(422, f"This looks like an eMASS {er.TYPES[det_type['type']]} export, not a Test Plan – use “Import from eMASS” for it")
    try:
        det = xlsx.detect(xdata, min_score=2)
    except ValueError as exc:
        raise HTTPException(422, f"{exc}. Required columns: AP Acronym, CCI.") from exc
    except Exception as exc:  # noqa: BLE001 – corrupt workbook
        raise HTTPException(422, f"Could not read the workbook: {exc.__class__.__name__}") from exc
    missing = [lab for k, lab in REQUIRED.items() if k not in det["roles"]]
    if missing:
        raise HTTPException(422, {"message": f"Missing required column(s): {', '.join(missing)}", "missing_columns": missing,
                                  "found_columns": [c["header"] for c in det["columns"]]})
    if len(det["rows"]) > MAX_ROWS:
        raise HTTPException(422, f"More than {MAX_ROWS:,} rows – split the file")
    cmap, catalog = trs._ref(db)
    assigned = set(db.scalars(select(ControlAssignment.control_id).where(ControlAssignment.system_id == s.id)))
    existing = {(r.ap_acronym, r.cci_id): (w.file_name, w.version, r.row_number) for r, w in db.execute(
        select(TrRow, TrWorkbook).join(TrWorkbook, TrRow.workbook_id == TrWorkbook.id)
        .where(TrWorkbook.system_id == s.id, TrWorkbook.status != "failed"))}
    accepted, rejected, seen = [], [], {}
    for r in det["rows"]:
        ap, cci_raw = r.get("ap_acronym"), r.get("cci")
        m = trs.match(cmap, catalog, ap, cci_raw, r.get("control_acronym"))
        base = {"row": r["row"], "ap_acronym": ap, "cci": m["cci_id"] or cci_raw, "control": (m["control_id"] or "").upper() or r.get("control_acronym")}
        key = (ap, m["cci_id"])
        reason = None
        if not ap:
            reason = "AP Acronym is empty (required)"
        elif not trs.parse_ap(ap)[0]:
            reason = f"Invalid AP Acronym “{ap}” – expected e.g. AC-2.1 or AC-2(1).3"
        elif not cci_raw:
            reason = "CCI is empty (required)"
        elif not m["cci_id"]:
            reason = f"Invalid CCI “{cci_raw}” – expected e.g. CCI-000015"
        elif m["match_status"] == "unmatched":
            reason = m["match_reason"]
        elif m["control_id"] and m["control_id"] not in assigned:
            reason = f"{m['control_id'].upper()} is not selected for this system (unmatched control)"
        elif key in seen:
            reason = f"Duplicate procedure: same AP Acronym and CCI as row {seen[key]}"
        elif key in existing:
            f, v, rn = existing[key]
            reason = f"Duplicate procedure: already in Test Results workbook “{f}” v{v}, row {rn}"
        seen.setdefault(key, r["row"])
        if reason:
            rejected.append({**base, "reason": reason})
        else:
            accepted.append({**base, "match_status": m["match_status"], "note": m["match_reason"]})
    return {"file_name": name, "format": fmt, "detected": {"type": "test_results", "label": er.label("test_results"), "confidence": det_type["confidence"]},
            "sheet": det["sheet"], "header_row": det["header_row"],
            "columns": [{"col": c["col"], "header": c["header"], "role": LABELS.get(c["role"] or "")} for c in det["columns"]],
            "optional_missing": [lab for k, lab in LABELS.items() if k not in REQUIRED and k not in det["roles"] and k in ("control_acronym", "assessment_procedures")],
            "accepted": accepted, "rejected": rejected, "counts": {"rows": len(det["rows"]), "accepted": len(accepted), "rejected": len(rejected),
                                                                  "needs_mapping_review": sum(1 for a in accepted if a["match_status"] == "ambiguous")},
            "_xlsx": xdata}


def import_accepted(db: Session, s: System, file_name: str, data: bytes, actor) -> tuple[TrWorkbook, dict]:
    p = preview(db, s, file_name, data)
    if not p["accepted"]:
        raise HTTPException(422, {"message": "No row can be imported – fix the rejected rows and upload again", "rejected": p["rejected"]})
    wb = trs.import_workbook(db, s, p["file_name"], p.pop("_xlsx"), actor, enqueue=False)
    trs.detect_and_match(db, wb, min_score=2)
    drop = {r["row"] for r in p["rejected"]}
    if drop:
        db.query(TrRow).filter(TrRow.workbook_id == wb.id, TrRow.row_number.in_(drop)).delete(synchronize_session=False)
        db.flush()
    wb.detection = {**(wb.detection or {}), "test_plan_import": {"accepted": len(p["accepted"]), "rejected": p["rejected"], "format": p["format"]}}
    trs.refresh_counts(db, wb)
    return wb, p
