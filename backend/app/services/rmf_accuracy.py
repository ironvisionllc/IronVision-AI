"""RMF accuracy rules: categorization revisions + approval, Privacy Threshold Analysis, overlay applicability, DoD Cloud SRG impact levels.
Interpretations and sources are recorded in docs/RMF_INTERPRETATION_DECISIONS.md; anything not verifiable is labelled SME review required."""
import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CategorizationRecord, PtaQuestionSet, PtaResponse, System

SME = "SME review required"
FRAMEWORKS = {
    "fips199": {"label": "FIPS 199 / NIST SP 800-60 (non-national security systems)",
                "help": "Federal information systems that are not National Security Systems. Impact per objective is the high-water mark across the "
                        "information types (SP 800-60 Vol. 2 Rev. 1); the overall category is the highest objective and selects the SP 800-53B baseline "
                        "(FIPS 200).", "source": "FIPS 199 §3; FIPS 200 §3; NIST SP 800-60 Vol. 1 Rev. 1 §4; NIST SP 800-53B §2.2"},
    "cnssi1253": {"label": "CNSSI 1253 (National Security Systems)",
                  "help": "National Security Systems. Information types still come from SP 800-60, but C, I and A stay as three separate values "
                          "(e.g. M-H-L) – CNSSI 1253 does not use a single high-water mark – and controls are selected per objective.",
                  "source": "CNSSI No. 1253 (security categorization of NSS, 3x3 per-objective approach)"},
}
NSS_HELP = ("A National Security System is defined in 44 U.S.C. §3552(b)(6): e.g. intelligence activities, cryptologic activities related to "
            "national security, command and control of military forces, equipment integral to a weapon system, systems critical to military or "
            "intelligence missions, or systems protected for classified information. NIST SP 800-59 gives the guideline and checklist for "
            "identifying an NSS. If you are unsure, record 'Unsure' and ask your AO/ISSM – do not guess.")
SRG = "DoD Cloud Computing Security Requirements Guide (CC SRG) v1r2 (Jan 2025), §3 Information Impact Levels"
IL_REASON = {"not_cloud": "SRG impact levels apply to cloud service offerings – this environment has no cloud component.",
             "il6": "IL6 is for classified information up to SECRET in a DoD cloud: it needs the CNSSI 1253 (NSS) framework and a Yes to "
                    "'processes classified information'."}
CLOUD_ENVS = {"cloud_iaas", "cloud_paas", "cloud_saas", "hybrid"}


def now():
    return datetime.now(timezone.utc)


# ---------- categorization revisions ----------
def _hash(framework: str, nss: str | None, rows: list[dict], impacts: dict) -> str:
    key = [framework, nss, sorted((r["id"], r["c"], r["i"], r["a"]) for r in rows), impacts]
    return hashlib.sha256(json.dumps(key, sort_keys=True, default=str).encode()).hexdigest()


def latest(db: Session, sid, status: str | None = None) -> CategorizationRecord | None:
    q = select(CategorizationRecord).where(CategorizationRecord.system_id == sid)
    if status:
        q = q.where(CategorizationRecord.status == status)
    return db.scalar(q.order_by(CategorizationRecord.revision.desc()).limit(1))


def record(db: Session, s: System, calc: dict, framework: str, nss: str | None, rationale: str | None, actor_email: str) -> CategorizationRecord:
    """New revision when the inputs change. With an approved revision the change becomes 'pending_reapproval' and does not replace it."""
    impacts = {"c": calc["c"], "i": calc["i"], "a": calc["a"]}
    h = _hash(framework, nss, calc["rows"], impacts)
    cur = latest(db, s.id)
    if cur and cur.inputs_hash == h:
        if rationale and cur.status != "approved":
            cur.rationale = rationale
        return cur
    approved = latest(db, s.id, "approved")
    for old in db.scalars(select(CategorizationRecord).where(CategorizationRecord.system_id == s.id,
                                                             CategorizationRecord.status.in_(("draft", "pending_reapproval", "legacy_unreviewed")))):
        old.status = "superseded"
    n = (db.scalar(select(func.max(CategorizationRecord.revision)).where(CategorizationRecord.system_id == s.id)) or 0) + 1
    rec = CategorizationRecord(system_id=s.id, revision=n, framework=framework, nss_determination=nss, impacts=impacts, inputs_hash=h,
                               information_types=[{k: r[k] for k in ("id", "name", "c", "i", "a", "rationale", "adjusted", "provisional")} for r in calc["rows"]],
                               overall=calc["overall"], baseline=calc["baseline"], rationale=rationale, submitted_by=actor_email,
                               detail={"steps": calc["steps"], "security_category": calc["security_category"], "baseline_selection": calc.get("baseline_selection")},
                               status="pending_reapproval" if approved else "draft")
    db.add(rec)
    db.flush()
    return rec


def approve(db: Session, s: System, rec: CategorizationRecord, approver, real_email: str, rationale: str) -> CategorizationRecord:
    if rec.status not in ("draft", "pending_reapproval", "legacy_unreviewed"):
        raise ValueError(f"Revision {rec.revision} is {rec.status} – only the current draft or pending revision can be approved")
    if not rec.information_types:
        raise ValueError("Pick at least one information type before approval")
    for old in db.scalars(select(CategorizationRecord).where(CategorizationRecord.system_id == s.id, CategorizationRecord.status == "approved")):
        old.status = "superseded"
    rec.status, rec.approved_by, rec.approved_by_real, rec.approved_at, rec.approval_rationale = "approved", approver.email, real_email, now(), rationale
    s.categorization_mode, s.nss_determination = rec.framework, rec.nss_determination
    s.information_types = [{k: t.get(k) for k in ("id", "name", "c", "i", "a", "rationale", "adjusted")} for t in rec.information_types]
    s.confidentiality_impact, s.integrity_impact, s.availability_impact = rec.impacts["c"], rec.impacts["i"], rec.impacts["a"]
    s.categorization = (rec.overall or rec.baseline or "").lower() or None
    s.categorization_detail = {**(rec.detail or {}), "baseline": rec.baseline, "approved_revision": rec.revision}
    return rec


def rec_out(r: CategorizationRecord) -> dict:
    return {k: getattr(r, k) for k in ("revision", "framework", "nss_determination", "information_types", "impacts", "overall", "baseline", "detail",
                                        "rationale", "status", "submitted_by", "approved_by", "approved_by_real", "approval_rationale")} | {
        "id": str(r.id), "created_at": r.created_at.isoformat() if r.created_at else None, "approved_at": r.approved_at.isoformat() if r.approved_at else None}


# ---------- applicability: overlays and SRG impact levels ----------
def flags(s: System) -> dict:
    return dict(s.applicability_flags or {})


def overlay_availability(s: System, group: str) -> tuple[bool, str | None]:
    if s.categorization_mode != "cnssi1253":
        if group == "privacy":
            return False, ("Not applicable: this system uses FIPS 199 (non-NSS). Privacy controls come from the NIST SP 800-53B privacy baseline, "
                           "selected through the PTA / PII determination – not from the CNSS Privacy Overlays (CNSSI 1253F Att. 6 applies to NSS).")
        return False, "Not applicable: CNSSI 1253 overlays apply to National Security Systems categorized under CNSSI 1253 (switch the framework in Categorize)."
    if group == "classified" and flags(s).get("classified_information") != "yes":
        return False, ("Needs an explicit Yes to 'Does the system, by intent and design, store, process, or transmit classified information?' "
                       "(Classified System Overlay, CNSSI 1253 App. E Att. 5 §3, p. 3). Classification level alone never applies it.")
    return True, None


def il_options(env: str | None, framework: str | None, classified: str | None) -> list[dict]:
    if env not in CLOUD_ENVS:
        return []
    out = [{"value": v, "available": True, "reason": None} for v in ("IL2", "IL4", "IL5")]
    ok6 = framework == "cnssi1253" and classified == "yes"
    out.append({"value": "IL6", "available": ok6, "reason": None if ok6 else IL_REASON["il6"]})
    return out + [{"value": "Not DoD", "available": True, "reason": None}]


def validate_environment(env: str | None, detail: dict | None, framework: str | None, classified: str | None) -> None:
    il = (detail or {}).get("impact_level")
    if not il:
        return
    if env not in CLOUD_ENVS:
        raise ValueError(IL_REASON["not_cloud"])
    opt = next((o for o in il_options(env, framework, classified) if o["value"] == il), None)
    if opt is None or not opt["available"]:
        raise ValueError(opt["reason"] if opt else f"Unknown impact level {il}")


def baseline_review(s: System) -> dict | None:
    """Approved FIPS 199 categorization above/below the applied 800-53B baseline → a proposal to review in Select (never auto-changed).
    CNSSI 1253 systems use the existing cnssi1253.proposal flow."""
    rec = (s.categorization or "").lower()
    if s.categorization_mode == "cnssi1253" or rec not in ("low", "moderate", "high") or not s.baseline_key or s.baseline_key == rec:
        return None
    return {"from": s.baseline_key, "to": rec, "title": "Categorization changed – review baseline",
            "message": f"The approved categorization is {rec.title()} but the applied baseline is {s.baseline_key.title()}. "
                       f"Preview the {rec.title()} baseline in Select and apply it if appropriate – nothing changes automatically."}


def review_flags(s: System) -> list[dict]:
    """Existing values kept as-is but flagged when they no longer fit the framework/context."""
    out = []
    if br := baseline_review(s):
        out.append({"field": "baseline", "value": br["from"], "message": f"{br['title']}: {br['message']}"})
    det, f = s.environment_detail or {}, flags(s)
    il = det.get("impact_level")
    if il and s.operating_environment not in CLOUD_ENVS:
        out.append({"field": "impact_level", "value": il, "message": f"Review applicability: {IL_REASON['not_cloud']}"})
    elif il == "IL6" and not (s.categorization_mode == "cnssi1253" and f.get("classified_information") == "yes"):
        out.append({"field": "impact_level", "value": il, "message": f"Review applicability: {IL_REASON['il6']}"})
    for k in s.overlay_keys or []:
        g = k.split("-")[1] if k.startswith("cnssi-") else None
        if g:
            ok, why = overlay_availability(s, g)
            if not ok:
                out.append({"field": "overlay", "value": k, "message": f"Applicability review needed: {why}"})
    return out


# ---------- Privacy Threshold Analysis ----------
ANS = ("yes", "no", "not_sure")
DEFAULT_SET = {"key": "default-pta", "version": 1, "title": "Privacy Threshold Analysis",
               "label": "Example set – validate against your agency's privacy requirements",
               "questions": [
                   {"id": "pii", "text": "Does the system collect, use, store, maintain or disseminate personally identifiable information (PII)?", "required": True},
                   {"id": "pii_whose", "text": "Is the PII about members of the public (not only employees or contractors)?", "required": True, "show_if": {"pii": "yes"}},
                   {"id": "retrieved_by_id", "text": "Is information retrieved by a person's name or other personal identifier?", "required": True,
                    "show_if": {"pii": "yes"}, "flag_if_yes": "A System of Records Notice (SORN) may be required – privacy official to confirm."},
                   {"id": "ssn", "text": "Does the system collect Social Security Numbers?", "required": True, "show_if": {"pii": "yes"},
                    "flag_if_yes": "SSN collection needs a documented authority and justification."},
                   {"id": "shared", "text": "Is PII shared outside the organization?", "required": True, "show_if": {"pii": "yes"},
                    "flag_if_yes": "External sharing – check agreements and the routine uses."},
                   {"id": "pia_done", "text": "Has a Privacy Impact Assessment (PIA) been completed for this system?", "required": True, "show_if": {"pii": "yes"}},
                   {"id": "audit_only", "text": "Is the only PII held in audit logs or account management records?", "required": False, "show_if": {"pii": "yes"}},
               ]}


def default_set(db: Session) -> PtaQuestionSet:
    q = db.scalar(select(PtaQuestionSet).where(PtaQuestionSet.org_id.is_(None), PtaQuestionSet.key == DEFAULT_SET["key"]))
    if q is None:
        q = PtaQuestionSet(org_id=None, **DEFAULT_SET, created_by="system")
        db.add(q)
        db.flush()
    return q


def active_set(db: Session, org_id) -> PtaQuestionSet:
    own = db.scalar(select(PtaQuestionSet).where(PtaQuestionSet.org_id == org_id, PtaQuestionSet.is_active.is_(True))
                    .order_by(PtaQuestionSet.version.desc()).limit(1))
    return own or default_set(db)


def visible(q: dict, answers: dict) -> bool:
    return all((answers.get(k) or {}).get("answer") == v for k, v in (q.get("show_if") or {}).items())


def evaluate(qs: PtaQuestionSet, answers: dict) -> tuple[list[dict], str, list[str]]:
    """Returns (flags, recommendation, missing). The outcome is always a recommendation for the privacy official to confirm."""
    flags_, missing = [], []
    for q in qs.questions:
        if not visible(q, answers):
            continue
        a = (answers.get(q["id"]) or {}).get("answer")
        if a is None:
            if q.get("required"):
                missing.append(q["text"])
            continue
        if a not in ANS:
            raise ValueError(f"{q['id']}: answer must be yes, no or not_sure")
        if a == "not_sure":
            flags_.append({"question": q["id"], "flag": "Needs privacy review – answered 'Not sure'."})
        elif a == "yes" and q.get("flag_if_yes"):
            flags_.append({"question": q["id"], "flag": q["flag_if_yes"]})
    pii = (answers.get("pii") or {}).get("answer")
    if pii == "yes":
        rec = "Recommendation: the system handles PII – a PIA is likely required" + ("" if (answers.get("pia_done") or {}).get("answer") == "yes" else " (none completed yet)")
    elif pii == "no" and not flags_:
        rec = ("Recommendation: the answers indicate no PII. This is not a finding that no PIA is required – the privacy official must confirm "
               "before any such conclusion.")
    else:
        rec = "Recommendation: unresolved answers – the privacy official must review before any determination."
    return flags_, rec + " Requires privacy official confirmation.", missing


def submit(db: Session, s: System, answers: dict, actor_email: str) -> PtaResponse:
    qs = active_set(db, s.org_id)
    fl, rec, missing = evaluate(qs, answers)
    if missing:
        raise ValueError("Answer every required question (Yes, No or Not sure): " + "; ".join(missing[:3]))
    n = (db.scalar(select(func.max(PtaResponse.revision)).where(PtaResponse.system_id == s.id)) or 0) + 1
    r = PtaResponse(system_id=s.id, question_set_id=qs.id, question_set_key=qs.key, question_set_version=qs.version, revision=n, answers=answers,
                    flags=fl, recommendation=rec, status="submitted", submitted_by=actor_email)
    db.add(r)
    db.flush()
    return r


def review(db: Session, s: System, r: PtaResponse, reviewer_email: str, decision: str, rationale: str, determination: str | None) -> PtaResponse:
    if r.status != "submitted":
        raise ValueError(f"This PTA is {r.status} – only a submitted PTA can be reviewed")
    r.status, r.reviewer, r.reviewed_at, r.review_rationale = ("approved" if decision == "approve" else "returned"), reviewer_email, now(), rationale
    if decision == "approve":
        r.determination = determination
        s.processes_pii = {"pii": True, "no_pii": False}.get(determination or "", s.processes_pii)
        s.pta = {**(s.pta or {}), "approved_pta_revision": r.revision, "determination": determination, "reviewer": reviewer_email}
    return r


def pta_out(r: PtaResponse) -> dict:
    return {k: getattr(r, k) for k in ("revision", "question_set_key", "question_set_version", "answers", "flags", "recommendation", "status",
                                        "submitted_by", "reviewer", "review_rationale", "determination")} | {
        "id": str(r.id), "created_at": r.created_at.isoformat() if r.created_at else None, "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None}
