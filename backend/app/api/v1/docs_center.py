"""Read-only handover documentation. Serves ONLY the allowlisted repository docs (no user-supplied paths)."""
import io
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.config import BACKEND_DIR
from app.security.deps import CurrentUser, get_current_user

router = APIRouter(prefix="/docs-center", tags=["docs"])

# slug -> (relative path under DOCS_ROOT, title). Order = display order.
DOCS: dict[str, tuple[str, str]] = {
    "readme": ("README.md", "README – Overview & quick start"),
    "digitalocean": ("docs/DIGITALOCEAN_DEPLOYMENT.md", "DigitalOcean deployment guide"),
    "deployment": ("docs/DEPLOYMENT.md", "Deployment"),
    "security": ("docs/SECURITY.md", "Security"),
    "portability": ("docs/PORTABILITY.md", "Portability & Emergent dependency register"),
    "migration": ("docs/MIGRATION_PROCEDURE.md", "Schema migration procedure"),
    "external-validation": ("docs/EXTERNAL_VALIDATION.md", "External validation"),
    "content-updates": ("docs/CONTENT_UPDATES.md", "Controlled content updates"),
    "architecture": ("docs/ARCHITECTURE.md", "Architecture"),
    "api": ("docs/API.md", "API"),
    "test-results": ("docs/TEST_RESULTS.md", "Test results"),
    "design-system": ("docs/DESIGN_SYSTEM.md", "IronVision Design System"),
}


def _root() -> Path:
    return Path(os.environ.get("DOCS_ROOT") or BACKEND_DIR.parent).resolve()


def _file(slug: str) -> Path:
    if slug not in DOCS:
        raise HTTPException(404, "Unknown document")
    root = _root()
    p = (root / DOCS[slug][0]).resolve()
    if root not in p.parents or not p.is_file():
        raise HTTPException(404, "Document not available in this deployment")
    return p


def _meta(slug: str) -> dict:
    rel, title = DOCS[slug]
    p = _root() / rel
    ok = p.is_file()
    return {"slug": slug, "title": title, "path": rel, "available": ok, "bytes": p.stat().st_size if ok else 0,
            "updated_at": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat() if ok else None}


@router.get("")
def list_docs(_: CurrentUser = Depends(get_current_user)) -> dict:
    return {"items": [_meta(s) for s in DOCS]}


@router.get("/archive.zip")
def download_all(_: CurrentUser = Depends(get_current_user)) -> Response:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for slug, (rel, _t) in DOCS.items():
            p = _root() / rel
            if p.is_file():
                z.write(p, f"ironvision-ai-docs/{rel}")
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="ironvision-ai-docs.zip"'})


@router.get("/{slug}")
def get_doc(slug: str, _: CurrentUser = Depends(get_current_user)) -> dict:
    p = _file(slug)
    return _meta(slug) | {"markdown": p.read_text(encoding="utf-8")}


@router.get("/{slug}/download")
def download_doc(slug: str, _: CurrentUser = Depends(get_current_user)) -> Response:
    p = _file(slug)
    return Response(p.read_bytes(), media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{p.name}"'})
