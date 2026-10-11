"""Stage a new official content release as an AVAILABLE version. It is applied later through the controlled
preview → apply flow in Evidence Ledger → Content Updates, which needs the content.apply permission.

  python scripts/stage_content_release.py kev                       # fetch the current CISA KEV JSON into content/kev/snapshots/
  python scripts/stage_content_release.py cci_list FILE --version 2026-xx-xx --source-url URL
  python scripts/stage_content_release.py oscal_catalog FILE --version 5.x.y --source-url URL

Each file is hashed (SHA-256) and recorded in content/staged/staged.json, or kept as a KEV snapshot. The backend registers it on
POST /api/v1/content-updates/register (Admin → "Register staged content"). Installed versions are never modified.
"""
import argparse
import hashlib
import json
import shutil
import urllib.request
from pathlib import Path

CONTENT = Path(__file__).resolve().parents[1] / "backend" / "content"
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"


def stage_kev() -> None:
    raw = urllib.request.urlopen(KEV_URL, timeout=60).read()
    ver = json.loads(raw)["catalogVersion"]
    pinned = json.loads((CONTENT / "manifest.json").read_text())["kev"]
    if hashlib.sha256(raw).hexdigest() == pinned["sha256"]:
        print("KEV unchanged from pinned version", ver)
        return
    out = CONTENT / "kev" / "snapshots" / f"kev_{ver}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(raw)
    print("staged", out.relative_to(CONTENT), hashlib.sha256(raw).hexdigest())


def stage_file(content_type: str, path: str, version: str, source_url: str) -> None:
    src = Path(path)
    dest = CONTENT / "staged" / content_type / version / src.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    sha = hashlib.sha256(dest.read_bytes()).hexdigest()
    idx = CONTENT / "staged" / "staged.json"
    rows = json.loads(idx.read_text()) if idx.exists() else []
    key = {"cci_list": "disa-cci-list", "oscal_catalog": "sp800-53r5-catalog"}[content_type]
    rows.append({"content_type": content_type, "key": key, "version": version, "title": f"{key} {version} (staged)",
                 "path": str(dest.relative_to(CONTENT)), "sha256": sha, "source_url": source_url})
    idx.write_text(json.dumps(rows, indent=1) + "\n")
    print("staged", dest.relative_to(CONTENT), sha)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("content_type", choices=["kev", "cci_list", "oscal_catalog"])
    ap.add_argument("file", nargs="?")
    ap.add_argument("--version")
    ap.add_argument("--source-url")
    a = ap.parse_args()
    stage_kev() if a.content_type == "kev" else stage_file(a.content_type, a.file, a.version, a.source_url)
