"""Manage imported data for every import type (Import Center history): eMASS workbooks (delegated to import_manage), Test Results /
Test Plan workbooks, HW/SW inventory, scan uploads (STIG CKL/CKLB, SCAP, Nessus/ACAS, SARIF) and policy uploads.

Deleting = snapshot the row plus every cascaded child and SET-NULL reference (generic, from the FK metadata) into import_trash, then delete –
so every list, dashboard and export (eMASS TR both modes, HW/SW, OSCAL) excludes it without per-query filters. Undo re-inserts the snapshot
within 30 days. Decisions (approvals, assessments, authorization, POA&Ms, categorization, ISCM strategy, implementations) are never deleted:
their link is set to NULL (restored on undo) and a "needs re-review" ReviewFlag is raised. Evidence: deleting the link removes the link only;
deleting the file is a separate, explicitly confirmed action (logical removal, file kept for retention)."""
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import (
    Assessment,
    Asset,
    Base,
    ControlAssignment,
    Evidence,
    EvidenceControl,
    Finding,
    FindingControlMap,
    FindingObservation,
    Implementation,
    ImportTrash,
    IngestRun,
    InventoryDiscrepancy,
    InventoryExport,
    InventoryImport,
    PoamFinding,
    Policy,
    PolicyControlMap,
    ReviewFlag,
    SoftwareItem,
    System,
    TrRow,
    TrWorkbook,
)
from app.services import audit

UNDO_DAYS = 30
KIND_PERM = {"tr": "ingest.upload", "inventory": "system.write", "ingest": "ingest.upload", "policy": "implementation.write"}
KIND_LABEL = {"emass": "eMASS workbook", "tr": "Test Results / Test Plan", "inventory": "HW/SW inventory", "ingest": "Scan / checklist upload",
              "policy": "Policy upload"}
# decision tables: never cascaded – their link is nulled (and restored on undo), the decision is flagged for re-review
PROTECT = {"approval_requests", "approval_decisions", "assessments", "authorization_decisions", "audit_events", "poams", "poam_history",
           "categorization_records", "iscm_strategies", "implementations", "attestations", "review_flags", "import_trash"}
FLAG_PERM = {"assessment": "assessment.perform", "tr_row": "assessment.perform", "categorization": "authorization.decide",
             "iscm_strategy": "system.write", "inventory": "system.write", "poam": "poam.manage", "policy_mapping": "implementation.write",
             "finding": "finding.map", "approval": "system.write"}
now = lambda: datetime.now(UTC)


# ---------- generic snapshot / restore ----------
def _ser(v):
    if isinstance(v, uuid.UUID):
        return {"$u": str(v)}
    if isinstance(v, datetime):
        return {"$dt": v.isoformat()}
    if isinstance(v, date):
        return {"$d": v.isoformat()}
    if isinstance(v, Decimal):
        return {"$n": str(v)}
    return v


def _de(v):
    if isinstance(v, dict) and len(v) == 1:
        k, x = next(iter(v.items()))
        if k == "$u":
            return uuid.UUID(x)
        if k == "$dt":
            return datetime.fromisoformat(x)
        if k == "$d":
            return date.fromisoformat(x)
        if k == "$n":
            return Decimal(x)
    return v


def _refs(table):
    return [(t, fk.parent, (fk.ondelete or "").upper()) for t in Base.metadata.tables.values() for fk in t.foreign_keys if fk.column.table is table]


def _collect(db: Session, table, ids: list, snap: dict, seen: set) -> None:
    ids = [i for i in ids if (table.name, str(i)) not in seen]
    if not ids:
        return
    seen.update((table.name, str(i)) for i in ids)
    rows = [dict(r) for r in db.execute(select(table).where(table.c.id.in_(ids))).mappings()]
    snap["tables"].append([table.name, [{k: _ser(v) for k, v in r.items()} for r in rows]])
    for child, col, ondel in _refs(table):
        hits = db.execute(select(child.c.id, col).where(col.in_(ids))).all() if "id" in child.c else []
        if not hits:
            continue
        if child.name in PROTECT or ondel == "SET NULL" or child is table:
            if not col.nullable:
                raise HTTPException(409, f"Linked to a decision record ({child.name}) – it cannot be deleted")
            snap["updates"] += [[child.name, str(cid), col.name, _ser(val)] for cid, val in hits]
            if child.name in PROTECT:
                snap["protected"] += [[child.name, str(cid)] for cid, _ in hits]
        else:
            _collect(db, child, [cid for cid, _ in hits], snap, seen)


def delete_rows(db: Session, model, ids: list) -> dict:
    """Snapshot + delete (children cascade in the DB; protected decision links are nulled first)."""
    snap: dict = {"tables": [], "updates": [], "protected": []}
    _collect(db, model.__table__, ids, snap, set())
    tables = Base.metadata.tables
    for tname, cid, col, _ in snap["updates"]:
        db.execute(update(tables[tname]).where(tables[tname].c.id == uuid.UUID(cid)).values({col: None}))
    db.flush()
    db.execute(model.__table__.delete().where(model.__table__.c.id.in_(ids)))
    db.expire_all()
    return snap


def restore_rows(db: Session, snap: dict) -> None:
    tables = Base.metadata.tables
    for tname, rows in snap.get("tables") or []:
        t = tables[tname]
        for r in rows:
            vals = {k: _de(v) for k, v in r.items()}
            if db.execute(select(t.c.id).where(t.c.id == vals["id"])).first() is None:
                db.execute(t.insert().values(**vals))
    for tname, cid, col, val in snap.get("updates") or []:
        t = tables[tname]
        db.execute(update(t).where(t.c.id == uuid.UUID(cid)).values({col: _de(val)}))
    db.expire_all()


# ---------- imports ----------
def load(db: Session, kind: str, import_id: uuid.UUID, org_id):
    model = {"tr": TrWorkbook, "inventory": InventoryImport, "ingest": IngestRun, "policy": Policy}.get(kind)
    obj = db.get(model, import_id) if model else None
    if obj is None or org_of(db, obj) != org_id:
        raise HTTPException(404, "Import not found")
    return obj


def org_of(db: Session, obj):
    return getattr(obj, "org_id", None) or db.scalar(select(System.org_id).where(System.id == obj.system_id))


def system_of(obj):
    if isinstance(obj, Policy):
        return uuid.UUID(str(obj.system_ids[0])) if obj.system_ids else None
    return obj.system_id


def header(kind: str, obj) -> dict:
    return {"kind": kind, "kind_label": KIND_LABEL[kind], "id": str(obj.id), "file_name": obj.file_name, "sha256": obj.sha256,
            "status": getattr(obj, "status", None) if kind != "policy" else obj.analysis_status, "system_id": str(system_of(obj) or "") or None}


def _created_by_run(db: Session, run_id) -> set:
    first = (select(FindingObservation.finding_id, FindingObservation.ingest_run_id)
             .distinct(FindingObservation.finding_id).order_by(FindingObservation.finding_id, FindingObservation.created_at)).subquery()
    return set(db.scalars(select(first.c.finding_id).where(first.c.ingest_run_id == run_id)))


def _e(eid, record, label, dest, imported=None, current=None, actions=("delete",), **kw) -> dict:
    return {"id": eid, "record": record, "label": label, "destination": dest, "field": "*", "prior": None, "imported": imported,
            "current": current, "created": True, "state": "applied", "changed_since_import": False, "actions": list(actions), **kw}


def entries(db: Session, kind: str, obj) -> list[dict]:
    out: list[dict] = []
    if kind == "tr":
        for r in db.scalars(select(TrRow).where(TrRow.workbook_id == obj.id).order_by(TrRow.row_number)):
            fin = r.final or {}
            acts = (["restore"] if r.state in ("edited", "approved", "conflict") else []) + ["delete"]
            out.append(_e(f"tr_row|{r.id}", (r.control_acronym or r.ap_acronym or "?") + (f" {r.cci_id}" if r.cci_id else ""), f"Row {r.row_number}",
                          "Test Results", (r.proposed or {}).get("compliance_status"), fin.get("compliance_status") or r.state, acts,
                          entity_id=str(r.id), decision="SCA-approved result" if r.state == "approved" else None))
    elif kind == "inventory":
        for a in db.scalars(select(Asset).where(Asset.system_id == obj.system_id, Asset.provenance["import_id"].astext == str(obj.id))):
            out.append(_e(f"asset|{a.id}", a.name, "Hardware asset", "HW/SW Inventory", a.hostname or a.ip_address, a.os, entity_id=str(a.id)))
        for s in db.scalars(select(SoftwareItem).where(SoftwareItem.import_id == obj.id)):
            out.append(_e(f"software|{s.id}", f"{s.vendor} {s.name}", "Software", "HW/SW Inventory", s.version, s.version, entity_id=str(s.id)))
    elif kind == "ingest":
        created = _created_by_run(db, obj.id)
        touched = set(db.scalars(select(FindingObservation.finding_id).where(FindingObservation.ingest_run_id == obj.id)))
        for f in db.scalars(select(Finding).where(Finding.id.in_(touched))) if touched else []:
            ro = None if f.id in created else "Existed before this upload (only updated by it) – delete it from the upload that created it"
            out.append(_e(f"finding|{f.id}", f.rule_id or f.vuln_id or f.plugin_id or "finding", (f.title or "")[:120], "Findings", f.severity,
                          f.current_state, [] if ro else ["delete"], entity_id=str(f.id), read_only=ro))
        if obj.evidence_id:
            ev = db.get(Evidence, obj.evidence_id)
            for ec, cid in db.execute(select(EvidenceControl, ControlAssignment.control_id).join(ControlAssignment, ControlAssignment.id == EvidenceControl.assignment_id)
                                      .where(EvidenceControl.evidence_id == obj.evidence_id, EvidenceControl.removed_at.is_(None))):
                out.append(_e(f"evidence_link|{ec.id}", cid.upper(), "Evidence link (link only – the file stays)", "Evidence", ev.name if ev else None, None,
                              entity_id=str(ec.id)))
            if ev and ev.status == "active":
                out.append(_e(f"evidence_file|{ev.id}", ev.name, "Evidence file (separate confirmation; removed logically, kept for retention)",
                              "Evidence", ev.sha256[:12], ev.status, entity_id=str(ev.id), needs_file_confirm=True))
    if kind == "policy" and obj.status != "removed":
        out.append(_e(f"policy|{obj.id}", obj.policy_key, f"Whole policy “{obj.title}” with its mappings, coverage and findings", "Policy Auditor",
                      f"v{obj.version}", obj.status, entity_id=str(obj.id)))
    if kind == "policy":
        for m in db.scalars(select(PolicyControlMap).where(PolicyControlMap.policy_id == obj.id, PolicyControlMap.valid_to.is_(None))):
            human = m.decided_by is not None
            out.append(_e(f"policy_map|{m.id}", m.control_id.upper(), f"Mapping ({m.status}{', human-approved' if human else ''})", "Policy Auditor → Mapping Review",
                          m.confidence, m.status, entity_id=str(m.id), decision="Human-approved mapping" if human else None))
    return out


def trashed(db: Session, kind: str, import_id) -> list[ImportTrash]:
    return list(db.scalars(select(ImportTrash).where(ImportTrash.import_kind == kind, ImportTrash.import_id == import_id).order_by(ImportTrash.created_at)))


def log(db: Session, kind: str, import_id) -> list[dict]:
    ops: dict = {}
    for t in trashed(db, kind, import_id):
        o = ops.setdefault(t.op_id, {"op_id": t.op_id, "action": t.action, "at": t.created_at.isoformat(), "by": t.deleted_by, "entries": [], "undone": False})
        o["entries"].append({"id": t.entry_id, "label": t.label})
        o["undone"] = t.restored_at is not None
    return list(ops.values())


# ---------- re-review flags ----------
def flag(db: Session, org_id, system_id, entity_type: str, entity_id, label: str, reason: str, kind: str, import_id, op_id: str) -> None:
    if db.scalar(select(ReviewFlag.id).where(ReviewFlag.entity_type == entity_type, ReviewFlag.entity_id == str(entity_id),
                                              ReviewFlag.status == "open", ReviewFlag.op_id == op_id)):
        return
    db.add(ReviewFlag(org_id=org_id, system_id=system_id, entity_type=entity_type, entity_id=str(entity_id), label=label, reason=reason,
                      import_kind=kind, import_id=import_id, op_id=op_id))


def _flag_assessments(db: Session, org_id, sid, control_ids: set, why: str, kind, iid, op_id) -> None:
    for a in db.scalars(select(Assessment).where(Assessment.system_id == sid, Assessment.control_id.in_(control_ids))) if control_ids else []:
        flag(db, org_id, sid, "assessment", a.id, f"SCA determination {a.control_id.upper()} ({a.result})", why, kind, iid, op_id)


def _flag_protected(db: Session, org_id, sid, snap: dict, why: str, kind, iid, op_id) -> None:
    for tname, cid in snap.get("protected") or []:
        et = {"approval_requests": "approval", "poams": "poam", "assessments": "assessment", "implementations": "implementation"}.get(tname, tname)
        flag(db, org_id, sid, et, cid, f"{tname.replace('_', ' ')} {cid[:8]}", why, kind, iid, op_id)


def flags(db: Session, org_id, system_id=None, import_id=None, open_only: bool = True) -> list[dict]:
    q = select(ReviewFlag).where(ReviewFlag.org_id == org_id)
    q = q.where(ReviewFlag.system_id == system_id) if system_id else q
    q = q.where(ReviewFlag.import_id == import_id) if import_id else q
    q = q.where(ReviewFlag.status == "open") if open_only else q
    return [{"id": str(f.id), "entity_type": f.entity_type, "entity_id": f.entity_id, "label": f.label, "reason": f.reason, "status": f.status,
             "import_kind": f.import_kind, "import_id": str(f.import_id) if f.import_id else None, "at": f.created_at.isoformat(),
             "resolve_permission": FLAG_PERM.get(f.entity_type, "system.write")} for f in db.scalars(q.order_by(ReviewFlag.created_at.desc()).limit(500))]


# ---------- actions ----------
def _do(db: Session, kind: str, obj, e: dict, action: str, org_id, sid, op_id: str, why: str) -> dict:
    """One entry → snapshot dict stored in the trash (undo). Raises HTTPException on a per-item problem."""
    typ, ent = e["id"].split("|", 1)
    ent_id = uuid.UUID(ent)
    if typ == "tr_row":
        r = db.get(TrRow, ent_id)
        if r.state == "approved" or r.final:
            flag(db, org_id, sid, "tr_row", r.id, f"Test result {r.control_acronym or ''} {r.cci_id or ''} row {r.row_number} (SCA decision)".strip(),
                 why, kind, obj.id, op_id)
            _flag_assessments(db, org_id, sid, {r.control_id} if r.control_id else set(), why, kind, obj.id, op_id)
        if action == "restore":
            prev = {"final": r.final, "state": r.state, "decided_by": r.decided_by, "justification": r.justification}
            r.final, r.state, r.decided_by, r.decided_at, r.justification = None, "auto" if r.proposed else "missing", None, None, None
            return {"tables": [], "updates": [["tr_rows", str(r.id), k, _ser(v)] for k, v in prev.items()], "protected": []}
        return delete_rows(db, TrRow, [ent_id])
    if typ in ("asset", "software"):
        if db.scalar(select(InventoryExport.id).where(InventoryExport.system_id == sid)) or (typ == "asset" and db.scalar(
                select(InventoryDiscrepancy.id).where(InventoryDiscrepancy.system_id == sid, InventoryDiscrepancy.status.in_(("applied", "approved"))))):
            flag(db, org_id, sid, "inventory", sid, "Approved / exported HW/SW inventory", why, kind, obj.id, op_id)
        return delete_rows(db, Asset if typ == "asset" else SoftwareItem, [ent_id])
    if typ == "finding":
        f = db.get(Finding, ent_id)
        ctl = set(db.scalars(select(FindingControlMap.control_id).where(FindingControlMap.finding_id == f.id)))
        _flag_assessments(db, org_id, sid, ctl, why, kind, obj.id, op_id)
        for (pid,) in db.execute(select(PoamFinding.poam_id).where(PoamFinding.finding_id == f.id)):
            flag(db, org_id, sid, "poam", pid, f"POA&M linked to {f.rule_id or f.vuln_id or 'finding'}", why, kind, obj.id, op_id)
        if f.disposition:
            flag(db, org_id, sid, "finding", f.id, f"Disposition “{f.disposition}” of {f.rule_id or f.vuln_id or 'finding'}", why, kind, obj.id, op_id)
        snap = delete_rows(db, Finding, [ent_id])
        _flag_protected(db, org_id, sid, snap, why, kind, obj.id, op_id)
        return snap
    if typ == "evidence_link":
        ec = db.get(EvidenceControl, ent_id)
        ec.removed_at = now()
        return {"tables": [], "updates": [["evidence_controls", str(ec.id), "removed_at", None]], "protected": []}
    if typ == "evidence_file":
        ev = db.get(Evidence, ent_id)
        if ev.legal_hold:
            raise HTTPException(409, "Evidence is on legal hold")
        prev = {"status": ev.status, "removed_reason": ev.removed_reason, "removed_by": ev.removed_by, "removed_at": ev.removed_at}
        ev.status, ev.removed_reason, ev.removed_by, ev.removed_at = "removed", why, e.get("_by"), now()
        links = list(db.scalars(select(EvidenceControl).where(EvidenceControl.evidence_id == ev.id, EvidenceControl.removed_at.is_(None))))
        for ec in links:
            ec.removed_at = now()
        return {"tables": [], "updates": [["evidence", str(ev.id), k, _ser(v)] for k, v in prev.items()]
                + [["evidence_controls", str(ec.id), "removed_at", None] for ec in links], "protected": []}
    if typ == "policy":
        maps = list(db.scalars(select(PolicyControlMap).where(PolicyControlMap.policy_id == ent_id, PolicyControlMap.decided_by.is_not(None))))
        _flag_policy_maps(db, org_id, sid, obj, maps, why, kind, op_id)
        from app.models import PolicyFinding, PolicyRequirementCoverage
        snap: dict = {"tables": [], "updates": [], "protected": []}
        for mdl in (PolicyControlMap, PolicyRequirementCoverage, PolicyFinding):
            ids_ = list(db.scalars(select(mdl.id).where(mdl.policy_id == ent_id)))
            if ids_:
                s2 = delete_rows(db, mdl, ids_)
                snap = {k: snap[k] + s2[k] for k in snap}
        p = db.get(Policy, ent_id)  # the policy row is kept as "removed" (import history, audit and undo stay reachable)
        snap["updates"].append(["policies", str(p.id), "status", p.status])
        p.status = "removed"
        return snap
    if typ == "policy_map":
        m = db.get(PolicyControlMap, ent_id)
        if m.decided_by is not None:
            _flag_policy_maps(db, org_id, sid, obj, [m], why, kind, op_id)
        from app.models import PolicyRequirementCoverage
        cov = list(db.scalars(select(PolicyRequirementCoverage.id).where(PolicyRequirementCoverage.policy_id == m.policy_id,
                                                                         PolicyRequirementCoverage.control_id == m.control_id)))
        snap = delete_rows(db, PolicyControlMap, [ent_id])
        if cov:
            s2 = delete_rows(db, PolicyRequirementCoverage, cov)
            snap = {k: snap[k] + s2[k] for k in snap}
        return snap
    raise HTTPException(422, "Unknown entry")


def _flag_policy_maps(db: Session, org_id, sid, pol, maps: list, why: str, kind: str, op_id: str) -> None:
    for m in maps:
        flag(db, org_id, sid, "policy_mapping", m.id, f"Human-approved mapping {pol.policy_key} → {m.control_id.upper()}", why, kind, pol.id, op_id)
        for sys_id in pol.system_ids or []:
            for impl in db.scalars(select(Implementation).join(ControlAssignment, ControlAssignment.id == Implementation.assignment_id).where(
                    ControlAssignment.system_id == uuid.UUID(str(sys_id)), ControlAssignment.control_id == m.control_id, Implementation.is_current.is_(True))):
                impl.needs_reconsideration = True


def act(db: Session, kind: str, obj, current, meta: dict, ids: list[str], action: str, force: bool = False, confirm_file: bool = False) -> dict:
    by = {e["id"]: e for e in entries(db, kind, obj)}
    sid, org_id = system_of(obj), org_of(db, obj)
    op_id = uuid.uuid4().hex[:12]
    why = f"Imported data deleted via Manage imported data ({obj.file_name}, op {op_id}) – the decision is kept and needs re-review"
    results, done = [], []
    for eid in dict.fromkeys(ids):
        e = by.get(eid)
        if e is None:
            results.append({"id": eid, "ok": False, "error": "Not part of this import (or already deleted)"})
            continue
        if action not in e["actions"]:
            results.append({"id": eid, "ok": False, "error": e.get("read_only") or f"'{action}' is not possible here"})
            continue
        if e.get("needs_file_confirm") and not confirm_file:
            results.append({"id": eid, "ok": False, "error": "Deleting the evidence FILE needs its own confirmation", "needs_file_confirm": True})
            continue
        if e.get("decision") and not force:
            results.append({"id": eid, "ok": False, "error": f"{e['decision']} – confirm to continue (the decision is kept and flagged for re-review)",
                            "needs_confirm": True})
            continue
        try:
            with db.begin_nested():
                snap = _do(db, kind, obj, {**e, "_by": current.user.email}, action, org_id, sid, op_id, why)
                db.add(ImportTrash(org_id=org_id, system_id=sid, import_kind=kind, import_id=obj.id, op_id=op_id, action=action, entry_id=eid,
                                   label=f"{e['record']} – {e['label']}"[:500], snapshot=snap, deleted_by=current.user.email))
                db.flush()
            results.append({"id": eid, "ok": True, "state": "deleted" if action == "delete" else "restored"})
            done.append(eid)
        except HTTPException as exc:
            results.append({"id": eid, "ok": False, "error": str(exc.detail)})
    if done:
        audit.record(db, action=f"import_data.{action}", actor_user_id=current.user.id, actor_email=current.user.email, entity_type=f"import_{kind}",
                     entity_id=str(obj.id), after={"entries": done, "op_id": op_id},
                     details={"file_name": obj.file_name, "sha256": obj.sha256, "failed": [r for r in results if not r["ok"]][:50]}, **meta)
    return {"results": results, "op": {"op_id": op_id} if done else None, "ok": len(done), "failed": len(results) - len(done)}


def undo(db: Session, kind: str, obj, current, meta: dict, op_id: str) -> dict:
    rows = [t for t in trashed(db, kind, obj.id) if t.op_id == op_id]
    if not rows:
        raise HTTPException(404, "Operation not found")
    if any(t.restored_at for t in rows):
        raise HTTPException(409, "Already undone")
    if now() - rows[0].created_at > timedelta(days=UNDO_DAYS):
        raise HTTPException(409, f"Undo is available for {UNDO_DAYS} days")
    for t in reversed(rows):
        restore_rows(db, t.snapshot)
        t.restored_at, t.restored_by = now(), current.user.email
    for f in db.scalars(select(ReviewFlag).where(ReviewFlag.op_id == op_id, ReviewFlag.status == "open")):
        f.status, f.resolved_by, f.resolved_at, f.resolution = "undone", current.user.email, now(), "Deletion undone – underlying data restored"
    audit.record(db, action="import_data.undo", actor_user_id=current.user.id, actor_email=current.user.email, entity_type=f"import_{kind}",
                 entity_id=str(obj.id), after={"op_id": op_id, "entries": [t.entry_id for t in rows]}, **meta)
    return {"undone": [t.entry_id for t in rows], "skipped": []}


# ---------- destination-screen index ----------
def index(db: Session, system: System, what: str) -> dict:
    """entity id → {import_kind, import_id, file_name, entry_id, actions} for the 'Imported from <file>' marker and row Delete."""
    out: dict = {}
    if what == "tr_row":
        for r, w in db.execute(select(TrRow, TrWorkbook).join(TrWorkbook, TrWorkbook.id == TrRow.workbook_id).where(TrWorkbook.system_id == system.id)):
            out[str(r.id)] = {"import_kind": "tr", "import_id": str(w.id), "file_name": w.file_name, "entry_id": f"tr_row|{r.id}", "actions": ["delete"],
                              "decision": r.state == "approved"}
    elif what in ("asset", "software"):
        imps = {i.id: i.file_name for i in db.scalars(select(InventoryImport).where(InventoryImport.system_id == system.id))}
        if what == "asset":
            for a in db.scalars(select(Asset).where(Asset.system_id == system.id, Asset.provenance["import_id"].astext.is_not(None))):
                iid = uuid.UUID(a.provenance["import_id"])
                if iid in imps:
                    out[str(a.id)] = {"import_kind": "inventory", "import_id": str(iid), "file_name": imps[iid], "entry_id": f"asset|{a.id}", "actions": ["delete"]}
        else:
            for s in db.scalars(select(SoftwareItem).where(SoftwareItem.system_id == system.id, SoftwareItem.import_id.is_not(None))):
                out[str(s.id)] = {"import_kind": "inventory", "import_id": str(s.import_id), "file_name": imps.get(s.import_id), "entry_id": f"software|{s.id}",
                                  "actions": ["delete"]}
    elif what == "finding":
        first = (select(FindingObservation.finding_id, FindingObservation.ingest_run_id).join(Finding, Finding.id == FindingObservation.finding_id)
                 .where(Finding.system_id == system.id).distinct(FindingObservation.finding_id)
                 .order_by(FindingObservation.finding_id, FindingObservation.created_at)).subquery()
        for fid, rid, name in db.execute(select(first.c.finding_id, first.c.ingest_run_id, IngestRun.file_name).join(IngestRun, IngestRun.id == first.c.ingest_run_id)):
            out[str(fid)] = {"import_kind": "ingest", "import_id": str(rid), "file_name": name, "entry_id": f"finding|{fid}", "actions": ["delete"]}
    else:  # eMASS destinations: emass_field (control_id|field), ppsm (entry id), strategy
        from app.models import EmassImport
        from app.services import import_manage as im
        for imp in db.scalars(select(EmassImport).where(EmassImport.system_id == system.id, EmassImport.status.in_(("applied", "reverted")))
                              .order_by(EmassImport.created_at)):
            undo_by = {r["key"]: r["undo"] for r in (imp.report or {}).get("apply_results") or [] if r.get("undo")}
            for e in im.entries(db, imp):
                if e["state"] != "applied":
                    continue
                u = undo_by.get(e["key"]) or {}
                key = (f"{e['control_id']}|{e['field']}" if what == "emass_field" and e["field"] != "*" else
                       u.get("id") if what == "ppsm" and u.get("kind") == "ppsm" else
                       "strategy" if what == "strategy" and u.get("kind") == "strategy" else None)
                if key:
                    out[str(key)] = {"import_kind": "emass", "import_id": str(imp.id), "file_name": imp.file_name, "entry_id": e["id"], "actions": e["actions"]}
    return out

