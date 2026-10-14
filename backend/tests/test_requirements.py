"""requirements.prod.txt must not drift from requirements.txt (see scripts/check_requirements.py)."""
import importlib.util
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_requirements", ROOT / "scripts" / "check_requirements.py")
cr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cr)


def test_prod_requirements_match_dev_pins_and_cover_imports():
    assert cr.run() == []


def _copy(tmp_path: Path) -> Path:
    for f in ("requirements.txt", "requirements.prod.txt", "requirements.prod-exclude.txt"):
        shutil.copy(ROOT / "backend" / f, tmp_path / f)
    return tmp_path


def test_missing_python_multipart_is_caught(tmp_path):
    b = _copy(tmp_path)
    p = b / "requirements.prod.txt"
    p.write_text("\n".join(line for line in p.read_text().splitlines() if not line.startswith("python-multipart")))
    errs = cr.run(b, with_imports=False)
    assert any("python-multipart==0.0.32 is in requirements.txt but missing" in e for e in errs)
    assert any(e.startswith("python-multipart is required") for e in errs)


def test_version_mismatch_and_reasonless_exclusion_are_caught(tmp_path):
    b = _copy(tmp_path)
    p = b / "requirements.prod.txt"
    p.write_text(p.read_text().replace("fastapi==0.143.0", "fastapi==0.142.0"))
    (b / "requirements.prod-exclude.txt").write_text((b / "requirements.prod-exclude.txt").read_text() + "requests\n")
    errs = cr.run(b, with_imports=False)
    assert any("fastapi: version mismatch" in e for e in errs)
    assert any("'requests' has no reason" in e for e in errs) and any("requests is both excluded" in e for e in errs)


def test_selfcheck_imports_every_module():
    from app.tools import selfcheck
    assert selfcheck.run() == 0
