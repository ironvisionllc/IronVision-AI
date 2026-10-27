"""Unified Mapping Review queue: automated STIG→CCI→control mappings, Policy Auditor proposals and evidence-based status
suggestions. Nothing here changes a status or mapping by itself – every item waits for a human decision."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (ControlAssignment, Evidence, EvidenceControl, Finding, FindingControlMap, Policy, PolicyControlMap, System)
from app.services.evaluation import FRESH_OK
from app.services.rmf import get_setting, set_setting

DISMISSED = "status_suggestions_dismissed"


def now() -> datetime:
    return datetime.now(timezone.utc)


def automated_maps(db: Session, system_id) -> list[dict]:
    rows = db.execute(select(FindingControlMap, Finding).join(Finding, Finding.id == FindingControlMap.finding_id)
                      .where(Finding.system_id == system_id, FindingControlMap.valid_to.is_(None),
                             FindingControlMap.review_status == "auto_from_authoritative_source")).all()
    groups: dict = {}
    for m, f in rows:
        rule = f.vuln_id or f.rule_id or f.plugin_id
        g = groups.setdefault((rule, m.control_id), {"kind": "finding_map", "key": f"fm:{rule}:{m.control_id}", "control_id": m.control_id, "ids": [],
                                                    "title": f"{rule} – {f.title}", "source": "STIG rule → DISA CCI → NIST control (automated)",
                                                    "confidence": "Authoritative crosswalk", "reasoning": f"The STIG rule lists {m.cci_id or 'a CCI'}, which DISA maps to this control.",
                                                    "evidence": [], "open": 0})
        g["ids"].append(str(m.id))
        g["open"] += f.current_state == "open"
    if groups:  # legitimately new: the same rule → control was approved before for other findings (new host / new checklist)
        appr = {}
        for m, f in db.execute(select(FindingControlMap, Finding).join(Finding, Finding.id == FindingControlMap.finding_id)
                               .where(Finding.system_id == system_id, FindingControlMap.review_status == "human_approved")):
            appr[(f.vuln_id or f.rule_id or f.plugin_id, m.control_id)] = m.reviewed_at
        for k, g in groups.items():
            if k in appr:
                g["why_new"] = (f"New review: this rule → control was approved{' on ' + appr[k].date().isoformat() if appr[k] else ''}; "
                                f"{len(g['ids'])} new finding mapping(s) from a later checklist/host need their own decision")
    return list(groups.values())


def policy_proposals(db: Session, system: System) -> list[dict]:
    rows = db.execute(select(PolicyControlMap, Policy).join(Policy, Policy.id == PolicyControlMap.policy_id)
                      .where(PolicyControlMap.org_id == system.org_id, PolicyControlMap.valid_to.is_(None), PolicyControlMap.status == "proposed",
                             Policy.status == "current")).all()
    # why a proposal is legitimately new although the same control was approved before (e.g. a new policy version re-proposes it)
    prior = {}
    for m, p in db.execute(select(PolicyControlMap, Policy).join(Policy, Policy.id == PolicyControlMap.policy_id)
                           .where(PolicyControlMap.org_id == system.org_id, PolicyControlMap.status == "mapped")):
        prior.setdefault((p.title, m.control_id), p.version)
    out = [{"kind": "policy_map", "key": f"pm:{m.id}", "ids": [str(m.id)], "control_id": m.control_id, "title": f"Policy “{p.title}” v{p.version}",
             "not_selected": ((p.analysis or {}).get("not_selected") or {}).get(m.control_id),
             "group": "not_selected" if ((p.analysis or {}).get("not_selected") or {}).get(m.control_id) else "proposal",
             "policy_id": str(p.id), "source": "Policy Auditor", "confidence": m.confidence, "reasoning": m.basis, "snippets": m.snippets or [], "evidence": [],
             **({"why_new": f"New review: approved for v{prior[(p.title, m.control_id)]}; policy version v{p.version} must be reviewed on its own"}
                if (p.title, m.control_id) in prior else {})}
            for m, p in rows if not p.system_ids or str(system.id) in p.system_ids]
    return sorted(out, key=lambda x: x["group"] == "not_selected")  # "Policy states not selected – confirm" grouped after normal proposals


def status_suggestions(db: Session, system: System) -> list[dict]:
    dismissed = get_setting(db, system.org_id, DISMISSED, {}).get(str(system.id), {})
    open_ctl = set(db.scalars(select(FindingControlMap.control_id).join(Finding, Finding.id == FindingControlMap.finding_id)
                              .where(Finding.system_id == system.id, Finding.current_state == "open", FindingControlMap.valid_to.is_(None),
                                     FindingControlMap.review_status != "rejected")))
    out = []
    for a in db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == system.id, ControlAssignment.evidence_freshness_status.in_(FRESH_OK))):
        if a.control_id in open_ctl or a.implementation_status in ("not_applicable", "inherited"):
            continue
        if a.implementation_status == "implemented" and a.assessment_status == "satisfied":
            continue
        evs = db.execute(select(Evidence.id, Evidence.file_name, Evidence.collected_at).join(EvidenceControl, EvidenceControl.evidence_id == Evidence.id)
                         .where(EvidenceControl.assignment_id == a.id, Evidence.evidence_type != "policy")  # a policy document is not passing technical evidence
                         .order_by(Evidence.collected_at.desc()).limit(5)).all()
        if not evs:
            continue
        fp = ",".join(sorted(str(e.id) for e in evs))
        if dismissed.get(a.control_id, {}).get("evidence") == fp:
            continue
        sca_only = a.implementation_status == "implemented"
        out.append({"kind": "status", "key": f"st:{a.control_id}", "ids": [str(a.id)], "control_id": a.control_id, "awaiting_sca": sca_only,
                    "next_actor": "SCA (assessor) confirms Satisfied" if sca_only else "ISSO / ISSM approve the implementation",
                    "title": (f"{a.control_id.upper()}: implementation approved – waiting for the SCA to confirm Satisfied" if sca_only
                              else f"Set {a.control_id.upper()} to Implemented + Satisfied"), "source": "Evidence-based status suggestion",
                    "confidence": "Suggestion", "current": {"implementation": a.implementation_status, "assessment": a.assessment_status},
                    "reasoning": f"{len(evs)} current evidence item(s) pass and no open finding is mapped to this control. "
                                 "Approving sets Implementation → Implemented; Assessment → Satisfied only if you hold the assessor (SCA) role.",
                    "evidence": [{"id": str(e.id), "file_name": e.file_name, "collected_at": e.collected_at.isoformat() if e.collected_at else None} for e in evs],
                    "evidence_fp": fp})
    return out


def dismiss_status(db: Session, system: System, control_id: str, fp: str, actor, justification: str) -> None:
    all_ = get_setting(db, system.org_id, DISMISSED, {})
    all_.setdefault(str(system.id), {})[control_id] = {"evidence": fp, "by": actor.email, "at": now().isoformat(), "justification": justification}
    set_setting(db, system.org_id, DISMISSED, all_)


def decide_finding_maps(db: Session, ids: list[str], action: str, actor, justification: str, system_id, edit_ids: list[str]) -> list[str]:
    done = []
    for i in ids:
        m = db.get(FindingControlMap, uuid.UUID(i))
        f = db.get(Finding, m.finding_id) if m else None
        if m is None or f is None or f.system_id != system_id or m.valid_to is not None:
            continue
        m.reviewed_by, m.reviewed_at, m.justification = actor.id, now(), justification or m.justification
        if action == "approve":
            m.review_status = "human_approved"
        else:
            m.review_status, m.valid_to = "rejected", now()
            for c in edit_ids if action == "edit" else []:
                db.add(FindingControlMap(finding_id=f.id, control_id=c, cci_id=m.cci_id, mapping_source="human_edit", review_status="human_approved",
                                         confidence="human_confirmed", justification=justification, mapped_by=actor.id, content_version_id=m.content_version_id))
        done.append(m.control_id)
    db.flush()
    return done
