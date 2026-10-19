"""Idempotent ingestion pipeline: receive → validate → store original → hash → parse → match assets → dedup →
map (STIG CCI refs → pinned DISA CCI list; ACAS → versioned org mapping rules) → link evidence → re-evaluate → snapshot → audit."""
import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import (Asset, EvidenceSource, Implementation, Cci, CciControlMap, ContentVersion, ControlAssignment, DedupRule, Evidence,
                        EvidenceControl, Finding, FindingControlMap, FindingObservation, IngestRun, OrgMappingRule,
                        StigRuleCci, System)
from app.services import audit
from app.services.ingest.parsers import MAX_BYTES, PARSERS, SOURCE_TYPE, ParseError, detect_format
from app.services.evaluation import apply_freshness
from app.services.kev import is_kev
from app.services.workflow import on_remediation_observed
from app.services.storage import get_storage

EVIDENCE_TYPE = {"ckl": "stig_checklist", "cklb": "stig_checklist", "xccdf": "stig_checklist", "nessus_xml": "vulnerability_scan",
                 "nessus_csv": "vulnerability_scan", "sarif": "pipeline"}
SRC_NAMES = {"stig_checklist": "DISA STIG Checklists (uploads)", "acas": "ACAS / Nessus (uploads)", "sarif": "Pipeline SAST / container scans (SARIF uploads)"}
DEFAULT_DEDUP = {"sarif": ["source_type", "rule_id", "asset", "component"]}


def now() -> datetime:
    return datetime.now(timezone.utc)


def receive_upload(db: Session, *, system_id: uuid.UUID, source_id: uuid.UUID | None, file_name: str, data: bytes,
                   actor_id: uuid.UUID | None = None, actor_email: str | None = None) -> IngestRun:
    if not data:
        raise ParseError("Empty file")
    if len(data) > MAX_BYTES:
        raise ParseError(f"File exceeds {MAX_BYTES // (1024 * 1024)} MB limit")
    fmt = detect_format(file_name, data)
    sha = hashlib.sha256(data).hexdigest()
    if source_id is None:
        source_id = attribute_source(db, system_id, fmt).id
    prior = db.scalar(select(IngestRun).where(IngestRun.system_id == system_id, IngestRun.sha256 == sha,
                                              IngestRun.status.in_(("completed", "queued", "processing"))))
    run = IngestRun(id=uuid.uuid4(), system_id=system_id, source_id=source_id, file_name=file_name[:500], file_format=fmt,
                    sha256=sha, requested_by=actor_id, received_at=now())
    if prior:
        run.status, run.duplicate_of_run_id, run.evidence_id, run.finished_at = "duplicate", prior.id, prior.evidence_id, now()
        run.stats = {"note": "Identical file (same SHA-256) already ingested; not re-processed or double-counted."}
        db.add(run)
        audit.record(db, action="ingest.duplicate_detected", actor_user_id=actor_id, actor_email=actor_email,
                     entity_type="ingest_run", entity_id=str(run.id), details={"sha256": sha, "duplicate_of": str(prior.id)})
        db.flush()
        return run
    key = f"evidence/{system_id}/{sha}/{file_name}"
    store = get_storage()
    if not store.exists(key):
        store.put(key, data, "application/octet-stream")
    ev = Evidence(id=uuid.uuid4(), system_id=system_id, source_id=source_id, name=file_name, evidence_type=EVIDENCE_TYPE[fmt],
                  file_name=file_name, storage_key=key, sha256=sha, size_bytes=len(data), content_type=fmt,
                  collected_at=now(), signature_status="unsigned", integrity_status="hash_recorded", last_verified_at=None,
                  source="upload", provenance={"received_by": actor_email, "format": fmt, "sha256_at_receipt": sha})
    db.add(ev)
    db.flush()
    apply_freshness(db, ev)
    run.evidence_id, run.status = ev.id, "queued"
    db.add(run)
    audit.record(db, action="ingest.received", actor_user_id=actor_id, actor_email=actor_email, entity_type="evidence",
                 entity_id=str(ev.id), details={"file": file_name, "sha256": sha, "format": fmt, "signature": "unsigned"})
    db.flush()
    return run


def active_cat_rules(db: Session, system_id) -> dict[str, dict]:
    from app.models import CatRule, System

    org_id = db.get(System, system_id).org_id
    out = {}
    for r in db.scalars(select(CatRule).where(CatRule.org_id == org_id, CatRule.is_active.is_(True)).order_by(CatRule.version)):
        out[r.source_type] = r.mapping
    return out


def derive_cat(rules: dict, src_type: str, rec: dict) -> str | None:
    """STIG: checklist severity high/medium/low → CAT I/II/III (DISA). ACAS: org rule table (cat_rules). Persisted on the finding."""
    m = rules.get(src_type)
    if m is None:
        return rec.get("cat")
    return m.get((rec.get("severity") or "").lower())


def attribute_source(db: Session, system_id, fmt: str) -> EvidenceSource:
    """Uploads without a source are attributed to the system's file-import source for that artifact type (created if missing)."""
    st = SOURCE_TYPE.get(fmt, "acas")
    src = db.scalar(select(EvidenceSource).where(EvidenceSource.system_id == system_id, EvidenceSource.source_type == st)
                    .order_by(EvidenceSource.created_at).limit(1))
    if src is None:
        src = EvidenceSource(id=uuid.uuid4(), system_id=system_id, source_type=st, adapter="file_import", health="ok", config={},
                             name=SRC_NAMES[st], source="auto:upload-attribution")
        db.add(src)
        db.flush()
    return src


def backfill_attribution(db: Session, system_id) -> None:
    for ev in db.scalars(select(Evidence).where(Evidence.system_id == system_id, Evidence.source_id.is_(None),
                                                Evidence.evidence_type.in_(("stig_checklist", "vulnerability_scan")))):
        src = attribute_source(db, system_id, "ckl" if ev.evidence_type == "stig_checklist" else "nessus_xml")
        ev.source_id = src.id
        for run in db.scalars(select(IngestRun).where(IngestRun.evidence_id == ev.id, IngestRun.source_id.is_(None))):
            run.source_id = src.id


def _match_asset(db: Session, system_id, host: str | None, ip: str | None, fmt: str) -> Asset:
    short = (host or "").split(".")[0].lower()
    conds = []
    if short:
        conds.append(func.lower(Asset.hostname) == short)
    if ip:
        conds.append(Asset.ip_address == ip)
    asset = db.scalar(select(Asset).where(Asset.system_id == system_id, or_(*conds)).limit(1)) if conds else None
    if asset is None:
        asset = Asset(system_id=system_id, name=short or ip or "unknown", hostname=short or None, ip_address=ip,
                      asset_type="unknown", inventory_source=f"ingest:{fmt}", is_unmatched=True, review_status="needs_review",
                      source="ingest", provenance={"reason": "host in scan not found in inventory"})
        db.add(asset)
        db.flush()
    asset.last_observed_at = now()
    return asset


def _dedup(rule: DedupRule, rec: dict, asset: Asset) -> tuple[str, dict]:
    values = {f: (str(asset.id) if f == "asset" else rec.get(f)) for f in rule.fields}
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest(), values


def _map_stig(db: Session, finding: Finding, rec: dict, ev: Evidence, cci_cv: ContentVersion | None) -> int:
    n = 0
    for cci in rec["ccis"]:
        if not db.scalar(select(StigRuleCci.id).where(StigRuleCci.benchmark == (rec["benchmark"] or ""), StigRuleCci.rule_id == rec["rule_id"],
                                                     StigRuleCci.cci_id == cci, StigRuleCci.evidence_id == ev.id)):
            db.add(StigRuleCci(benchmark=rec["benchmark"] or "", benchmark_version=rec["benchmark_version"], rule_id=rec["rule_id"],
                               vuln_id=rec["vuln_id"], cci_id=cci, evidence_id=ev.id, review_status="auto_from_authoritative_source",
                               source="STIG checklist CCI_REF", provenance={"evidence_sha256": ev.sha256}))
        if cci_cv is None:
            continue
        rows = db.execute(select(CciControlMap.control_id, CciControlMap.reference_index).join(Cci, Cci.id == CciControlMap.cci_uuid)
                          .where(Cci.content_version_id == cci_cv.id, CciControlMap.cci_id == cci,
                                 CciControlMap.control_uuid.is_not(None))).all()
        for control_id, ref in rows:
            n += 1
            if db.scalar(select(FindingControlMap.id).where(FindingControlMap.finding_id == finding.id,
                                                            FindingControlMap.control_id == control_id, FindingControlMap.cci_id == cci,
                                                            FindingControlMap.valid_to.is_(None))):
                continue
            db.add(FindingControlMap(finding_id=finding.id, control_id=control_id, cci_id=cci, mapping_source="stig_cci",
                                     content_version_id=cci_cv.id, effective_date=cci_cv.effective_date,
                                     review_status="auto_from_authoritative_source", confidence="authoritative",
                                     source=f"STIG CCI_REF → DISA CCI List {cci_cv.version}",
                                     provenance={"cci_reference_index": ref, "cci_list_sha256": cci_cv.sha256,
                                                 "checklist_sha256": ev.sha256}))
    return n


def _map_acas(db: Session, finding: Finding, rules: list[OrgMappingRule], cwes: list | None = None) -> int:
    n = 0
    for rule in rules:
        if rule.match.get("requires_cve") and not finding.cves:
            continue
        if rule.match.get("cwes") and not set(rule.match["cwes"]) & set(cwes or []):
            continue
        for control_id in rule.control_ids:
            n += 1
            if db.scalar(select(FindingControlMap.id).where(FindingControlMap.finding_id == finding.id,
                                                            FindingControlMap.control_id == control_id, FindingControlMap.valid_to.is_(None))):
                continue
            db.add(FindingControlMap(finding_id=finding.id, control_id=control_id, mapping_source="org_rule", org_rule_id=rule.id,
                                     effective_date=rule.effective_date, review_status=rule.review_status,
                                     confidence="organizational_rule", source=f"{rule.title} v{rule.version}",
                                     provenance={"rule_key": rule.rule_key, "version": rule.version, "synthetic": rule.is_synthetic}))
    return n


def process_run(db: Session, run_id: uuid.UUID) -> dict:
    from app.services.evaluation import evaluate_system, take_snapshots

    run = db.get(IngestRun, run_id)
    if run.status not in ("queued", "failed"):
        return {"skipped": True, "status": run.status}
    run.status = "processing"
    ev = db.get(Evidence, run.evidence_id)
    data = get_storage().get(ev.storage_key)
    if hashlib.sha256(data).hexdigest() != ev.sha256:
        run.status, run.errors = "failed", ["Stored original does not match SHA-256 recorded at receipt"]
        return {"failed": True}
    try:
        records = PARSERS[run.file_format](data)
    except ParseError as exc:
        run.status, run.errors, run.finished_at = "failed", [str(exc)], now()
        return {"failed": True, "error": str(exc)}
    src_type = SOURCE_TYPE.get(run.file_format, "acas")
    rule = db.scalar(select(DedupRule).where(DedupRule.source_type == src_type, DedupRule.is_active.is_(True))
                     .order_by(DedupRule.version.desc()))
    if rule is None and src_type in DEFAULT_DEDUP:
        rule = DedupRule(source_type=src_type, version=1, fields=DEFAULT_DEDUP[src_type], description="SARIF: rule + asset/image + file location")
        db.add(rule)
        db.flush()
    cci_cv = db.scalar(select(ContentVersion).where(ContentVersion.content_type == "cci_list", ContentVersion.is_active.is_(True)))
    org_rules = list(db.scalars(select(OrgMappingRule).where(OrgMappingRule.source_type == src_type, OrgMappingRule.is_active.is_(True),
                                                             OrgMappingRule.review_status == "human_approved")))
    cat_rules = active_cat_rules(db, run.system_id)
    stig_versions = {cv.meta.get("benchmark"): cv.id for cv in db.scalars(select(ContentVersion).where(
        ContentVersion.content_type == "stig_benchmark", ContentVersion.is_active.is_(True)))}
    observed = run.received_at or now()
    mapped = unmapped = created = updated = 0
    finding_ids, finding_ids_fixed = set(), set()
    for rec in records:
        asset = _match_asset(db, run.system_id, rec["host"], rec["ip"], run.file_format)
        key, fields = _dedup(rule, rec, asset)
        f = db.scalar(select(Finding).where(Finding.system_id == run.system_id, Finding.dedup_key == key))
        if f is None:
            f = Finding(id=uuid.uuid4(), system_id=run.system_id, asset_id=asset.id, dedup_key=key, dedup_rule_id=rule.id,
                        dedup_fields=fields, source_type=src_type, rule_id=rec["rule_id"], vuln_id=rec["vuln_id"],
                        plugin_id=rec["plugin_id"], benchmark=rec["benchmark"], component=rec["component"], port=rec["port"],
                        protocol=rec["protocol"], title=rec["title"] or "", severity=rec["severity"], cat=derive_cat(cat_rules, src_type, rec),
                        cves=rec["cves"], ccis=rec["ccis"], first_seen_at=observed, last_seen_at=observed,
                        current_state=rec["status"], observation_count=0)
            db.add(f)
            db.flush()
            created += 1
        else:
            updated += 1
            f.last_seen_at = max(f.last_seen_at, observed)
            if f.current_state in ("open", "closed_by_review") and rec["status"] == "pass":
                finding_ids_fixed.add(f.id)
            if rec["status"] == "open" and f.remediation_status:
                f.remediation_status = None
            f.current_state = rec["status"]
            f.severity, f.cat = rec["severity"] or f.severity, derive_cat(cat_rules, src_type, rec) or f.cat
        f.observation_count += 1
        f.latest_evidence_id = ev.id
        f.is_kev = is_kev(f.cves, db)
        stig_cv = stig_versions.get(rec["benchmark"]) if src_type == "stig_checklist" else None
        f.content_version_id = stig_cv or f.content_version_id
        db.add(FindingObservation(finding_id=f.id, ingest_run_id=run.id, evidence_id=ev.id, observed_status=rec["status"],
                                  observed_at=observed, raw=rec["raw"], content_version_id=stig_cv))
        n = _map_stig(db, f, rec, ev, cci_cv) if src_type == "stig_checklist" else _map_acas(db, f, org_rules, rec["raw"].get("cwes"))
        db.flush()
        has_map = db.scalar(select(func.count()).select_from(FindingControlMap).where(FindingControlMap.finding_id == f.id)) > 0
        if f.mapping_status != "dispositioned":
            f.mapping_status = "mapped" if (n or has_map) else "unmapped"
        mapped += f.mapping_status == "mapped"
        unmapped += f.mapping_status == "unmapped"
        finding_ids.add(f.id)
    # Remediation detection: fixed in this run, or absent for an asset this run fully covered (same source type / benchmark).
    assets_in_run = {db.get(Finding, fid).asset_id for fid in finding_ids}
    benchmarks = {r["benchmark"] for r in records}
    absent_q = select(Finding).where(Finding.system_id == run.system_id, Finding.source_type == src_type, Finding.current_state == "open",
                                     Finding.asset_id.in_(assets_in_run), Finding.id.not_in(finding_ids))
    if src_type == "stig_checklist":
        absent_q = absent_q.where(Finding.benchmark.in_(benchmarks))
    for f in db.scalars(absent_q):
        f.current_state = "not_detected"
        db.add(FindingObservation(finding_id=f.id, ingest_run_id=run.id, evidence_id=ev.id, observed_status="not_detected",
                                  observed_at=observed, raw={"note": "absent from rescan covering this asset"}))
        f.observation_count += 1
        finding_ids_fixed.add(f.id)
    fixed = [f for f in (db.get(Finding, i) for i in finding_ids_fixed) if f.current_state in ("pass", "not_detected")]
    db.flush()
    eligible = on_remediation_observed(db, fixed, run.id)
    control_ids = {c for (c,) in db.execute(select(FindingControlMap.control_id).where(FindingControlMap.finding_id.in_(finding_ids)))} if finding_ids else set()
    assignments = list(db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == run.system_id,
                                                                  ControlAssignment.control_id.in_(control_ids)))) if control_ids else []
    for a in assignments:
        if not db.scalar(select(EvidenceControl.id).where(EvidenceControl.evidence_id == ev.id, EvidenceControl.assignment_id == a.id)):
            db.add(EvidenceControl(evidence_id=ev.id, assignment_id=a.id))
            for impl in db.scalars(select(Implementation).where(Implementation.assignment_id == a.id,
                                                                Implementation.review_status.in_(("approved", "draft", "in_review")))):
                impl.needs_reconsideration = True
    run.total, run.mapped, run.unmapped, run.controls_touched = len(records), mapped, unmapped, len(assignments)
    run.stats = {"findings_created": created, "findings_updated": updated, "assets_seen": len({r["host"] for r in records}),
                 "mapped_controls_not_assigned": sorted(control_ids - {a.control_id for a in assignments}),
                 "remediation_observed": len(fixed), "poams_closure_eligible": eligible}
    run.status, run.finished_at = "completed", now()
    db.flush()
    evaluate_system(db, run.system_id)
    take_snapshots(db, trigger="ingest", org_id=db.scalar(select(System.org_id).where(System.id == run.system_id)))
    audit.record(db, action="ingest.completed", entity_type="ingest_run", entity_id=str(run.id), actor_user_id=run.requested_by,
                 details={"total": run.total, "mapped": mapped, "unmapped": unmapped, "controls_touched": len(assignments)})
    return {"run_id": str(run.id), "total": run.total, "mapped": mapped, "unmapped": unmapped, "controls_touched": len(assignments)}
