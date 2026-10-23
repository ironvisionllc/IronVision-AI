"""Controlled content updates: versioned STIG benchmarks, KEV snapshots and staged NIST catalog / CCI releases.

The flow is register (hash-verified) → diff → impact preview → apply (needs the content.apply permission). Applying never
rewrites historical observations, assessments or mappings: those keep the content version that was in force at the time.
"""
import hashlib
import json
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (Asset, Cci, CciControlMap, ContentUpdate, ContentVersion, ControlAssignment, Finding, FindingControlMap,
                        Poam, PoamFinding, StigRule, System, User)
from app.services import audit

STIG = "stig_benchmark"
TYPE_LABELS = {"stig_benchmark": "DISA STIGs", "oscal_catalog": "NIST SP 800-53 catalog", "oscal_profile": "NIST baselines",
               "cci_list": "DISA CCI list", "overlay": "Overlays", "kev_catalog": "CISA KEV", "threat_intel": "Threat intelligence",
               "scap_content": "SCAP content", "epss": "FIRST EPSS"}
NOT_CONFIGURED = {"threat_intel": "No threat-intel feed configured", "scap_content": "No SCAP datastreams loaded (checklists are imported as CKL/CKLB)",
                  "epss": "EPSS not loaded – scores show 'not loaded'"}


def now() -> datetime:
    return datetime.now(timezone.utc)


def content_dir() -> Path:
    return Path(get_settings().content_dir)


def _read(rel: str, sha: str) -> bytes:
    raw = (content_dir() / rel).read_bytes()
    if hashlib.sha256(raw).hexdigest() != sha:
        raise RuntimeError(f"Content hash mismatch for {rel}")
    return raw


def _cv(db: Session, **kw) -> ContentVersion:
    cv = ContentVersion(id=uuid.uuid4(), loaded_at=now(), source=kw.pop("source", "pinned"), **kw)
    db.add(cv)
    db.flush()
    return cv


# ---------- registration ----------
def content_date(d, synthetic: bool):
    """Content effective/published dates must be ≤ today. Synthetic seed content is dated relative to the current date;
    a real release with a future date is rejected."""
    from datetime import date as _date, timedelta as _td

    if d is None or d <= _date.today():
        return d
    if synthetic:
        return _date.today() - _td(days=1)
    raise ValueError(f"content effective date {d} is in the future")


def register_all(db: Session) -> dict:
    return {"stig": register_stig(db), "kev": register_kev(db), "staged": register_staged(db)}


def register_stig(db: Session) -> int:
    n = 0
    manifest = json.loads((content_dir() / "manifest.json").read_text())
    for e in manifest.get("stig", []):
        if db.scalar(select(ContentVersion.id).where(ContentVersion.content_type == STIG, ContentVersion.sha256 == e["sha256"])):
            continue
        doc = json.loads(_read(e["path"], e["sha256"]))
        installed = e["seed_status"] == "installed" and not db.scalar(
            select(ContentVersion.id).where(ContentVersion.content_type == STIG, ContentVersion.content_key == e["key"], ContentVersion.is_active.is_(True)))
        cv = _cv(db, content_type=STIG, content_key=e["key"], title=doc["title"], version=e["version"], source_url=e["source_url"], sha256=e["sha256"],
                 file_name=Path(e["path"]).name, effective_date=content_date(datetime.fromisoformat(e["effective_date"]).date(), True), item_count=len(doc["rules"]),
                 status="installed" if installed else "available", is_active=installed,
                 meta={"benchmark": doc["benchmark"], "path": e["path"], "synthetic": True, "format": doc["format"]}, source="synthetic")
        for r in doc["rules"]:
            db.add(StigRule(content_version_id=cv.id, vuln_id=r["vuln_id"], rule_id=r["rule_id"], title=r["title"], severity=r["severity"],
                            check_text=r.get("check_text"), fix_text=r.get("fix_text"), ccis=r["ccis"]))
        n += 1
    db.flush()
    return n


def register_kev(db: Session) -> int:
    n = 0
    m = json.loads((content_dir() / "manifest.json").read_text())["kev"]
    entries = [{**m, "installed": True}]
    snap = content_dir() / "kev" / "snapshots"
    for f in sorted(snap.glob("*.json")) if snap.exists() else []:
        raw = f.read_bytes()
        entries.append({"path": str(f.relative_to(content_dir())), "sha256": hashlib.sha256(raw).hexdigest(), "source_url": m["source_url"],
                        "installed": False})
    for e in entries:
        if db.scalar(select(ContentVersion.id).where(ContentVersion.content_type == "kev_catalog", ContentVersion.sha256 == e["sha256"])):
            continue
        doc = json.loads(_read(e["path"], e["sha256"]))
        active = e["installed"] and not db.scalar(select(ContentVersion.id).where(ContentVersion.content_type == "kev_catalog", ContentVersion.is_active.is_(True)))
        _cv(db, content_type="kev_catalog", content_key="cisa-kev", title="CISA Known Exploited Vulnerabilities Catalog", version=doc.get("catalogVersion"),
            source_url=e["source_url"], sha256=e["sha256"], file_name=Path(e["path"]).name, item_count=len(doc.get("vulnerabilities", [])),
            effective_date=content_date(datetime.fromisoformat(doc["dateReleased"][:10]).date(), True) if doc.get("dateReleased") else None,
            status="installed" if active else "available", is_active=active, meta={"path": e["path"]}, source="official")
        n += 1
    return n


def register_staged(db: Session) -> int:
    """Staged NIST catalog / CCI releases written by scripts/stage_content_release.py (content/staged/staged.json)."""
    path = content_dir() / "staged" / "staged.json"
    n = 0
    for e in json.loads(path.read_text()) if path.exists() else []:
        if db.scalar(select(ContentVersion.id).where(ContentVersion.content_type == e["content_type"], ContentVersion.sha256 == e["sha256"])):
            continue
        _read(e["path"], e["sha256"])
        _cv(db, content_type=e["content_type"], content_key=e["key"], title=e["title"], version=e["version"], source_url=e["source_url"],
            sha256=e["sha256"], file_name=Path(e["path"]).name, status="available", is_active=False, meta={"path": e["path"], "staged": True})
        n += 1
    return n


# ---------- overview ----------
def overview(db: Session, show_synthetic: bool = True, show_updates: bool = True) -> list[dict]:
    """show_synthetic=False: a clean tenant without loaded demo data never sees the synthetic sample STIG content.
    show_updates=False: tenant has no systems → reference content is listed as installed, never as updates/diffs to review."""
    rows = [r for r in db.scalars(select(ContentVersion).order_by(ContentVersion.content_type, ContentVersion.loaded_at))
            if show_synthetic or not (r.meta or {}).get("synthetic")]
    out = []
    for t, label in TYPE_LABELS.items():
        items = [r for r in rows if r.content_type == t]
        if t == "overlay":
            from app.models import Overlay
            ov = list(db.scalars(select(Overlay))) if show_synthetic else []
            out.append({"content_type": t, "label": label, "installed": [{"title": o.title, "version": o.version, "status": "installed"} for o in ov],
                        "available": [], "note": "Overlays are versioned records; synthetic demo overlay only"})
            continue
        out.append({"content_type": t, "label": label,
                    "installed": [_cv_out(r) for r in items if r.is_active],
                    "available": [_cv_out(r) for r in items if r.status == "available"] if show_updates else [],
                    "superseded": [_cv_out(r) for r in items if r.status == "superseded"] if show_updates else [],
                    "note": NOT_CONFIGURED.get(t) if not items else (None if show_updates else "reference content – no updates to review until you register a system")})
    return out


def _cv_out(r: ContentVersion) -> dict:
    return {"id": str(r.id), "key": r.content_key, "title": r.title, "version": r.version, "effective_date": str(r.effective_date) if r.effective_date else None,
            "status": "installed" if r.is_active else r.status, "sha256": r.sha256, "items": r.item_count, "source_url": r.source_url,
            "synthetic": bool((r.meta or {}).get("synthetic"))}


# ---------- STIG diff / impact ----------
def _rules(db: Session, cv_id) -> dict[str, StigRule]:
    return {r.vuln_id: r for r in db.scalars(select(StigRule).where(StigRule.content_version_id == cv_id))}


def stig_diff(db: Session, old_id, new_id) -> dict:
    a, b = _rules(db, old_id), _rules(db, new_id)
    item = lambda r: {"vuln_id": r.vuln_id, "rule_id": r.rule_id, "title": r.title, "severity": r.severity, "ccis": r.ccis}
    d = {"added": [item(b[v]) for v in sorted(set(b) - set(a))], "removed": [item(a[v]) for v in sorted(set(a) - set(b))],
         "changed_requirement": [], "changed_severity": []}
    for v in sorted(set(a) & set(b)):
        o, n = a[v], b[v]
        if o.severity != n.severity:
            d["changed_severity"].append({**item(n), "old_severity": o.severity, "new_severity": n.severity})
        if (o.title, o.check_text, o.fix_text, o.ccis) != (n.title, n.check_text, n.fix_text, n.ccis):
            d["changed_requirement"].append({**item(n), "old_title": o.title, "new_title": n.title, "ccis_changed": o.ccis != n.ccis,
                                             "old_check": o.check_text, "new_check": n.check_text})
    return d


STIG_CAT = {"high": "CAT I", "medium": "CAT II", "low": "CAT III"}


def _controls_for_ccis(db: Session, ccis: set[str]) -> set[str]:
    cci_cv = db.scalar(select(ContentVersion.id).where(ContentVersion.content_type == "cci_list", ContentVersion.is_active.is_(True)))
    if not ccis or cci_cv is None:
        return set()
    return {c for (c,) in db.execute(select(CciControlMap.control_id).join(Cci, Cci.id == CciControlMap.cci_uuid)
                                     .where(Cci.content_version_id == cci_cv, CciControlMap.cci_id.in_(ccis), CciControlMap.control_id.is_not(None)))}


def stig_impact(db: Session, org_id, old: ContentVersion, new: ContentVersion, d: dict) -> dict:
    bench = new.meta["benchmark"]
    sys_ids = [s for (s,) in db.execute(select(System.id).where(System.org_id == org_id))]
    findings = list(db.scalars(select(Finding).where(Finding.benchmark == bench, Finding.system_id.in_(sys_ids))))
    names = {s.id: s.acronym or s.name for s in db.scalars(select(System).where(System.id.in_(sys_ids)))}
    sev = {x["vuln_id"]: x for x in d["changed_severity"]}
    req = {x["vuln_id"]: x for x in d["changed_requirement"]}
    rem = {x["vuln_id"] for x in d["removed"]}
    assets = {}
    for f in findings:
        if f.asset_id and f.asset_id not in assets:
            a = db.get(Asset, f.asset_id)
            assets[f.asset_id] = {"asset_id": str(a.id), "asset": a.name, "system": names[f.system_id],
                                  "reason": f"Checklist built on {old.version}; {new.version} adds {len(d['added'])} and changes {len(req) + len(sev)} rules – new checklist required"}
    aff_f = []
    for f in findings:
        kinds = [k for k, hit in (("removed", f.vuln_id in rem), ("changed_requirement", f.vuln_id in req), ("changed_severity", f.vuln_id in sev)) if hit]
        if kinds:
            x = {"finding_id": str(f.id), "vuln_id": f.vuln_id, "system": names[f.system_id], "state": f.current_state, "changes": kinds,
                 "asset": db.get(Asset, f.asset_id).name if f.asset_id else None}
            if f.vuln_id in sev:
                x.update(old_cat=STIG_CAT.get(sev[f.vuln_id]["old_severity"]), new_cat=STIG_CAT.get(sev[f.vuln_id]["new_severity"]))
            aff_f.append(x)
    ccis = {c for grp in ("added", "removed", "changed_requirement", "changed_severity") for x in d[grp] for c in x["ccis"]}
    ctrl_ids = _controls_for_ccis(db, ccis)
    sys_bench = {f.system_id for f in findings}
    controls = [{"system": names[a.system_id], "system_id": str(a.system_id), "control_id": a.control_id}
                for a in db.scalars(select(ControlAssignment).where(ControlAssignment.system_id.in_(sys_bench), ControlAssignment.control_id.in_(ctrl_ids))
                                    .order_by(ControlAssignment.control_id))] if sys_bench else []
    fmap = {x["finding_id"]: x for x in aff_f}
    poams = {}
    for p, fid in db.execute(select(Poam, PoamFinding.finding_id).join(PoamFinding, PoamFinding.poam_id == Poam.id)
                             .where(PoamFinding.finding_id.in_([uuid.UUID(k) for k in fmap]))) if fmap else []:
        x = fmap[str(fid)]
        e = poams.setdefault(p.human_id, {"poam_id": str(p.id), "human_id": p.human_id, "weakness": p.weakness, "current_cat": p.cat, "impacts": set()})
        if x.get("new_cat") and x["new_cat"] != p.cat:
            e["impacts"].add(f"severity {x['old_cat']} → {x['new_cat']}")
            e["new_cat"] = x["new_cat"]
        e["impacts"].update(c for c in x["changes"] if c != "changed_severity")
    for e in poams.values():
        e["impacts"] = sorted(e["impacts"])
    return {"benchmark": bench, "from": old.version, "to": new.version, "assets": list(assets.values()), "findings": aff_f, "controls": controls,
            "poams": sorted(poams.values(), key=lambda e: e["human_id"]),
            "counts": {"assets": len(assets), "findings": len(aff_f), "controls": len(controls), "poams": len(poams)}}


def _active(db: Session, content_type: str, key: str) -> ContentVersion | None:
    return db.scalar(select(ContentVersion).where(ContentVersion.content_type == content_type, ContentVersion.content_key == key,
                                                  ContentVersion.is_active.is_(True)))


def preview(db: Session, org_id, actor: User, version_id: uuid.UUID) -> ContentUpdate:
    new = db.get(ContentVersion, version_id)
    if new is None or new.status != "available":
        raise HTTPException(409, "Only an available (not yet installed) version can be previewed")
    old = _active(db, new.content_type, new.content_key)
    if new.content_type == STIG:
        d = stig_diff(db, old.id, new.id)
        imp = stig_impact(db, org_id, old, new, d)
    elif new.content_type == "kev_catalog":
        d, imp = kev_diff_impact(db, org_id, new)
    elif new.content_type in ("cci_list", "oscal_catalog"):
        d, imp = staged_diff(db, old, new)
    else:
        raise HTTPException(422, f"No update procedure for {new.content_type}")
    upd = ContentUpdate(org_id=org_id, content_type=new.content_type, content_key=new.content_key, from_version_id=old.id if old else None,
                        to_version_id=new.id, diff_summary={k: len(v) for k, v in d.items() if isinstance(v, list)}, impact={**imp, "diff": d},
                        requested_by=actor.id)
    db.add(upd)
    db.flush()
    audit.record(db, action="content.update.previewed", actor_user_id=actor.id, actor_email=actor.email, entity_type="content_update",
                 entity_id=str(upd.id), details={"type": new.content_type, "to": new.version, "summary": upd.diff_summary, "counts": imp.get("counts")})
    return upd


def apply(db: Session, upd: ContentUpdate, actor: User, justification: str) -> dict:
    if upd.status != "previewed":
        raise HTTPException(409, f"Update is {upd.status}")
    new = db.get(ContentVersion, upd.to_version_id)
    old = db.get(ContentVersion, upd.from_version_id) if upd.from_version_id else None
    if new.status != "available":
        raise HTTPException(409, "Target version is no longer available")
    if new.content_type == STIG:
        result = _apply_stig(db, upd, old, new, actor)
    elif new.content_type == "kev_catalog":
        _switch(db, old, new)
        from app.services.kev import reevaluate
        result = reevaluate(db, trigger=f"content_update:{upd.id}")
    elif new.content_type == "cci_list":
        result = _apply_cci(db, old, new)
    else:
        raise HTTPException(422, "Applying a new NIST catalog requires re-baselining every system; this build supports preview only")
    upd.status, upd.applied_by, upd.applied_at, upd.justification, upd.result = "applied", actor.id, now(), justification, result
    audit.record(db, action="content.update.applied", actor_user_id=actor.id, actor_email=actor.email, entity_type="content_update",
                 entity_id=str(upd.id), before={"version": old.version if old else None}, after={"version": new.version},
                 details={"type": new.content_type, "justification": justification, "result": result})
    return result


def _switch(db: Session, old: ContentVersion | None, new: ContentVersion) -> None:
    if old:
        old.is_active, old.status = False, "superseded"
    new.is_active, new.status = True, "installed"
    db.flush()


def _apply_stig(db: Session, upd: ContentUpdate, old: ContentVersion, new: ContentVersion, actor: User) -> dict:
    from app.services import workflow as wf
    from app.services.evaluation import evaluate_system, take_snapshots
    from app.services.ingest.pipeline import _map_stig

    d = stig_diff(db, old.id, new.id)
    imp = stig_impact(db, upd.org_id, old, new, d)
    _switch(db, old, new)
    new_rules = _rules(db, new.id)
    rem = {x["vuln_id"] for x in d["removed"]}
    sev = {x["vuln_id"]: x["new_severity"] for x in d["changed_severity"]}
    cci_changed = {x["vuln_id"] for x in d["changed_requirement"] if x["ccis_changed"]}
    cci_cv = db.scalar(select(ContentVersion).where(ContentVersion.content_type == "cci_list", ContentVersion.is_active.is_(True)))
    sys_ids = set()
    remapped = 0
    for f in db.scalars(select(Finding).join(System, System.id == Finding.system_id)
                        .where(System.org_id == upd.org_id, Finding.benchmark == new.meta["benchmark"])):
        sys_ids.add(f.system_id)
        f.content_version_id = new.id
        if f.vuln_id in rem:
            f.content_flag = f"rule_removed_in_{new.version}"
        elif f.vuln_id in sev:
            f.severity, f.cat = sev[f.vuln_id], STIG_CAT.get(sev[f.vuln_id])
        if f.vuln_id in cci_changed:
            for m in db.scalars(select(FindingControlMap).where(FindingControlMap.finding_id == f.id, FindingControlMap.valid_to.is_(None))):
                m.valid_to, m.superseded_by_version_id = now(), new.id
            db.flush()
            r = new_rules[f.vuln_id]
            remapped += _map_stig(db, f, {"ccis": r.ccis, "benchmark": f.benchmark, "benchmark_version": new.version, "rule_id": r.rule_id,
                                          "vuln_id": r.vuln_id}, db.get(__import__("app.models", fromlist=["Evidence"]).Evidence, f.latest_evidence_id), cci_cv)
            for m in db.scalars(select(FindingControlMap).where(FindingControlMap.finding_id == f.id, FindingControlMap.valid_to.is_(None))):
                m.stig_version_id = new.id
    for a in imp["assets"]:
        db.get(Asset, uuid.UUID(a["asset_id"])).recheck_reason = f"{new.title} applied – new checklist required"
    note = f"STIG change: {new.version} ({len(d['added'])} added, {len(d['removed'])} removed, {len(d['changed_requirement'])} changed, {len(d['changed_severity'])} severity)"
    for c in imp["controls"]:
        a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == uuid.UUID(c["system_id"]), ControlAssignment.control_id == c["control_id"]))
        a.content_change = {"note": note, "update_id": str(upd.id), "version": new.version, "acknowledged": False}
    for pi in imp["poams"]:
        p = db.get(Poam, uuid.UUID(pi["poam_id"]))
        p.content_impact = {"update_id": str(upd.id), "version": new.version, "impacts": pi["impacts"], "new_cat": pi.get("new_cat"),
                            "status": "pending_review"}
        wf.history(db, p, actor, "content_impact_flagged", version=new.version, impacts=pi["impacts"])
        if p.owner_id:
            wf.notify(db, p.owner_id, f"{p.human_id}: {new.version} impact review needed ({', '.join(pi['impacts'])})", f"/poams/{p.id}", "assignment")
    db.flush()
    for sid in sys_ids:
        evaluate_system(db, sid)
    take_snapshots(db, trigger="content.update")
    return {**imp["counts"], "remapped_mappings": remapped, "observations_rewritten": 0}


# ---------- KEV ----------
def kev_diff_impact(db: Session, org_id, new: ContentVersion) -> tuple[dict, dict]:
    from app.services.kev import kev_catalog, load_kev

    cur, nxt = kev_catalog(db)["cves"], load_kev(new.meta["path"], new.sha256)["cves"]
    d = {"added": sorted(nxt - cur)[:500], "removed": sorted(cur - nxt)[:500]}
    changed = []
    for f in db.scalars(select(Finding).join(System, System.id == Finding.system_id).where(System.org_id == org_id, Finding.cves.is_not(None))):
        will = any(c in nxt for c in (f.cves or []))
        if will != f.is_kev:
            changed.append({"finding_id": str(f.id), "title": f.title, "now_kev": will})
    return d, {"findings": changed, "counts": {"findings": len(changed), "added_cves": len(nxt - cur), "removed_cves": len(cur - nxt)}}


# ---------- staged NIST catalog / CCI ----------
def _ids(raw: bytes, content_type: str) -> set[str]:
    if content_type == "cci_list":
        from app.services.content.loader import CCI_NS
        import defusedxml.ElementTree as SafeET
        return {i.get("id") for i in SafeET.fromstring(raw, forbid_dtd=True).iterfind("c:cci_items/c:cci_item", CCI_NS)}
    out = set()

    def walk(n):
        for c in n.get("controls", []):
            out.add(c["id"])
            walk(c)
    for g in json.loads(raw)["catalog"].get("groups", []):
        walk(g)
    return out


def staged_diff(db: Session, old: ContentVersion, new: ContentVersion) -> tuple[dict, dict]:
    from app.services.storage import get_storage
    old_raw = get_storage().get(old.storage_key)
    new_raw = _read(new.meta["path"], new.sha256)
    a, b = _ids(old_raw, new.content_type), _ids(new_raw, new.content_type)
    d = {"added": sorted(b - a), "removed": sorted(a - b)}
    return d, {"counts": {"added": len(b - a), "removed": len(a - b), "unchanged": len(a & b)},
               "note": "Existing mappings keep their content version; new ingests use the applied version."}


def _apply_cci(db: Session, old: ContentVersion, new: ContentVersion) -> dict:
    from app.models import Control
    from app.services.content.loader import _load_cci, active_catalog_id

    cat_id = active_catalog_id(db)
    ids = {c.control_id: c.id for c in db.scalars(select(Control).where(Control.catalog_version_id == cat_id))}
    entry = {"key": new.content_key, "title": new.title, "path": new.meta["path"], "source_url": new.source_url,
             "rev5_reference_title": "NIST SP 800-53 Revision 5"}
    db.delete(new)
    db.flush()
    res = _load_cci(db, _read(entry["path"], new.sha256), entry, db.get(ContentVersion, cat_id), ids)
    db.execute(update(ContentVersion).where(ContentVersion.id == old.id).values(status="superseded", is_active=False))
    return res
