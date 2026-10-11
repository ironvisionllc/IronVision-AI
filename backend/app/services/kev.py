import hashlib
import json
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings


@lru_cache(maxsize=8)
def load_kev(rel_path: str, sha: str) -> dict:
    """Load a pinned CISA KEV snapshot (vendored file, SHA-256 verified)."""
    raw = (Path(get_settings().content_dir) / rel_path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != sha:
        raise RuntimeError("KEV catalog hash mismatch")
    doc = json.loads(raw)
    return {"version": doc.get("catalogVersion"), "sha256": sha, "path": rel_path, "count": len(doc.get("vulnerabilities", [])),
            "cves": frozenset(v["cveID"] for v in doc.get("vulnerabilities", []))}


def _manifest_entry() -> tuple[str, str]:
    e = json.loads((Path(get_settings().content_dir) / "manifest.json").read_text())["kev"]
    return e["path"], e["sha256"]


def kev_catalog(db: Session | None = None) -> dict:
    """The active KEV version in the database (content updates switch it); falls back to the manifest pin."""
    if db is not None:
        from app.models import ContentVersion
        cv = db.scalar(select(ContentVersion).where(ContentVersion.content_type == "kev_catalog", ContentVersion.is_active.is_(True)))
        if cv is not None and (cv.meta or {}).get("path"):
            return {**load_kev(cv.meta["path"], cv.sha256), "content_version_id": str(cv.id)}
    return load_kev(*_manifest_entry())


def is_kev(cves: list[str] | None, db: Session | None = None) -> bool:
    return bool(cves) and any(c in kev_catalog(db)["cves"] for c in cves)


def reevaluate(db: Session, trigger: str = "scheduled") -> dict:
    from app.models import Finding
    from app.services import audit
    from app.services.evaluation import evaluate_system

    cat = kev_catalog(db)
    changed, systems = 0, set()
    for f in db.scalars(select(Finding).where(Finding.cves.is_not(None))):
        flag = any(c in cat["cves"] for c in (f.cves or []))
        if flag != f.is_kev:
            f.is_kev, changed = flag, changed + 1
            systems.add(f.system_id)
    db.flush()
    for sid in systems:
        evaluate_system(db, sid)
    audit.record(db, action="kev.reevaluated", actor_email="system", entity_type="content", entity_id=cat.get("content_version_id"),
                 details={"version": cat["version"], "changed": changed, "trigger": trigger})
    return {"kev_version": cat["version"], "changed": changed, "systems": len(systems)}
