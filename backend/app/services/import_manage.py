"""Manage imported data: per-import view of what an applied eMASS import created/changed (prior → imported → current) and selective
restore / clear / delete with a 30-day undo. Builds on the import's own provenance (apply_results[].undo) and the existing write paths
(emass_fields.save_plan / save_risk, new draft Implementation versions, emass_migration.revert); every change is audited."""
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ControlAssignment, EmassImport, Implementation, PpsmEntry
from app.services import audit
from app.services import emass_fields as ef

UNDO_DAYS = 30
LABEL = {**{k: v[0] for k, v in ef.FIELD_META.items()}, "implementation_narrative": "Implementation statement"}


def destination(field: str) -> str:
    if field == "implementation_narrative":
        return "Implementation statement"
    if field in ef.RISK_FIELDS:
        return "Risk Assessment"
    if field in ef.SLCM:
        return "SLCM (Continuous Monitoring)"
    return "Implementation Plan"


def _cur_values(db: Session, a: ControlAssignment) -> dict:
    from app.services.emass_import import _current
    return _current(db, a)


def _state(db: Session, imp: EmassImport) -> dict:
    return dict((imp.report or {}).get("manage_state") or {})


REG_REQUIRED = {"name"}
REG_LABEL = {"name": "Name", "acronym": "Acronym", "emass_id": "eMASS ID", "description": "Description", "organization_name": "Organization",
             "mission_owner": "Mission owner"}


def _reg_entries(db: Session, imp: EmassImport, state: dict) -> list[dict]:
    """"Register a new system" path: registration values pre-filled from the file, shown as imported (clear / restore)."""
    from app.models import System
    s = db.get(System, imp.system_id) if imp.system_id else None
    out = []
    for k, v in ((imp.report or {}).get("registration_prefill") or {}).items():
        if s is None or not hasattr(s, k):
            continue
        eid, cur = f"reg|{k}", getattr(s, k)
        st = state.get(eid, "applied")
        out.append({"id": eid, "key": "registration", "record": "System", "control_id": None, "destination": "Registration (System Details)", "field": k,
                    "label": REG_LABEL.get(k, k), "prior": None, "imported": v, "current": cur, "created": True, "state": st,
                    "changed_since_import": st == "applied" and cur != v,
                    "actions": ["restore"] + ([] if k in REG_REQUIRED else ["clear"]) if (st == "applied" or cur != v) else []})
    return out


def entries(db: Session, imp: EmassImport) -> list[dict]:
    """One entry per imported field (Control Information) or per record (PPSM / SLCM / Categorization); registration pre-fill fields."""
    out, state, reverted = [], _state(db, imp), set((imp.report or {}).get("reverted_keys") or [])
    out += _reg_entries(db, imp, state)
    cache: dict[str, dict] = {}
    for r in (imp.report or {}).get("apply_results") or []:
        u = r.get("undo")
        if not u:
            continue
        if u["kind"] == "control_info":
            a = db.get(ControlAssignment, uuid.UUID(u["assignment_id"]))
            if a is None:
                continue
            cur = cache.setdefault(u["assignment_id"], _cur_values(db, a))
            for k, imported in u["imported"].items():
                eid = f"{r['key']}|{k}"
                prior = u["before"].get(k)
                created = prior in (None, "", [])
                st = state.get(eid, "applied")
                actions = ["restore"] + ([] if k == "implementation_status" else ["clear"]) + (["delete"] if created else [])
                out.append({"id": eid, "key": r["key"], "record": r.get("control"), "control_id": a.control_id, "destination": destination(k),
                            "field": k, "label": LABEL.get(k, k), "prior": prior, "imported": imported, "current": cur.get(k),
                            "created": created, "state": st, "changed_since_import": st == "applied" and cur.get(k) != imported,
                            "actions": actions if st == "applied" else []})
        else:
            eid = f"{r['key']}|*"
            created = u.get("before") is None
            st = "restored" if r.get("key") in reverted else state.get(eid, "applied")
            dest = {"ppsm": "PPSM", "slcm": "SLCM (Continuous Monitoring)", "strategy": "Continuous Monitoring Strategy"}.get(u["kind"], "Categorization")
            out.append({"id": eid, "key": r["key"], "record": r.get("control"), "control_id": None, "destination": dest, "field": "*",
                        "label": "Whole record", "prior": u.get("before"), "imported": r.get("applied"), "current": None, "created": created,
                        "state": st, "changed_since_import": False,
                        "actions": ([] if st != "applied" else (["delete"] if created and u["kind"] == "ppsm" else ["restore"]))})
    return out


def _write_ci(db: Session, a: ControlAssignment, field: str, value, current, meta: dict, src: dict) -> None:
    """Set one Control Information field through the normal save paths (validation, audit, status mapping)."""
    if field == "implementation_narrative":
        latest = db.scalar(select(func.max(Implementation.version)).where(Implementation.assignment_id == a.id)) or 0
        for old in db.scalars(select(Implementation).where(Implementation.assignment_id == a.id, Implementation.is_current.is_(True))):
            old.is_current = False
        db.add(Implementation(assignment_id=a.id, version=latest + 1, narrative=value or "", implementation_status=a.implementation_status,
                              author_id=current.user.id, review_status="draft"))  # a new draft version → the normal review applies again
        audit.record(db, action="implementation.saved", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="control_assignment",
                     entity_id=str(a.id), after={"version": latest + 1, "narrative": (value or "")[:500], "review_status": "draft"}, details=src, **meta)
        return
    cur = _cur_values(db, a)
    if field in ef.RISK_FIELDS:
        ef.save_risk(db, a, {field: value}, current, {"source": "import_manage", "fields": []}, meta, src)
    else:
        status = value if field == "implementation_status" else cur["implementation_status"]
        vals = {k: cur.get(k) for k in ef.PLAN_FIELDS}
        if field != "implementation_status":
            vals[field] = value
        from datetime import date
        if isinstance(vals.get("estimated_completion_date"), str):
            vals["estimated_completion_date"] = date.fromisoformat(vals["estimated_completion_date"])
        ef.save_plan(db, a, status, vals, current, {"source": "import_manage", "fields": []}, meta, src, enforce_required=False)
    for impl in db.scalars(select(Implementation).where(Implementation.assignment_id == a.id, Implementation.is_current.is_(True),
                                                        Implementation.review_status == "approved")):
        impl.needs_reconsideration = True  # approved statement: the change must be re-reviewed


def _flag_decision(db: Session, imp: EmassImport, e: dict, current) -> None:
    """Record-level revert of data under an AO categorization / ISSM-approved strategy: the decision stays, flagged for re-review."""
    from app.models import CategorizationRecord, IscmStrategy
    from app.services import import_data as idm
    why = f"Imported data reverted via Manage imported data ({imp.file_name}) – the decision is kept and needs re-review"
    if e["destination"] == "Categorization":
        rec = db.scalar(select(CategorizationRecord).where(CategorizationRecord.system_id == imp.system_id, CategorizationRecord.status == "approved")
                        .order_by(CategorizationRecord.revision.desc()))
        if rec:
            idm.flag(db, imp.org_id, imp.system_id, "categorization", rec.id, f"AO-approved categorization rev {rec.revision}", why, "emass", imp.id, None)
    if e["destination"] == "Continuous Monitoring Strategy":
        st = db.scalar(select(IscmStrategy).where(IscmStrategy.system_id == imp.system_id))
        if st and st.status == "approved":
            idm.flag(db, imp.org_id, imp.system_id, "iscm_strategy", st.id, f"ISSM-approved ISCM strategy v{st.version}", why, "emass", imp.id, None)


def act(db: Session, imp: EmassImport, current, meta: dict, ids: list[str], action: str, force: bool = False) -> dict:
    """Restore previous value / clear field / delete created data for the selected entries. Per-item result; failures don't stop others."""
    from app.services import emass_migration as em
    if action not in ("restore", "clear", "delete"):
        raise HTTPException(422, "action must be restore, clear or delete")
    by = {e["id"]: e for e in entries(db, imp)}
    undo_raw = {f"{r['key']}": r["undo"] for r in (imp.report or {}).get("apply_results") or [] if r.get("undo")}
    src = {"source": f"Manage imported data – {imp.file_name}", "import_id": str(imp.id), "import_sha256": imp.sha256, "action": action}
    state, results, log = _state(db, imp), [], []
    for eid in dict.fromkeys(ids):
        e = by.get(eid)
        if e is None:
            results.append({"id": eid, "ok": False, "error": "Not part of this import"})
            continue
        if action not in e["actions"]:
            results.append({"id": eid, "ok": False, "error": f"'{action}' is not possible here (state: {e['state']})"})
            continue
        if e["changed_since_import"] and not force:
            results.append({"id": eid, "ok": False, "error": f"Changed after the import (now: {e['current']!r}) – confirm to overwrite", "needs_confirm": True})
            continue
        try:
            with db.begin_nested():
                if e["key"] == "registration":
                    from app.models import System
                    s = db.get(System, imp.system_id)
                    prev = getattr(s, e["field"])
                    setattr(s, e["field"], e["imported"] if action == "restore" else None)
                    audit.record(db, action="system.updated", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="system",
                                 entity_id=str(s.id), before={e["field"]: prev}, after={e["field"]: getattr(s, e["field"])}, details=src, **meta)
                    log.append({"id": eid, "prev": prev, "system_field": e["field"]})
                    state[eid] = "applied" if action == "restore" else "cleared"
                    results.append({"id": eid, "ok": True, "state": state[eid]})
                    continue
                if e["field"] == "*":
                    if e["destination"] == "PPSM" and action == "delete":
                        row = db.get(PpsmEntry, uuid.UUID(undo_raw[e["key"]]["id"]))
                        snap = {c.key: getattr(row, c.key) for c in PpsmEntry.__table__.columns if c.key not in ("created_at", "updated_at")} if row else None
                    else:
                        snap = None
                    _flag_decision(db, imp, e, current)
                    done = em.revert(db, imp, current, meta, [e["key"]])
                    if not done:
                        raise HTTPException(409, ((imp.report or {}).get("revert_skipped") or [{}])[-1].get("reason") or "Could not be reverted")
                    log.append({"id": eid, "prev": None, "ppsm_row": {k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in snap.items()} if snap else None})
                else:
                    a = db.get(ControlAssignment, uuid.UUID(undo_raw[e["key"]]["assignment_id"]))
                    value = e["prior"] if action == "restore" else None
                    _write_ci(db, a, e["field"], value, current, meta, src)
                    log.append({"id": eid, "prev": e["current"], "assignment_id": str(a.id), "field": e["field"]})
                state[eid] = {"restore": "restored", "clear": "cleared", "delete": "deleted"}[action]
            results.append({"id": eid, "ok": True, "state": state[eid]})
        except HTTPException as exc:
            results.append({"id": eid, "ok": False, "error": str(exc.detail)})
    op = None
    if log:
        op = {"op_id": uuid.uuid4().hex[:12], "action": action, "at": datetime.now(UTC).isoformat(), "by": current.user.email,
              "entries": log, "undone": False}
        audit.record(db, action=f"import_data.{action}", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="emass_import",
                     entity_id=str(imp.id), after={"entries": [x["id"] for x in log], "op_id": op["op_id"]},
                     details={"file_name": imp.file_name, "sha256": imp.sha256, "failed": [r for r in results if not r["ok"]][:50]}, **meta)
    imp.report = {**(imp.report or {}), "manage_state": state, "manage_log": [*((imp.report or {}).get("manage_log") or []), *([op] if op else [])]}
    return {"results": results, "op": op, "ok": sum(r["ok"] for r in results), "failed": sum(not r["ok"] for r in results)}


def undo(db: Session, imp: EmassImport, current, meta: dict, op_id: str) -> dict:
    """Undo one manage operation within 30 days: field values put back, deleted PPSM rows re-created (record-level restores: re-import)."""
    ops = list((imp.report or {}).get("manage_log") or [])
    op = next((o for o in ops if o["op_id"] == op_id), None)
    if op is None:
        raise HTTPException(404, "Operation not found")
    if op["undone"]:
        raise HTTPException(409, "Already undone")
    if datetime.now(UTC) - datetime.fromisoformat(op["at"]) > timedelta(days=UNDO_DAYS):
        raise HTTPException(409, f"Undo is available for {UNDO_DAYS} days")
    state, done, skipped = _state(db, imp), [], []
    src = {"source": f"Manage imported data – undo {op_id}", "import_id": str(imp.id), "import_sha256": imp.sha256}
    for x in op["entries"]:
        if x.get("system_field"):
            from app.models import System
            setattr(db.get(System, imp.system_id), x["system_field"], x["prev"])
        elif x.get("field"):
            _write_ci(db, db.get(ControlAssignment, uuid.UUID(x["assignment_id"])), x["field"], x["prev"], current, meta, src)
        elif x.get("ppsm_row"):
            db.add(PpsmEntry(**{k: (uuid.UUID(v) if k in ("id", "system_id", "import_id", "updated_by") and v else v) for k, v in x["ppsm_row"].items()}))
            imp.report = {**imp.report, "reverted_keys": [k for k in imp.report.get("reverted_keys") or [] if f"{k}|*" != x["id"]]}
            if imp.status == "reverted":
                imp.status = "applied"
        else:
            skipped.append({"id": x["id"], "reason": "Record-level restores are undone by re-applying the import file"})
            continue
        state[x["id"]] = "applied"
        done.append(x["id"])
    op["undone"] = True
    audit.record(db, action="import_data.undo", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="emass_import",
                 entity_id=str(imp.id), after={"op_id": op_id, "entries": done}, details={"skipped": skipped}, **meta)
    imp.report = {**imp.report, "manage_state": state, "manage_log": ops}
    return {"undone": done, "skipped": skipped}
