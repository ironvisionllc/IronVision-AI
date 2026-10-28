"""Phase 3 services: notifications, attestations + expiry cascade, SCA assessments, authorization, policy auditor, workflow, search."""
import hashlib
import io
import re
import uuid

from app.services.queue import fmt_control
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import (AppSetting, ApprovalRequest, Assessment, Attestation, CommonControlProvider, ControlAssignment, DedupRule, Evidence,
                        EvidenceControl, EvidenceSource, Finding, FindingControlMap, FreshnessPolicy, Implementation, Notification,
                        NotificationPref, ObservedConfigValue, OdpValue, Poam, Policy, PolicyFinding, RoleAssignment, System, User)
from app.services import audit
from app.services.storage import get_storage
from app.services.storage.base import safe_key_part  # noqa: E402

SIGNATURE = "Simulated signature – not CAC/PIV"
NOTIFICATION_KINDS = {
    "assignment": "POA&M / item assigned to you", "new_findings": "New findings assigned", "collection_failed": "Evidence collection failed",
    "evidence_expiring": "Evidence expiring soon", "attestation_overdue": "Attestation overdue / expired", "poam_deadline": "Upcoming POA&M deadline",
    "pending_review": "Review awaiting your decision", "returned": "Request returned", "rejected": "Request rejected", "approved": "Request approved",
    "closure_eligible": "POA&M closure eligible", "emass_sync_failed": "eMASS sync failure (Phase 4 trigger)", "content_release": "New content release",
    "authorization_expiring": "Authorization expiration warning",
}


def now() -> datetime:
    return datetime.now(timezone.utc)


# ---------- notifications ----------
class EmailAdapter:
    """Interface stub. DISABLED: no email transport configured in this deployment (in-app only)."""
    enabled = False

    def send(self, to: str, subject: str, body: str) -> None:
        raise RuntimeError("Email notifications are not configured (adapter disabled)")


def pref_enabled(db: Session, user_id, kind: str) -> bool:
    p = db.scalar(select(NotificationPref.enabled).where(NotificationPref.user_id == user_id, NotificationPref.kind == kind))
    return True if p is None else p


def send(db: Session, user_id, kind: str, title: str, link: str | None, body: str | None = None, dedupe_key: str | None = None) -> bool:
    """In-app delivery honoring per-user prefs; dedupe_key makes scheduled generation idempotent."""
    if not user_id or not pref_enabled(db, user_id, kind):
        return False
    if dedupe_key and db.scalar(select(Notification.id).where(Notification.user_id == user_id, Notification.dedupe_key == dedupe_key)):
        return False
    db.add(Notification(user_id=user_id, title=title[:255], body=body, link=link, kind=kind, dedupe_key=dedupe_key,
                        severity="warning" if kind in ("returned", "rejected", "closure_eligible", "attestation_overdue",
                                                       "authorization_expiring", "collection_failed") else "info"))
    return True


def role_users(db: Session, org_id, system_id, role: str) -> list:
    return list(db.scalars(select(RoleAssignment.user_id).where(RoleAssignment.role == role, or_(
        (RoleAssignment.scope_type == "system") & (RoleAssignment.scope_id == system_id),
        (RoleAssignment.scope_type == "org") & (RoleAssignment.scope_id == org_id))).distinct()))


def generate_deadline_notifications(db: Session) -> int:
    today, n = date.today(), 0
    for p in db.scalars(select(Poam).where(Poam.status.in_(("new", "in_progress")), Poam.due_date <= today + timedelta(days=14))):
        n += send(db, p.owner_id or p.created_by, "poam_deadline", f"{p.human_id} due {p.due_date}", f"/poams/{p.id}", dedupe_key=f"poam:{p.id}:{p.due_date}")
    for a in db.scalars(select(Attestation).where(Attestation.status.in_(("pending", "expired")), Attestation.due_date < today)):
        n += send(db, a.owner_id, "attestation_overdue", f"Attestation {fmt_control(a.control_id)} v{a.version} overdue", "/inheritance",
                  dedupe_key=f"att:{a.id}:overdue")
    for e in db.scalars(select(Evidence).where(Evidence.state == "near_expiration")):
        s = db.get(System, e.system_id)
        for uid in role_users(db, s.org_id, s.id, "isso"):
            n += send(db, uid, "evidence_expiring", f"{s.acronym}: {e.name} nearing expiration", "/evidence-ledger", dedupe_key=f"ev:{e.id}:near")
    for s in db.scalars(select(System).where(System.authorization_expiration.is_not(None), System.authorization_expiration <= today + timedelta(days=90))):
        for uid in role_users(db, s.org_id, s.id, "ao") + role_users(db, s.org_id, s.id, "isso"):
            n += send(db, uid, "authorization_expiring", f"{s.acronym} authorization expires {s.authorization_expiration}", f"/systems/{s.id}",
                      dedupe_key=f"ato:{s.id}:{s.authorization_expiration}")
    for src in db.scalars(select(EvidenceSource).where(EvidenceSource.health.in_(("error", "failed")))):
        s = db.get(System, src.system_id)
        for uid in role_users(db, s.org_id, s.id, "isso"):
            n += send(db, uid, "collection_failed", f"{s.acronym}: {src.name} collection failed", "/evidence-sources",
                      dedupe_key=f"src:{src.id}:{src.last_run_at}")
    db.flush()
    return n


# ---------- settings ----------
AI_DEFAULTS = {"provider": None, "endpoint": None, "model": None, "logging_policy": "full_prompt_and_response_retained",
               "human_approval_required": True, "retrieval_restrictions": "Only records of the requesting user's authorized system",
               "use_cases": {"control.implementation_statement": True, "policy.audit": True, "health.ping": True, "mapping.suggest": True,
                             "control.emass_fields_suggest": True}}


def get_setting(db: Session, org_id, key: str, default: dict) -> dict:
    s = db.scalar(select(AppSetting).where(AppSetting.org_id == org_id, AppSetting.key == key))
    return {**default, **(s.value if s else {})}


def set_setting(db: Session, org_id, key: str, value: dict) -> dict:
    s = db.scalar(select(AppSetting).where(AppSetting.org_id == org_id, AppSetting.key == key))
    if s is None:
        s = AppSetting(org_id=org_id, key=key, value=value)
        db.add(s)
    else:
        s.value = value
    db.flush()
    return s.value


def require_ai_use_case(db: Session, org_id, prompt_id: str) -> None:
    if not get_setting(db, org_id, "ai", AI_DEFAULTS)["use_cases"].get(prompt_id, AI_DEFAULTS["use_cases"].get(prompt_id, False)):
        raise HTTPException(403, f"AI use case '{prompt_id}' is disabled by AI administration settings")


# ---------- attestations ----------
def store_evidence(db: Session, system_id, file_name: str, data: bytes, evidence_type: str, actor_email: str, source_label: str) -> Evidence:
    from app.services.evaluation import apply_freshness

    sha = hashlib.sha256(data).hexdigest()
    key = f"evidence/{system_id}/{sha}/{safe_key_part(file_name)}"
    store = get_storage()
    if not store.exists(key):
        store.put(key, data, "application/octet-stream")
    st = "manual_attestation" if evidence_type == "attestation" else "manual_upload"
    sq = select(EvidenceSource).where(EvidenceSource.system_id == system_id, EvidenceSource.source_type == st)
    if st == "manual_attestation":
        sq = sq.where(EvidenceSource.name == "Manual attestations")
    src = db.scalar(sq.order_by(EvidenceSource.created_at).limit(1))
    if src is None:
        src = EvidenceSource(id=uuid.uuid4(), system_id=system_id, source_type=st, adapter="file_import", health="ok", config={},
                             name="Manual attestations" if st == "manual_attestation" else "Policy library / manual uploads", source="auto:upload-attribution")
        db.add(src)
        db.flush()
    from app.services.queue import fmt_control

    name = f"{fmt_control(file_name.split('_attestation')[0])} attestation record" if evidence_type == "attestation" and "_attestation" in file_name else file_name
    ev = Evidence(id=uuid.uuid4(), system_id=system_id, source_id=src.id, name=name, evidence_type=evidence_type, file_name=file_name, storage_key=key,
                  sha256=sha, size_bytes=len(data), content_type=file_name.rsplit(".", 1)[-1], collected_at=now(), signature_status="unsigned",
                  integrity_status="hash_recorded", source=source_label, provenance={"received_by": actor_email, "sha256_at_receipt": sha})
    ev.uploaded_by = actor_email
    db.add(ev)
    db.flush()
    from app.services.evidence_versions import _snapshot

    _snapshot(db, ev, actor_email, "Initial version")
    apply_freshness(db, ev)
    audit.record(db, action="evidence.stored", actor_email=actor_email, entity_type="evidence", entity_id=str(ev.id),
                 details={"sha256": sha, "type": evidence_type, "source": source_label})
    return ev


def attestation_window(db: Session) -> int:
    p = db.scalar(select(FreshnessPolicy).where(FreshnessPolicy.evidence_type == "attestation"))
    return p.window_days if p else 365


def sign_attestation(db: Session, a: Attestation, actor: User) -> Attestation:
    if a.owner_id != actor.id:
        audit.record_now(action="authz.denied", outcome="denied", actor_user_id=actor.id, actor_email=actor.email, entity_type="attestation",
                         entity_id=str(a.id), details={"reason": "only_assigned_owner_may_attest"})
        raise HTTPException(403, "Only the assigned owner can attest")
    if a.status not in ("pending", "expired"):
        raise HTTPException(409, f"Attestation is {a.status}; renew to create a new version")
    if not a.evidence_id:
        raise HTTPException(422, "Upload the required evidence before attesting")
    a.status, a.signed_at, a.signed_by, a.signature = "signed", now(), actor.id, SIGNATURE
    a.expires_at = date.today() + timedelta(days=attestation_window(db))
    ev = db.get(Evidence, a.evidence_id)
    ev.collected_at, ev.signature_status = now(), "simulated_attestation"
    _link_evidence(db, a, ev)
    audit.record(db, action="attestation.signed", actor_user_id=actor.id, actor_email=actor.email, entity_type="attestation", entity_id=str(a.id),
                 after={"control_id": a.control_id, "version": a.version, "expires_at": str(a.expires_at), "signature": SIGNATURE})
    return a


def _link_evidence(db: Session, a: Attestation, ev: Evidence) -> None:
    if not db.scalar(select(EvidenceControl.id).where(EvidenceControl.evidence_id == ev.id, EvidenceControl.assignment_id == a.assignment_id)):
        db.add(EvidenceControl(evidence_id=ev.id, assignment_id=a.assignment_id))


def renew_attestation(db: Session, a: Attestation, actor: User) -> Attestation:
    if a.status not in ("signed", "expired"):
        raise HTTPException(409, "Only signed or expired attestations can be renewed")
    new = Attestation(system_id=a.system_id, assignment_id=a.assignment_id, control_id=a.control_id, version=a.version + 1, statement=a.statement,
                      owner_id=a.owner_id, evidence_required=a.evidence_required, due_date=date.today() + timedelta(days=30), supersedes_id=a.id)
    a.status = "superseded" if a.status == "signed" else a.status
    db.add(new)
    db.flush()
    send(db, a.owner_id, "attestation_overdue", f"Renewal: attest {fmt_control(a.control_id)} v{new.version}", "/inheritance", dedupe_key=f"att:{new.id}:renew")
    audit.record(db, action="attestation.renewed", actor_user_id=actor.id, actor_email=actor.email, entity_type="attestation", entity_id=str(new.id),
                 details={"previous_id": str(a.id), "previous_preserved": True})
    return new


def expire_attestations(db: Session) -> dict:
    """Cascade: expired attestation → evidence stale(expired) → control freshness/queue → leadership snapshot → owner notified. Record kept."""
    from app.services.evaluation import evaluate_system, take_snapshots

    today, systems, n = date.today(), set(), 0
    for a in db.scalars(select(Attestation).where(Attestation.status == "signed", Attestation.expires_at < today)):
        a.status = "expired"
        if a.evidence_id:
            ev = db.get(Evidence, a.evidence_id)
            ev.state, ev.signature_status = "expired", "attestation_expired"
        send(db, a.owner_id, "attestation_overdue", f"Attestation {fmt_control(a.control_id)} v{a.version} expired – renew", "/inheritance",
             dedupe_key=f"att:{a.id}:expired")
        audit.record(db, action="attestation.expired", actor_email="system", entity_type="attestation", entity_id=str(a.id),
                     details={"expired_on": str(a.expires_at), "signed_record_preserved": True})
        systems.add(a.system_id)
        n += 1
    for sid in systems:
        evaluate_system(db, sid)
    if systems:
        take_snapshots(db, trigger="attestation.expired")
    return {"expired": n, "systems": len(systems)}


# ---------- SCA assessments ----------
def record_assessment(db: Session, *, system: System, a: ControlAssignment, actor: User, assignments: list, body: dict) -> Assessment:
    from app.services.workflow import rule_for

    rule = rule_for(db, system.org_id, "assessment_result")
    role = rule.steps[0]["role"]
    if not any(r.role == role and r.scope_id in (system.id, system.org_id) for r in assignments):
        audit.record_now(action="authz.denied", outcome="denied", actor_user_id=actor.id, actor_email=actor.email, entity_type="control_assignment",
                         entity_id=str(a.id), details={"reason": f"decision_rule_requires_{role}", "rule_version": rule.version})
        raise HTTPException(403, f"Decision rule v{rule.version}: only {role.upper()} may record assessment results")
    authors = set(db.scalars(select(Implementation.author_id).where(Implementation.assignment_id == a.id)))
    implementer_roles = {r.role for r in assignments if r.scope_id in (system.id, system.org_id)} & {"isso", "system_owner", "devsecops"}
    if actor.id in authors or (get_setting(db, system.org_id, "independence", {"block_implementer_roles": True})["block_implementer_roles"] and implementer_roles):
        audit.record_now(action="authz.denied", outcome="denied", actor_user_id=actor.id, actor_email=actor.email, entity_type="control_assignment",
                         entity_id=str(a.id), details={"reason": "assessor_independence_violation", "authored": actor.id in authors,
                                                       "implementer_roles": sorted(implementer_roles)})
        raise HTTPException(403, "Assessor independence: you authored this control's implementation or hold an implementing role")
    res = Assessment(system_id=system.id, assignment_id=a.id, control_id=a.control_id, assessor_id=actor.id, objectives=body["objectives"],
                     methods=body["methods"], findings_text=body.get("findings_text"), result=body["result"], evidence_ids=body.get("evidence_ids") or [],
                     decision_rule_version=rule.version)
    db.add(res)
    a.assessment_status = body["result"]
    audit.record(db, action="assessment.recorded", actor_user_id=actor.id, actor_email=actor.email, entity_type="control_assignment",
                 entity_id=str(a.id), after={"control_id": a.control_id, "result": body["result"], "methods": body["methods"]})
    db.flush()
    return res


def package(db: Session, system: System) -> dict:
    from app.services.evaluation import system_metrics

    ac = list(db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == system.id)))
    approved = db.scalar(select(func.count(func.distinct(Implementation.assignment_id))).join(ControlAssignment, ControlAssignment.id == Implementation.assignment_id)
                         .where(ControlAssignment.system_id == system.id, Implementation.review_status == "approved"))
    by_res: dict = {}
    for x in ac:
        by_res[x.assessment_status] = by_res.get(x.assessment_status, 0) + 1
    poams = list(db.scalars(select(Poam).where(Poam.system_id == system.id)))
    return {"system": {"id": str(system.id), "name": system.name, "acronym": system.acronym, "authorization_status": system.authorization_status,
                       "authorization_expiration": system.authorization_expiration},
            "ssp": {"assigned": len(ac), "with_any_narrative": db.scalar(select(func.count(func.distinct(Implementation.assignment_id)))
                    .join(ControlAssignment, ControlAssignment.id == Implementation.assignment_id).where(ControlAssignment.system_id == system.id,
                                                                                         func.length(func.trim(Implementation.narrative)) > 0)),
                    "approved_narratives": approved},
            "assessment": by_res,
            "open_poams": [{"id": str(p.id), "human_id": p.human_id, "weakness": p.weakness, "severity": p.severity, "due_date": p.due_date}
                           for p in poams if p.status not in ("closed", "risk_accepted")],
            "risk_acceptances": [{"id": str(p.id), "human_id": p.human_id, "expires": p.risk_acceptance_expiration} for p in poams if p.status == "risk_accepted"],
            "metrics": system_metrics(db, system)}


# ---------- policy auditor ----------
PARAMS = [
    ("ac-2.3", "inactivity_disable_days", r"(?:inactiv\w*|disabled? after)[^.\n]{0,80}?(\d+)\s*(?:calendar\s+)?days|(\d+)\s*days[^.\n]{0,40}inactiv", "days"),
    ("ac-7", "unsuccessful_logon_attempts", r"(\d+)\s+(?:consecutive\s+)?(?:invalid|unsuccessful|failed)\s+(?:logon|login|log-on)?\s*attempts", "attempts"),
    ("ac-7", "logon_attempt_window_minutes", r"attempts[^.\n]{0,60}?\b(?:within|during|in)\s+(?:a\s+|any\s+)?(\d+)[\s-]*minutes?", "minutes"),
    ("ac-7", "lockout_minutes", r"lock\w*\s+(?:the\s+)?(?:account|node|user)?[^.\n]{0,30}?\bfor\s+(?:a\s+(?:period\s+of\s+)?)?(\d+)\s*minutes?", "minutes"),
    ("ac-11", "session_lock_minutes", r"(?:session|screen)\s+lock[^.\n]{0,60}?(\d+)\s*minutes|(\d+)\s*minutes[^.\n]{0,60}(?:session|screen)\s+lock", "minutes"),
]
REQUIRED_SECTIONS = [("ac-17", r"remote[\s-]+access|teleworking|telework", "Remote access section"), ("ac-1", "official", "Named official / policy owner designation")]


def extract_text(file_name: str, data: bytes) -> str:
    ext = file_name.lower().rsplit(".", 1)[-1]
    if ext == "pdf":  # one form feed per page break, so excerpts can cite the page
        from pypdf import PdfReader
        return "\n\f".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages)
    if ext == "docx":
        return _docx_text(data)
    if ext == "txt":
        return data.decode("utf-8", errors="replace")
    raise HTTPException(422, "Supported policy formats: PDF, DOCX, TXT")


def policy_review_status(p: Policy, today: date | None = None) -> str:
    """Single derivation of policy review status from dates (used by cards, library, detail)."""
    today = today or date.today()
    if p.status != "current":
        return p.status
    if p.review_due and p.review_due < today:
        return "review_overdue"
    if p.review_due and p.review_due <= today + timedelta(days=30):
        return "review_due_soon"
    return "current"


ABBR = {"e.g", "i.e", "etc", "rev", "no", "vs", "u.s", "fig", "sec", "approx", "dr", "mr", "ms", "inc", "st", "al", "cf"}


def is_stop(text: str, i: int) -> bool:
    """A "." at i ends a sentence only if followed by whitespace/end/closing quote – never inside "TLS 1.2", "8.2", "RA-1c.1" – and not
    after an abbreviation ("e.g.", "Rev.", "U.S.") or a single-letter initial ("J. Doe")."""
    if text[i] != ".":
        return False
    nxt = text[i + 1] if i + 1 < len(text) else " "
    if not (nxt.isspace() or nxt in "\"”’)"):
        return False
    j = i
    while j > 0 and (text[j - 1].isalpha() or text[j - 1] == "."):
        j -= 1
    w = text[j:i].lower()
    return not (w in ABBR or (len(w) == 1 and w.isalpha() and text[j].isupper()))


def split_sentences(text: str) -> list[tuple[int, int]]:
    out, s = [], 0
    for i, ch in enumerate(text):
        if ch == "\n" or (ch == "." and is_stop(text, i)):
            e = i if ch == "\n" else i + 1
            if text[s:e].strip():
                out.append((s, e))
            s = i + 1
    if text[s:].strip():
        out.append((s, len(text)))
    return out


def sentence_at(text: str, start: int, end: int) -> tuple[int, int]:
    s = start
    while s > 0 and text[s - 1] != "\n" and not (text[s - 1] == "." and is_stop(text, s - 1)):
        s -= 1
    e = max(end, start)
    while e < len(text) and text[e] != "\n" and not (text[e] == "." and is_stop(text, e)):
        e += 1
    e = min(e + 1, len(text)) if e < len(text) and text[e] == "." else e
    while s < e and text[s].isspace():
        s += 1
    return s, e


TEXT_VERSION = "text-3"  # text-3: docx tables extracted; text-2: pdf per-page form feeds + docx page-break markers; older policies are re-extracted from the stored file


def _docx_text(data: bytes) -> str:
    """Paragraphs AND tables in document order (tables were dropped before: traceability matrices, schedules, timelines).
    Each table row becomes one line "cell | cell | …"; a merged cell is emitted once."""
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    d = docx.Document(io.BytesIO(data))
    out = []
    for el in d.element.body.iterchildren():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "p":
            out.append(_docx_para(Paragraph(el, d)))
        elif tag == "tbl":
            for row in Table(el, d).rows:
                cells, seen = [], []
                for c in row.cells:
                    if any(c._tc is x for x in seen):
                        continue
                    seen.append(c._tc)
                    cells.append(" ".join(c.text.split()))
                if any(cells):
                    out.append(" | ".join(cells))
    return "\n".join(out)


def _docx_para(p) -> str:
    """Paragraph text with a form feed where Word marks a page break (explicit break, page-break-before or rendered break)."""
    x = p._p.xml
    before = "w:pageBreakBefore" in x or "w:lastRenderedPageBreak" in x
    after = 'w:type="page"' in x
    return ("\f" if before else "") + p.text + ("\n\f" if after else "")


def refresh_text(db: Session, p: Policy) -> bool:
    """Re-extract an older policy from its stored original; when the text changed, QUEUE a background re-analysis (never inline)."""
    a = p.analysis or {}
    if a.get("text_version") == TEXT_VERSION or not p.storage_key or (p.file_name or "").lower().rsplit(".", 1)[-1] not in ("pdf", "docx"):
        return False
    text = extract_text(p.file_name, get_storage().get(p.storage_key))
    changed = text != (p.text_content or "")
    p.text_content = text
    p.analysis = {**a, "text_version": TEXT_VERSION}
    if changed and p.analysis_status == "analyzed":  # never analyse on access: a normal background job (AI lane, not the bulk lane)
        p.analysis = {**p.analysis, "text_refreshed": {"at": datetime.now(timezone.utc).isoformat(), "text_version": TEXT_VERSION,
                                                       "reason": "improved table extraction"}}
        queue_reanalysis(db, p, "text_refresh")
    return changed


def queue_reanalysis(db: Session, p: Policy, reason: str) -> None:
    """Queue one ordinary policy.analyze job (AI lane) unless one is already queued/running; human decisions are kept by the analysis."""
    from app.models import Job
    from app.services import jobs as jobsvc
    from app.services.policy_analyzer_v2 import queued_progress
    p.analysis_status = "queued"
    pending = db.scalar(select(Job.id).where(Job.job_type == "policy.analyze", Job.status.in_(("queued", "running")),
                                             Job.payload["policy_id"].astext == str(p.id)).limit(1))
    if pending is None:
        queued_progress(db, p, jobsvc.enqueue(db, "policy.analyze", {"policy_id": str(p.id), "reason": reason}))


def section_at(text: str, start: int, window: int | None = 40) -> str | None:
    """Nearest preceding heading line (numbered, 'Section n', control ID or Title Case), including the offset's own line."""
    eol = text.find("\n", start)
    lines = text[:eol if eol >= 0 else len(text)].splitlines()
    for line in reversed(lines[-window:] if window else lines):  # include the snippet's own line (A4: a "2. Scope." sentence is § 2)
        t = line.strip()
        if "|" in t or re.match(r"[A-Z]{2}-\d+(?:\s*\(\d+\))?[a-z]?(?:,?\s*(?:and|or)?\s*[A-Z]{2}-\d+(?:\s*\(\d+\))?)*\s+(?:is|are|was|were|shall|must|has|have)\b", t):
            continue  # table rows / prose starting with an ID ("RA-5(4) is a High-baseline enhancement.") are not headings
        if re.match(r"^(\d+(\.\d+)*\.?\s+\S|section\s+\d+|[A-Z]{2}-\d+(?:\s*\(\d+\))?\s+[A-Z]|[A-Z][A-Za-z &/-]{3,60}$)", t, re.IGNORECASE):
            m = re.match(r"^((?:section\s+)?\d+(?:\.\d+)*\.?\s+[^.:;]{1,60}|[A-Z]{2}-\d+(?:\s*\(\d+\))?\s+[^.:;]{1,60})(?:[.:;]|$)", t, re.IGNORECASE)
            return (m.group(1) if m else t)[:80]
    return None


def locate(text: str, start: int) -> str:
    """Page / section reference for an offset: nearest preceding heading line and form-feed page count."""
    head = section_at(text, start) or section_at(text, start, window=None)  # nearest heading, however far back
    return f"p. {text.count(chr(12), 0, start) + 1}" + (f", § {head}" if head else "")


def verbatim_quote(text: str, quote: str | None) -> dict:
    """Every stored quote must be an exact substring of the extracted text. Paraphrases are replaced by the best-matching
    sentence when one is close enough; otherwise they are flagged 'paraphrase – not a quote'."""
    import difflib

    q = (quote or "").strip().strip('"“”')
    if not q:
        return {"quote": None, "quote_status": "none"}
    i = text.find(q)
    if i >= 0:
        s, e = sentence_at(text, i, i + len(q))
        return {"quote": text[s:e], "start": s, "end": e, "quote_status": "verbatim", "location": locate(text, s)}
    sents = split_sentences(text)
    best = max(sents, key=lambda se: difflib.SequenceMatcher(None, q.lower(), text[se[0]:se[1]].lower()).ratio(), default=None)
    if best and difflib.SequenceMatcher(None, q.lower(), text[best[0]:best[1]].lower()).ratio() >= 0.6:
        s, e = sentence_at(text, best[0], best[1] - 1)
        return {"quote": text[s:e], "start": s, "end": e, "quote_status": "replaced_with_exact_sentence", "location": locate(text, s), "ai_text": q}
    return {"quote": q, "quote_status": "paraphrase", "label": "paraphrase – not a quote"}


def rule_extract(text: str, families: set[str] | None = None, top_policy_control: str | None = "ac-1") -> dict:
    """families: control families the policy maps to (None = legacy behaviour: AC). Required-section checks apply only to the
    policy's own subject – an RA policy is never flagged for a missing AC-17 remote-access section."""
    fam = {"ac"} if families is None else families
    vals = []
    from app.services.policy_profile import mask

    masked = mask(text)  # "AC-7 Unsuccessful Logon Attempts" must not yield "7 attempts"
    for cid, param, rx, unit in PARAMS:
        m = re.search(rx, masked, re.IGNORECASE)
        if m:
            v = next(g for g in m.groups() if g)
            s, e = sentence_at(text, m.start(), m.end())
            vals.append({"control_id": cid, "parameter": param, "value": f"{v} {unit}", "numeric_value": float(v), "unit": unit,
                         "quote": text[s:e], "start": s, "end": e, "quote_status": "verbatim", "location": locate(text, s)})
    low = text.lower()
    missing = [{"control_id": c if c != "ac-1" else (top_policy_control or "ac-1"), "section": label} for c, kw, label in REQUIRED_SECTIONS
               if (c == "ac-17" and "ac" in fam or c == "ac-1" and top_policy_control)
               and ((not re.search(kw, low)) or (kw == "official" and re.search(r"official:\s*(tbd|\[?name\]?|_+)?\s*$", low, re.M) and "named official" not in low))]
    outdated = [{"quote": text[slice(*sentence_at(text, m.start(), m.end()))]} for m in re.finditer(r"(?:NIST\s+)?SP\s*800-53\s*(?:Rev(?:ision)?\.?\s*4|r4)", text, re.IGNORECASE)][:3]
    return {"values": vals, "missing_sections": missing, "outdated_references": outdated}


def analyze_policy(db: Session, policy: Policy, ai_output: dict | None = None, ai_interaction_id=None, use_ai: bool = False,
                   ai_prefetched: dict | None = None) -> list[PolicyFinding]:
    """Deterministic extractor + optional AIService suggestions; every finding is 'proposed' until a human confirms/dismisses."""
    from app.models import Control
    from app.services import policy_mapping as pm

    det: dict = {}
    mappings = pm.extract_mappings(db, policy.text_content or "", det)
    families = {m["control_id"].split("-")[0] for m in mappings}
    in_scope = {m["control_id"].split("-")[0] for m in mappings if m["sources"] != ["title_language"]} or families
    dropped_scope = []
    top1 = next((m["control_id"] for m in mappings if re.fullmatch(r"[a-z]{2}-1", m["control_id"])), None)
    ex = rule_extract(policy.text_content or "", families, top1)
    pm.store_proposals(db, policy, mappings)
    known = set(db.scalars(select(Control.control_id)))
    out: list[PolicyFinding] = []
    db.query(PolicyFinding).filter(PolicyFinding.policy_id == policy.id, PolicyFinding.status == "proposed").delete()
    for sid in [uuid.UUID(x) for x in policy.system_ids or []]:
        def add(**kw):
            pf = PolicyFinding(policy_id=policy.id, system_id=sid, **kw)
            db.add(pf)
            out.append(pf)
        for v in ex["values"]:
            odp = db.scalar(select(OdpValue).where(OdpValue.system_id == sid, OdpValue.control_id == v["control_id"], OdpValue.parameter == v["parameter"]))
            obs = db.scalar(select(ObservedConfigValue).where(ObservedConfigValue.system_id == sid, ObservedConfigValue.control_id == v["control_id"],
                                                              ObservedConfigValue.parameter == v["parameter"]).order_by(ObservedConfigValue.observed_at.desc()))
            base = dict(control_id=v["control_id"], parameter=v["parameter"], policy_value=v["value"], odp_value=odp.value if odp else None,
                        observed_value=obs.value if obs else None, observed_evidence_id=obs.evidence_id if obs else None, quote=v["quote"], origin="rule_extractor")
            if odp and odp.numeric_value is not None and odp.numeric_value != v["numeric_value"]:
                add(finding_type="odp_not_met", description=f"Policy sets {v['value']} but the system's approved ODP for {v['control_id'].upper()} is {odp.value} ({odp.source})", **base)
            if obs and obs.numeric_value is not None and obs.numeric_value != v["numeric_value"]:
                add(finding_type="policy_vs_config_difference",
                    description=f"Policy documents {v['value']}; observed configuration is {obs.value} ({obs.source}, observed {obs.observed_at:%Y-%m-%d})", **base)
        for m in ex["missing_sections"]:
            add(finding_type="missing_policy_requirement", control_id=m["control_id"], description=f"Policy has no '{m['section']}'", origin="rule_extractor")
        for o in ex["outdated_references"]:
            add(finding_type="possible_outdated_reference", control_id="ac-1", description="Policy cites NIST SP 800-53 Rev 4; current catalog is Rev 5",
                quote=o["quote"], origin="rule_extractor")
        for s in (ai_output or {}).get("findings", []):
            cid = (s.get("control_id") or "").lower().replace("(", ".").replace(")", "").strip()
            if cid not in known:
                continue  # unknown control IDs from AI are dropped (validated against catalog)
            if cid.split("-")[0] not in in_scope or cid in det["not_selected"]:  # e.g. AC-17 for an RA policy – never a gap of this policy
                if sid == uuid.UUID((policy.system_ids or [None])[0]):
                    dropped_scope.append({"control_id": cid, "description": (s.get("description") or "")[:300]})
                continue
            vq = verbatim_quote(policy.text_content or "", s.get("quote"))
            qtxt = vq["quote"] if vq["quote_status"] != "paraphrase" else f"[paraphrase – not a quote] {vq['quote']}"
            add(finding_type="ai_suggested_needs_validation", control_id=cid, description=s.get("description", "")[:2000], quote=(qtxt or "")[:1000],
                origin="ai", ai_interaction_id=ai_interaction_id)
    policy.analysis_status = "analyzed"
    policy.analysis = {**ex, "text_version": (policy.analysis or {}).get("text_version"), "history": (policy.analysis or {}).get("history"), "control_mappings": [{k: m[k] for k in ("control_id", "confidence", "sources", "basis", "snippets", "parts")} for m in mappings],
                       "not_selected": det["not_selected"], "possible_related_controls": det["possible_related"],
                       "counts": {"proposed_maps": len(mappings), "possible_related_not_proposed": len(det["possible_related"]),
                                  "not_selected_flagged": len([m for m in mappings if m.get("not_selected")])},
                       "ai_dropped_out_of_scope": dropped_scope,
                       "ai_used": ai_output is not None, "ai_dropped_unknown_controls": [s.get("control_id") for s in (ai_output or {}).get("findings", [])
                                                                                                 if (s.get("control_id") or "").lower().replace("(", ".").replace(")", "") not in known]}
    from app.services import policy_coverage as pc

    pc.analyze(db, policy, use_ai=use_ai, ai_prefetched=ai_prefetched)  # after policy.analysis is set, so requirement-level values reach the top-level list
    db.flush()
    return out


def confirm_policy_finding(db: Session, pf: PolicyFinding, actor: User) -> Finding:
    if pf.status != "proposed":
        raise HTTPException(409, f"Already {pf.status}")
    rule = db.scalar(select(DedupRule).where(DedupRule.is_active.is_(True)).limit(1))
    controls = [pf.control_id] + ([pf.control_id.split(".")[0]] if pf.control_id and "." in pf.control_id else [])
    assigned = set(db.scalars(select(ControlAssignment.control_id).where(ControlAssignment.system_id == pf.system_id, ControlAssignment.control_id.in_(controls))))
    pol = db.get(Policy, pf.policy_id)
    f = Finding(id=uuid.uuid4(), system_id=pf.system_id, dedup_key=f"policy_audit:{pf.id}", dedup_rule_id=rule.id if rule else None,
                dedup_fields={"policy_finding_id": str(pf.id)}, source_type="policy_audit", rule_id=f"POL-{pf.finding_type}", title=pf.description[:500],
                severity="medium", cat="CAT II", first_seen_at=now(), last_seen_at=now(), current_state="open", observation_count=1,
                mapping_status="mapped" if assigned else "unmapped", latest_evidence_id=uuid.UUID(pol.evidence_ids[0]) if pol.evidence_ids else None)
    db.add(f)
    db.flush()
    for c in sorted(assigned):
        db.add(FindingControlMap(finding_id=f.id, control_id=c, mapping_source="policy_audit", review_status="human_approved", confidence="human_confirmed",
                                 source=f"Policy Auditor: {pol.title} v{pol.version}", provenance={"policy_finding_id": str(pf.id), "confirmed_by": actor.email}))
    pf.status, pf.reviewer_id, pf.decided_at, pf.finding_id = "confirmed", actor.id, now(), f.id
    audit.record(db, action="policy_finding.confirmed", actor_user_id=actor.id, actor_email=actor.email, entity_type="policy_finding", entity_id=str(pf.id),
                 after={"finding_id": str(f.id), "controls": sorted(assigned), "type": pf.finding_type})
    from app.services.evaluation import evaluate_system, take_snapshots
    db.flush()
    evaluate_system(db, pf.system_id)
    take_snapshots(db, trigger="policy_finding.confirmed")
    return f


# ---------- RMF workflow ----------
MONITOR_RULE = ("Monitor = needs attention when any open KEV, open CAT I, overdue POA&M, stale/expired control evidence or unhealthy source exists; "
                "completed only when none exist AND ≥80% of assigned controls have current supporting evidence; otherwise in progress.")


def _monitor(m: dict, srcs: list, stale_src: int) -> dict:
    if not srcs:
        return {"state": "not_configured", "reason": "No evidence sources connected", "link": "/evidence-sources", "rule": MONITOR_RULE}
    blockers = [f"{m['kev_open']} open KEV" if m["kev_open"] else None, f"{m['open_cat1']} open CAT I" if m["open_cat1"] else None,
                f"{m['overdue_poams']} overdue POA&M" if m["overdue_poams"] else None,
                f"{m['controls_stale']} controls with stale/expired evidence" if m["controls_stale"] else None,
                f"{stale_src} unhealthy sources" if stale_src else None]
    blockers = [b for b in blockers if b]
    cov = m["control_evidence_coverage_pct"] or 0
    facts = (f"Controls with current evidence: {m['controls_with_current_evidence']} of {m['assigned_controls']} ({cov}%); "
             f"evidence items within their freshness window: {m.get('evidence_items_fresh', 0)} of {m.get('evidence_total', 0)} collected items")
    state = "needs_attention" if blockers else ("completed" if cov >= 80 else "in_progress")
    return {"state": state, "reason": ("; ".join(blockers) + " · " if blockers else "") + facts, "link": "/evidence-sources", "rule": MONITOR_RULE,
            "blockers": blockers}


def workflow_stages(db: Session, s: System) -> list[dict]:
    """Derivation rules (documented in README): each stage reads live records only."""
    from app.services.evaluation import system_metrics

    m = system_metrics(db, s)
    roles = {r for (r,) in db.execute(select(RoleAssignment.role).where(RoleAssignment.scope_type == "system", RoleAssignment.scope_id == s.id))}
    ac = list(db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == s.id)))
    from app.services.evaluation import statement_map

    stm = statement_map(db, s.id)
    need_stmt = [a for a in ac if a.responsibility != "inherited"]
    narr = sum(1 for a in need_stmt if stm.get(a.id) == "has")
    assessed = sum(1 for a in ac if a.assessment_status not in ("not_assessed", None))
    srcs = list(db.scalars(select(EvidenceSource).where(EvidenceSource.system_id == s.id, EvidenceSource.enabled.is_(True))))
    stale_src = sum(1 for x in srcs if x.health not in ("ok", "healthy"))

    def st(ok, partial, reason, link):
        return {"state": "completed" if ok else ("in_progress" if partial else "needs_attention"), "reason": reason, "link": link}
    need = {"isso", "system_owner", "ao"} - roles
    stages = [
        ("1. Prepare", st(not need, bool(roles), "All key roles assigned" if not need else f"Missing system roles: {', '.join(sorted(need))}", f"/systems/{s.id}")),
        ("2. Categorize", st(bool(s.confidentiality_impact and s.integrity_impact and s.availability_impact), False,
                             f"FIPS 199 C/I/A = {s.confidentiality_impact}/{s.integrity_impact}/{s.availability_impact}", f"/systems/{s.id}")),
        ("3. Select", st(bool(ac), False, _select_label(db, s), f"/systems/{s.id}/controls")),
        ("4. Implement", st(need_stmt and narr == len(need_stmt), narr > 0, f"{narr} of {len(need_stmt)} non-inherited controls have an approved or submitted statement",
                            f"/systems/{s.id}/controls")),
        ("5. Assess", st(ac and assessed == len(ac), assessed > 0, f"{assessed} of {len(ac)} controls assessed by SCA", "/reviews")),
        ("6. Authorize", st(str(s.authorization_status).startswith("Authorized") and (m["days_to_expiration"] or 0) > 0, False,
                            f"{s.authorization_status}; expires {s.authorization_expiration or '—'}", f"/systems/{s.id}/authorization")),
        ("7. Monitor", _monitor(m, srcs, stale_src)),
    ]
    out = [{"stage": k, **v} for k, v in stages]
    att = db.scalar(select(func.count()).select_from(Attestation).where(Attestation.system_id == s.id, Attestation.status.in_(("pending", "expired")),
                                                                          Attestation.due_date < date.today()))
    pend = db.scalar(select(func.count()).select_from(ApprovalRequest).where(ApprovalRequest.system_id == s.id, ApprovalRequest.status == "pending"))
    pols = db.scalar(select(func.count()).select_from(PolicyFinding).where(PolicyFinding.system_id == s.id, PolicyFinding.status == "proposed"))
    def nc(reason, link):
        return {"state": "not_configured", "reason": reason, "link": link}
    n_poam = db.scalar(select(func.count()).select_from(Poam).where(Poam.system_id == s.id))
    n_att = db.scalar(select(func.count()).select_from(Attestation).where(Attestation.system_id == s.id))
    n_req = db.scalar(select(func.count()).select_from(ApprovalRequest).where(ApprovalRequest.system_id == s.id))
    n_pol = db.scalar(select(func.count()).select_from(PolicyFinding).where(PolicyFinding.system_id == s.id))
    out += [{"stage": "Ongoing: POA&M", **(st(m["overdue_poams"] == 0, True, f"{m['open_poams']} open, {m['overdue_poams']} overdue", "/poams")
                                           if n_poam else nc("No POA&Ms yet", "/poams"))},
            {"stage": "Ongoing: Attestations", **(st(att == 0, True, f"{att} overdue attestations", "/inheritance") if n_att else nc("No attestations yet", "/inheritance"))},
            {"stage": "Ongoing: Reviews", **(st(pend == 0, True, f"{pend} pending review requests", "/reviews") if n_req else nc("No review requests yet", "/reviews"))},
            {"stage": "Ongoing: Policy audit", **(st(pols == 0, True, f"{pols} proposed policy findings awaiting confirmation", "/policy-auditor")
                                                  if n_pol else nc("No policies audited yet", "/policy-auditor"))}]
    return out


# ---------- search ----------
def search(db: Session, q: str, systems: list, org_id, selected=None) -> list[dict]:
    """Server-side ILIKE search restricted to RBAC-visible systems. Control hits resolve to the selected system when it is
    visible and assigns the control; otherwise one hit per visible system that assigns it (labelled with the system)."""
    from app.models import Asset, Control

    like, res = f"%{q}%", []
    system_ids = [s.id for s in systems]
    names = {s.id: s.acronym or s.name for s in systems}
    for s in db.scalars(select(System).where(System.id.in_(system_ids), or_(System.name.ilike(like), System.acronym.ilike(like))).limit(5)):
        res.append({"type": "system", "label": f"{s.acronym} · {s.name}", "link": f"/systems/{s.id}", "system_id": str(s.id)})
    for a in db.scalars(select(Asset).where(Asset.system_id.in_(system_ids), or_(Asset.name.ilike(like), Asset.ip_address.ilike(like))).limit(5)):
        res.append({"type": "asset", "label": f"{a.name} ({a.ip_address})", "link": f"/systems/{a.system_id}", "system_id": str(a.system_id)})
    from app.services.content.loader import active_catalog_id

    cat = active_catalog_id(db)
    for c in db.scalars(select(Control).where(Control.catalog_version_id == cat, or_(Control.control_id.ilike(q.lower().replace("(", ".").replace(")", "")),
                                                                                    Control.title.ilike(like))).limit(5)):
        owners = [sid for (sid,) in db.execute(select(ControlAssignment.system_id).where(ControlAssignment.control_id == c.control_id,
                                                                                       ControlAssignment.system_id.in_(system_ids)))]
        if selected in owners:
            owners = [selected]
        if not owners:
            res.append({"type": "control", "label": f"{c.label} {c.title} (catalog)", "link": "/catalog", "group": "Catalog"})
        for sid in owners[:4]:
            res.append({"type": "control", "label": f"{c.label} {c.title} · {names[sid]}", "link": f"/systems/{sid}/controls/{c.control_id}",
                        "system_id": str(sid), "group": names[sid]})
    for f in db.scalars(select(Finding).where(Finding.system_id.in_(system_ids), or_(Finding.title.ilike(like), Finding.vuln_id.ilike(like),
                                                                                    Finding.plugin_id.ilike(like))).limit(5)):
        res.append({"type": "finding", "label": f"{f.vuln_id or f.plugin_id or ''} {f.title}", "link": f"/findings/{f.id}", "system_id": str(f.system_id)})
    for e in db.scalars(select(Evidence).where(Evidence.system_id.in_(system_ids), or_(Evidence.name.ilike(like), Evidence.sha256.ilike(like))).limit(5)):
        res.append({"type": "evidence", "label": e.name, "link": "/evidence-ledger", "system_id": str(e.system_id)})
    for p in db.scalars(select(Poam).where(Poam.system_id.in_(system_ids), or_(Poam.human_id.ilike(like), Poam.weakness.ilike(like))).limit(5)):
        res.append({"type": "poam", "label": f"{p.human_id} {p.weakness}", "link": f"/poams/{p.id}", "system_id": str(p.system_id)})
    for p in db.scalars(select(Policy).where(Policy.org_id == org_id, Policy.title.ilike(like)).limit(5)):
        res.append({"type": "policy", "label": f"{p.title} v{p.version}", "link": f"/policy-auditor/{p.id}"})
    for r in db.scalars(select(ApprovalRequest).where(ApprovalRequest.system_id.in_(system_ids), or_(ApprovalRequest.human_id.ilike(like),
                                                                                                    ApprovalRequest.justification.ilike(like))).limit(5)):
        res.append({"type": "review", "label": f"{r.human_id} {r.request_type}", "link": f"/reviews/{r.id}", "system_id": str(r.system_id)})
    return res


_ = (CommonControlProvider,)


def _select_label(db: Session, s) -> str:
    from app.services.counts import system_counts
    c = system_counts(db, s)["labels"]
    return f"{c['assigned']} ({c['reconciliation']})"
