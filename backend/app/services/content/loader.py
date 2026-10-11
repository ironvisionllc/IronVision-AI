"""Versioned, pinned reference content loader (NIST SP 800-53 Rev5 OSCAL + baselines + DISA CCI list)."""
import hashlib
import io
import json
import logging
import re
import uuid
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import requests
from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Baseline, BaselineControl, Cci, CciControlMap, ContentVersion, Control, ControlObjective
from app.services.content.oscal import assessment_methods, flatten_objectives, prop, render_prose, render_statement
from app.services.storage import get_storage

log = logging.getLogger("aegis.content")
CCI_NS = {"c": "http://iase.disa.mil/cci"}
CCI_REF_RE = re.compile(r"^\s*([A-Z]{2})-(\d+)\s*(?:\((\d+)\))?\s*(.*)$")


class ContentIntegrityError(RuntimeError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def load_manifest(content_dir: Path) -> dict:
    return json.loads((content_dir / "manifest.json").read_text())


def _read_pinned(content_dir: Path, rel_path: str, expected_sha: str, source_url: str, fetch_remote: bool,
                 archive_member: str | None = None, archive_sha: str | None = None) -> bytes:
    if fetch_remote:
        resp = requests.get(source_url, timeout=120, headers={"User-Agent": "AegisRMF-content-loader"})
        resp.raise_for_status()
        raw = resp.content
        if archive_member:
            if archive_sha and _sha256(raw) != archive_sha:
                raise ContentIntegrityError(f"Archive hash mismatch for {source_url}")
            raw = zipfile.ZipFile(io.BytesIO(raw)).read(archive_member)
    else:
        raw = (content_dir / rel_path).read_bytes()
    actual = _sha256(raw)
    if actual != expected_sha:
        raise ContentIntegrityError(f"SHA-256 mismatch for {rel_path}: expected {expected_sha}, got {actual}")
    return raw


def _existing(db: Session, content_type: str, key: str, sha: str) -> ContentVersion | None:
    return db.scalar(select(ContentVersion).where(ContentVersion.content_type == content_type,
                                                  ContentVersion.content_key == key, ContentVersion.sha256 == sha))


def _new_version(db: Session, *, content_type: str, key: str, title: str, raw: bytes, file_name: str, source_url: str,
                 version: str | None, effective: date | None, release_tag: str | None = None,
                 commit: str | None = None, meta: dict | None = None) -> ContentVersion:
    sha = _sha256(raw)
    storage_key = f"reference-content/{content_type}/{sha}/{file_name}"
    get_storage().put(storage_key, raw, "application/xml" if file_name.endswith(".xml") else "application/json")
    db.execute(update(ContentVersion).where(ContentVersion.content_type == content_type,
                                            ContentVersion.content_key == key).values(is_active=False))
    cv = ContentVersion(
        id=uuid.uuid4(), content_type=content_type, content_key=key, title=title, version=version,
        release_tag=release_tag, commit_sha=commit, source_url=source_url, sha256=sha, file_name=file_name,
        storage_key=storage_key, effective_date=effective, loaded_at=datetime.now(timezone.utc), status="loading",
        is_active=True, meta=meta, source="official",
        provenance={"loader": "app.services.content.loader", "verified_sha256": True},
    )
    db.add(cv)
    db.flush()
    return cv


def _load_catalog(db: Session, raw: bytes, entry: dict, oscal: dict) -> tuple[ContentVersion, dict[str, uuid.UUID]]:
    doc = json.loads(raw)["catalog"]
    md = doc["metadata"]
    cv = _new_version(
        db, content_type="oscal_catalog", key=entry["key"], title=md["title"], raw=raw,
        file_name=Path(entry["path"]).name, source_url=entry["source_url"], version=md.get("version"),
        effective=_date(md.get("published") or md.get("last-modified")), release_tag=oscal["release_tag"],
        commit=oscal["commit"], meta={"oscal_version": md.get("oscal-version"), "last_modified": md.get("last-modified"),
                                      "repository": oscal["repository"]},
    )
    params: dict[str, dict] = {}

    def collect(ctrls):
        for c in ctrls:
            for p in c.get("params", []) or []:
                params[p["id"]] = p
            collect(c.get("controls", []) or [])

    for g in doc["groups"]:
        collect(g.get("controls", []))

    controls, objectives, ids = [], [], {}
    prov = {"catalog_version_id": str(cv.id), "sha256": cv.sha256}

    def walk(ctrls, group, parent_uuid=None, parent_cid=None):
        for c in ctrls:
            cu = uuid.uuid4()
            ids[c["id"]] = cu
            parts = c.get("parts", []) or []
            stmt = next((p for p in parts if p.get("name") == "statement"), None)
            guidance = next((p for p in parts if p.get("name") == "guidance"), None)
            ctrl_params = [
                {**p, "rendered": render_prose("{{ insert: param, %s }}" % p["id"], params)} for p in c.get("params", []) or []
            ]
            controls.append({
                "id": cu, "catalog_version_id": cv.id, "control_id": c["id"], "label": prop(c, "label"),
                "parent_id": parent_uuid, "parent_control_id": parent_cid, "family_id": group["id"],
                "family_title": group["title"], "title": c["title"], "control_class": c.get("class"),
                "is_enhancement": parent_uuid is not None, "is_withdrawn": prop(c, "status") == "withdrawn",
                "sort_id": prop(c, "sort-id"), "statement": "\n".join(render_statement(stmt, params)) if stmt else None,
                "statement_parts": stmt.get("parts") if stmt else None, "parameters": ctrl_params,
                "guidance": render_prose(guidance.get("prose"), params) if guidance else None,
                "assessment_methods": assessment_methods(parts), "links": c.get("links"), "props": c.get("props"),
                "source": "NIST SP 800-53 Rev5 OSCAL", "provenance": prov,
            })
            for obj_part in (p for p in parts if p.get("name") == "assessment-objective"):
                for o in flatten_objectives(obj_part, params):
                    objectives.append({**o, "id": uuid.uuid4(), "control_uuid": cu, "source": "NIST SP 800-53A Rev5 (OSCAL)"})
            walk(c.get("controls", []) or [], group, cu, c["id"])

    for g in doc["groups"]:
        walk(g.get("controls", []), g)
    db.execute(insert(Control), controls)
    for i in range(0, len(objectives), 5000):
        db.execute(insert(ControlObjective), objectives[i:i + 5000])
    cv.item_count = len(controls)
    cv.status = "loaded"
    cv.meta = {**(cv.meta or {}), "enhancements": sum(1 for c in controls if c["is_enhancement"]),
               "withdrawn": sum(1 for c in controls if c["is_withdrawn"]), "objectives": len(objectives)}
    return cv, ids


def _load_profile(db: Session, raw: bytes, entry: dict, oscal: dict, catalog: ContentVersion, ids: dict) -> dict:
    doc = json.loads(raw)["profile"]
    md = doc["metadata"]
    cv = _new_version(
        db, content_type="oscal_profile", key=entry["key"], title=md["title"], raw=raw,
        file_name=Path(entry["path"]).name, source_url=entry["source_url"], version=md.get("version"),
        effective=_date(md.get("published") or md.get("last-modified")), release_tag=oscal["release_tag"],
        commit=oscal["commit"], meta={"baseline_key": entry["baseline_key"]},
    )
    with_ids: list[str] = []
    for imp in doc.get("imports", []):
        for inc in imp.get("include-controls", []) or []:
            with_ids.extend(inc.get("with-ids", []))
    missing = [cid for cid in with_ids if cid not in ids]
    bl = Baseline(id=uuid.uuid4(), profile_version_id=cv.id, catalog_version_id=catalog.id,
                  baseline_key=entry["baseline_key"], title=md["title"], control_count=len(with_ids) - len(missing),
                  source="NIST SP 800-53B (OSCAL profile)", provenance={"profile_sha256": cv.sha256})
    db.add(bl)
    db.flush()
    rows = [{"id": uuid.uuid4(), "baseline_id": bl.id, "control_uuid": ids[cid], "control_id": cid}
            for cid in dict.fromkeys(with_ids) if cid in ids]
    if rows:
        db.execute(insert(BaselineControl), rows)
    cv.item_count = len(rows)
    cv.status = "loaded"
    return {"baseline": entry["baseline_key"], "controls": len(rows), "unresolved": missing}


def parse_cci_reference(index: str) -> tuple[str | None, str | None]:
    m = CCI_REF_RE.match(index or "")
    if not m:
        return None, None
    fam, num, enh, rest = m.groups()
    cid = f"{fam.lower()}-{int(num)}" + (f".{int(enh)}" if enh else "")
    return cid, (rest.strip() or None)


def _load_cci(db: Session, raw: bytes, entry: dict, catalog: ContentVersion, ids: dict) -> dict:
    import defusedxml.ElementTree as SafeET
    root = SafeET.fromstring(raw, forbid_dtd=True)
    version = root.findtext("c:metadata/c:version", namespaces=CCI_NS)
    published = root.findtext("c:metadata/c:publishdate", namespaces=CCI_NS)
    effective = _date(published)
    cv = _new_version(
        db, content_type="cci_list", key=entry["key"], title=entry["title"], raw=raw, file_name=Path(entry["path"]).name,
        source_url=entry["source_url"], version=version, effective=effective,
        meta={"archive_sha256": entry.get("archive_sha256"), "publishdate": published, "archive_member": entry.get("archive_member")},
    )
    ccis, maps = [], []
    unresolved = 0
    for item in root.iterfind("c:cci_items/c:cci_item", CCI_NS):
        cu = uuid.uuid4()
        cci_id = item.get("id")
        refs = [dict(r.attrib) for r in item.iterfind("c:references/c:reference", CCI_NS)]
        ccis.append({
            "id": cu, "content_version_id": cv.id, "cci_id": cci_id, "status": item.findtext("c:status", namespaces=CCI_NS),
            "publish_date": _date(item.findtext("c:publishdate", namespaces=CCI_NS)),
            "contributor": item.findtext("c:contributor", namespaces=CCI_NS),
            "definition": (item.findtext("c:definition", namespaces=CCI_NS) or "").strip(),
            "cci_type": item.findtext("c:type", namespaces=CCI_NS), "references": refs,
            "source": "DISA CCI List", "provenance": {"cci_version_id": str(cv.id), "sha256": cv.sha256},
        })
        for r in refs:
            if r.get("title") != entry["rev5_reference_title"]:
                continue
            cid, part = parse_cci_reference(r.get("index", ""))
            control_uuid = ids.get(cid) if cid else None
            if control_uuid is None:
                unresolved += 1
            maps.append({
                "id": uuid.uuid4(), "cci_uuid": cu, "control_uuid": control_uuid, "cci_id": cci_id, "control_id": cid,
                "reference_index": r.get("index", ""), "statement_part": part, "version": r.get("version") or "5",
                "effective_date": effective, "review_status": "source_asserted" if control_uuid else "unresolved",
                "source": f"DISA CCI List {version}",
                "provenance": {"file": entry["path"], "sha256": cv.sha256, "creator": r.get("creator"),
                               "title": r.get("title"), "location": r.get("location"),
                               "catalog_version_id": str(catalog.id)},
            })
    for i in range(0, len(ccis), 5000):
        db.execute(insert(Cci), ccis[i:i + 5000])
    for i in range(0, len(maps), 5000):
        db.execute(insert(CciControlMap), maps[i:i + 5000])
    cv.item_count = len(ccis)
    cv.status = "loaded"
    cv.meta = {**(cv.meta or {}), "rev5_mappings": len(maps), "unresolved_mappings": unresolved,
               "ccis_with_rev5_reference": len({m["cci_id"] for m in maps})}
    return {"ccis": len(ccis), "rev5_mappings": len(maps), "unresolved_mappings": unresolved}


def load_reference_content(db: Session, force: bool = False) -> dict:
    s = get_settings()
    content_dir = Path(s.content_dir)
    manifest = load_manifest(content_dir)
    oscal = manifest["oscal"]
    cat_entry = next(f for f in oscal["files"] if f["content_type"] == "oscal_catalog")
    cat_raw = _read_pinned(content_dir, cat_entry["path"], cat_entry["sha256"], cat_entry["source_url"], s.content_fetch_remote)
    existing = _existing(db, "oscal_catalog", cat_entry["key"], cat_entry["sha256"])
    if existing and not force:
        return {"skipped": True, "reason": "pinned catalog already loaded", "catalog_version_id": str(existing.id)}
    if existing and force:
        db.delete(existing)
        for ct, key, sha in [("oscal_profile", f["key"], f["sha256"]) for f in oscal["files"] if f["content_type"] == "oscal_profile"] + [
            ("cci_list", manifest["cci"]["key"], manifest["cci"]["sha256"])]:
            old = _existing(db, ct, key, sha)
            if old:
                db.delete(old)
        db.flush()
    catalog, ids = _load_catalog(db, cat_raw, cat_entry, oscal)
    result = {"catalog": {"version": catalog.version, "controls": catalog.item_count, **catalog.meta}, "baselines": []}
    for entry in (f for f in oscal["files"] if f["content_type"] == "oscal_profile"):
        raw = _read_pinned(content_dir, entry["path"], entry["sha256"], entry["source_url"], s.content_fetch_remote)
        result["baselines"].append(_load_profile(db, raw, entry, oscal, catalog, ids))
    cci = manifest["cci"]
    cci_raw = _read_pinned(content_dir, cci["path"], cci["sha256"], cci["source_url"], s.content_fetch_remote,
                           archive_member=cci.get("archive_member"), archive_sha=cci.get("archive_sha256"))
    result["cci"] = _load_cci(db, cci_raw, cci, catalog, ids)
    db.flush()
    log.info("Reference content loaded", extra={"result": result})
    return result


def active_catalog_id(db: Session) -> uuid.UUID | None:
    return db.scalar(select(ContentVersion.id).where(ContentVersion.content_type == "oscal_catalog",
                                                     ContentVersion.is_active.is_(True), ContentVersion.status == "loaded")
                     .order_by(ContentVersion.loaded_at.desc()).limit(1))


def content_stats(db: Session) -> dict:
    cat_id = active_catalog_id(db)
    if cat_id is None:
        return {"loaded": False}
    total = db.scalar(select(func.count()).select_from(Control).where(Control.catalog_version_id == cat_id))
    enh = db.scalar(select(func.count()).select_from(Control).where(Control.catalog_version_id == cat_id, Control.is_enhancement.is_(True)))
    withdrawn = db.scalar(select(func.count()).select_from(Control).where(Control.catalog_version_id == cat_id, Control.is_withdrawn.is_(True)))
    objectives = db.scalar(select(func.count()).select_from(ControlObjective).join(Control).where(Control.catalog_version_id == cat_id))
    baselines = {b.baseline_key: b.control_count for b in db.scalars(
        select(Baseline).join(ContentVersion, ContentVersion.id == Baseline.profile_version_id)
        .where(Baseline.catalog_version_id == cat_id, ContentVersion.is_active.is_(True)))}
    cci_cv = db.scalar(select(ContentVersion).where(ContentVersion.content_type == "cci_list", ContentVersion.is_active.is_(True)))
    ccis = db.scalar(select(func.count()).select_from(Cci).where(Cci.content_version_id == cci_cv.id)) if cci_cv else 0
    maps = db.scalar(select(func.count()).select_from(CciControlMap).join(Cci).where(Cci.content_version_id == cci_cv.id)) if cci_cv else 0
    resolved = db.scalar(select(func.count()).select_from(CciControlMap).join(Cci).where(
        Cci.content_version_id == cci_cv.id, CciControlMap.control_uuid.is_not(None))) if cci_cv else 0
    return {"loaded": True, "controls_total": total, "base_controls": total - enh, "enhancements": enh,
            "withdrawn": withdrawn, "assessment_objectives": objectives, "baselines": baselines, "ccis": ccis,
            "cci_rev5_mappings": maps, "cci_rev5_mappings_resolved": resolved}
