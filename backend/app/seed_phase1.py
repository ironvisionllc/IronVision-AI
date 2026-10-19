"""Phase 1 SYNTHETIC demo data. Ingest data is produced by running sample files THROUGH the real pipeline."""
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (Asset, CommonControlProvider, DedupRule, EvidenceSource, FreshnessPolicy, Organization,
                        OrgMappingRule, Overlay, PriorityWeight, ProviderControl, RiskSnapshot, RoleAssignment, System, User)
from app.services.connectors import SOURCE_TYPES, adapter_for
from app.services.evaluation import evaluate_freshness, evaluate_system, take_snapshots
from app.services.ingest.pipeline import process_run, receive_upload
from app.services.systems import register_system

log = logging.getLogger("aegis.seed")
SEED = "seed:phase1-demo"
LTP_HOSTS = [("db-server-01", "192.0.2.11"), ("app-server-02", "192.0.2.12"), ("web-server-03", "192.0.2.13"),
             ("api-gateway-04", "192.0.2.14"), ("mq-broker-05", "192.0.2.15"), ("cache-node-06", "192.0.2.16"),
             ("batch-worker-07", "192.0.2.17"), ("report-server-08", "192.0.2.18"), ("dc-ldap-09", "192.0.2.21"),
             ("file-server-10", "192.0.2.22"), ("print-server-11", "192.0.2.23"), ("backup-server-12", "192.0.2.24"),
             ("jump-host-13", "192.0.2.25"), ("ntp-server-14", "192.0.2.26")]
WEIGHTS = {"kev": (40, "Open finding on a CISA Known Exploited Vulnerability"), "cat1_open": (25, "Open CAT I / critical finding"),
           "expired_evidence": (15, "All supporting evidence expired or failed integrity"), "failed_technical_checks": (10, "Per open failed check (max 5)"),
           "unmapped_findings": (5, "Findings without an approved mapping"), "pending_attestation": (5, "Attestation awaiting response"),
           "overdue_review": (5, "Review overdue"), "catalog_change": (3, "Catalog/STIG content changed"),
           "missing_implementation_statement": (2, "No implementation narrative"), "missing_assessment_evidence": (1, "Not assessed and no evidence")}
_CLOUD_INH = ([f"pe-{i}" for i in (1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17)] + ["pe-6.1", "pe-13.1"]
              + ["ma-1", "ma-2", "ma-3", "ma-3.1", "ma-3.2", "ma-3.3", "ma-4", "ma-5", "ma-6"]
              + ["mp-1", "mp-2", "mp-3", "mp-4", "mp-5", "mp-7"] + ["sc-20", "sc-21", "sc-22", "sc-39", "sc-5", "cp-6.1", "cp-6.3", "sc-15"])
_CLOUD_SH = ["cm-6", "sc-28", "sc-28.1", "sc-7", "sc-7.18", "sc-7.3", "sc-7.4", "sc-7.5", "sc-7.7", "sc-7.8", "sc-8", "sc-8.1", "sc-12", "sc-10",
             "sc-23", "sc-2", "sc-4", "sc-17", "sc-18", "cp-6", "cp-7", "cp-7.1", "cp-7.2", "cp-7.3", "cp-8", "cp-8.1", "cp-8.2", "cp-9", "cp-9.1",
             "cp-9.8", "cp-10", "cp-10.2", "au-4", "au-8", "au-11", "si-12", "cm-8", "cm-8.1"]
_IDP_INH = ["ia-2.1", "ia-2.2", "ia-2.8", "ia-2.12", "ia-5.1", "ia-5.2", "ia-5.6", "ia-8.1", "ia-8.2", "ia-8.4", "ia-12.2", "ia-12.3"]
_IDP_SH = ["ia-2", "ia-5", "ac-2", "ia-8", "ia-12", "ia-12.5"]
_SOC_INH = ["ir-6", "ir-6.1", "ir-6.3", "ir-5", "ir-7", "ir-7.1", "si-5", "si-4.12"]
# SYNTHETIC provider packages sized so LTP (moderate + overlay, 291 controls) shows 61 inherited / 44 shared / 186 system-owned.
PROVIDERS = [
    ("Cloud infrastructure provider – FedRAMP High package (SYNTHETIC)", "FedRAMP High P-ATO (synthetic ref)",
     {**{c: "inherited" for c in _CLOUD_INH}, **{c: "shared" for c in _CLOUD_SH}}),
    ("Enterprise identity service (SYNTHETIC)", "Enterprise ICAM (synthetic)", {**{c: "inherited" for c in _IDP_INH}, **{c: "shared" for c in _IDP_SH}}),
    ("Enterprise security operations (SYNTHETIC)", "Enterprise CSSP (synthetic)", {c: "inherited" for c in _SOC_INH}),
]


def _seed_config(db: Session, org: Organization, providers: bool = True) -> None:
    if not db.scalar(select(DedupRule.id).limit(1)):
        db.add(DedupRule(source_type="stig_checklist", version=1, fields=["source_type", "benchmark", "vuln_id", "rule_id", "asset"],
                         description="STIG: benchmark + Vuln ID (group) + Rule ID + asset"))
        db.add(DedupRule(source_type="acas", version=1, fields=["source_type", "plugin_id", "asset", "component", "port", "protocol"],
                         description="ACAS: plugin + asset + component + port/protocol"))
    if not db.scalar(select(FreshnessPolicy.id).limit(1)):
        for et, days in (("pipeline", 7), ("cloud_config", 2), ("stig_checklist", 30), ("training", 365), ("vulnerability_scan", 30), ("attestation", 365)):
            db.add(FreshnessPolicy(evidence_type=et, window_days=days, label=f"{et}: {days}d (demo settings, not NIST requirements)"))
    for code, (w, d) in WEIGHTS.items():
        if not db.scalar(select(PriorityWeight.id).where(PriorityWeight.reason_code == code)):
            db.add(PriorityWeight(reason_code=code, weight=w, description=d))
    if not db.scalar(select(Overlay.id).where(Overlay.overlay_key == "demo-cloud-overlay")):
        db.add(Overlay(overlay_key="demo-cloud-overlay", version="1", title="Demo Cloud Hosting Overlay (SYNTHETIC – not an official DoD overlay)",
                       description="Synthetic overlay for demonstration only.", controls_add=["ac-6.3", "au-9.2", "sc-7.18", "si-4.12"],
                       controls_remove=[], source=SEED))
    if not db.scalar(select(OrgMappingRule.id).limit(1)):
        db.add(OrgMappingRule(rule_key="acas-vuln-to-ra5-si2", version=1, title="Organizational mapping rule v1 (SYNTHETIC)",
                              source_type="acas", match={"requires_cve": True}, control_ids=["ra-5", "si-2"], review_status="human_approved",
                              approved_by="Synthetic ISSM approval (demo seed)", effective_date=date(2026, 1, 1), source=SEED,
                              provenance={"note": "Synthetic organizational rule: CVE-bearing vulnerability findings → RA-5, SI-2"}))
    if not db.scalar(select(OrgMappingRule.id).where(OrgMappingRule.source_type == "sarif").limit(1)):
        db.add(OrgMappingRule(rule_key="sarif-cwe-to-controls", version=1, title="CWE → control org mapping v1 (SYNTHETIC)", source_type="sarif",
                              match={"cwes": ["CWE-79", "CWE-89", "CWE-78", "CWE-22", "CWE-20", "CWE-502", "CWE-798", "CWE-259", "CWE-327"]},
                              control_ids=["si-10", "sa-11", "ra-5"], review_status="human_approved", approved_by="Synthetic ISSM approval (demo seed)",
                              effective_date=date(2026, 1, 1), source=SEED,
                              provenance={"note": "Synthetic organizational rule: listed injection/input/crypto/credential CWEs → SI-10, SA-11, RA-5"}))
    if providers and not db.scalar(select(CommonControlProvider.id).where(CommonControlProvider.org_id == org.id).limit(1)):
        for name, pkg, ctrls in PROVIDERS:
            p = CommonControlProvider(id=uuid.uuid4(), org_id=org.id, name=name, package=pkg, source=SEED)
            db.add(p)
            db.flush()
            for cid, resp in ctrls.items():
                db.add(ProviderControl(provider_id=p.id, control_id=cid, responsibility=resp))
    db.flush()
    from app.services.responsibility import seed_matrix

    seed_matrix(db, org.id)


def _user(db, email):
    return db.scalar(select(User).where(User.email == email))


def role_user(db, org, role: str):
    """Org-scoped holder of a role: sandbox persona, or the role fixture user in tests."""
    return db.scalar(select(User).join(RoleAssignment, RoleAssignment.user_id == User.id).where(
        User.org_id == org.id, User.is_active.is_(True), RoleAssignment.role == role, RoleAssignment.scope_type == "org",
        RoleAssignment.scope_id == org.id).order_by(User.persona_role.is_(None), User.created_at).limit(1))


def seed_tenant_config(db: Session, org: Organization) -> None:
    """Clean tenant: shared rule tables + this tenant's decision/match/CAT rules. No systems, providers or records."""
    from app.seed_phase2 import seed_phase2_config
    from app.seed_phase4 import seed_phase4

    _seed_config(db, org, providers=False)
    seed_phase2_config(db, org)
    seed_phase4(db, org)
    db.flush()


def seed_phase1(db: Session, org: Organization, samples_dir: str) -> None:
    from app.seed_phase2 import seed_phase2, seed_phase2_config

    _seed_config(db, org)
    seed_phase2_config(db, org)
    if db.scalar(select(System.id).where(System.org_id == org.id).limit(1)):
        from app.models import Poam
        if not db.scalar(select(Poam.id).where(Poam.org_id == org.id).limit(1)):
            seed_phase2(db, org)
            take_snapshots(db, trigger="seed_phase2", org_id=org.id)
        from app.models import Policy
        if not db.scalar(select(Policy.id).where(Policy.org_id == org.id).limit(1)):
            from app.seed_phase3 import seed_phase3
            seed_phase3(db, org, samples_dir)
            evaluate_system(db, db.scalar(select(System.id).where(System.org_id == org.id, System.acronym == "LTP")))
            take_snapshots(db, trigger="seed_phase3", org_id=org.id)
        from app.seed_phase4 import seed_phase4
        seed_phase4(db, org)
        return
    sd = Path(samples_dir)
    isso, issm, ao, so = (role_user(db, org, r) for r in ("isso", "issm", "ao", "system_owner"))
    specs = [
        ("Logistics Tracking Platform", "LTP", "moderate", ["demo-cloud-overlay"], "Test", "In assessment", None, None, "AWS GovCloud (synthetic)"),
        ("Mission Planning Portal", "MPP", "high", [], "Operations", "Authorized (ATO)", date(2023, 11, 30), date(2026, 11, 30), "On-prem enclave"),
        ("Fleet Maintenance Data Hub", "FMDH", "moderate", [], "Operations", "Authorized (continuous ATO)", date(2024, 3, 1), None, "Azure Government (synthetic)"),
        ("Training Records Service", "TRS", "low", [], "Operations", "Authorized (continuous ATO)", date(2024, 6, 1), None, "Hybrid"),
    ]
    systems = {}
    for i, (name, acr, bl, ovs, phase, auth, adate, aexp, env) in enumerate(specs):
        lvl = bl.capitalize()
        s = register_system(db, dict(org_id=org.id, name=name, acronym=acr, emass_id=f"DEMO-{1000 + i}", description=f"{name} (SYNTHETIC)",
                                     organization_name="IronVision Demo Command (SYNTHETIC)", mission_owner="Mission Owner (synthetic)",
                                     system_owner_id=so.id, isso_id=isso.id, issm_id=issm.id, ao_id=ao.id, operating_environment=env,
                                     deployment_type="Cloud" if "Gov" in env else "On-premises", boundary_description="Synthetic boundary",
                                     lifecycle_phase=phase, authorization_status=auth, authorization_type="continuous" if "continuous" in auth else "ATO",
                                     authorization_date=adate, authorization_expiration=aexp, confidentiality_impact=lvl, integrity_impact=lvl,
                                     availability_impact="Low" if bl != "high" else "High", baseline_key=bl, overlay_keys=ovs,
                                     information_types=[{"id": "C.3.5.1", "title": "Synthetic info type"}], mission_criticality="Mission essential",
                                     is_synthetic=True, source=SEED), [], None, None, "seed")
        systems[acr] = s
        for u, role in ((isso, "isso"), (issm, "issm"), (ao, "ao"), (so, "system_owner")):
            db.add(RoleAssignment(user_id=u.id, role=role, scope_type="system", scope_id=s.id, source=SEED))
    db.add(RoleAssignment(user_id=role_user(db, org, "devsecops").id, role="isso", scope_type="system", scope_id=systems["TRS"].id, source=SEED))
    for idx, (h, ip) in enumerate(LTP_HOSTS):
        onprem = idx >= 8
        db.add(Asset(system_id=systems["LTP"].id, name=h, hostname=h, ip_address=ip, os="Demo Linux 9", asset_type="server",
                     criticality="high" if h in ("db-server-01", "app-server-02") else "moderate", network_zone="on-prem DMZ" if onprem else "cloud VPC",
                     environment="production", inventory_source="seed", cloud_resource_id=None if onprem else f"i-0demo{idx:04d}",
                     software_components=[{"name": "postgresql", "version": "15.4"}] if h == "db-server-01" else [], source=SEED))
    for acr, h, ip in (("MPP", "mpp-app-01", "203.0.113.10"), ("FMDH", "fmdh-db-01", "198.51.100.21"), ("TRS", "trs-web-01", "198.51.100.40")):
        db.add(Asset(system_id=systems[acr].id, name=h, hostname=h, ip_address=ip, asset_type="server", criticality="moderate",
                     environment="production", inventory_source="seed", source=SEED))
    db.flush()
    src_specs = {"LTP": [("DISA STIG Checklists", "stig_checklist", {}), ("ACAS / Nessus", "acas", {}),
                         ("AWS GovCloud Config", "aws_govcloud", {"control_ids": ["cm-2", "cm-6", "ac-2", "cm-8"]}),
                         ("GitLab DevSecOps Pipeline", "devsecops_pipeline", {"control_ids": ["sa-11", "cm-3", "ra-5"]}),
                         ("Annual Security Awareness Attestation", "manual_attestation", {"control_ids": ["at-2", "at-3"]}),
                         ("eMASS", "emass", {"not_configured": True})],
                 "MPP": [("DISA STIG Checklists", "stig_checklist", {})], "FMDH": [("ACAS / Nessus", "acas", {})],
                 "TRS": [("Azure Gov Config", "azure_gov", {"control_ids": ["cm-2", "cm-6"]})]}
    srcs = {}
    for acr, lst in src_specs.items():
        for name, st, cfg in lst:
            src = EvidenceSource(id=uuid.uuid4(), system_id=systems[acr].id, name=name, source_type=st, adapter=SOURCE_TYPES[st][1],
                                 config=cfg, enabled=st != "emass", health="not_configured" if st == "emass" else "ok",
                                 schedule_hours=24 if SOURCE_TYPES[st][1] == "mock" and st != "emass" else None, source=SEED)
            db.add(src)
            srcs[(acr, st)] = src
    db.flush()
    files = [("LTP", "stig_checklist", p) for p in sorted((sd / "stig").glob("ltp_*"))]
    files += [("MPP", "stig_checklist", sd / "stig" / "mpp_mpp-app-01.ckl"), ("LTP", "acas", sd / "acas" / "ltp_weekly_scan.nessus"),
              ("FMDH", "acas", sd / "acas" / "fmdh_scan_export.csv")]
    for acr, st, path in files:
        run = receive_upload(db, system_id=systems[acr].id, source_id=srcs[(acr, st)].id, file_name=path.name, data=path.read_bytes(),
                             actor_email="seed")
        process_run(db, run.id)
        srcs[(acr, st)].last_run_at = run.finished_at
    for (acr, st), src in srcs.items():
        if src.adapter == "mock" and src.enabled:
            adapter_for(st).collect(db, src)
            src.last_run_at = datetime.now(timezone.utc)
            src.next_run_at = src.last_run_at + timedelta(hours=src.schedule_hours or 24)
    for sid in list(db.scalars(select(System.id).where(System.org_id == org.id))):  # this org only: never re-evaluate restored evidence
        evaluate_freshness(db, sid)
    seed_phase2(db, org)
    from app.seed_phase3 import seed_phase3
    seed_phase3(db, org, samples_dir)
    from app.seed_phase4 import seed_phase4
    seed_phase4(db, org)
    for s_ in db.scalars(select(System).where(System.org_id == org.id)):
        evaluate_system(db, s_.id)
    take_snapshots(db, trigger="seed", org_id=org.id)
    base = datetime.now(timezone.utc)
    for w in range(8, 0, -1):
        ts = base - timedelta(weeks=w)
        for acr, s in systems.items():
            db.add(RiskSnapshot(org_id=org.id, system_id=s.id, taken_at=ts, trigger="synthetic_history", is_synthetic=True,
                                metrics={"open_cat1": max(0, 3 + (w % 3) - (8 - w) // 3) if acr in ("LTP", "MPP") else 0,
                                         "kev_open": 1 if acr == "LTP" and w < 5 else 0, "evidence_fresh_pct": 70 + (8 - w) * 3}))
        db.add(RiskSnapshot(org_id=org.id, system_id=None, taken_at=ts, trigger="synthetic_history", is_synthetic=True,
                            metrics={"open_cat1": 4 + w % 3, "kev_open": 1 if w < 5 else 0, "evidence_fresh_pct": 70 + (8 - w) * 3}))
    db.flush()
    log.info("Phase 1 demo data seeded")


def reset_demo(db: Session, org: Organization, samples_dir: str) -> None:
    from app.models import Notification

    from app.models import CommonControlProvider, ContentUpdate, EmassSyncRun, Policy
    from app.seed_phase4 import reset_phase4
    db.execute(delete(Policy).where(Policy.org_id == org.id))
    db.execute(delete(ContentUpdate).where(ContentUpdate.org_id == org.id))
    db.execute(delete(EmassSyncRun).where(EmassSyncRun.org_id == org.id))
    reset_phase4(db, org)
    from app.seed import SEED_SOURCE
    from sqlalchemy import update as _upd
    db.execute(_upd(User).where(User.org_id == org.id, User.source.is_distinct_from(SEED_SOURCE), User.persona_role.is_(None),
                                User.id != (org.owner_user_id or uuid.uuid4())).values(is_active=False))
    db.execute(delete(RiskSnapshot).where(RiskSnapshot.org_id == org.id))
    db.execute(delete(Notification).where(Notification.user_id.in_(select(User.id).where(User.org_id == org.id))))
    sys_ids = list(db.scalars(select(System.id).where(System.org_id == org.id, System.is_synthetic.is_(True))))
    db.execute(delete(RoleAssignment).where(RoleAssignment.scope_type == "system", RoleAssignment.scope_id.in_(sys_ids)))
    db.execute(delete(System).where(System.id.in_(sys_ids)))
    db.execute(delete(CommonControlProvider).where(CommonControlProvider.org_id == org.id))
    db.flush()
    seed_phase1(db, org, samples_dir)
