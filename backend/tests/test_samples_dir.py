"""Droplet rehearsal: Explore Demo sandbox provisioning failed with FileNotFoundError /app/samples/stig/mpp_mpp-app-01.ckl –
the recovery tool container had no SAMPLES_DIR and no samples mount, and sandbox.samples_dir() silently fell back to parents[3]."""
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Organization, RoleAssignment, System, User
from app.services import sandbox as sbx

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "samples"


def _droplet_env(**extra) -> dict:
    keys = ("STORAGE_DRIVER", "S3_ENDPOINT_URL", "S3_BUCKET", "KEYCLOAK_URL", "KEYCLOAK_REALM", "OIDC_ISSUER", "OIDC_CLIENT_ID", "APP_DOMAIN")
    return {"PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin", "HOME": "/root", "APP_ENV": "production", "IRONVISION_DOTENV": "0",
            "DATABASE_URL": "postgresql+psycopg://u:p@postgres:5432/ironvision", "JWT_SECRET": "x" * 48} | {k: "x" for k in keys} | extra


def test_old_fallback_in_the_recovery_container_layout_reproduces_the_droplet_file_not_found(tmp_path):
    """Recovery image: COPY backend /app/backend, no /app/samples, no SAMPLES_DIR → old samples_dir() = /app/samples."""
    old = subprocess.run(["git", "show", "5e07712:backend/app/services/sandbox.py"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    fn = re.search(r"^def samples_dir\(\) -> str:\n(?:    .*\n)+", old, re.M).group(0)
    mod = tmp_path / "app" / "backend" / "app" / "services" / "sandbox.py"   # = /app/backend/app/services/sandbox.py in the image
    mod.parent.mkdir(parents=True)
    ns = {"os": __import__("os"), "__file__": str(mod)}
    exec(compile(fn, str(mod), "exec"), ns)  # noqa: S102 – the exact old function, evaluated at the image's path
    env_sd = __import__("os").environ.pop("SAMPLES_DIR", None)
    try:
        sd = ns["samples_dir"]()
    finally:
        if env_sd is not None:
            __import__("os").environ["SAMPLES_DIR"] = env_sd
    assert sd == str(tmp_path / "app" / "samples")
    with pytest.raises(FileNotFoundError, match=r"app/samples/stig/mpp_mpp-app-01\.ckl"):
        (Path(sd) / "stig" / "mpp_mpp-app-01.ckl").read_bytes()                # seed_phase1.py:179-182


def test_new_code_in_the_droplet_tool_env_fails_clearly_with_the_named_path(tmp_path):
    code = "from app.services import sandbox as s\ntry:\n    s.check_samples()\nexcept s.SamplesMissing as e:\n    print('MISSING', e)"
    r = subprocess.run([sys.executable, "-c", code], env=_droplet_env(), cwd=ROOT / "backend", capture_output=True, text=True, check=True)
    assert "MISSING SAMPLES_DIR is not set" in r.stdout
    r = subprocess.run([sys.executable, "-c", code], env=_droplet_env(SAMPLES_DIR=str(tmp_path / "samples")), cwd=ROOT / "backend",
                       capture_output=True, text=True, check=True)
    assert f"{tmp_path}/samples/stig/mpp_mpp-app-01.ckl" in r.stdout and f"{tmp_path}/samples/stig/ltp_*" in r.stdout


def test_samples_present_provisioning_reaches_ready(monkeypatch):
    from app.seed import ensure_demo_launcher_sandbox
    monkeypatch.setenv("SAMPLES_DIR", str(SAMPLES))
    ok = sbx.check_samples()
    assert "stig/mpp_mpp-app-01.ckl" in ok["files"] and any(f.startswith("stig/ltp_") for f in ok["files"])
    with SessionLocal() as db:
        r = ensure_demo_launcher_sandbox(db)
        assert r["sandbox_status"] == "ready"
        assert db.scalar(select(func.count()).select_from(User).where(User.email == sbx.DEMO_EMAIL)) == 1


def _counts(db):
    return tuple(db.scalar(select(func.count()).select_from(m)) for m in (User, Organization, RoleAssignment, System))


def test_one_missing_sample_file_fails_clearly_with_no_partial_sandbox_rows(tmp_path, monkeypatch):
    from app.seed import ensure_demo_launcher_sandbox
    part = tmp_path / "samples"
    shutil.copytree(SAMPLES, part)                      # the real sample files (nothing fabricated) …
    (part / "acas" / "fmdh_scan_export.csv").unlink()   # … minus one
    monkeypatch.setenv("SAMPLES_DIR", str(part))
    called = []
    monkeypatch.setattr(sbx, "seed_demo_account", lambda *a, **k: called.append(1))
    with SessionLocal() as db:
        before = _counts(db)
        with pytest.raises(sbx.SamplesMissing, match=re.escape(str(part / "acas" / "fmdh_scan_export.csv"))):
            ensure_demo_launcher_sandbox(db)
        assert called == [] and _counts(db) == before                          # nothing written
        demo_org = db.scalar(select(Organization).join(User, User.org_id == Organization.id).where(User.email == sbx.DEMO_EMAIL))
        if demo_org is not None:                                                # provision + reset: refused before the first write
            status = demo_org.sandbox_status
            with pytest.raises(sbx.SamplesMissing):
                sbx.provision(db, demo_org.id)
            with pytest.raises(sbx.SamplesMissing):
                sbx.reset(db, demo_org, None)
            db.rollback()
            db.refresh(demo_org)
            assert demo_org.sandbox_status == status and _counts(db) == before


def _block(text: str, svc: str) -> str:
    m = re.search(rf"^  {re.escape(svc)}:\n((?:(?:    .*)?\n)+)", text, re.M)
    return m.group(1) if m else ""


def test_every_compose_service_that_provisions_the_demo_sandbox_has_samples_dir_and_a_read_only_mount():
    base = (ROOT / "docker-compose.yml").read_text()
    rec = (ROOT / "deploy/compose/recovery.yml").read_text()
    do = (ROOT / "deploy/digitalocean/docker-compose.do.yml").read_text()
    assert re.search(r"^  SAMPLES_DIR: /samples$", base.split("services:")[0], re.M)           # x-backend-env
    assert re.search(r"^  SAMPLES_DIR: /samples\b", rec.split("services:")[0], re.M)           # x-recovery-env
    need = {"docker-compose.yml": (base, ("migrate", "backend", "worker")),                    # app.seed / API reset / worker jobs
            "recovery.yml": (rec, ("recovery", "rehearsal-backend")),                         # demo_account step / rehearsal reset
            "docker-compose.do.yml": (do, ("migrate", "backend", "worker"))}                  # volumes: !override must re-add it
    for f, (text, svcs) in need.items():
        for svc in svcs:
            assert "- ./samples:/samples:ro" in _block(text, svc), f"{f}: {svc} lacks ./samples:/samples:ro"
    assert "<<: *backend-env" in _block(base, "migrate") and "<<: *recovery-env" in _block(rec, "rehearsal-backend")
    assert "environment: *recovery-env" in _block(rec, "recovery")
    for f in ("docker-compose.yml", "docker-compose.prod.yml", "deploy/compose/recovery.yml", "deploy/digitalocean/docker-compose.do.yml",
              "deploy/digitalocean/docker-compose.staging.yml"):
        for line in (ROOT / f).read_text().splitlines():
            if "samples:/samples" in line and line.strip().startswith("- "):
                assert line.split("#")[0].rstrip().endswith(":ro"), f"{f}: samples mount must be read-only: {line}"
        if f.endswith(("prod.yml", "staging.yml")):                                           # overlays: no volume override dropping it
            t = (ROOT / f).read_text()
            for svc in ("migrate", "backend", "worker"):
                assert "volumes" not in _block(t, svc) or "./samples:/samples:ro" in _block(t, svc)
