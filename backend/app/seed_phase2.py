"""Phase 2 synthetic seed: decision rules, POA&M match rule, operational-priority weights, demo LTP POA&Ms."""
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (DecisionRule, Finding, FindingControlMap, Organization, PoamMatchRule, PoamMilestone, PriorityWeight, System,
                        User)
from app.services.evaluation import OP_WEIGHTS
from app.services.workflow import DEFAULT_RULES, create_poam


def seed_phase2_config(db: Session, org: Organization) -> None:
    for t, steps, label in DEFAULT_RULES:
        if not db.scalar(select(DecisionRule.id).where(DecisionRule.org_id == org.id, DecisionRule.request_type == t)):
            db.add(DecisionRule(org_id=org.id, request_type=t, version=1, steps=steps, label=label,
                                description="Demo decision rule (SYNTHETIC tenant configuration)"))
    if not db.scalar(select(PoamMatchRule.id).where(PoamMatchRule.org_id == org.id)):
        db.add(PoamMatchRule(org_id=org.id, version=1, fields=["identifier", "control"], across_assets=True,
                             description="Same STIG rule / ACAS plugin / CVE AND overlapping control → link to existing open POA&M (any asset)"))
    from app.models import CatRule, Poam, PoamFinding

    for st, mapping, label in (
            ("stig_checklist", {"high": "CAT I", "medium": "CAT II", "low": "CAT III"}, "DISA STIG checklist severity → CAT (authoritative, from checklist)"),
            ("acas", {"critical": "CAT I", "high": "CAT I", "medium": "CAT II", "low": "CAT III", "info": None},
             "ORG RULE (synthetic demo): ACAS severity → CAT (critical/high=CAT I, medium=CAT II, low=CAT III, info=none)")):
        if not db.scalar(select(CatRule.id).where(CatRule.org_id == org.id, CatRule.source_type == st)):
            db.add(CatRule(org_id=org.id, source_type=st, version=1, mapping=mapping, label=label))
            db.flush()
            sys_ids = select(System.id).where(System.org_id == org.id)
            for f in db.scalars(select(Finding).where(Finding.source_type == st, Finding.system_id.in_(sys_ids))):
                f.cat = mapping.get((f.severity or "").lower())
            for p in db.scalars(select(Poam).where(Poam.org_id == org.id)):
                cats = [f.cat for f in db.scalars(select(Finding).join(PoamFinding, PoamFinding.finding_id == Finding.id).where(PoamFinding.poam_id == p.id))]
                if cats:
                    p.cat = min(cats, key=lambda c: {"CAT I": 0, "CAT II": 1, "CAT III": 2}.get(c, 9))
    for code, (w, d) in OP_WEIGHTS.items():
        if not db.scalar(select(PriorityWeight.id).where(PriorityWeight.reason_code == code)):
            db.add(PriorityWeight(reason_code=code, weight=w, description=f"Operational prioritization: {d}"))
    db.flush()


def _find(db, sid, **kw) -> list[Finding]:
    q = select(Finding).where(Finding.system_id == sid, Finding.current_state == "open")
    for k, v in kw.items():
        q = q.where(getattr(Finding, k) == v)
    return list(db.scalars(q.order_by(Finding.created_at)))


def _controls(db, fs: list[Finding], fallback: list[str]) -> list[str]:
    ids = sorted({c for f in fs for c in db.scalars(select(FindingControlMap.control_id).where(FindingControlMap.finding_id == f.id))})
    return ids or fallback


def seed_phase2(db: Session, org: Organization) -> None:
    seed_phase2_config(db, org)
    ltp = db.scalar(select(System).where(System.org_id == org.id, System.acronym == "LTP"))
    if ltp is None:
        return
    so = db.scalar(select(User).where(User.email == "system.owner@aegisrmf.demo"))
    devsec = db.scalar(select(User).where(User.email == "devsecops@aegisrmf.demo"))
    today = date.today()
    kev = [f for f in _find(db, ltp.id, is_kev=True)][:1]
    fips = _find(db, ltp.id, vuln_id="V-900140")[:1]
    ssh = _find(db, ltp.id, vuln_id="V-900101")[:1]
    audit_perm = _find(db, ltp.id, vuln_id="V-900118")
    terrapin = _find(db, ltp.id, plugin_id="187315")[:1]
    specs = [
        (15, "Apache Log4j RCE (Log4Shell, CVE-2021-44228 – CISA KEV) on app-server-02", kev, ["ra-5", "si-2"], "critical", None, "ACAS", 10, so,
         "Remote code execution on an internet-reachable application tier.", "Upgrade log4j-core to 2.17.1+ and rescan."),
        (19, "FIPS 140-validated cryptography not enabled on db-server-01", fips, ["sc-13"], "high", "CAT I", "STIG", -12, devsec,
         "Unvalidated cryptographic modules protecting data at rest/in transit.", "Enable FIPS mode, reboot, verify with checklist rescan."),
        (22, "SSH daemon permits direct root login on app-server-02", ssh, ["cm-6"], "medium", "CAT II", "STIG", 25, devsec,
         "Direct privileged remote access without individual accountability.", "Set PermitRootLogin no; rescan."),
        (26, "Audit record review and analysis (AU-6) not performed weekly – manual review finding", [], ["au-6"], "medium", None, "Manual review", 60, so,
         "Malicious activity may go undetected.", "Stand up weekly SIEM review procedure and retain review records."),
        (30, "Contingency plan not tested within the last year (CP-4) – manual review finding", [], ["cp-4"], "medium", None, "Manual review", -5, so,
         "Recovery capability unverified.", "Conduct tabletop exercise and record after-action report."),
        (27, "Audit log files permit group/world read (multiple assets)", audit_perm, ["au-9"], "medium", "CAT II", "STIG", 45, devsec,
         "Audit information could be read or altered by unauthorized users.", "chmod 0600 audit logs via configuration management."),
        (31, "SSH Terrapin prefix truncation weakness on app-server-02", terrapin, ["ra-5", "si-2"], "medium", None, "ACAS", 30, devsec,
         "Downgrade of SSH channel integrity.", "Disable ChaCha20-Poly1305 / CBC-EtM ciphers; rescan."),
    ]
    for seq, weakness, fs, fallback, sev, cat, src, due, owner, impact, plan in specs:
        p = create_poam(db, system=ltp, actor=None, findings=fs,
                        data={"seq": seq, "weakness": weakness, "control_ids": _controls(db, fs, fallback), "severity": sev, "cat": (fs[0].cat if fs else cat),
                              "source_label": src, "due_date": today + timedelta(days=due), "owner_id": owner.id if owner else None,
                              "security_impact": impact, "remediation_plan": plan, "status": "in_progress" if due < 20 else "new",
                              "root_cause": "Synthetic demo root cause: configuration baseline drift."})
        db.add(PoamMilestone(poam_id=p.id, title="Remediation scheduled in change window", due_date=today + timedelta(days=due - 7),
                             status="completed" if due < 0 else "open"))
        db.add(PoamMilestone(poam_id=p.id, title="Verify fix with rescan / review", due_date=today + timedelta(days=due)))
    db.flush()
