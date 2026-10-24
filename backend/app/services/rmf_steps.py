"""RMF 7 steps (NIST SP 800-37 Rev 2): step status from live records, FIPS 199 / CNSSI 1253 categorization, Select-step tailoring."""
import csv
import io
import json
import uuid
from datetime import date
from functools import lru_cache
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (ApprovalRequest, Control, ControlAssignment, EvidenceSource, Implementation, Overlay, Poam, RoleAssignment,
                        System, TailoringDecision, User)
from app.services import audit
from app.services.content.loader import active_catalog_id
from app.services.systems import LEVEL, baseline_control_ids

KEY_ROLES = [
    ("system_owner", "System Owner (ISO)", "Owns the system and its risk; signs the SSP.", True),
    ("isso", "ISSO", "Information System Security Officer – maintains the security posture day to day.", True),
    ("issm", "ISSM", "Information System Security Manager – oversees ISSOs and the security program.", True),
    ("ao", "Authorizing Official (AO)", "Senior official who accepts the risk and grants the authorization.", True),
    ("aodr", "AO Designated Representative (AODR)", "Acts for the AO on coordination tasks; cannot make the final decision.", False),
    ("sca", "Security Control Assessor (SCA)", "Independent assessor who tests the controls and writes the SAR.", True),
    ("ccp", "Common Control Provider (CCP)", "Organization or system whose controls this system inherits.", False),
    ("pm", "Program Manager (PM)", "Responsible for cost, schedule and performance of the program.", False),
    ("privacy_officer", "Senior Agency Official for Privacy / Privacy Officer", "Reviews PII handling and the privacy controls.", False),
    ("user_rep", "User Representative", "Speaks for the operational users of the system.", False),
]
REQUIRED_ROLES = [k for k, _, _, req in KEY_ROLES if req]
# Not offered in the system registration role picker (they stay in the authorization model: CCP in Inheritance, AODR in Authorize).
NOT_AT_REGISTRATION = {"aodr": "AODR", "ccp": "Common Control Provider (CCP)", "user_rep": "User Representative"}
ROLE_ALIASES = {"common_control_provider": "ccp", "user_representative": "user_rep", "userrep": "user_rep",
                "ao_designated_representative": "aodr", "ao_designated_rep": "aodr", "authorizing_official_designated_representative": "aodr"}
ROLE_KEYS = [k for k, _, _, _ in KEY_ROLES]


def unknown_role_keys(roles: dict | None) -> list[str]:
    return sorted(k for k in (roles or {}) if k not in ROLE_KEYS and k not in ROLE_ALIASES)
ROLE_USER_FIELD = {"system_owner": "system_owner_id", "isso": "isso_id", "issm": "issm_id", "ao": "ao_id"}

EMASS = "eMASS-aligned; verify against your eMASS instance"
ACTION_LABELS = {
    "system.write": "Changing system records, roles, categorization or the control selection",
    "implementation.write": "Changing implementation status or writing implementation statements",
    "assessment.perform": "Recording assessment results (Satisfied / Other than satisfied)",
    "authorization.decide": "Recording an authorization decision (ATO / IATT / DATO)",
    "risk.accept": "Accepting residual risk",
    "poam.manage": "Creating or editing POA&M items",
    "finding.map": "Approving, rejecting or editing mappings",
    "ingest.upload": "Uploading scan, checklist or policy files",
    "source.manage": "Connecting tools and creating evidence sources",
    "system.register": "Registering a new system",
    "system.roles.manage": "Assigning people to system roles",
    "comment.write": "Adding reviewer comments",
    "evidence.verify": "Running evidence integrity checks",
    "emass.queue": "Queuing eMASS changes",
    "content.apply": "Applying content updates (STIG / KEV / CCI)",
    "admin.content.load": "Loading reference content and official overlay lists",
    "audit.read": "Reading the audit log",
    "portfolio.read": "Viewing the portfolio / leadership dashboard",
}
MISSION_CRITICALITY = [
    ("MC", "Mission Critical (MC)", "Loss would prevent the organization from performing a primary mission (e.g. warfighting, direct mission support)."),
    ("ME", "Mission Essential (ME)", "Basic and necessary for accomplishing the mission; loss degrades it but a work-around may exist for a short time."),
    ("MS", "Mission Support (MS)", "Supports day-to-day business but is not critical or essential to the primary mission."),
]
SYSTEM_TYPES = [
    ("IS Major Application", "A software application that needs special security attention because of the impact of its loss."),
    ("IS Enclave", "A collection of computing environments under one authority, with a common security policy (e.g. a LAN/base network)."),
    ("Platform IT System", "IT that is part of a special-purpose platform (weapon system, vehicle, medical device, SCADA/ICS)."),
    ("Platform IT Interconnection", "A connection between a Platform IT system and an external network."),
    ("PIT Product / IT Service", "A stand-alone product or a service that is assessed and accepted rather than authorized as a system."),
    ("Cloud Service Offering", "A service delivered by a cloud provider (IaaS/PaaS/SaaS) under its own or a DoD provisional authorization."),
]
ACQUISITION_CATEGORIES = [
    ("ACAT I", "Major Defense Acquisition Program – the largest programs (highest cost thresholds)."),
    ("ACAT IA", "Major Automated Information System (legacy category for large IT programs)."),
    ("ACAT II", "Major systems below the ACAT I thresholds."),
    ("ACAT III", "Programs that do not meet ACAT I/II criteria."),
    ("Non-ACAT / Not applicable", "Not an acquisition program (e.g. operations & maintenance or a service)."),
]
AUTHORIZATION_TYPES = [
    ("ATO", "Authorization to Operate – the AO accepts the risk for a fixed period."),
    ("ATO with conditions", "ATO that requires specific actions or limits by a set date."),
    ("IATT", "Interim Authorization to Test – operate only for testing in a defined environment and period."),
    ("DATO", "Denial of Authorization to Operate – risk not acceptable; the system may not operate."),
    ("Common Control Authorization", "Authorization of a common control provider whose controls other systems inherit."),
    ("Type Authorization", "One authorization for identical systems deployed to multiple locations."),
]
ENVIRONMENTS = [
    ("on_prem_gov", "On-premises (government facility)", False),
    ("contractor", "Contractor facility", False),
    ("cloud_iaas", "Cloud – IaaS", True), ("cloud_paas", "Cloud – PaaS", True), ("cloud_saas", "Cloud – SaaS", True),
    ("hybrid", "Hybrid (on-premises + cloud)", True),
    ("tactical", "Tactical / deployed", False),
    ("other", "Other (describe)", False),
]
CNSSI_OVERLAYS = [
    ("cnssi-privacy", "CNSSI 1253 Appendix F Attachment 6 – Privacy Overlay"),
    ("cnssi-classified", "CNSSI 1253 Appendix F Attachment 5 – Classified Information Overlay"),
    ("cnssi-intelligence", "CNSSI 1253 Appendix F – Intelligence Overlay"),
    ("cnssi-space", "CNSSI 1253 Appendix F Attachment 2 – Space Platform Overlay"),
    ("cnssi-cds", "CNSSI 1253 Appendix F Attachment 3 – Cross Domain Solution Overlay"),
    ("cnssi-nc3", "CNSSI 1253 Appendix F – Nuclear Command, Control & Communications (NC3) Overlay"),
]
STRUCTURE_NOTE = ("Structure only – load the official control list. The official overlay text is distributed by CNSS and is not "
                  "reproduced here; import its control list as CSV (control_id,action) under Select → Overlays.")


@lru_cache
def info_type_catalog() -> dict:
    return json.loads((Path(__file__).parent / "content" / "sp800_60_info_types.json").read_text())


def _lvl(v: str | None) -> int:
    return LEVEL.get((v or "").lower(), 0)


def categorize(mode: str, info_types: list[dict], cia: dict | None = None) -> dict:
    """FIPS 199: per objective the high-water mark across information types; FIPS 200 / 800-53B: baseline = highest objective."""
    cat = {t["id"]: t for t in info_type_catalog()["types"]}
    rows, errors = [], []
    for it in info_types:
        ref = cat.get(it.get("id"))
        if ref is None:
            errors.append(f"Unknown information type {it.get('id')}")
            continue
        row = {"id": ref["id"], "name": ref["name"], "provisional": {k: ref[k] for k in "cia"}}
        adjusted = False
        for k in "cia":
            v = it.get(k) or ref[k]
            row[k] = v
            adjusted |= v != ref[k]
        row["rationale"] = (it.get("rationale") or "").strip()
        row["adjusted"] = adjusted
        if adjusted and len(row["rationale"]) < 10:
            errors.append(f"{ref['id']} {ref['name']}: you changed the provisional C/I/A – add a rationale (at least 10 characters)")
        rows.append(row)
    hw = {}
    for k, word in (("c", "Confidentiality"), ("i", "Integrity"), ("a", "Availability")):
        vals = [r[k] for r in rows if _lvl(r[k])]
        top = max(vals, key=_lvl) if vals else None
        if mode == "cnssi1253" and cia and cia.get(k):
            top = cia[k]
        hw[k] = top
    steps = []
    for k, word in (("c", "Confidentiality"), ("i", "Integrity"), ("a", "Availability")):
        src = [f"{r['id']} {r['name']} = {r[k]}" for r in rows if r[k] == hw[k]][:3]
        how = "chosen separately (CNSSI 1253)" if mode == "cnssi1253" and cia and cia.get(k) else f"high-water mark of {len(rows)} information type(s)"
        steps.append(f"{word}: {hw[k] or '—'} – {how}{(' – from ' + '; '.join(src)) if src and 'high-water' in how else ''}")
    vals = [v for v in hw.values() if v]
    top = max(vals, key=_lvl) if vals else None
    baseline = top.lower() if top else None
    selection = None
    if mode == "cnssi1253":
        overall = None  # CNSSI 1253 keeps three separate values – no single high-water category
        tri = "-".join((hw[k] or "—")[0] for k in "cia")
        steps.append(f"CNSSI 1253: security category stays per objective ({tri}); no single high-water value is computed.")
        if all(hw[k] for k in "cia"):
            from app.services import cnssi1253

            sel = cnssi1253.selection("-".join(hw[k][0].upper() for k in "cia"))
            b = sel["by"]
            selection = (f"CNSSI 1253 Appendix D (Tables D-1 to D-20) baseline for {sel['trigraph']}: C={hw['c']} → {len(b['c'])}, I={hw['i']} → {len(b['i'])}, "
                         f"A={hw['a']} → {len(b['a'])} controls; union {sel['security_union']} + NSS privacy control baseline {len(b['privacy'])} "
                         f"= {len(sel['ids'])} (Task S-1, §3.2.1, p. 10).")
        else:
            selection = "Set all three impact values to select the CNSSI 1253 Appendix D baseline (Task S-1, §3.2.1, p. 10)."
        steps.append(selection)
    else:
        overall = top
        steps.append(f"Overall categorization = highest of C/I/A = {overall or '—'} → 800-53B {overall or '—'} baseline (FIPS 200)")
    label = f"{{(confidentiality, {hw['c'] or '—'}), (integrity, {hw['i'] or '—'}), (availability, {hw['a'] or '—'})}}"
    return {"mode": mode, "rows": rows, "c": hw["c"], "i": hw["i"], "a": hw["a"], "overall": overall, "baseline": baseline, "baseline_selection": selection,
            "security_category": label, "steps": steps, "errors": errors}


def role_holders(db: Session, s: System) -> dict:
    out = {}
    kr = s.key_roles or {}
    for key, label, _, _ in KEY_ROLES:
        v = dict(kr.get(key) or {})
        fld = ROLE_USER_FIELD.get(key)
        if not v.get("user_id") and fld and getattr(s, fld):
            v["user_id"] = str(getattr(s, fld))
        if v.get("user_id"):
            u = db.get(User, uuid.UUID(str(v["user_id"])))
            v["display"] = u.display_name if u else "(unknown user)"
            v["email"] = u.email if u else v.get("email")
        elif v.get("name"):
            v["display"] = f"{v['name']} (placeholder – no account yet)"
        out[key] = v if v.get("display") else None
    return out


def save_roles(db: Session, s: System, roles: dict, actor: User) -> dict:
    before = s.key_roles
    bad = [k for k in roles if k not in ROLE_KEYS]
    if bad:
        raise ValueError(f"Unknown role key(s): {', '.join(sorted(bad))}. Allowed: {', '.join(ROLE_KEYS)}")
    clean = {}
    for key, _, _, _ in KEY_ROLES:
        v = roles.get(key) or {}
        uid = v.get("user_id") or None
        if uid:
            u = db.get(User, uuid.UUID(str(uid)))
            if u is None or u.org_id != s.org_id:
                raise ValueError(f"{key}: user not found in your organization")
            clean[key] = {"user_id": str(u.id)}
        elif (v.get("name") or "").strip():
            clean[key] = {"name": v["name"].strip()[:200], "email": (v.get("email") or "").strip()[:200] or None}
        fld = ROLE_USER_FIELD.get(key)
        if fld:
            setattr(s, fld, uuid.UUID(str(uid)) if uid else None)
    s.key_roles = clean
    audit.record(db, action="system.roles_updated", actor_user_id=actor.id, actor_email=actor.email, entity_type="system",
                 entity_id=str(s.id), before={"key_roles": before}, after={"key_roles": clean})
    return role_holders(db, s)


def _assignments(db, s):
    return list(db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == s.id)))


def steps(db: Session, s: System) -> dict:
    from app.services.counts import system_counts
    from app.services.evaluation import statement_map, system_metrics
    from app.services.rmf import _monitor

    ac = _assignments(db, s)
    n = len(ac)
    cnt = system_counts(db, s)
    holders = role_holders(db, s)
    missing = [lbl for k, lbl, _, req in KEY_ROLES if req and not holders.get(k)]
    filled = sum(1 for k in REQUIRED_ROLES if holders.get(k))

    def S(state, summary, criteria, label, link, progress=None):
        return {"status": state, "summary": summary, "criteria": criteria, "next_action": {"label": label, "link": link}, "progress": progress}

    out = []
    out.append(("prepare", "Prepare", S("complete" if not missing else ("needs_attention" if filled or s.key_roles else "not_started"),
               "All key roles assigned" if not missing else f"Missing: {', '.join(missing)}",
               "Complete when System Owner, ISSO, ISSM, AO and SCA each have a person (a user or a name/e-mail placeholder).",
               "Assign key roles", "/rmf/prepare", f"{filled} of {len(REQUIRED_ROLES)} required roles")))
    its = s.information_types or []
    cat_missing = [x for x, ok in (("information types", bool(its)), ("C/I/A", bool(s.confidentiality_impact and s.integrity_impact and s.availability_impact)),
                                   ("mission criticality", bool(s.mission_criticality)), ("operating environment", bool(s.operating_environment)),
                                   ("privacy question", s.processes_pii is not None)) if not ok]
    out.append(("categorize", "Categorize", S("complete" if not cat_missing else ("not_started" if not its else "needs_attention"),
               f"{(s.categorization or '—').capitalize()} ({s.confidentiality_impact or '—'}/{s.integrity_impact or '—'}/{s.availability_impact or '—'}) from {len(its)} information type(s)"
               + (f" · missing: {', '.join(cat_missing)}" if cat_missing else ""),
               "Complete when at least one SP 800-60 information type is selected, C/I/A is set, and mission criticality, operating environment and the PII question are answered.",
               "Categorize the system", "/rmf/categorize", f"{5 - len(cat_missing)} of 5 items")))
    rec = (s.categorization or "").lower() or None
    sel_issues = []
    if not ac:
        sel_issues.append("no controls selected yet")
    if rec and s.baseline_key and LEVEL.get(rec, 0) > LEVEL.get(s.baseline_key, 0):
        sel_issues.append(f"categorization is {s.categorization.capitalize()} but the baseline is {s.baseline_key.capitalize()}")
    if s.processes_pii and not s.include_privacy:
        sel_issues.append("system processes PII but the privacy baseline is not applied")
    out.append(("select", "Select", S("complete" if not sel_issues else ("not_started" if not ac else "needs_attention"),
               cnt["labels"]["reconciliation"] if not sel_issues else (lambda t: t[:1].upper() + t[1:])("; ".join(sel_issues)),
               "Complete when controls are selected, the baseline is at least the categorization level, and the privacy baseline is applied when the system processes PII.",
               "Review baseline, overlays and tailoring", "/rmf/select", cnt["labels"]["assigned"])))
    stm = statement_map(db, s.id)
    impl = sum(1 for a in ac if a.implementation_status in ("implemented", "inherited", "not_applicable"))
    narr = sum(1 for a in ac if a.responsibility != "inherited" and stm.get(a.id) == "has")
    out.append(("implement", "Implement", S("complete" if n and impl == n else ("not_started" if not impl and not narr else "needs_attention"),
               f"{impl:,} of {n:,} controls implemented (incl. inherited / N/A); {narr:,} have an implementation statement",
               "Complete when every assigned control is Implemented, Inherited or Not applicable.",
               "Work on unimplemented controls", f"/systems/{s.id}/controls?implementation_status=planned", f"{impl:,} of {n:,} implemented")))
    assessed = sum(1 for a in ac if a.assessment_status not in ("not_assessed", None))
    sat = sum(1 for a in ac if a.assessment_status == "satisfied")
    out.append(("assess", "Assess", S("complete" if n and assessed == n else ("not_started" if not assessed else "needs_attention"),
               f"{assessed:,} of {n:,} controls assessed ({sat:,} satisfied)",
               "Complete when the SCA has recorded an assessment result for every assigned control.",
               "Assess controls", f"/systems/{s.id}/controls?assessment_status=not_assessed", f"{assessed:,} of {n:,} assessed")))
    m = system_metrics(db, s)
    authorized = str(s.authorization_status).startswith("Authorized") and s.authorization_expiration and s.authorization_expiration > date.today()
    pending = db.scalar(select(func.count()).select_from(ApprovalRequest).where(ApprovalRequest.system_id == s.id, ApprovalRequest.status == "pending",
                                                                               ApprovalRequest.request_type == "authorization_package_review"))
    out.append(("authorize", "Authorize", S("complete" if authorized else ("needs_attention" if pending or s.authorization_expiration else "not_started"),
               f"{s.authorization_status}; expires {s.authorization_expiration or '—'}" + (" · package submitted, awaiting AO" if pending else ""),
               "Complete when the AO has recorded an ATO (or ATO with conditions / IATT) that has not expired.",
               "Prepare the authorization package", "/rmf/authorize", f"{m['open_poams']} open POA&Ms")))
    srcs = list(db.scalars(select(EvidenceSource).where(EvidenceSource.system_id == s.id, EvidenceSource.enabled.is_(True))))
    mon = _monitor(m, srcs, sum(1 for x in srcs if x.health not in ("ok", "healthy")))
    mstate = {"completed": "complete", "not_configured": "not_started"}.get(mon["state"], "needs_attention")
    out.append(("monitor", "Monitor", S(mstate, mon["reason"],
               "Complete when evidence sources are connected, ≥80% of controls have current evidence and there are no open KEV / CAT I, overdue POA&Ms or unhealthy sources.",
               "Review continuous monitoring", "/rmf/monitor", cnt["labels"]["with_current_evidence"])))
    rows = [{"key": k, "number": i + 1, "label": lbl, **v} for i, (k, lbl, v) in enumerate(out)]
    nxt = next((r for r in rows if r["status"] != "complete"), None)
    return {"system": {"id": str(s.id), "name": s.name, "acronym": s.acronym}, "steps": rows,
            "next_action": ({"step": nxt["label"], **nxt["next_action"]} if nxt else
                            {"step": "Monitor", "label": "All steps complete – keep monitoring", "link": "/rmf/monitor"})}


def ensure_overlays(db: Session) -> None:
    from app.services.overlays import ensure_public

    for key, title in CNSSI_OVERLAYS:
        if not db.scalar(select(Overlay.id).where(Overlay.overlay_key == key)):
            db.add(Overlay(overlay_key=key, version="structure", title=title, description=STRUCTURE_NOTE, controls_add=[], controls_remove=[],
                           is_synthetic=False, structure_only=True, source="CNSSI 1253 (structure only)"))
    db.flush()
    ensure_public(db)


def import_overlay_csv(db: Session, key: str, version: str, data: bytes, actor: User) -> Overlay:
    base = db.scalar(select(Overlay).where(Overlay.overlay_key == key).order_by(Overlay.created_at.desc()))
    if base is None:
        raise ValueError("Unknown overlay")
    if db.scalar(select(Overlay.id).where(Overlay.overlay_key == key, Overlay.version == version)):
        raise ValueError(f"Version {version} of this overlay already exists – use a new version label")
    cat = active_catalog_id(db)
    known = set(db.scalars(select(Control.control_id).where(Control.catalog_version_id == cat)))
    add, rem, errs = [], [], []
    for i, r in enumerate(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))), start=2):
        cid = (r.get("control_id") or "").strip().lower().replace("(", ".").replace(")", "")
        act = (r.get("action") or "add").strip().lower()
        if cid not in known:
            errs.append(f"row {i}: {cid or '(blank)'} is not in the 800-53 Rev 5 catalog")
        elif act not in ("add", "remove"):
            errs.append(f"row {i}: action must be add or remove")
        else:
            (add if act == "add" else rem).append(cid)
    if errs:
        raise ValueError("; ".join(errs[:10]))
    if not add and not rem:
        raise ValueError("The CSV has no rows – expected columns control_id,action")
    db.query(Overlay).filter(Overlay.overlay_key == key).update({"is_active": False})
    ov = Overlay(overlay_key=key, version=version, title=base.title, description=f"Imported from the official list by {actor.email}",
                 controls_add=sorted(set(add)), controls_remove=sorted(set(rem)), is_synthetic=False, structure_only=False, source="csv import",
                 group_key=base.group_key, variant=base.variant, provenance={**(base.provenance or {}), "csv_import": True, "date": version},
                 details={c: d for c, d in (base.details or {}).items() if c in set(add) | set(rem)})
    db.add(ov)
    audit.record(db, action="overlay.imported", actor_user_id=actor.id, actor_email=actor.email, entity_type="overlay", entity_id=key,
                 after={"version": version, "add": len(add), "remove": len(rem)})
    return ov


def _catalog_ids(db, ids):
    cat = active_catalog_id(db)
    return {c.control_id: c.id for c in db.scalars(select(Control).where(Control.catalog_version_id == cat, Control.control_id.in_(ids)))}


def _add(db, s, ids, origin, detail, actor):
    have = {a.control_id for a in _assignments(db, s)}
    ids = [c for c in dict.fromkeys(ids) if c not in have]
    cat = _catalog_ids(db, ids)
    missing = [c for c in ids if c not in cat]
    if missing:
        raise ValueError(f"Not in the 800-53 Rev 5 catalog: {', '.join(missing[:10])}")
    for cid in ids:
        a = ControlAssignment(id=uuid.uuid4(), system_id=s.id, control_uuid=cat[cid], control_id=cid, origin=origin, origin_detail=detail,
                              responsibility="system", implementation_status="planned")
        db.add(a)
        db.add(Implementation(assignment_id=a.id, version=1, narrative="", implementation_status="planned", author_id=actor.id))
    return ids


def _remove(db, s, ids):
    rows = [a for a in _assignments(db, s) if a.control_id in set(ids)]
    for a in rows:
        db.delete(a)
    return sorted(a.control_id for a in rows)


def _finish(db, s, actor, action, detail):
    db.flush()
    from app.services.evaluation import evaluate_system

    evaluate_system(db, s.id)
    audit.record(db, action=action, actor_user_id=actor.id, actor_email=actor.email, entity_type="system", entity_id=str(s.id), after=detail)


def apply_baseline(db: Session, s: System, key: str, include_privacy: bool, actor: User) -> dict:
    if s.categorization_mode == "cnssi1253" and (s.cnssi_baseline or {}).get("applied"):
        raise ValueError("This NSS system uses the CNSSI 1253 Appendix D baseline for its C-I-A trigraph – review the CNSSI 1253 baseline proposal instead of applying an SP 800-53B baseline")
    before = (s.baseline_key, s.include_privacy)
    s.baseline_key, s.include_privacy = key, include_privacy
    want = list(baseline_control_ids(db, key)) + (list(baseline_control_ids(db, "privacy")) if include_privacy else [])
    removed = set(db.scalars(select(TailoringDecision.control_id).where(TailoringDecision.system_id == s.id, TailoringDecision.action == "remove")))
    added = _add(db, s, [c for c in want if c not in removed], "baseline", key, actor)
    beyond = sorted(a.control_id for a in _assignments(db, s) if a.origin == "baseline" and a.control_id not in set(want))
    _finish(db, s, actor, "system.baseline_applied", {"from": before, "to": [key, include_privacy], "added": len(added)})
    return {"added": len(added), "added_ids": added[:50], "beyond_baseline": beyond}


def set_overlay(db: Session, s: System, key: str, on: bool, actor: User) -> dict:
    from app.services import overlays as ovs

    ov = db.scalar(select(Overlay).where(Overlay.overlay_key == key, Overlay.is_active.is_(True)).order_by(Overlay.created_at.desc()))
    if ov is None:
        raise ValueError("Unknown overlay")
    if on and key.startswith("cnssi-"):
        from app.services.rmf_accuracy import overlay_availability

        ok, why = overlay_availability(s, key.split("-")[1])
        if not ok:
            raise ValueError(why)
    if on:
        if ov.structure_only:
            raise ValueError(f"{ov.title} is structure only – load the official control list (CSV import) before applying it")
        if key in (s.overlay_keys or []):
            raise ValueError(f"{ov.title} is already applied")
        out = ovs.apply(db, s, ov, actor, _add)
    else:
        if key not in (s.overlay_keys or []):
            raise ValueError(f"{ov.title} is not applied to this system")
        out = ovs.remove(db, s, ov, actor)
    _finish(db, s, actor, "system.overlay_" + ("applied" if on else "removed"), {"overlay": key, "version": ov.version, **out})
    return {"added": [], "removed": [], **out}


def tailor(db: Session, s: System, action: str, ids: list[str], justification: str, actor: User) -> dict:
    if len((justification or "").strip()) < 10:
        raise ValueError("A rationale of at least 10 characters is required for every tailoring decision")
    ids = [c.strip().lower().replace("(", ".").replace(")", "") for c in ids if c.strip()]
    if not ids:
        raise ValueError("Select or enter at least one control")
    done = _add(db, s, ids, "tailored_in", "tailoring", actor) if action == "add" else _remove(db, s, ids)
    for cid in done:
        db.add(TailoringDecision(system_id=s.id, control_id=cid, action=action, justification=justification.strip(), decided_by=actor.id))
    _finish(db, s, actor, "system.tailored", {"action": action, "controls": done, "justification": justification})
    return {"action": action, "controls": done, "skipped": sorted(set(ids) - set(done))}


def authorization_checklist(db: Session, s: System) -> list[dict]:
    from app.services.rmf import package

    p = package(db, s)
    ac = p["ssp"]["assigned"]
    holders = role_holders(db, s)
    open_cat1 = p["metrics"].get("open_cat1", 0)
    items = [
        ("Key roles assigned (Prepare)", all(holders.get(k) for k in REQUIRED_ROLES), "/rmf/prepare"),
        ("Security categorization documented (FIPS 199 / CNSSI 1253)", bool(s.information_types and s.categorization), "/rmf/categorize"),
        ("Privacy Threshold Analysis answered", s.processes_pii is not None, "/rmf/categorize"),
        (f"System Security Plan: {p['ssp']['approved_narratives']:,} of {ac:,} controls have an approved statement",
         ac and p["ssp"]["approved_narratives"] >= ac, f"/systems/{s.id}/controls"),
        (f"Security Assessment Report: {ac - p['assessment'].get('not_assessed', 0):,} of {ac:,} controls assessed",
         ac and not p["assessment"].get("not_assessed"), "/reviews"),
        (f"POA&M: {len(p['open_poams'])} open item(s) documented", True, "/poams"),
        (f"No open CAT I findings ({open_cat1} open)", open_cat1 == 0, f"/systems/{s.id}/controls"),
        ("Package submitted to the AO", db.scalar(select(func.count()).select_from(ApprovalRequest).where(
            ApprovalRequest.system_id == s.id, ApprovalRequest.request_type == "authorization_package_review")) > 0, f"/systems/{s.id}/authorization"),
    ]
    return [{"item": t, "done": bool(d), "link": link} for t, d, link in items]


def traceability(db: Session, s: System) -> list[dict]:
    from app.models import EvidenceControl, Finding, FindingControlMap

    stm_rows = dict(db.execute(select(Implementation.assignment_id, func.max(Implementation.review_status))
                               .join(ControlAssignment, ControlAssignment.id == Implementation.assignment_id)
                               .where(ControlAssignment.system_id == s.id).group_by(Implementation.assignment_id)).all())
    ev = dict(db.execute(select(EvidenceControl.assignment_id, func.count()).join(ControlAssignment, ControlAssignment.id == EvidenceControl.assignment_id)
                         .where(ControlAssignment.system_id == s.id).group_by(EvidenceControl.assignment_id)).all())
    fnd = dict(db.execute(select(FindingControlMap.control_id, func.count(func.distinct(Finding.id))).join(Finding, Finding.id == FindingControlMap.finding_id)
                          .where(Finding.system_id == s.id, FindingControlMap.valid_to.is_(None), FindingControlMap.review_status != "rejected",
                                 Finding.current_state == "open").group_by(FindingControlMap.control_id)).all())
    poam: dict = {}
    for ids in db.scalars(select(Poam.control_ids).where(Poam.system_id == s.id, Poam.status.notin_(("closed",)))):
        for c in ids or []:
            poam[c] = poam.get(c, 0) + 1
    return [{"control_id": a.control_id, "origin": a.origin, "responsibility": a.responsibility, "implementation_status": a.implementation_status,
             "statement": stm_rows.get(a.id) or "none", "evidence": ev.get(a.id, 0), "open_findings": fnd.get(a.control_id, 0),
             "open_poams": poam.get(a.control_id, 0), "assessment_status": a.assessment_status, "freshness": a.evidence_freshness_status}
            for a in sorted(_assignments(db, s), key=lambda x: x.control_id)]


def role_on_system(db, s, user_id) -> list[str]:
    return list(db.scalars(select(RoleAssignment.role).where(RoleAssignment.user_id == user_id, RoleAssignment.scope_id == s.id)))
