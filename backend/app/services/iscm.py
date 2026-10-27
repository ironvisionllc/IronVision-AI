"""Continuous Monitoring Strategy (ISCM, SP 800-37 Rev 2 Task S-5; SP 800-137) → effective eMASS SLCM values per control.

Resolution per SLCM field: per-control override → first matching profile (sort_order) → system default → empty.
Only the APPROVED snapshot feeds controls/exports; Inherited and Not Applicable controls get no SLCM values."""
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Assessment, ControlAssignment, EmassControlFields, Evidence, EvidenceControl, IscmProfile, IscmStrategy, System

SLCM = ["slcm_criticality", "slcm_frequency", "slcm_method", "slcm_reporting", "slcm_tracking", "slcm_comments"]
NO_SLCM = ("Inherited", "Not Applicable")
FREQ_DAYS = {"Constantly": 1, "Daily": 1, "Weekly": 7, "Monthly": 31, "Quarterly": 92, "Semi-Annually": 183, "Annually": 366,
             "Every Two Years": 731, "Every Three Years": 1096}
MATCH_TYPES = ("family", "control_list", "designation")


def strategy(db: Session, s: System) -> IscmStrategy | None:
    return db.scalar(select(IscmStrategy).where(IscmStrategy.system_id == s.id))


def snapshot(st: IscmStrategy, profiles: list[IscmProfile]) -> dict:
    return {"version": st.version, "defaults": {k: v for k, v in (st.defaults or {}).items() if k in SLCM and v},
            "profiles": [{"name": p.name, "match_type": p.match_type, "match_value": p.match_value,
                          "values": {k: v for k, v in (p.values or {}).items() if k in SLCM and v}} for p in sorted(profiles, key=lambda p: p.sort_order)]}


def _matches(p: dict, control_id: str, designation: str | None) -> bool:
    vals = {v.strip().lower().replace("(", ".").replace(")", "") for v in p["match_value"].split(",") if v.strip()}
    if p["match_type"] == "family":
        return control_id.split("-")[0] in vals
    if p["match_type"] == "control_list":
        return control_id in vals
    return (designation or "").lower() in vals


class Resolver:
    def __init__(self, snap: dict | None):
        self.snap = snap or {}

    def strategy_values(self, control_id: str, designation: str | None) -> tuple[dict, dict]:
        vals, src = {}, {}
        for k in SLCM:
            p = next((p for p in self.snap.get("profiles", []) if k in p["values"] and _matches(p, control_id, designation)), None)
            if p:
                vals[k], src[k] = p["values"][k], f"Profile: {p['name']}"
            elif k in self.snap.get("defaults", {}):
                vals[k], src[k] = self.snap["defaults"][k], "System default"
        return vals, src

    def apply(self, control_id: str, status: str, f: EmassControlFields | None, raw: dict) -> tuple[dict, dict]:
        """→ (values with effective SLCM, {field: source}). Source ∈ Override | Profile: X | System default | ''."""
        if status in NO_SLCM:
            return raw, {}
        strat, ssrc = self.strategy_values(control_id, raw.get("control_designation"))
        follow = (f.slcm_inherit or {}) if f else {}
        out, src = dict(raw), {}
        for k in SLCM:
            if raw.get(k) not in (None, "") and not follow.get(k):
                src[k] = "Override"
            elif k in strat:
                out[k], src[k] = strat[k], ssrc[k]
            else:
                src[k] = ""
        return out, src


def resolver(db: Session, s: System | None) -> Resolver:
    st = strategy(db, s) if s else None
    return Resolver(st.approved_snapshot if st else None)


def resolver_for_system_id(db: Session, system_id) -> Resolver:
    return Resolver(db.scalar(select(IscmStrategy.approved_snapshot).where(IscmStrategy.system_id == system_id)))


def view(db: Session, s: System) -> dict:
    from app.services import emass_fields as ef
    st = strategy(db, s)
    profiles = list(db.scalars(select(IscmProfile).where(IscmProfile.strategy_id == st.id).order_by(IscmProfile.sort_order))) if st else []
    rows = ef.rows(db, s)
    fed = sum(1 for r in rows if any(v not in ("Override", "") for v in (r.get("slcm_source") or {}).values()))
    overrides = sum(1 for r in rows if "Override" in (r.get("slcm_source") or {}).values())
    pending = st is not None and st.status != "approved"
    return {"strategy": None if not st else {
        "id": str(st.id), "status": st.status, "version": st.version, "narrative": st.narrative, "scope": st.scope, "defaults": st.defaults,
        "reporting": st.reporting, "review_activities": st.review_activities, "evidence_requirements": st.evidence_requirements,
        "approved_snapshot": st.approved_snapshot, "submitted_by": st.submitted_by, "approved_by": st.approved_by,
        "approved_at": st.approved_at.isoformat() if st.approved_at else None, "is_synthetic": st.is_synthetic,
        "profiles": [{"id": str(p.id), "name": p.name, "match_type": p.match_type, "match_value": p.match_value, "values": p.values, "sort_order": p.sort_order}
                     for p in profiles]},
        "feeds": {"controls": fed, "overrides": overrides, "total": len(rows)}, "pending_changes": pending,
        "options": {"frequencies": ef.FREQUENCIES, "methods": ef.METHODS, "match_types": MATCH_TYPES, "fields": {k: ef.FIELD_META[k][0] for k in SLCM}},
        "people": ef._people(db, s)}


def _clean(vals: dict | None) -> dict:
    from app.services import emass_fields as ef
    out = {k: (v.strip() if isinstance(v, str) else v) for k, v in (vals or {}).items() if k in SLCM and v not in (None, "")}
    ef.check_values(out)
    return out


def save(db: Session, s: System, body: dict, actor) -> IscmStrategy:
    from app.services import audit
    st = strategy(db, s)
    before = None
    if st is None:
        st = IscmStrategy(system_id=s.id, status="draft", version=1)
        db.add(st)
        db.flush()
    else:
        before = {"defaults": st.defaults, "narrative": st.narrative, "status": st.status}
        if st.status == "approved":
            st.version += 1
    st.narrative, st.scope = body.get("narrative"), body.get("scope")
    st.defaults = _clean(body.get("defaults"))
    for k in ("reporting", "review_activities", "evidence_requirements"):
        setattr(st, k, list(body.get(k) or []))
    db.query(IscmProfile).filter(IscmProfile.strategy_id == st.id).delete()
    for i, p in enumerate(body.get("profiles") or []):
        if p.get("match_type") not in MATCH_TYPES or not str(p.get("match_value") or "").strip() or not str(p.get("name") or "").strip():
            raise HTTPException(422, f"Profile {i + 1}: name, match type ({', '.join(MATCH_TYPES)}) and match value are required")
        db.add(IscmProfile(strategy_id=st.id, name=p["name"].strip()[:120], match_type=p["match_type"], match_value=str(p["match_value"]).strip()[:2000],
                           values=_clean(p.get("values")), sort_order=i))
    st.status = "draft"
    db.flush()
    audit.record(db, action="iscm.strategy_saved", actor_user_id=actor.user.id, actor_email=actor.user.email, entity_type="iscm_strategy",
                 entity_id=str(st.id), before=before, after={"defaults": st.defaults, "profiles": len(body.get("profiles") or []), "version": st.version},
                 details={"system_id": str(s.id)})
    return st


def submit(db: Session, s: System, actor) -> IscmStrategy:
    from app.services import audit, sod
    st = strategy(db, s)
    if st is None or st.status not in ("draft", "rejected"):
        raise HTTPException(409, "Save a draft strategy first" if st is None else f"The strategy is already {st.status.replace('_', ' ')}")
    st.status, st.submitted_by = "pending_approval", sod.identity(actor)
    audit.record(db, action="iscm.strategy_submitted", actor_user_id=actor.user.id, actor_email=actor.user.email, entity_type="iscm_strategy",
                 entity_id=str(st.id), details={"system_id": str(s.id), "version": st.version})
    return st


def decide(db: Session, s: System, actor, approve: bool, comment: str) -> IscmStrategy:
    from app.services import audit, sod
    from app.services import emass_fields as ef
    st = strategy(db, s)
    if st is None or st.status != "pending_approval":
        raise HTTPException(409, "No strategy is waiting for approval")
    if "issm" not in (actor.roles or []):
        raise HTTPException(403, "Only the ISSM approves the Continuous Monitoring Strategy (SP 800-37 Task S-5)")
    blocked, sod_details = sod.evaluate(st.submitted_by, actor, sod.is_sandbox(db, s.org_id), "submitted")
    if blocked:
        raise HTTPException(403, blocked)
    if not approve:
        st.status = "rejected"
        audit.record(db, action="iscm.strategy_rejected", actor_user_id=actor.user.id, actor_email=actor.user.email, entity_type="iscm_strategy",
                     entity_id=str(st.id), details={"comment": comment, **(sod_details or {})})
        return st
    profiles = list(db.scalars(select(IscmProfile).where(IscmProfile.strategy_id == st.id)))
    st.approved_snapshot = snapshot(st, profiles)
    st.status, st.approved_by, st.approved_at = "approved", sod.identity(actor), datetime.now(timezone.utc)
    db.flush()
    merged = merge_equal_overrides(db, s)
    audit.record(db, action="iscm.strategy_approved", actor_user_id=actor.user.id, actor_email=actor.user.email, entity_type="iscm_strategy",
                 entity_id=str(st.id), after=st.approved_snapshot, details={"comment": comment, "overrides_now_following_strategy": merged, **(sod_details or {})})
    _ = ef
    return st


def merge_equal_overrides(db: Session, s: System) -> list[dict]:
    """After approval: an override that equals the approved strategy value is marked "follows strategy" (effective value unchanged; audited)."""
    from app.services import emass_fields as ef
    res = resolver(db, s)
    out = []
    for f in db.scalars(select(EmassControlFields).where(EmassControlFields.system_id == s.id)):
        strat, _ = res.strategy_values(f.control_id, f.control_designation)
        same = [k for k in SLCM if getattr(f, k) not in (None, "") and strat.get(k) == getattr(f, k) and not (f.slcm_inherit or {}).get(k)]
        if same:
            for k in same:
                setattr(f, k, None)
            f.slcm_inherit = {**(f.slcm_inherit or {}), **{k: True for k in same}}
            out.append({"control_id": f.control_id, "fields": same})
    _ = ef
    return out


def promote_preview(db: Session, s: System) -> list[dict]:
    """Common override values that could become a system default or family profile – shown for review, never applied automatically."""
    from collections import Counter
    from app.services import emass_fields as ef
    rows = [r for r in ef.rows(db, s) if r["implementation_status"] not in NO_SLCM]
    out = []
    for k in SLCM:
        ov = [(r["control_id"], r[k]) for r in rows if (r.get("slcm_source") or {}).get(k) == "Override"]
        for val, n in Counter(v for _, v in ov).most_common(3):
            if n < 2:
                continue
            fams = Counter(c.split("-")[0] for c, v in ov if v == val)
            out.append({"field": k, "label": ef.FIELD_META[k][0], "value": val, "controls": n, "of": len(rows),
                        "suggest": "system_default" if n >= len(rows) / 2 else "family_profile", "families": [f.upper() for f, _ in fams.most_common(5)]})
    return out


def reset_fields(db: Session, a: ControlAssignment, fields: list[str], actor, meta: dict) -> list[str]:
    from app.services import emass_fields as ef
    f = ef.ensure(db, a)
    ks = [k for k in fields if k in SLCM]
    before = ef.values(f)
    for k in ks:
        setattr(f, k, None)
    f.slcm_inherit = {**(f.slcm_inherit or {}), **{k: True for k in ks}}
    f.updated_by = actor.user.id
    ef._audit(db, actor, a, "emass.slcm_reset_to_strategy", before, ef.values(f), {"fields": ks}, meta)
    return ks


def due(db: Session, s: System, today: date | None = None) -> list[dict]:
    """Monitor (Tasks M-2/M-3): next SLCM review per control = last assessment or evidence date + effective SLCM Frequency."""
    from app.services import emass_fields as ef
    today = today or date.today()
    last_ass = dict(db.execute(select(Assessment.assignment_id, func.max(Assessment.created_at)).where(Assessment.system_id == s.id)
                               .group_by(Assessment.assignment_id)).all())
    ids = {a.control_id: a.id for a in db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == s.id))}
    last_ev = dict(db.execute(select(EvidenceControl.assignment_id, func.max(Evidence.collected_at)).join(Evidence, Evidence.id == EvidenceControl.evidence_id)
                              .where(Evidence.system_id == s.id, EvidenceControl.removed_at.is_(None)).group_by(EvidenceControl.assignment_id)).all())
    out = []
    for r in ef.rows(db, s):
        if r["implementation_status"] in NO_SLCM:
            continue
        freq = r.get("slcm_frequency")
        days = FREQ_DAYS.get(freq or "")
        aid = ids.get(r["control_id"])
        dates = [d for d in (last_ass.get(aid), last_ev.get(aid)) if d]
        last = max(d.date() if isinstance(d, datetime) else d for d in dates) if dates else None
        nxt = last + timedelta(days=days) if last and days else None
        status = "no_frequency" if not days else "never_monitored" if not last else "overdue" if nxt < today else "due_soon" if nxt <= today + timedelta(days=14) else "on_track"
        out.append({"control_id": r["control_id"], "acronym": r["acronym"], "title": r["title"], "slcm_frequency": freq, "slcm_method": r.get("slcm_method"),
                    "source": (r.get("slcm_source") or {}).get("slcm_frequency") or "", "last_monitored": last.isoformat() if last else None,
                    "next_due": nxt.isoformat() if nxt else None, "status": status})
    order = {"overdue": 0, "never_monitored": 1, "due_soon": 2, "on_track": 3, "no_frequency": 4}
    return sorted(out, key=lambda x: (order[x["status"]], x["next_due"] or "9999"))


def run_due_job(db: Session) -> dict:
    """Scheduled job conmon.slcm_due: counts due/overdue SLCM reviews for every system with an approved strategy (Monitor shows the list)."""
    out = {}
    for st in db.scalars(select(IscmStrategy).where(IscmStrategy.approved_snapshot.is_not(None))):
        s = db.get(System, st.system_id)
        items = due(db, s)
        out[s.acronym or str(s.id)] = {k: sum(1 for i in items if i["status"] == k) for k in ("overdue", "due_soon", "never_monitored")}
    return {"systems": out}
