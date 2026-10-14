"""ISSO work queue: lanes (needs action now / due soon / backlog) mixing control, POA&M, attestation, policy and review items.
One scoring function (score_poam / control priority_score) is shared with the POA&M list default sort."""
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (ApprovalRequest, Attestation, Control, ControlAssignment, Poam, PoamMilestone, Policy, PolicyFinding, RoleAssignment, System)

SEV_RANK = {"CAT I": 0, "critical": 0, "high": 1, "CAT II": 1, "medium": 2, "CAT III": 2, "low": 3}
BACKLOG_CODES = {"missing_implementation_statement", "missing_assessment_evidence", "responsibility_split_missing"}
ACTION_CODES = {"failed_technical_checks", "cat1_open", "kev", "expired_evidence", "catalog_change"}


def fmt_control(cid: str | None) -> str:
    """eMASS/NIST display form: ac-2.3 → AC-2(3)."""
    if not cid:
        return ""
    base, *enh = cid.split(".")
    return base.upper() + "".join(f"({e})" for e in enh)


def score_poam(p: Poam, today: date | None = None) -> tuple[float, list[dict]]:
    today = today or date.today()
    parts = [{"code": "severity", "label": p.cat or p.severity or "unrated",
              "points": {"CAT I": 10, "CAT II": 5, "CAT III": 2}.get(p.cat or "", {"critical": 10, "high": 8, "medium": 5, "low": 2}.get(p.severity or "", 1))}]
    if p.due_date and p.due_date < today and p.status in ("new", "in_progress"):
        parts.append({"code": "overdue", "label": f"overdue {(today - p.due_date).days}d", "points": 8 + min((today - p.due_date).days // 15, 6)})
    elif p.due_date and p.due_date <= today + timedelta(days=7):
        parts.append({"code": "due_7d", "label": f"due {p.due_date}", "points": 4})
    if any(str(v).upper().startswith("CVE") for v in (p.vuln_ids or [])) and p.cat == "CAT I":
        parts.append({"code": "cve_cat1", "label": "CVE on CAT I", "points": 2})
    if p.status == "closure_eligible":
        parts.append({"code": "closure_eligible", "label": "closure eligible – awaiting action", "points": 3})
    return float(sum(x["points"] for x in parts)), parts


def _item(kind, title, link, score, reasons, *, control_id=None, system_id=None, severity=None, due=None, kev=False, age=0, ref=None, owner_id=None):
    return {"kind": kind, "title": title, "link": link, "score": score, "reasons": reasons, "control_id": control_id,
            "control_label": fmt_control(control_id), "control_link": f"/systems/{system_id}/controls/{control_id}" if control_id else None,
            "severity": severity, "due": due, "kev": kev, "age_days": age, "ref": ref, "owner_id": str(owner_id) if owner_id else None}


def _sort_key(i):
    return (-i["score"], SEV_RANK.get(i["severity"] or "", 9), i["due"] or date.max, not i["kev"], -i["age_days"], i["ref"] or i["title"])


def work_queue(db: Session, system: System, user, roles_here: set[str], mine: bool) -> dict:
    today, sid = date.today(), system.id
    now_items, soon, backlog = [], [], defaultdict(list)
    ctl_titles = dict(db.execute(select(ControlAssignment.control_id, Control.title).join(Control, Control.id == ControlAssignment.control_uuid)
                                 .where(ControlAssignment.system_id == sid)).all())
    owns_controls = bool(roles_here & {"isso", "system_owner"})
    for a in db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == sid)):
        rs = a.reasons or []
        act = [r for r in rs if r["code"] in ACTION_CODES]
        if a.evidence_freshness_status == "partially_stale" and not any(r["code"] == "expired_evidence" for r in act):
            act.append({"code": "expired_evidence", "points": 2, "detail": "partially stale evidence"})
        if act:
            now_items.append(_item("control", f"{fmt_control(a.control_id)} {ctl_titles.get(a.control_id, '')}", f"/systems/{sid}/controls/{a.control_id}",
                                   float(a.priority_score or 0), rs, control_id=a.control_id, system_id=sid,
                                   severity="CAT I" if any(r["code"] == "cat1_open" for r in rs) else None, kev=any(r["code"] == "kev" for r in rs),
                                   ref=a.control_id, owner_id=user.id if owns_controls else None))
        elif a.evidence_freshness_status == "near_expiration":
            soon.append(_item("evidence", f"{fmt_control(a.control_id)} evidence nearing expiry", f"/systems/{sid}/controls/{a.control_id}", 1.0,
                              [{"code": "near_expiration", "points": 1}], control_id=a.control_id, system_id=sid, ref=a.control_id,
                              owner_id=user.id if owns_controls else None))
        missing = [r for r in rs if r["code"] in BACKLOG_CODES]
        if missing and not act:
            backlog[a.control_id.split("-")[0].upper()].append({"control_id": a.control_id, "control_label": fmt_control(a.control_id),
                                                                "title": ctl_titles.get(a.control_id, ""), "reasons": [r["code"] for r in missing],
                                                                "link": f"/systems/{sid}/controls/{a.control_id}"})
    from app.services.workflow import ACTIVE_POAM
    for p in db.scalars(select(Poam).where(Poam.system_id == sid, Poam.status.in_(ACTIVE_POAM))):
        sc, parts = score_poam(p, today)
        cid = (p.control_ids or [None])[0]
        it = _item("poam", f"{p.human_id} {p.weakness[:120]}", f"/poams/{p.id}", sc, parts, control_id=cid, system_id=sid, severity=p.cat or p.severity,
                   due=p.due_date, age=(today - p.created_at.date()).days, ref=p.human_id, owner_id=p.owner_id or p.created_by)
        if any(x["code"] in ("overdue", "due_7d", "closure_eligible") for x in parts):
            now_items.append(it)
        elif p.due_date and p.due_date <= today + timedelta(days=30):
            soon.append(it)
    for m, p in db.execute(select(PoamMilestone, Poam).join(Poam, Poam.id == PoamMilestone.poam_id).where(
            Poam.system_id == sid, PoamMilestone.status != "completed", PoamMilestone.due_date.is_not(None),
            PoamMilestone.due_date <= today + timedelta(days=30))):
        soon.append(_item("milestone", f"{p.human_id} milestone: {m.title[:100]}", f"/poams/{p.id}", 2.0, [{"code": "milestone_due", "points": 2}],
                          control_id=(p.control_ids or [None])[0], system_id=sid, due=m.due_date, ref=p.human_id, owner_id=p.owner_id))
    for a in db.scalars(select(Attestation).where(Attestation.system_id == sid, Attestation.status.in_(("pending", "expired")))):
        overdue = a.status == "expired" or (a.due_date and a.due_date < today)
        it = _item("attestation", f"Attestation {fmt_control(a.control_id)} v{a.version} {'expired' if a.status == 'expired' else 'due'}", "/inheritance",
                   7.0 if overdue else 2.0, [{"code": "attestation_overdue" if overdue else "attestation_due", "points": 7 if overdue else 2}],
                   control_id=a.control_id, system_id=sid, due=a.due_date, ref=f"att-{a.control_id}-{a.version}", owner_id=a.owner_id)
        if overdue:
            now_items.append(it)
        elif a.due_date and a.due_date <= today + timedelta(days=30):
            soon.append(it)
    for pf, pol in db.execute(select(PolicyFinding, Policy).join(Policy, Policy.id == PolicyFinding.policy_id).where(
            PolicyFinding.system_id == sid, PolicyFinding.status.in_(("proposed", "confirmed")))):
        mism = pf.finding_type in ("odp_not_met", "policy_vs_config_difference")
        if not mism and pf.status != "proposed":
            continue
        label = f"{fmt_control(pf.control_id)} policy {'mismatch' if mism else 'finding'}: {pf.policy_value or ''}" + (
            f" vs {pf.observed_value or pf.odp_value}" if mism else f" {pf.description[:80]}")
        now_items.append(_item("policy_finding", label + (" (proposed)" if pf.status == "proposed" else " (confirmed)"), f"/policy-auditor/{pol.id}",
                               6.0 if mism else 3.0, [{"code": f"policy_{pf.status}", "points": 6 if mism else 3}], control_id=pf.control_id, system_id=sid,
                               ref=str(pf.id), owner_id=user.id if owns_controls else None))
    for r in db.scalars(select(ApprovalRequest).where(ApprovalRequest.system_id == sid, ApprovalRequest.status.in_(("pending", "returned", "more_evidence_requested")))):
        to_me = r.status == "pending" and r.assigned_role in roles_here and r.requester_id != user.id
        back = r.status in ("returned", "more_evidence_requested")
        if not (to_me or back):
            continue
        it = _item("review", f"{r.human_id} {r.request_type.replace('_', ' ')} {'returned to requester' if back else 'awaiting ' + (r.assigned_role or '').upper()}",
                   f"/reviews/{r.id}", 5.0, [{"code": "review_returned" if back else "review_assigned", "points": 5}], control_id=r.control_id,
                   system_id=sid, due=r.deadline, ref=r.human_id, owner_id=r.requester_id if back else (user.id if to_me else None))
        (now_items if not r.deadline or r.deadline <= today + timedelta(days=7) else soon).append(it)
    for c in db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == sid, ControlAssignment.content_change.is_not(None))):
        pass  # catalog/STIG changes surface through the control's catalog_change reason above
    if mine:
        me = str(user.id)
        now_items = [i for i in now_items if i["owner_id"] == me]
        soon = [i for i in soon if i["owner_id"] == me]
    now_items.sort(key=_sort_key)
    soon.sort(key=lambda i: (i["due"] or date.max, _sort_key(i)))
    fams = [{"family": f, "count": len(v), "controls": sorted(v, key=lambda x: x["control_id"])} for f, v in sorted(backlog.items())]
    return {"lanes": {"needs_action": now_items, "due_soon": soon, "backlog": fams},
            "counts": {"needs_action": len(now_items), "due_soon": len(soon), "backlog": sum(f["count"] for f in fams)},
            "mine": mine, "tie_break": "score ↓, severity, due date, KEV first, age ↓, id",
            "scoring": "Controls: weighted reason points (Admin → priority weights). POA&Ms: severity + overdue + due ≤7d + closure-eligible (same function as the POA&M list default sort)."}
