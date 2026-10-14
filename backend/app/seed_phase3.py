"""Phase 3 synthetic seed: providers, shared responsibilities, attestations, ODP/observed values, policy library."""
import os
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (Attestation, CommonControlProvider, ControlAssignment, Evidence, EvidenceSource, ObservedConfigValue, OdpValue, Organization,
                        Policy, System, User)
from app.services import rmf

SHARED = {
    "cm-6": ("Provider hardens the GovCloud host OS images to the DISA STIG baseline and publishes monthly compliance scans.",
             "System team configures application, database and container settings and remediates checklist findings on LTP assets."),
    "ac-2": ("Provider manages the enterprise identity provider, privileged cloud console accounts and federation.",
             "System team manages application accounts, role assignments, inactivity disablement and quarterly reviews."),
    "sc-28": ("Provider supplies FIPS-capable KMS keys and encrypts storage volumes at rest by default.",
              "System team enables encryption on application data stores and manages key policies for LTP buckets."),
}
POLICIES = ["Audit and Accountability Policy", "Awareness and Training Policy", "Configuration Management Policy", "Contingency Planning Policy",
            "Identification and Authentication Policy", "Incident Response Policy", "Maintenance Policy", "Media Protection Policy",
            "Physical and Environmental Protection Policy", "Personnel Security Policy", "Risk Assessment Policy",
            "System and Communications Protection Policy", "System and Information Integrity Policy"]


def seed_phase3(db: Session, org: Organization, samples_dir: str) -> None:
    ltp = db.scalar(select(System).where(System.org_id == org.id, System.acronym == "LTP"))
    if ltp is None or db.scalar(select(Policy.id).where(Policy.org_id == org.id).limit(1)):
        return
    today = date.today()
    from app.seed_phase1 import role_user

    owner = role_user(db, org, "system_owner")
    prov = db.scalar(select(CommonControlProvider).where(CommonControlProvider.org_id == org.id).limit(1))
    if prov is None:
        prov = CommonControlProvider(org_id=org.id, name="IronVision GovCloud Platform", source="seed")
        db.add(prov)
    prov.package = prov.package or "IronVision GovCloud Platform – FedRAMP High authorization package (SYNTHETIC)"
    prov.basis, prov.coverage_text = "FedRAMP High P-ATO (synthetic)", "Physical/environmental, hypervisor, host OS hardening, KMS, enterprise IdP"
    prov.last_validated_at, prov.package_expiration, prov.evidence_refs = today - timedelta(days=40), today + timedelta(days=320), ["SYN-FEDRAMP-PKG-2026"]
    db.flush()
    for cid, (ptxt, stxt) in SHARED.items():
        a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == ltp.id, ControlAssignment.control_id == cid))
        if a:
            a.responsibility, a.provider_id = "shared", a.provider_id or prov.id
            a.provider_responsibility_text, a.system_responsibility_text = ptxt, stxt
    for a in db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == ltp.id, ControlAssignment.responsibility.in_(("shared", "inherited")),
                                                        ControlAssignment.provider_id.is_(None))):
        a.provider_id = prov.id
    atts = [("cp-4", "Contingency plan tested (tabletop) within the last 12 months", -10, False),
            ("at-2", "All LTP users completed annual security awareness training", 12, False),
            ("mp-6", "Media sanitization records reviewed for decommissioned drives", 200, True),
            ("ir-3", "Incident response capability tested this year", 150, True),
            ("ps-3", "Personnel screening completed for all privileged users", 260, True)]
    for cid, stmt, due, signed in atts:
        a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == ltp.id, ControlAssignment.control_id == cid))
        if a is None:
            continue
        at = Attestation(system_id=ltp.id, assignment_id=a.id, control_id=cid, statement=stmt, owner_id=owner.id if owner else None,
                         evidence_required="Signed record or report (PDF/DOCX)", due_date=today + timedelta(days=due))
        db.add(at)
        db.flush()
        if signed:
            ev = rmf.store_evidence(db, ltp.id, f"{cid}_attestation_record.txt", f"SYNTHETIC attestation record for {cid}".encode(), "attestation",
                                    "seed", "manual_attestation")
            at.evidence_id = ev.id
            at.due_date = today - timedelta(days=30)
            rmf.sign_attestation(db, at, owner)
            at.expires_at = today + timedelta(days=due)
    extra = ["pl-1", "pl-2", "pl-4", "pl-4.1", "pl-8", "pl-10", "pl-11", "ps-1", "ps-2", "ps-4", "ps-5", "ps-6", "ps-7", "ps-8", "ps-9", "at-1",
             "at-3", "at-4", "at-2.2", "at-2.3", "ca-1", "ca-2", "ca-3", "ca-5", "ca-6", "ca-9", "sa-1", "sa-2", "sa-3", "sa-5", "sa-8", "sr-1", "sr-2"]
    for i, cid in enumerate(extra):
        a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == ltp.id, ControlAssignment.control_id == cid))
        if a is not None:
            db.add(Attestation(system_id=ltp.id, assignment_id=a.id, control_id=cid, owner_id=owner.id if owner else None,
                               statement=f"{cid.upper()} procedural requirement met for LTP (annual attestation, SYNTHETIC)",
                               evidence_required="Signed record or report (PDF/DOCX)", due_date=today + timedelta(days=45 + i * 8)))
    aws = db.scalar(select(Evidence).join(EvidenceSource, EvidenceSource.id == Evidence.source_id)
                    .where(Evidence.system_id == ltp.id, EvidenceSource.source_type.like("aws%")).order_by(Evidence.collected_at.desc()).limit(1))
    for cid, param, odp, obs, unit in (("ac-2.3", "inactivity_disable_days", 35, 90, "days"), ("ac-7", "unsuccessful_logon_attempts", 3, 3, "attempts"),
                                       ("ac-11", "session_lock_minutes", 15, 15, "minutes")):
        db.add(OdpValue(system_id=ltp.id, control_id=cid, parameter=param, value=f"{odp} {unit}", numeric_value=odp, unit=unit,
                        source="LTP SSP organization-defined parameter (SYNTHETIC)", approved_by="ISSM (synthetic)", approved_at=today - timedelta(days=120)))
        db.add(ObservedConfigValue(system_id=ltp.id, control_id=cid, parameter=param, value=f"{obs} {unit}", numeric_value=obs, unit=unit,
                                   evidence_id=aws.id if aws else None, observed_at=aws.collected_at if aws else datetime.now(timezone.utc),
                                   source="AWS GovCloud demo connector (MOCK)" if aws else "Manual configuration record (synthetic)"))
    db.flush()
    path = os.path.join(samples_dir, "policies", "access_control_policy.txt")
    if os.path.exists(path):
        data = open(path, "rb").read()
        ev = rmf.store_evidence(db, ltp.id, "access_control_policy.txt", data, "policy", "seed", "policy_library")
        p = Policy(org_id=org.id, policy_key="access-control-policy", title="Access Control Policy", owner="Office of the CISO (synthetic)",
                   approval_date=today - timedelta(days=400), review_due=today - timedelta(days=35), system_ids=[str(ltp.id)], file_name="access_control_policy.txt",
                   storage_key=ev.storage_key, sha256=ev.sha256, evidence_ids=[str(ev.id)], text_content=data.decode())
        db.add(p)
        db.flush()
        rmf.analyze_policy(db, p)
        p.analysis = {**p.analysis, "ai_note": "Seeded with deterministic extractor only (no AI call at seed time)"}
    for i, t in enumerate(POLICIES):
        db.add(Policy(org_id=org.id, policy_key=t.lower().replace(" ", "-"), title=t, owner="Office of the CISO (synthetic)", metadata_only=True,
                      approval_date=today - timedelta(days=200 + i * 20), review_due=today + timedelta(days=165 - i * 20), system_ids=[str(ltp.id)],
                      analysis_status="metadata_only"))
    db.flush()


_ = uuid
