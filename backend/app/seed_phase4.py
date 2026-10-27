"""Phase 4 synthetic seed: content versions (Demo OS STIG V1R1 installed, V1R2 available; pinned KEV), observation content
version backfill, risk weights, job schedules, and the MOCK eMASS remote store for LTP. Idempotent."""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models import (ContentVersion, EmassChange, EmassRemoteRecord, EmassSyncRun, Finding, FindingControlMap, FindingObservation, Organization, Poam, PriorityWeight,
                        System)
from app.services import content_updates as cu
from app.services import scheduler
from app.services.risk import DEFAULT_WEIGHTS

BENCH = "Demo Linux Server STIG (SYNTHETIC)"


def seed_phase4(db: Session, org: Organization) -> None:
    cu.register_all(db)
    for code, (w, d) in DEFAULT_WEIGHTS.items():
        if not db.scalar(select(PriorityWeight.id).where(PriorityWeight.reason_code == code)):
            db.add(PriorityWeight(reason_code=code, weight=w, description=d))
    scheduler.ensure_defaults(db)
    v1 = db.scalar(select(ContentVersion).where(ContentVersion.content_type == cu.STIG, ContentVersion.version == "V1R1"))
    sys_ids = [s for (s,) in db.execute(select(System.id).where(System.org_id == org.id))]
    fids = select(Finding.id).where(Finding.benchmark == BENCH, Finding.system_id.in_(sys_ids))
    db.execute(update(Finding).where(Finding.id.in_(fids), Finding.content_version_id.is_(None)).values(content_version_id=v1.id))
    db.execute(update(FindingObservation).where(FindingObservation.finding_id.in_(fids), FindingObservation.content_version_id.is_(None))
               .values(content_version_id=v1.id))
    db.execute(update(FindingControlMap).where(FindingControlMap.finding_id.in_(fids), FindingControlMap.stig_version_id.is_(None))
               .values(stig_version_id=v1.id))
    ltp = db.scalar(select(System).where(System.org_id == org.id, System.acronym == "LTP"))
    if ltp and not db.scalar(select(EmassRemoteRecord.id).where(EmassRemoteRecord.system_id == ltp.id).limit(1)):
        db.add(EmassRemoteRecord(system_id=ltp.id, entity_type="system", remote_id=ltp.emass_id or "DEMO-1000",
                                 data={"emass_id": ltp.emass_id, "name": ltp.name, "acronym": ltp.acronym, "authorization_status": "In assessment",
                                       "SYNTHETIC_MOCK": True}))
        for cid in ("ac-2", "ac-2.3", "at-2", "cm-6", "cp-4", "ia-2", "ra-5", "sc-13", "sc-28", "si-2", "au-9", "ac-17"):
            db.add(EmassRemoteRecord(system_id=ltp.id, entity_type="control", remote_id=f"EM-CTL-{cid}",
                                     data={"control_id": cid, "implementation_status": "Planned", "SYNTHETIC_MOCK": True}))
        for i, p in enumerate(db.scalars(select(Poam).where(Poam.system_id == ltp.id, Poam.seq.in_((15, 19, 22, 26, 27))).order_by(Poam.seq))):
            rid = f"EM-POAM-{7000 + p.seq}"
            data = {"weakness": p.weakness, "status": p.status, "due_date": str(p.due_date) if p.due_date else None, "severity": p.severity,
                    "human_id": p.human_id, "SYNTHETIC_MOCK": True}
            if p.seq == 22:
                data.update(status="Ongoing", due_date=str(p.due_date + timedelta(days=30)) if p.due_date else None)
            db.add(EmassRemoteRecord(system_id=ltp.id, entity_type="poam", remote_id=rid, data=data, remote_version=2 if p.seq == 22 else 1))
            p.emass_remote_id, p.emass_status = rid, "out_of_sync" if p.seq == 22 else "synced"
            ts = datetime.now(timezone.utc)
            db.add(EmassChange(org_id=org.id, system_id=ltp.id, entity_type="poam", entity_id=str(p.id), entity_label=p.human_id, remote_id=rid,
                               operation="create", after=data, trigger="seed: initial synthetic eMASS load", status="succeeded", final_status="succeeded",
                               approval_status="approved", submitted_at=ts, attempts=1, response={"status": 200, "remote_id": rid, "remote_version": 1, "mock": True},
                               history=[{"at": ts.isoformat(), "event": "submitted", "note": "SYNTHETIC seed sync history"}]))
            db.add(EmassSyncRun(org_id=org.id, system_id=ltp.id, kind="submit", mode="mock", status="succeeded", actor_email="seed",
                                summary={"remote_id": rid, "seed": True}))
        db.add(EmassRemoteRecord(system_id=ltp.id, entity_type="poam", remote_id="EM-POAM-6999",
                                 data={"weakness": "Legacy remote-only POA&M (exists only in mock eMASS)", "status": "Ongoing", "SYNTHETIC_MOCK": True}))
    db.flush()
    if ltp:
        seed_emass_fields(db, ltp)
        seed_iscm(db, ltp)


def seed_iscm(db: Session, s: System) -> None:
    """SYNTHETIC approved Continuous Monitoring Strategy (Task S-5) for LTP. Tracking/Comments are left to the controls so the
    "missing required eMASS fields" demo (cp-4, au-2) still shows. Idempotent."""
    from app.models import IscmProfile, IscmStrategy
    from app.services import iscm

    if db.scalar(select(IscmStrategy.id).where(IscmStrategy.system_id == s.id)):
        return
    st = IscmStrategy(system_id=s.id, status="approved", version=1, is_synthetic=True,
                      narrative="SYNTHETIC ISCM strategy: automated scanner evidence (ACAS/STIG) is reviewed monthly, policy and procedure controls annually; "
                                "the ISSO reviews SLCM results and reports to the ISSM monthly and to the AO annually.",
                      scope="All selected controls of LTP that are not Inherited or Not Applicable.",
                      defaults={"slcm_criticality": "Moderate", "slcm_frequency": "Annually", "slcm_method": "Manual",
                                "slcm_reporting": "Annual security review report to the ISSM"},
                      reporting=[{"report": "ConMon summary", "audience": "ISSM", "frequency": "Monthly"},
                                 {"report": "Security status / ATO health", "audience": "AO", "frequency": "Annually"}],
                      review_activities=[{"activity": "Vulnerability scan review (ACAS/STIG)", "frequency": "Monthly", "role": "isso"},
                                         {"activity": "Annual control assessment subset", "frequency": "Annually", "role": "sca"}],
                      evidence_requirements=[{"evidence": "Scanner results (ACAS, STIG checklists)", "freshness_days": 30},
                                             {"evidence": "Policies and procedures", "freshness_days": 365}],
                      submitted_by={"persona_email": "seed", "real_email": "seed"}, approved_by={"persona_email": "seed (SYNTHETIC)", "real_email": "seed"},
                      approved_at=datetime.now(timezone.utc))
    db.add(st)
    db.flush()
    p = IscmProfile(strategy_id=st.id, name="AU/SI – scanner-monitored", match_type="family", match_value="au,si,ra", sort_order=0,
                    values={"slcm_frequency": "Monthly", "slcm_method": "Automated", "slcm_reporting": "Monthly ConMon report to the ISSM"})
    db.add(p)
    db.flush()
    st.approved_snapshot = iscm.snapshot(st, [p])


EMASS_DEMO = ("ac-2", "ac-2.3", "ac-17", "at-2", "au-9", "cm-6", "ia-2", "ra-5", "sc-13", "sc-28", "si-2")
EMASS_PARTIAL = ("cp-4", "au-2")  # intentionally incomplete: shows the "missing required eMASS fields" filter


def seed_emass_fields(db: Session, s: System) -> None:
    """SYNTHETIC eMASS Implementation Plan / Risk Assessment values for a subset of LTP controls, derived with the same deterministic
    rules as "Suggest values" (no AI). Idempotent; statuses are not changed."""
    from app.models import ControlAssignment, EmassControlFields
    from app.services import emass_fields as ef

    if db.scalar(select(EmassControlFields.id).where(EmassControlFields.system_id == s.id).limit(1)):
        return
    for a in db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == s.id, ControlAssignment.control_id.in_(EMASS_DEMO + EMASS_PARTIAL))):
        st = ef.emass_status(a, None)
        if st == "Inherited":
            continue
        f = EmassControlFields(system_id=s.id, assignment_id=a.id, control_id=a.control_id, is_synthetic=True,
                               assisted={"_seed": {"source": "rules", "note": "SYNTHETIC demo values"}})
        for it in ef.rule_suggestions(ef.grounding(db, s, a), st):
            if a.control_id in EMASS_PARTIAL and it["field"] in ("slcm_reporting", "slcm_tracking", "slcm_comments"):
                continue
            v = it["value"]
            setattr(f, it["field"], date.fromisoformat(v) if it["field"] == "estimated_completion_date" else v)
        db.add(f)
    db.flush()


def reset_phase4(db: Session, org: Organization) -> None:
    """Restore content to the seeded state: STIG V1R1 installed / V1R2 available, manifest KEV active, settings cleared."""
    from app.models import AppSetting
    for cv in db.scalars(select(ContentVersion).where(ContentVersion.content_type == cu.STIG)):
        cv.is_active, cv.status = cv.version == "V1R1", "installed" if cv.version == "V1R1" else "available"
    import json
    kev_sha = json.loads((cu.content_dir() / "manifest.json").read_text())["kev"]["sha256"]
    for cv in db.scalars(select(ContentVersion).where(ContentVersion.content_type == "kev_catalog")):
        cv.is_active = cv.sha256 == kev_sha
        cv.status = "installed" if cv.is_active else "available"
    db.execute(delete(AppSetting).where(AppSetting.org_id == org.id, AppSetting.key.in_(("emass", "emass_mock_failures"))))
    db.flush()
