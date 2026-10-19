"""Control evaluation (monitoring/freshness/queue), evidence freshness + integrity, risk snapshots.
assessment_status is NEVER changed here: only an SCA assessment may set it."""
import hashlib
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import (ControlAssignment, Evidence, EvidenceControl, Finding, FindingControlMap, FreshnessPolicy,
                        Implementation, IntegrityCheck, Organization, PriorityWeight, RiskSnapshot, System)
from app.services.storage import get_storage



def now() -> datetime:
    return datetime.now(timezone.utc)


def _policy_for(policies: list[FreshnessPolicy], ev: Evidence, source_type: str | None) -> FreshnessPolicy | None:
    for p in policies:
        if p.evidence_type and p.evidence_type == ev.evidence_type:
            return p
    for p in policies:
        if p.source_type and p.source_type == source_type:
            return p
    return None


STALE = ("expired", "integrity_mismatch", "signature_invalid", "unverified")
FRESH_OK = ("current", "near_expiration")


def apply_freshness(db: Session, ev: Evidence, policies: list[FreshnessPolicy] | None = None) -> str:
    """Freshness is independent of signature: unsigned-but-hashed evidence is 'current' inside its window.
    'unverified' only when integrity could not be established (no hash recorded / storage read failed)."""
    from app.models import EvidenceSource

    policies = policies if policies is not None else list(db.scalars(select(FreshnessPolicy)))
    src = db.get(EvidenceSource, ev.source_id) if ev.source_id else None
    p = _policy_for(policies, ev, src.source_type if src else None)
    window = p.window_days if p else 30
    pct = p.near_expiration_pct if p else 20
    age = (now() - ev.collected_at).total_seconds() / 86400
    if ev.integrity_status == "mismatch":
        state = "integrity_mismatch"
    elif ev.signature_status == "invalid":
        state = "signature_invalid"
    elif ev.signature_status == "attestation_expired":
        state = "expired"
    elif ev.integrity_status not in ("hash_recorded", "verified"):
        state = "unverified"
    elif age > window:
        state = "expired"
    elif age > window * (1 - pct / 100):
        state = "near_expiration"
    else:
        state = "current"
    ev.state, ev.freshness_window_days = state, window
    return state


def evaluate_freshness(db: Session, system_id=None) -> dict:
    policies = list(db.scalars(select(FreshnessPolicy)))
    q = select(Evidence)
    if system_id:
        q = q.where(Evidence.system_id == system_id)
    counts = defaultdict(int)
    systems = set()
    for ev in db.scalars(q):
        counts[apply_freshness(db, ev, policies)] += 1
        systems.add(ev.system_id)
    db.flush()
    for sid in systems:
        evaluate_system(db, sid)
    return dict(counts)


def verify_integrity(db: Session, system_id=None, job_id=None) -> dict:
    store = get_storage()
    q = select(Evidence)
    if system_id:
        q = q.where(Evidence.system_id == system_id)
    ok = bad = 0
    for ev in db.scalars(q):
        try:
            actual = hashlib.sha256(store.get(ev.storage_key)).hexdigest()
            detail = None
        except Exception as exc:
            actual, detail = None, f"read failed: {exc}"[:500]
        good = actual == ev.sha256
        db.add(IntegrityCheck(evidence_id=ev.id, job_id=job_id, expected_sha256=ev.sha256, actual_sha256=actual, ok=good, detail=detail))
        ev.integrity_status = "verified" if good else ("unverified" if actual is None else "mismatch")
        ev.last_verified_at = now()
        ok, bad = ok + good, bad + (not good)
    db.flush()
    evaluate_freshness(db, system_id)
    return {"checked": ok + bad, "ok": ok, "mismatched": bad}


STATEMENT_RULE = ("A control HAS an implementation statement when it has an approved version, or its current version is non-blank "
                  "and submitted for review (in_review). Blank/placeholder or unsubmitted drafts count as MISSING. Inherited controls are exempt.")


def statement_map(db: Session, system_id) -> dict:
    """Single shared definition used by the ISSO queue, RMF workflow and metrics: {assignment_id: has|draft|missing}."""
    out: dict = {}
    for aid, narr, rs, cur in db.execute(select(Implementation.assignment_id, Implementation.narrative, Implementation.review_status, Implementation.is_current)
                                         .join(ControlAssignment, ControlAssignment.id == Implementation.assignment_id)
                                         .where(ControlAssignment.system_id == system_id)):
        blank = not (narr or "").strip()
        st = "has" if (rs == "approved" and not blank) or (cur and rs == "in_review" and not blank) else ("draft" if cur and not blank else None)
        if st == "has" or (st and out.get(aid) != "has"):
            out[aid] = st
    return out


def mark_superseded(db: Session, system_id) -> None:
    """Older evidence from the same source + artifact name is 'superseded' (a newer version exists) – never counted as expired."""
    newest: dict = {}
    for ev in db.scalars(select(Evidence).where(Evidence.system_id == system_id).order_by(Evidence.collected_at.desc())):
        k = (ev.source_id, ev.name)
        if ev.source_id is None or k not in newest:
            newest[k] = ev.id
            if ev.state == "superseded":
                apply_freshness(db, ev)
        elif ev.state not in ("integrity_mismatch", "signature_invalid"):
            ev.state = "superseded"
    db.flush()


def config_observations(db: Session, system_id) -> dict:
    """Observed configuration values vs approved ODPs per control; links the config evidence to the control (EvidenceControl)."""
    from app.models import ObservedConfigValue, OdpValue

    out: dict = defaultdict(list)
    odps = {(o.control_id, o.parameter): o for o in db.scalars(select(OdpValue).where(OdpValue.system_id == system_id))}
    assigns = {a.control_id: a.id for a in db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == system_id))}
    seen = set()
    for o in db.scalars(select(ObservedConfigValue).where(ObservedConfigValue.system_id == system_id).order_by(ObservedConfigValue.observed_at.desc())):
        if (o.control_id, o.parameter) in seen:
            continue
        seen.add((o.control_id, o.parameter))
        odp = odps.get((o.control_id, o.parameter))
        out[o.control_id].append({"parameter": o.parameter, "observed": o, "odp": odp,
                                  "mismatch": bool(odp and odp.numeric_value is not None and o.numeric_value != odp.numeric_value)})
        aid = assigns.get(o.control_id)
        if aid and o.evidence_id and not db.scalar(select(EvidenceControl.id).where(EvidenceControl.evidence_id == o.evidence_id,
                                                                                     EvidenceControl.assignment_id == aid)):
            db.add(EvidenceControl(evidence_id=o.evidence_id, assignment_id=aid))
    db.flush()
    return out


def evaluate_system(db: Session, system_id) -> None:
    from app.services.responsibility import apply_to_system, split_missing

    mark_superseded(db, system_id)
    apply_to_system(db, system_id)
    cfg = config_observations(db, system_id)
    weights = {w.reason_code: w.weight for w in db.scalars(select(PriorityWeight))}
    stats = defaultdict(lambda: {"open": 0, "pass": 0, "kev": 0, "cat1": 0})
    rows = db.execute(select(FindingControlMap.control_id, Finding.id, Finding.current_state, Finding.is_kev, Finding.cat)
                      .join(Finding, Finding.id == FindingControlMap.finding_id)
                      .where(Finding.system_id == system_id, Finding.disposition.is_distinct_from("false_positive"), FindingControlMap.valid_to.is_(None))
                      .distinct()).all()
    seen = set()
    for cid, fid, state, kev, cat in rows:
        if (cid, fid) in seen:
            continue
        seen.add((cid, fid))
        s = stats[cid]
        if state == "open":
            s["open"] += 1
            s["kev"] += bool(kev)
            s["cat1"] += cat == "CAT I"
        elif state == "pass":
            s["pass"] += 1
    # Per-asset coverage: for every asset (or asset-less source) covered by a control's evidence, only the newest
    # evidence counts. Control = current if all covered assets are fresh, expired if none, partially_stale otherwise.
    from app.models import FindingObservation

    ev_assets = defaultdict(set)
    for eid, asset_id in db.execute(select(FindingObservation.evidence_id, Finding.asset_id).join(Finding, Finding.id == FindingObservation.finding_id)
                                    .where(Finding.system_id == system_id).distinct()):
        ev_assets[eid].add(str(asset_id))
    cover = defaultdict(dict)
    for aid, eid, state, collected, src in db.execute(
            select(EvidenceControl.assignment_id, Evidence.id, Evidence.state, Evidence.collected_at, Evidence.source_id)
            .join(Evidence, Evidence.id == EvidenceControl.evidence_id).where(Evidence.system_id == system_id)):
        for k in ev_assets.get(eid) or {f"source:{src or eid}"}:
            cur = cover[aid].get(k)
            if cur is None or collected > cur[0]:
                cover[aid][k] = (collected, state)
    fresh = {aid: [st for _, st in d.values()] for aid, d in cover.items()}
    stmts = statement_map(db, system_id)
    for a in db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == system_id)):
        s = stats.get(a.control_id, {"open": 0, "pass": 0, "kev": 0, "cat1": 0})
        cmis = [c for c in cfg.get(a.control_id, []) if c["mismatch"]]
        a.monitoring_status = "failing" if s["open"] or cmis else "passing" if s["pass"] or cfg.get(a.control_id) else (
            "inherited" if a.responsibility == "inherited" else "no_data")
        states = fresh.get(a.id, [])
        stale = [x for x in states if x in STALE]
        if not states:
            a.evidence_freshness_status = "no_evidence"
        elif not stale:
            a.evidence_freshness_status = "near_expiration" if "near_expiration" in states else "current"
        elif len(stale) == len(states):
            a.evidence_freshness_status = "expired" if "expired" in stale else stale[0]
        else:
            a.evidence_freshness_status = "partially_stale"
        reasons = []
        if s["open"]:
            reasons.append({"code": "failed_technical_checks", "count": s["open"], "points": weights.get("failed_technical_checks", 0) * min(s["open"], 5)})
        if s["cat1"]:
            reasons.append({"code": "cat1_open", "count": s["cat1"], "points": weights.get("cat1_open", 0)})
        if s["kev"]:
            reasons.append({"code": "kev", "count": s["kev"], "points": weights.get("kev", 0)})
        if stale:
            reasons.append({"code": "expired_evidence", "count": len(stale), "of": len(states), "points": weights.get("expired_evidence", 0),
                            "detail": f"expired evidence on {len(stale)} of {len(states)} assets"})
        if a.responsibility != "inherited" and stmts.get(a.id) != "has":
            reasons.append({"code": "missing_implementation_statement", "count": 1, "points": weights.get("missing_implementation_statement", 0),
                            "detail": "draft not yet submitted for review" if stmts.get(a.id) == "draft" else "no statement"})
        if split_missing(a):
            reasons.append({"code": "responsibility_split_missing", "points": 0, "detail": "Responsibility split not documented"})
        if cmis:
            reasons.append({"code": "failed_technical_checks", "count": len(cmis), "points": weights.get("failed_technical_checks", 0) * len(cmis),
                            "detail": "observed configuration ≠ approved ODP: " + ", ".join(f"{c['observed'].value} vs {c['odp'].value}" for c in cmis)})
        if a.content_change and not a.content_change.get("acknowledged"):
            reasons.append({"code": "catalog_change", "count": 1, "points": weights.get("catalog_change", 0), "detail": a.content_change.get("note")})
        if a.assessment_status == "not_assessed" and not states and a.responsibility != "inherited":
            reasons.append({"code": "missing_assessment_evidence", "count": 1, "points": weights.get("missing_assessment_evidence", 0)})
        a.reasons = reasons
        a.priority_score = sum(r["points"] for r in reasons)
        a.evaluation = {"open_findings": s["open"], "passing_checks": s["pass"], "kev_open": s["kev"], "evidence_items": len(states),
                        "assets_covered": len(states), "assets_stale": len(stale)}
        a.last_evaluated_at = now()
    from app.services.risk import recompute

    recompute(db, system_id)
    db.flush()


def open_findings_q(sid):
    """Open for metrics = still failing OR remediation observed but closure not yet approved; false positives excluded."""
    return select(func.count()).select_from(Finding).where(
        Finding.system_id == sid, Finding.disposition.is_distinct_from("false_positive"),
        or_(Finding.current_state == "open", Finding.remediation_status == "remediated_observed"))


OP_WEIGHTS = {"sys_cat1": (5, "Open CAT I finding (CAT from cat_rules)"), "sys_kev": (8, "Open KEV finding"),
              "sys_overdue_poam": (4, "Overdue POA&M"), "sys_stale_controls": (1, "Control with stale/partially stale evidence (per 5)"),
              "sys_auth_expiring": (10, "Authorization expires within 90 days"), "sys_pending_risk": (3, "Pending risk/waiver decision")}


def system_metrics(db: Session, system: System) -> dict:
    from app.services.metrics import system_metrics as _m
    return _m(db, system)


AGG_KEYS = ("open_cat1", "kev_open", "open_findings", "open_poams", "overdue_poams", "risk_acceptances", "pending_risk_decisions",
            "controls_with_evidence", "controls_fresh", "assigned_controls", "evidence_total", "evidence_items_fresh", "pending_emass_sync")


def take_snapshots(db: Session, trigger: str, org_id=None) -> None:
    ts = now()
    q = select(Organization) if org_id is None else select(Organization).where(Organization.id == org_id)
    for org in db.scalars(q):
        systems = list(db.scalars(select(System).where(System.org_id == org.id)))
        agg = defaultdict(int)
        for s in systems:
            m = system_metrics(db, s)
            db.add(RiskSnapshot(org_id=org.id, system_id=s.id, taken_at=ts, trigger=trigger, metrics=m))
            for k in AGG_KEYS:
                agg[k] += m[k] or 0
        if systems:
            pct = round(100 * agg["controls_fresh"] / agg["assigned_controls"], 1) if agg["assigned_controls"] else None
            db.add(RiskSnapshot(org_id=org.id, system_id=None, taken_at=ts, trigger=trigger,
                                metrics={"systems": len(systems), **{k: agg[k] for k in AGG_KEYS}, "evidence_fresh_pct": pct,
                                         "control_evidence_coverage_pct": pct,
                                         "evidence_items_fresh_pct": round(100 * agg["evidence_items_fresh"] / agg["evidence_total"], 1) if agg["evidence_total"] else None}))
    db.flush()


def snapshot_due(db: Session) -> bool:
    last = db.scalar(select(func.max(RiskSnapshot.taken_at)).where(RiskSnapshot.is_synthetic.is_(False)))
    return last is None or now() - last > timedelta(hours=24)
