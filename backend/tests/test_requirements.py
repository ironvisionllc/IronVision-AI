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


def _recovery_copy(tmp_path: Path) -> Path:
    p = tmp_path / "requirements.recovery.txt"
    shutil.copy(cr.RECOVERY_REQ, p)
    return p


def _prod_excl():
    excl, _ = cr.parse_exclusions(ROOT / "backend" / "requirements.prod-exclude.txt")
    return cr.parse_requirements(ROOT / "backend" / "requirements.prod.txt"), excl


def test_recovery_requirements_subset_of_prod_and_cover_the_recovery_closure():
    prod, excl = _prod_excl()
    assert cr.check_recovery(prod, excl) == []
    rec = cr.parse_requirements(cr.RECOVERY_REQ)
    assert "emergentintegrations" not in rec and all(prod[k] == v for k, v in rec.items())


def test_recovery_guard_rejects_private_package_version_drift_and_missing_import(tmp_path):
    prod, excl = _prod_excl()
    p = _recovery_copy(tmp_path)
    txt = p.read_text().replace("msgpack==1.2.3\n", "").replace("boto3==", "boto3==0.0.1#").replace("httpx==", "httpx==9.9.9  # was ")
    p.write_text(txt + "emergentintegrations==0.2.2\n")
    errs = cr.check_recovery(prod, excl, req=p)
    assert any("emergentintegrations is private/preview-only" in e for e in errs)
    assert any("httpx version mismatch" in e for e in errs)
    assert any("'msgpack' (imported by backend/app/tools/minio_xl.py) needs msgpack" in e for e in errs)


def test_recovery_closure_never_reaches_emergent(tmp_path):
    from app.tools.import_closure import closure
    local, third = closure()
    assert "emergentintegrations" not in third and not any("emergent" in m for m in local)
    assert {"app.tools.recovery", "app.api.v1", "app"} <= local  # parent packages are followed


def test_dockerfile_guard(tmp_path):
    assert cr.check_dockerfiles() == []
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "Dockerfile").write_text("FROM python:3.11-slim\n# never: requirements.txt\nCOPY backend/requirements.txt /r.txt\n"
                                              "RUN pip install -r /r.txt --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/\n")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "Dockerfile").write_text("FROM python:3.11-slim\nRUN pip install --index-url https://pypi.org/simple -r requirements.prod.txt\n")
    errs = cr.check_dockerfiles(tmp_path)
    assert len(errs) == 2 and "a/Dockerfile: installs requirements.txt" in errs[0] and "non-PyPI package index" in errs[1]


def test_backend_prod_dockerfiles_use_requirements_prod():
    for f in ("Dockerfile", "Dockerfile.worker"):
        assert "requirements.prod.txt" in (ROOT / "backend" / f).read_text()
    assert "requirements.recovery.txt" in (ROOT / "deploy" / "recovery" / "Dockerfile").read_text()
