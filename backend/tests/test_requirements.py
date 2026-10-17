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
    lock, errs = cr.load_lock("recovery")
    assert errs == [] and cr.check_recovery(prod, excl, lock) == []
    rec = cr.parse_requirements(cr.RECOVERY_REQ)
    assert "emergentintegrations" not in rec and all(prod[k] == v for k, v in rec.items())


def test_recovery_guard_rejects_private_package_version_drift_and_missing_import(tmp_path):
    prod, excl = _prod_excl()
    p = _recovery_copy(tmp_path)
    txt = p.read_text().replace("msgpack==1.2.3\n", "").replace("boto3==", "boto3==0.0.1#").replace("httpx==", "httpx==9.9.9  # was ")
    p.write_text(txt + "emergentintegrations==0.2.2\n")
    errs = cr.check_recovery(prod, excl, cr.load_lock("recovery")[0], req=p)
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



def test_static_check_is_host_independent_bare_interpreter():
    """No site-packages at all (-I -S): the static check must still PASS – host packages are never consulted."""
    import subprocess
    import sys
    r = subprocess.run([sys.executable, "-I", "-S", str(ROOT / "scripts/check_requirements.py")], capture_output=True, text=True, check=False)
    assert r.returncode == 0 and "host: static manifest check – host packages not used" in r.stdout and "RESULT: PASS" in r.stdout, r.stdout[-800:]


def test_stale_lock_is_reported_with_regen_command(tmp_path, monkeypatch):
    m = tmp_path / "requirements.recovery.txt"
    m.write_text(cr.RECOVERY_REQ.read_text() + "# edited\n")
    lf = tmp_path / "lock.json"
    shutil.copy(cr.LOCKS["recovery"], lf)
    monkeypatch.setitem(cr.TARGETS, "recovery", m)
    monkeypatch.setitem(cr.LOCKS, "recovery", lf)
    monkeypatch.setattr(cr, "ROOT", tmp_path)
    _, errs = cr.load_lock("recovery")
    assert len(errs) == 1 and "is STALE" in errs[0] and "--write-lock --target recovery" in errs[0] and "--no-deps" in errs[0]


def test_lock_completeness_catches_unpinned_transitive_dependencies():
    import json
    lock = json.loads(cr.LOCKS["recovery"].read_text())
    pins = cr.parse_requirements(cr.RECOVERY_REQ)
    assert cr.check_lock("recovery", pins, lock) == []
    lock["distributions"]["jsonschema"]["requires"].append("pyrsistent")  # e.g. an old jsonschema (<4.18) needs pyrsistent
    lock["distributions"]["extra-dist"] = {"version": "1.0", "requires": []}
    pins2 = {**pins, "httpx": "0.0.1"}
    errs = cr.check_lock("recovery", pins2, lock)
    assert any("pyrsistent (required by jsonschema) is not pinned" in e for e in errs)
    assert any("extra-dist==1.0 is in the resolved environment but not pinned" in e for e in errs)
    assert any("httpx pinned 0.0.1 but locked" in e for e in errs)


def test_locks_are_complete_closures_of_their_manifests():
    for t in ("prod", "recovery"):
        lock, errs = cr.load_lock(t)
        assert errs == [] and cr.check_lock(t, cr.parse_requirements(cr.TARGETS[t]), lock) == []
        assert lock["distributions"]["jsonschema"]["version"] == "4.26.0" and "pyrsistent" not in lock["distributions"]["jsonschema"]["requires"]


def test_deploy_and_recover_run_static_then_in_image_checks():
    rs, ds = (ROOT / "recover.sh").read_text(), (ROOT / "scripts" / "deploy.sh").read_text()
    g = rs[rs.index("image_gate() {"):rs.index("\n}\n", rs.index("image_gate() {"))]
    assert g.index("python3 scripts/check_requirements.py |") < g.index("build recovery") < g.index("--in-env --target recovery")
    # rehearsal backend = production backend image definition, rebuilt every run, then checked IN that image (uvicorn + app.main + startup)
    assert g.index("--in-env --target recovery") < g.index("build rehearsal-backend") < g.index("--in-env --target prod --app-dir /srv/backend")
    assert rs.count("    image_gate\n") == 3  # run + rehearse (standalone; no-op inside run) + cutover, before anything else
    assert ds.index("python3 scripts/check_requirements.py\n") < ds.index('"${DC[@]}" build') < ds.index("--in-env --target prod --app-dir /srv/backend")
