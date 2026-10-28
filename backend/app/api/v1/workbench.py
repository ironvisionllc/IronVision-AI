import uuid
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.records import assignment_for, get_system, to_dict, visible_systems
from app.db import get_db
from app.models import (ApprovalRequest, Poam, System, Asset, Cci, CciControlMap, CommonControlProvider, ContentVersion, ControlAssignment, Evidence,
                        EvidenceControl, EvidenceSource, Finding, FindingControlMap, Implementation, Organization,
                        PriorityWeight, ReviewerComment, RiskSnapshot)
from app.security.deps import CurrentUser, get_current_user, require_permission
from app.services import audit
from app.services.people import attach
from app.services.evaluation import evaluate_system, system_metrics

router = APIRouter(tags=["workbench"])


@router.get("/systems/{system_id}/workbench/summary")
def summary(system_id: uuid.UUID, db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    from app.services.metrics import system_metrics as metrics

    rows = list(db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == system_id)))
    c = lambda pred: sum(1 for a in rows if pred(a))  # noqa: E731
    sysobj = get_system(db, system_id)
    m = metrics(db, sysobj)
    from app.services.counts import system_counts
    counts = system_counts(db, sysobj)
    return {"overlapping_counts_note": "Counts overlap: one control can appear in several categories.", "metrics": m, "counts": counts,
            "total_assigned": counts["assigned"], "with_current_evidence": counts["with_current_evidence"], "with_evidence": counts["with_evidence"],
            "fully_inherited": c(lambda a: a.responsibility == "inherited"), "shared": c(lambda a: a.responsibility == "shared"),
            "not_assessed": c(lambda a: a.assessment_status == "not_assessed"),
            "with_open_findings": c(lambda a: (a.evaluation or {}).get("open_findings", 0) > 0),
            "requiring_manual_action": c(lambda a: any(r["code"] != "missing_assessment_evidence" for r in (a.reasons or []))),
            "unmapped_findings": m["unmapped_findings"],
            "by_origin": dict(Counter(a.origin for a in rows)),
            "monitoring": dict(Counter(a.monitoring_status for a in rows)), "freshness": dict(Counter(a.evidence_freshness_status for a in rows))}


@router.get("/systems/{system_id}/workbench/controls")
def controls(system_id: uuid.UUID, queue: str | None = None, q: str | None = None, implementation_status: str | None = None,
             responsibility: str | None = None, assessment_status: str | None = None, monitoring_status: str | None = None,
             family: str | None = None, origin: str | None = None, has_evidence: str | None = None, evidence: str | None = None,
             policy_mapping: str | None = None, policy: str | None = None, policy_coverage: str | None = None, fmt: str | None = None,
             emass_status: str | None = None, emass_missing: str | None = None,
             limit: str | None = None, db: Session = Depends(get_db),
             _: CurrentUser = Depends(require_permission("system.read"))):
    """Lenient list params: an empty/unknown queue or limit (e.g. sent mid tab switch) falls back to the default instead of a 422."""
    from app.models import Control

    queue = (queue or "").lower() in ("true", "1", "yes")
    limit = int(limit) if (limit or "").isdigit() else 2000
    from app.services.evaluation import FRESH_OK

    s = get_system(db, system_id)
    A = ControlAssignment
    stmt = select(A, Control.title, Control.label).join(Control, Control.id == A.control_uuid).where(A.system_id == system_id)
    if queue:
        stmt = stmt.where(A.priority_score > 2)
    for col, v in ((A.implementation_status, implementation_status), (A.responsibility, responsibility), (A.assessment_status, assessment_status),
                   (A.monitoring_status, monitoring_status), (A.origin, origin), (Control.family_id, family.lower() if family else None)):
        if v:
            stmt = stmt.where(col == v)
    if has_evidence in ("yes", "no"):   # same predicate as counts.system_counts["with_evidence"]
        stmt = stmt.where(A.evidence_freshness_status != "no_evidence" if has_evidence == "yes" else A.evidence_freshness_status == "no_evidence")
    if evidence == "current":           # same predicate as counts.system_counts["with_current_evidence"]
        stmt = stmt.where(A.evidence_freshness_status.in_(FRESH_OK))
    if q:
        stmt = stmt.where(A.control_id.ilike(f"%{q}%") | Control.title.ilike(f"%{q}%"))
    pols = {x for x in (policy or "").split(",") if x} or None
    if emass_status or emass_missing:
        from app.models import EmassControlFields
        from app.services import emass_fields as ef

        if emass_status and emass_status not in ef.STATUSES:
            raise HTTPException(422, f"emass_status must be one of: {', '.join(ef.STATUSES)}")
        want = {"yes": True, "true": True, "1": True, "no": False, "false": False, "0": False}.get((emass_missing or "").lower()) if emass_missing else None
        if emass_missing and want is None:
            raise HTTPException(422, "emass_missing must be yes/no (true/false and 1/0 are also accepted)")
        fm = {f.assignment_id: f for f in db.scalars(select(EmassControlFields).where(EmassControlFields.system_id == system_id))}
        narr = ef.narratives(db, system_id)
        from app.services import iscm
        res = iscm.resolver_for_system_id(db, system_id)
        keep = []
        for a in db.scalars(select(A).where(A.system_id == system_id)):
            st = ef.emass_status(a, fm.get(a.id))
            miss = bool(ef.missing_all(st, ef.effective(db, a, fm.get(a.id), res)[0], narr.get(a.id)))
            if (not emass_status or st == emass_status) and (want is None or miss == want):
                keep.append(a.control_id)
        stmt = stmt.where(A.control_id.in_(keep))
    if policy_mapping or pols or policy_coverage:
        from app.services import policy_coverage as pc

        idx = pc.index(db, s)
        keep = [c for c in db.scalars(select(A.control_id).where(A.system_id == system_id)) if pc.matches(idx.get(c), policy_mapping, pols, policy_coverage)]
        stmt = stmt.where(A.control_id.in_(keep))
    stmt = stmt.order_by(A.priority_score.desc(), Control.sort_id).limit(min(limit, 5000))
    rows = [{**to_dict(a, ("evaluation",)), "title": t, "label": lbl, "evaluation": a.evaluation} for a, t, lbl in db.execute(stmt).all()]
    if fmt == "csv":
        import csv
        import io

        from fastapi.responses import Response

        buf = io.StringIO()
        w = csv.writer(buf)
        cols = ["control_id", "title", "implementation_status", "assessment_status", "responsibility", "origin", "evidence_freshness_status", "monitoring_status"]
        w.writerow(cols)
        for r in rows:
            w.writerow([r.get(k) for k in cols])
        return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{s.acronym or "system"}-controls.csv"'})
    return rows


@router.get("/systems/{system_id}/workbench/policy-facets")
def policy_facets(system_id: uuid.UUID, db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    from app.services import policy_coverage as pc

    return pc.facet_counts(db, get_system(db, system_id))


@router.get("/systems/{system_id}/ccis")
def system_ccis(system_id: uuid.UUID, mapped: str | None = None, coverage: str | None = None, policy: str | None = None, control: str | None = None,
                family: str | None = None, q: str | None = None, fmt: str | None = None, db: Session = Depends(get_db),
                _: CurrentUser = Depends(require_permission("system.read"))):
    """DISA CCIs of the system's assigned controls with policy coverage (best status across applicable policies)."""
    from app.models import Cci, CciControlMap
    from app.services import policy_coverage as pc

    s = get_system(db, system_id)
    assigned = {a.control_id: a for a in db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == system_id))}
    idx = pc.index(db, s)
    pols = {str(p.id): p for p in pc.applicable_policies(db, s)}
    want = {x for x in (policy or "").split(",") if x}
    mapped = {"true": "yes", "1": "yes", "false": "no", "0": "no"}.get((mapped or "").lower(), (mapped or "").lower() or None)
    defs = dict(db.execute(select(Cci.cci_id, Cci.definition)).all())
    out, seen = [], set()
    for m in db.scalars(select(CciControlMap).where(CciControlMap.version == "5", CciControlMap.control_id.in_(assigned)).order_by(CciControlMap.control_id, CciControlMap.cci_id)):
        if (m.cci_id, m.control_id) in seen:
            continue
        seen.add((m.cci_id, m.control_id))
        cov = [c for c in pc.scoped(idx.get(m.control_id), want or None) if c.requirement_id == m.cci_id]
        allcov = [c for c in (idx.get(m.control_id) or {}).get("rows", []) if c.requirement_id == m.cci_id and (not want or str(c.policy_id) in want)]
        best = cov[0] if cov else None
        st = pc.effective(best) if best else None
        row = {"cci_id": m.cci_id, "definition": defs.get(m.cci_id), "control_id": m.control_id, "reference": m.reference_index,
               "implementation_status": assigned[m.control_id].implementation_status, "mapped": bool(cov), "coverage": st,
               "policies": sorted({f"{pols[str(c.policy_id)].title} v{pols[str(c.policy_id)].version}" for c in allcov if str(c.policy_id) in pols}),
               "policy_ids": sorted({str(c.policy_id) for c in allcov}),
               "matched_by": (f"{pols[str(best.policy_id)].title} v{pols[str(best.policy_id)].version}" if best and st != "missing" and str(best.policy_id) in pols else None),
               "confidence": best.confidence if best else None,
               "snippet": ((best.snippets or [{}])[0] if best and best.snippets else None), "reason": best.reason if best else None,
               "covered_elsewhere": bool(best and best.override)}
        if mapped == "yes" and not row["mapped"] or mapped == "no" and row["mapped"]:
            continue
        if coverage and row["coverage"] != coverage or want and not want & set(row["policy_ids"]):
            continue
        if control and m.control_id != control.lower() or family and m.control_id.split("-")[0] != family.lower():
            continue
        if q and q.lower() not in f"{m.cci_id} {row['definition']} {m.control_id}".lower():
            continue
        out.append(row)
    if fmt == "csv":
        import csv
        import io

        from fastapi.responses import Response

        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["cci_id", "control_id", "definition", "implementation_status", "mapped", "coverage", "policies", "snippet", "location"])
        for r in out:
            w.writerow([r["cci_id"], r["control_id"].upper(), r["definition"], r["implementation_status"], "yes" if r["mapped"] else "no", r["coverage"] or "",
                        "; ".join(r["policies"]), (r["snippet"] or {}).get("text", ""), (r["snippet"] or {}).get("location", "")])
        return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{s.acronym or "system"}-ccis.csv"'})
    return {"items": out, "total": len(out), "counts": {"mapped": sum(r["mapped"] for r in out), "met": sum(r["coverage"] == "met" for r in out),
                                                      "partial": sum(r["coverage"] == "partial" for r in out), "missing": sum(r["coverage"] == "missing" for r in out)}}


@router.get("/systems/{system_id}/workbench/queue")
def work_queue(system_id: uuid.UUID, mine: bool = False, db: Session = Depends(get_db),
               current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    from app.services.queue import work_queue as wq

    s = get_system(db, system_id)
    roles = {a.role for a in current.assignments if a.scope_id in (s.id, s.org_id)}
    return wq(db, s, current.user, roles, mine)


@router.get("/systems/{system_id}/workbench/controls/{control_id}/requirement-counts")
def requirement_counts(system_id: uuid.UUID, control_id: str, db: Session = Depends(get_db),
                       _: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    from app.services import policy_coverage as pc

    s = db.get(System, system_id)
    if s is None:
        raise HTTPException(404, "System not found")
    return pc.requirement_counts(db, s, control_id.lower())


@router.get("/systems/{system_id}/workbench/controls/{control_id}")
def control_detail(system_id: uuid.UUID, control_id: str, db: Session = Depends(get_db),
                   _: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    from app.api.v1.controls import get_control

    a = assignment_for(db, system_id, control_id)
    catalog = get_control(a.control_id, db).model_dump()
    findings = db.execute(select(Finding, Asset.name, FindingControlMap).join(FindingControlMap, FindingControlMap.finding_id == Finding.id)
                          .outerjoin(Asset, Asset.id == Finding.asset_id)
                          .where(Finding.system_id == system_id, FindingControlMap.control_id == a.control_id)).all()
    per_source: dict[str, dict] = {}
    for f, asset, _m in findings:
        s = per_source.setdefault(f.source_type, {"assets": set(), "failed_rules": set(), "passed": 0})
        s["assets"].add(asset)
        if f.current_state == "open":
            s["failed_rules"].add(f.rule_id)
        elif f.current_state == "pass":
            s["passed"] += 1
    evidence = db.execute(select(Evidence, EvidenceSource.name).join(EvidenceControl, EvidenceControl.evidence_id == Evidence.id)
                          .outerjoin(EvidenceSource, EvidenceSource.id == Evidence.source_id).where(EvidenceControl.assignment_id == a.id)
                          .order_by(Evidence.collected_at.desc())).all()
    from app.models import PoamFinding

    linked = {fid: (str(pid), hid) for fid, pid, hid in db.execute(select(PoamFinding.finding_id, Poam.id, Poam.human_id).join(Poam, Poam.id == PoamFinding.poam_id)
                                                                   .where(Poam.system_id == system_id))}
    seen, open_findings = set(), []
    for f, asset, m in findings:
        if f.current_state == "open" and f.id not in seen:
            seen.add(f.id)
            open_findings.append({**to_dict(f, ("dedup_fields",)), "asset_name": asset,
                                  "mapping": {"source": m.source, "review_status": m.review_status, "cci_id": m.cci_id or None, "confidence": m.confidence},
                                  "poam": {"id": linked[f.id][0], "human_id": linked[f.id][1]} if f.id in linked else None})
    impls = db.scalars(select(Implementation).where(Implementation.assignment_id == a.id).order_by(Implementation.version.desc()))
    prov = db.get(CommonControlProvider, a.provider_id) if a.provider_id else None
    cci_cv = db.scalar(select(ContentVersion).where(ContentVersion.content_type == "cci_list", ContentVersion.is_active.is_(True)))
    weights = {w.reason_code: w.description for w in db.scalars(select(PriorityWeight))}
    from app.services.overlays import control_notes

    from app.models import PolicyRequirementCoverage
    from app.services import policy_coverage as pc

    sysobj = db.get(System, system_id)
    pids = [p.id for p in pc.applicable_policies(db, sysobj)]
    pcov: dict = {}
    for c in db.scalars(select(PolicyRequirementCoverage).where(PolicyRequirementCoverage.policy_id.in_(pids), PolicyRequirementCoverage.control_id == a.control_id)
                        .order_by(PolicyRequirementCoverage.requirement_type, PolicyRequirementCoverage.requirement_id)):
        pcov.setdefault(str(c.policy_id), []).append(c)
    return {
        "policy_coverage": [{"policy_id": k, "policy_title": next((f"{p.title} v{p.version}" for p in pc.applicable_policies(db, sysobj) if str(p.id) == k), ""),
                             "summary": (sm := pc.summarize(v)), "line": pc.summary_line(a.control_id, sm),
                             "requirements": [{"id": str(c.id), "type": c.requirement_type, "label": c.label, "text": c.text, "status": pc.effective(c),
                                               "reason": c.reason, "snippets": c.snippets, "parameter": c.parameter, "value": c.parameter_value, "needs": c.needs,
                                               "confidence": c.confidence, "basis": pc.basis_label(c), "kind": pc.kind_label(c),
                                               "linked": c.linked, "override": c.override, **{k2: v2 for k2, v2 in pc.display(c).items() if k2 != "status"}}
                                              for c in v]} for k, v in pcov.items()],
        "overlay_notes": control_notes(db, sysobj, a.control_id),
        "status_last_changed": _status_last_changed(db, a),
        "policy_mappings": _policy_mappings(db, a),
        "assignment": {**to_dict(a), "provider_name": prov.name if prov else None, "selection_basis": _selection_basis(sysobj, a),
                       "reason_details": [{**r, "description": weights.get(r["code"])} for r in (a.reasons or [])]},
        "cnssi_parameters": _cnssi_parameters(db, sysobj, a.control_id),
        "catalog": catalog,
        "cci_provenance": {"source": "DISA CCI List", "version": cci_cv.version if cci_cv else None, "sha256": cci_cv.sha256 if cci_cv else None},
        "evidence_summary": [{"source_type": k, "assets_scanned": len(v["assets"]), "failed_rules": len(v["failed_rules"]), "passed_checks": v["passed"]}
                             for k, v in per_source.items()],
        "evidence": [{**to_dict(e, ("provenance",)), "source_name": n} for e, n in evidence],
        "open_findings": open_findings,
        "implementations": attach(db, [to_dict(i) for i in impls], "author_id", "author"),
        "comments": [to_dict(c) for c in db.scalars(select(ReviewerComment).where(ReviewerComment.assignment_id == a.id).order_by(ReviewerComment.created_at))],
        "emass_sync": "Not configured",
        "approved_implementation": next((to_dict(i) for i in db.scalars(select(Implementation).where(
            Implementation.assignment_id == a.id, Implementation.review_status == "approved"))), None),
        "poams": _control_poams(db, system_id, a.control_id),
        "policy_parameters": _policy_parameters(db, system_id, a.control_id),
        "statement_segments": _render_odps(db, system_id, a.control_id, catalog),
        "pending_reviews": [to_dict(r) for r in db.scalars(select(ApprovalRequest).where(
            ApprovalRequest.system_id == system_id, ApprovalRequest.control_id == a.control_id, ApprovalRequest.status == "pending"))],
    }


ODP_PARAM = {"inactivity_disable_days": "ac-02.03_odp.02", "unsuccessful_logon_attempts": "ac-07_odp.01", "logon_attempt_window_minutes": "ac-07_odp.02", "session_lock_minutes": "ac-11_odp.01"}


def _render_odps(db, system_id, control_id, catalog: dict) -> list[dict]:
    """Statement split into text + ODP segments; approved system ODP values fill the matching [Assignment: …] placeholder."""
    import re

    from app.models import OdpValue

    odps = {ODP_PARAM.get(o.parameter): o for o in db.scalars(select(OdpValue).where(OdpValue.system_id == system_id, OdpValue.control_id == control_id))}
    params = catalog.get("parameters") or []
    text, out, pos, i = catalog.get("statement") or "", [], 0, 0
    for m in re.finditer(r"\[(Assignment|Selection)[^\]]*\]", text):
        out.append({"text": text[pos:m.start()]})
        p = params[i] if i < len(params) else {}
        o = odps.get(p.get("id"))
        out.append({"odp_id": p.get("id"), "original": m.group(0), "value": f"{o.value} (organization-defined)" if o else None,
                    "source": f"{o.source}, approved {o.approved_at}" if o else None, "status": "filled" if o else "not yet defined"})
        pos, i = m.end(), i + 1
    out.append({"text": text[pos:]})
    return out


def _policy_parameters(db, system_id, control_id) -> list[dict]:
    from app.models import ObservedConfigValue, OdpValue, Policy, PolicyFinding

    rows = []
    for o in db.scalars(select(OdpValue).where(OdpValue.system_id == system_id, OdpValue.control_id == control_id)):
        obs = db.scalar(select(ObservedConfigValue).where(ObservedConfigValue.system_id == system_id, ObservedConfigValue.control_id == control_id,
                                                          ObservedConfigValue.parameter == o.parameter).order_by(ObservedConfigValue.observed_at.desc()))
        pfs = []
        for pf, pol in db.execute(select(PolicyFinding, Policy).join(Policy, Policy.id == PolicyFinding.policy_id).where(
                PolicyFinding.system_id == system_id, PolicyFinding.control_id == control_id, PolicyFinding.parameter == o.parameter,
                PolicyFinding.status != "dismissed")):
            pfs.append({"id": str(pf.id), "status": pf.status, "type": pf.finding_type, "policy_id": str(pol.id), "policy": f"{pol.title} v{pol.version}",
                        "policy_value": pf.policy_value, "quote": pf.quote, "finding_id": str(pf.finding_id) if pf.finding_id else None})
        pol = next(iter(pfs), None)
        result = None if not obs else ("Match" if obs.numeric_value == o.numeric_value else "Mismatch")
        rows.append({"parameter": o.parameter, "odp_value": o.value, "odp_source": f"{pol['policy'] if pol else o.source}, approved {o.approved_at}",
                     "observed_value": obs.value if obs else None,
                     "observed_source": f"{obs.source}, collected {obs.observed_at:%Y-%m-%d}" if obs else None,
                     "observed_evidence_id": str(obs.evidence_id) if obs and obs.evidence_id else None, "result": result,
                     "policy_findings": pfs, "poams": [p for p in _control_poams(db, system_id, control_id)]})
    return rows


def _policies_for(db, system_id, control_id) -> list[str]:
    """Same source of truth as coverage/filters (pc.index over PolicyControlMap): approved mappings listed, proposed ones flagged."""
    from app.models import Policy
    from app.services import policy_coverage as pc

    e = pc.index(db, db.get(System, system_id)).get(control_id) or {}
    pols = {str(p.id): p for p in db.scalars(select(Policy).where(Policy.id.in_([uuid.UUID(i) for i in e.get("mapped", set()) | e.get("proposed", set())])))} if e else {}
    out = [f"{p.title} v{p.version}" + (f" (approved {p.approval_date})" if p.approval_date else "") for i, p in pols.items() if i in e["mapped"]]
    return out + [f"{p.title} v{p.version} (mapping proposed – not yet approved)" for i, p in pols.items() if i not in e["mapped"]]


def _control_poams(db, system_id, control_id) -> list[dict]:
    from sqlalchemy import cast, String
    from app.services.workflow import display_status

    rows = db.scalars(select(Poam).where(Poam.system_id == system_id, cast(Poam.control_ids, String).like(f'%"{control_id}"%')))
    return [{"id": str(p.id), "human_id": p.human_id, "weakness": p.weakness, "status": display_status(p), "due_date": p.due_date} for p in rows]


def build_grounding(db, system_id, a: ControlAssignment) -> dict:
    from app.api.v1.controls import get_control

    c = get_control(a.control_id, db)
    s = db.get(System, system_id)
    ev = db.execute(select(Evidence, EvidenceSource.name).join(EvidenceControl, EvidenceControl.evidence_id == Evidence.id)
                    .outerjoin(EvidenceSource, EvidenceSource.id == Evidence.source_id)
                    .where(EvidenceControl.assignment_id == a.id, Evidence.state.in_(("current", "near_expiration")))).all()
    fs = db.execute(select(Finding).join(FindingControlMap, FindingControlMap.finding_id == Finding.id)
                    .where(Finding.system_id == system_id, FindingControlMap.control_id == a.control_id).distinct()).scalars().all()
    by_ev: dict = {}
    for f in fs:
        if f.latest_evidence_id:
            e = by_ev.setdefault(str(f.latest_evidence_id), {"open": [], "passing": 0})
            if f.current_state == "open":
                e["open"].append(f"{f.vuln_id or f.plugin_id} {f.title} ({f.cat or f.severity})")
            elif f.current_state == "pass":
                e["passing"] += 1
    approved = db.scalar(select(Implementation).where(Implementation.assignment_id == a.id, Implementation.review_status == "approved"))
    prov = db.get(CommonControlProvider, a.provider_id) if a.provider_id else None
    return {
        "control": {"id": c.label, "title": c.title, "statement": c.statement,
                    "parameters": [p.get("rendered") or p.get("label") for p in (c.parameters or [])][:15],
                    "objectives": [o.prose for o in c.objectives if o.prose][:20]},
        "system": {"name": s.name, "acronym": s.acronym, "description": s.description, "boundary": s.boundary_description,
                   "environment": s.operating_environment, "data_classification": "SYNTHETIC demo"},
        "responsibility": {"responsibility": a.responsibility, "origin": a.origin, "provider": prov.name if prov else None},
        "evidence": [{"evidence_id": str(e.id), "name": e.name, "source": n, "type": e.evidence_type, "collected_at": e.collected_at.isoformat(),
                      "sha256": e.sha256[:16], "summary": {"open_findings_for_control": by_ev.get(str(e.id), {}).get("open", [])[:10],
                                                           "passing_checks_for_control": by_ev.get(str(e.id), {}).get("passing", 0)}}
                     for e, n in ev],
        "existing_approved_statement": approved.narrative if approved else None,
        "odp_ids": [p.get("id") for p in (c.parameters or [])],
        "policies_list": _policies_for(db, system_id, a.control_id),
        "open_poams": [p["human_id"] + ": " + p["weakness"] for p in _control_poams(db, system_id, a.control_id) if p["status"] not in ("closed", "risk_accepted")],
        "policies": "; ".join(_policies_for(db, system_id, a.control_id)) or "No policy linked to this control – do not assume any policy exists.",
    }


TEMPLATE_VERSION = "impl-template-1.0.0"


def template_draft(db, system_id, a: ControlAssignment, ctx: dict) -> dict:
    """Deterministic, versioned template engine (no AI): same sections + citations as the AI draft, built only from records."""
    from app.services.queue import fmt_control

    segs = _render_odps(db, system_id, a.control_id, {"statement": ctx["control"]["statement"],
                                                       "parameters": [{"id": p} for p in ctx.get("odp_ids", [])]})
    req = "".join(s["text"] if "text" in s else (s["value"] or s["original"]) for s in segs).strip()
    s, r, cid = ctx["system"], ctx["responsibility"], fmt_control(a.control_id)
    ev = ctx["evidence"]
    split = {"inherited": f"This control is fully inherited from {r['provider'] or 'the common control provider'}.",
             "shared": f"Responsibility is shared with {r['provider'] or 'a common control provider'}: the provider implements its portion; "
                       f"{s['acronym']} implements the system-specific portion described below.",
             }.get(r["responsibility"], f"{s['acronym']} implements this control directly (system-owned).")
    facts = [f"{s['name']} ({s['acronym']}) boundary: {s['boundary'] or 'not documented'}; environment: {s['environment'] or 'not documented'}.", split]
    facts += [f"Evidence {e['name']} ({e['type']}, collected {e['collected_at'][:10]}) [EV:{e['evidence_id']}]" for e in ev[:8]]
    open_items = [f"Open finding: {x}" for e in ev for x in e["summary"]["open_findings_for_control"]][:6] + [f"Open POA&M: {p}" for p in ctx["open_poams"]][:6]
    missing = []
    if not ev:
        missing.append("No current supporting evidence is linked to this control.")
    missing += [f"Organization-defined parameter not yet defined: {x['original']}" for x in segs if x.get("status") == "not yet defined"]
    if not ctx.get("policies_list"):
        missing.append("No governing policy is linked to this control.")
    narrative = "\n\n".join(filter(None, [
        f"{cid} – {ctx['control']['title']}. Requirement: {req}",
        f"{split} {s['name']} implements the requirement as follows: [describe mechanism, responsible role and frequency].",
        ("Supporting evidence: " + "; ".join(f"{e['name']} collected {e['collected_at'][:10]} [EV:{e['evidence_id']}]" for e in ev[:8]) + ".") if ev else None,
        ("Known gaps: " + "; ".join(open_items) + ".") if open_items else None,
        ("Governing policy: " + "; ".join(ctx["policies_list"]) + ".") if ctx.get("policies_list") else None]))
    return {"narrative": narrative, "verified_facts": facts, "interpretation": [], "missing_information": missing,
            "suggested_actions": (["Resolve or document the open findings/POA&Ms listed above."] if open_items else []) +
                                 ["Replace the bracketed placeholder with the actual mechanism, owner and frequency before requesting review."],
            "citations": [e["evidence_id"] for e in ev[:8]]}


@router.post("/systems/{system_id}/workbench/controls/{control_id}/ai-draft")
async def ai_draft(system_id: uuid.UUID, control_id: str, mode: str = "auto", db: Session = Depends(get_db),
                   current: CurrentUser = Depends(require_permission("implementation.write"))) -> dict:
    """mode=auto → AI when configured, otherwise the template engine; mode=template forces the template engine."""
    import json

    from app.services.ai.prompts import get_prompt
    from app.services.ai.service import AIOutputValidationError, get_ai_service

    from app.services.rmf import require_ai_use_case

    a = assignment_for(db, system_id, control_id)
    ctx = build_grounding(db, system_id, a)
    svc = get_ai_service()
    if mode == "template" or not svc.configured:
        out = template_draft(db, system_id, a, ctx)
        audit.record_now(action="implementation.template_draft", actor_user_id=current.user.id, actor_email=current.user.email,
                         entity_type="control_assignment", entity_id=str(a.id), details={"template_version": TEMPLATE_VERSION, "citations": out["citations"]})
        return {"draft": out, "stripped_citations": [], "provider": "template", "model": None, "prompt_id": "template", "prompt_version": TEMPLATE_VERSION,
                "interaction_id": None, "template": True, "label": "TEMPLATE DRAFT (no AI)",
                "ai_status": svc.describe(), "grounding": {"evidence_count": len(ctx["evidence"]), "policies": ctx["policies"], "open_poams": ctx["open_poams"]}}
    require_ai_use_case(db, current.user.org_id, "control.implementation_statement")
    try:
        res = await svc.run("control.implementation_statement", "1.0.0", {"context": json.dumps(ctx, default=str)}, actor_user_id=current.user.id)
    except AIOutputValidationError as exc:
        raise HTTPException(502, f"AI output failed validation: {exc}") from exc
    out = res.output.model_dump()
    valid = {e["evidence_id"] for e in ctx["evidence"]}
    stripped = [c for c in out["citations"] if c not in valid]
    out["citations"] = [c for c in out["citations"] if c in valid]
    for bad in stripped:
        out["narrative"] = out["narrative"].replace(f"[EV:{bad}]", "[citation removed: not in evidence]")
    audit.record_now(action="ai.implementation_draft", actor_user_id=current.user.id, actor_email=current.user.email,
                     entity_type="control_assignment", entity_id=str(a.id),
                     details={"interaction_id": str(res.interaction_id), "citations": out["citations"], "stripped_citations": stripped})
    pv = get_prompt("control.implementation_statement", "1.0.0")
    return {"draft": out, "stripped_citations": stripped, "provider": res.provider, "model": res.model, "latency_ms": res.latency_ms,
            "prompt_id": pv.prompt_id, "prompt_version": pv.version, "interaction_id": str(res.interaction_id),
            "grounding": {"evidence_count": len(ctx["evidence"]), "policies": ctx["policies"], "open_poams": ctx["open_poams"]},
            "label": "AI DRAFT – not reviewed"}


class ReviewReqIn(BaseModel):
    justification: str = Field(min_length=10, max_length=5000)


@router.post("/systems/{system_id}/workbench/implementations/{impl_id}/request-review", status_code=201)
def request_impl_review(system_id: uuid.UUID, impl_id: uuid.UUID, body: ReviewReqIn, db: Session = Depends(get_db),
                        current: CurrentUser = Depends(require_permission("implementation.write"))) -> dict:
    from app.services.workflow import create_request

    impl = db.get(Implementation, impl_id)
    a = db.get(ControlAssignment, impl.assignment_id) if impl else None
    if a is None or a.system_id != system_id:
        raise HTTPException(404, "Implementation version not found")
    if impl.review_status != "draft":
        raise HTTPException(409, f"Version is {impl.review_status}")
    req = create_request(db, system=get_system(db, system_id), requester=current.user, request_type="control_implementation_review",
                         justification=body.justification, control_id=a.control_id, implementation_id=impl.id,
                         evidence_ids=impl.citations or [])
    impl.review_status = "in_review"
    db.commit()
    return to_dict(req)


class NarrativeIn(BaseModel):
    narrative: str = Field(min_length=1, max_length=20000)
    implementation_status: str = Field(pattern="^(planned|partially_implemented|implemented|not_applicable|inherited|not_implemented)$")
    ai_generated: bool = False
    prompt_version: str | None = Field(None, max_length=50)
    interaction_id: uuid.UUID | None = None
    ai_interaction_id: uuid.UUID | None = None
    ai_sections: dict | None = None
    citations: list[str] = []


@router.put("/systems/{system_id}/workbench/controls/{control_id}/implementation")
def save_narrative(system_id: uuid.UUID, control_id: str, body: NarrativeIn, request: Request, db: Session = Depends(get_db),
                   current: CurrentUser = Depends(require_permission("implementation.write"))) -> dict:
    a = assignment_for(db, system_id, control_id)
    latest = db.scalar(select(func.max(Implementation.version)).where(Implementation.assignment_id == a.id)) or 0
    for i in db.scalars(select(Implementation).where(Implementation.assignment_id == a.id, Implementation.is_current.is_(True))):
        i.is_current = False
    from app.models import AIInteraction
    from app.services.workflow import evidence_in_system

    iid = body.interaction_id or body.ai_interaction_id
    if iid and not db.get(AIInteraction, iid):
        raise HTTPException(422, "interaction_id does not reference a logged AI interaction")
    if body.ai_generated and not iid:
        raise HTTPException(422, "AI-generated versions must include the interaction_id returned by the generate endpoint")

    impl = Implementation(assignment_id=a.id, version=latest + 1, narrative=body.narrative, implementation_status=body.implementation_status,
                          author_id=current.user.id, review_status="draft", ai_generated=body.ai_generated, prompt_version=body.prompt_version,
                          ai_interaction_id=iid, ai_sections=body.ai_sections,
                          citations=evidence_in_system(db, system_id, body.citations))
    db.add(impl)
    before = a.implementation_status
    a.implementation_status = body.implementation_status
    audit.record(db, action="implementation.saved", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="control_assignment",
                 entity_id=str(a.id), before={"implementation_status": before, "version": latest},
                 after={"implementation_status": body.implementation_status, "version": latest + 1, "ai_generated": body.ai_generated,
                        "prompt_version": body.prompt_version}, **audit.request_meta(request))
    db.flush()
    evaluate_system(db, system_id)
    db.commit()
    return to_dict(impl)


class StatusIn(BaseModel):
    implementation_status: str = Field(pattern="^(planned|partially_implemented|implemented|not_applicable|inherited|not_implemented)$")


@router.put("/systems/{system_id}/workbench/controls/{control_id}/status")
def save_status(system_id: uuid.UUID, control_id: str, body: StatusIn, request: Request, db: Session = Depends(get_db),
                current: CurrentUser = Depends(require_permission("implementation.write"))) -> dict:
    a = assignment_for(db, system_id, control_id)
    before = a.implementation_status
    a.implementation_status = body.implementation_status
    audit.record(db, action="implementation.status_changed", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="control_assignment",
                 entity_id=str(a.id), before={"implementation_status": before}, after={"implementation_status": body.implementation_status},
                 **audit.request_meta(request))
    db.flush()
    evaluate_system(db, system_id)
    db.commit()
    return {"implementation_status": a.implementation_status, "status_last_changed": _status_last_changed(db, a)}


def _cnssi_parameters(db: Session, s, cid: str) -> dict | None:
    from app.services import cnssi_params

    return cnssi_params.control_view(db, s, cid)


def _selection_basis(s, a: ControlAssignment) -> str | None:
    from app.services import cnssi1253

    tri = cnssi1253.applied(s)
    return cnssi1253.basis(a.control_id, tri) if tri else None



def _status_last_changed(db: Session, a: ControlAssignment) -> dict | None:
    from app.models import AuditEvent, User
    ev = db.scalar(select(AuditEvent).where(AuditEvent.entity_id == str(a.id), AuditEvent.action.in_(("implementation.status_changed", "implementation.saved")))
                   .order_by(AuditEvent.occurred_at.desc()).limit(1))
    if ev is None:
        return None
    u = db.get(User, ev.actor_user_id) if ev.actor_user_id else None
    return {"by": u.display_name if u else ev.actor_email, "email": ev.actor_email, "at": ev.occurred_at.isoformat(), "action": ev.action}


def _policy_mappings(db: Session, a: ControlAssignment) -> list[dict]:
    from app.models import Policy, PolicyControlMap as PCM
    s = db.get(System, a.system_id)
    ids = {a.control_id, a.control_id.split(".")[0]}
    rows = db.execute(select(PCM, Policy).join(Policy, Policy.id == PCM.policy_id)
                      .where(PCM.org_id == s.org_id, PCM.control_id.in_(ids), PCM.valid_to.is_(None), PCM.status.in_(("mapped", "proposed")),
                             Policy.status == "current")).all()
    out = [{**to_dict(m), "policy_title": p.title, "policy_version": p.version} for m, p in rows if not p.system_ids or str(s.id) in p.system_ids]
    return attach(db, out, "decided_by", "decider")


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


@router.post("/systems/{system_id}/workbench/controls/{control_id}/comments", status_code=201)
def add_comment(system_id: uuid.UUID, control_id: str, body: CommentIn, db: Session = Depends(get_db),
                current: CurrentUser = Depends(require_permission("comment.write"))) -> dict:
    a = assignment_for(db, system_id, control_id)
    c = ReviewerComment(assignment_id=a.id, author_id=current.user.id, author_email=current.user.email, body=body.body)
    db.add(c)
    audit.record(db, action="comment.added", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="control_assignment", entity_id=str(a.id))
    db.commit()
    return to_dict(c)


@router.get("/priority-weights")
def priority_weights(db: Session = Depends(get_db), _: CurrentUser = Depends(get_current_user)) -> list[dict]:
    return [to_dict(w) for w in db.scalars(select(PriorityWeight).order_by(PriorityWeight.weight.desc()))]


@router.get("/dashboard/leadership")
def leadership(db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("portfolio.read"))) -> dict:
    from datetime import date, timedelta

    if current.operator is not None and not (current.operator.onboarding or {}).get("view_leadership"):
        audit.record(db, action="leadership.viewed", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="organization",
                     entity_id=str(current.user.org_id))
        current.operator.onboarding = {**(current.operator.onboarding or {}), "view_leadership": True}
        db.commit()

    from app.services.evaluation import OP_WEIGHTS
    from app.services.workflow import ACTIVE_POAM

    systems = visible_systems(db, current)
    rows = [{"id": s.id, "name": s.name, "acronym": s.acronym, "baseline": s.baseline_key, "lifecycle_phase": s.lifecycle_phase,
             "authorization_expiration": s.authorization_expiration, **system_metrics(db, s)} for s in systems]
    rows.sort(key=lambda r: -r["op_score"])
    cwe = sum(r["controls_with_evidence"] or 0 for r in rows)
    cf = sum(r["controls_fresh"] or 0 for r in rows)
    tot = lambda k: sum(r[k] or 0 for r in rows)  # noqa: E731
    cards = {"systems_total": len(rows),
             "systems_authorized": sum(1 for r in rows if r["authorization_status"].startswith("Authorized")),
             "systems_in_assessment": sum(1 for r in rows if "assessment" in r["authorization_status"].lower()),
             "auth_expiring_90d": sum(1 for r in rows if r["days_to_expiration"] is not None and r["days_to_expiration"] <= 90),
             "open_cat1": tot("open_cat1"), "kev_open": tot("kev_open"), "open_findings": tot("open_findings"),
             "overdue_poams": tot("overdue_poams"), "open_poams": tot("open_poams"), "risk_acceptances": tot("risk_acceptances"),
             "pending_risk_decisions": tot("pending_risk_decisions"),
             "evidence_fresh_pct": round(100 * cf / tot("assigned_controls"), 1) if tot("assigned_controls") else None,
             "control_evidence_coverage_pct": round(100 * cf / tot("assigned_controls"), 1) if tot("assigned_controls") else None,
             "controls_with_current_evidence": cf, "assigned_controls": tot("assigned_controls"),
             "evidence_items_fresh_pct": round(100 * tot("evidence_items_fresh") / tot("evidence_total"), 1) if tot("evidence_total") else None,
             "evidence_items_fresh": tot("evidence_items_fresh"), "evidence_total": tot("evidence_total"),
             "pending_emass_sync": tot("pending_emass_sync"), "controls_stale": tot("controls_stale")}
    _ = cwe
    trend = [{"taken_at": t.taken_at, "synthetic": t.is_synthetic, **t.metrics} for t in db.scalars(
        select(RiskSnapshot).where(RiskSnapshot.org_id == current.user.org_id, RiskSnapshot.system_id.is_(None)).order_by(RiskSnapshot.taken_at))]
    roles = {a.role for a in current.assignments}
    sids = [s.id for s in systems]
    waiting = []
    for r in db.scalars(select(ApprovalRequest).where(ApprovalRequest.system_id.in_(sids), ApprovalRequest.status == "pending",
                                                      ApprovalRequest.assigned_role.in_(roles), ApprovalRequest.requester_id != current.user.id)):
        waiting.append({"kind": "review", "label": f"{r.human_id} {r.request_type.replace('_', ' ')} awaiting {r.assigned_role.upper()}",
                        "link": f"/reviews/{r.id}", "due": r.deadline})
    if "ao" in roles:
        for r in rows:
            if r["days_to_expiration"] is not None and r["days_to_expiration"] <= 90:
                waiting.append({"kind": "authorization", "label": f"{r['acronym']} authorization expires in {r['days_to_expiration']} days",
                                "link": f"/systems/{r['id']}", "due": r["authorization_expiration"]})
    soon = date.today() + timedelta(days=14)
    for p in db.scalars(select(Poam).where(Poam.system_id.in_(sids), Poam.status.in_(ACTIVE_POAM), Poam.due_date <= soon,
                                           Poam.severity.in_(("critical", "high")))):
        waiting.append({"kind": "poam", "label": f"{p.human_id} ({p.severity}) due {p.due_date}", "link": f"/poams/{p.id}", "due": p.due_date})
    weights = {w.reason_code: w.weight for w in db.scalars(select(PriorityWeight).where(PriorityWeight.reason_code.like("sys_%")))}
    return {"cards": cards, "systems": rows, "trend": trend, "waiting_on_you": waiting,
            "op_score": {"label": "Operational prioritization – not a formal residual risk determination",
                         "weights": [{"code": k, "weight": weights.get(k, w), "description": d} for k, (w, d) in OP_WEIGHTS.items()]},
            "note": "Cards/table computed live from DB; trend reads stored risk_snapshots (written after every workflow event)."}


@router.post("/admin/demo/reset")
def reset_demo_data(request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("demo.tools"))) -> dict:
    import os

    from app.seed_phase1 import reset_demo

    org = db.get(Organization, current.user.org_id)
    if not org.is_synthetic or not os.environ.get("SAMPLES_DIR"):
        raise HTTPException(409, "Reset is only available for the synthetic demo tenant with SAMPLES_DIR configured")
    reset_demo(db, org, os.environ["SAMPLES_DIR"])
    audit.record(db, action="demo.reset", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="organization",
                 entity_id=str(org.id), details={"demo_tool": True}, **audit.request_meta(request))
    db.commit()
    return {"ok": True}


_ = (Cci, CciControlMap)
