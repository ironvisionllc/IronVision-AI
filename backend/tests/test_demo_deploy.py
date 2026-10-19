"""./deploy.sh --demo-without-recovery: read-only preflight refusals, legacy containers retained + never touched (docker shim),
port-conflict refusal + rollback, verified backup, launcher-only link guard (twice), idempotent demo seed (twice), smoke test."""
import hashlib
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from sqlalchemy import func, select

from tests.docker_safety import destructive_calls
from tests.test_legacy_project import base_url, scenario, shim  # noqa: F401  (fixtures)

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable


def _env(tmp: Path, db="ironvision", url=True) -> Path:
    t = (ROOT / "deploy/digitalocean/env.production.template").read_text()
    t = (t.replace("OIDC_CLIENT_SECRET=\n", "OIDC_CLIENT_SECRET=Oc7Lm2Vw9Rz4Kp8Td3Nb6Hc1Jf5Yg0Ua9Qe\n")
          .replace("DATA_ROOT=/srv/ironvision", f"DATA_ROOT={tmp}/data"))
    if url:
        t += f"\nDATABASE_URL=postgresql+psycopg://iv:pw@postgres:5432/{db}\n"
    f = tmp / ".env.production"
    f.write_text(t)
    f.chmod(0o600)
    return f


def _switch(rdir: Path, ts: str, prev: str, new: str, bk: Path | None = None, rolled=False):
    rdir.mkdir(parents=True, exist_ok=True)
    name = f"env-switch-{ts}{'.rolled-back' if rolled else ''}.json"
    (rdir / name).write_text(json.dumps({"ts": ts, "env_backup": str(bk or rdir / "nope"), "previous_db": prev, "new_db": new}))


def _pre(env: Path, rdir: Path):
    return subprocess.run([PY, str(ROOT / "scripts/demo_preflight.py"), str(env), "--recovery-dir", str(rdir)],
                          capture_output=True, text=True, timeout=30)


def test_preflight_refuses_unrolled_switch_and_deploy_changes_nothing(tmp_path):
    env = _env(tmp_path)
    rdir = tmp_path / "recovery"
    _switch(rdir, "20261020T000000Z", "ironvision", "rec_target_abc")
    r = _pre(env, rdir)
    assert r.returncode == 20 and "sudo ./recover.sh rollback" in r.stderr and "NOT rolled back" in r.stderr
    before = hashlib.sha256(env.read_bytes()).hexdigest()
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "docker").write_text(f'#!/bin/sh\necho "docker $*" >> {tmp_path}/docker.log\nexit 0\n')
    (bindir / "docker").chmod(0o755)
    e = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "RECOVERY_DIR": str(rdir)}
    d = subprocess.run([str(ROOT / "deploy.sh"), str(env), "--demo-without-recovery"], cwd="/", env=e, capture_output=True, text=True, timeout=60)
    assert d.returncode == 20, d.stdout + d.stderr
    assert "sudo ./recover.sh rollback" in d.stderr
    assert hashlib.sha256(env.read_bytes()).hexdigest() == before          # env untouched, nothing auto-switched
    assert not (tmp_path / "docker.log").exists()                           # no docker call at all
    assert sorted(p.name for p in rdir.iterdir()) == ["env-switch-20261020T000000Z.json"]   # recovery dir untouched


def test_preflight_refuses_recovery_target_database(tmp_path):
    r = _pre(_env(tmp_path, db="rec_target_6294cf78"), tmp_path / "recovery")
    assert r.returncode == 21 and "rec_target_6294cf78" in r.stderr


def test_preflight_env_must_match_pre_cutover_backup(tmp_path):
    rdir = tmp_path / "recovery"
    bk = tmp_path / "env.pre"
    bk.write_text("POSTGRES_DB=ironvision\nDATABASE_URL=postgresql+psycopg://iv:pw@postgres:5432/ironvision_old\n")
    _switch(rdir, "20261020T000000Z", "ironvision_old", "rec_target_x", bk, rolled=True)
    env = _env(tmp_path)
    r = _pre(env, rdir)
    assert r.returncode == 22, r.stdout + r.stderr
    bk.write_text("POSTGRES_DB=ironvision\nDATABASE_URL=postgresql+psycopg://iv:pw@postgres:5432/ironvision\n")
    r = _pre(env, rdir)
    assert r.returncode == 0 and "matches the pre-cutover env backup" in r.stdout
    assert "pw" not in r.stdout.replace("preflight", "")                   # no secret/URL is printed


@pytest.mark.parametrize("case", ["safe", "conflict"])
def test_demo_deploy_retains_legacy_never_destroys_and_rolls_back(shim, base_url, case, tmp_path):  # noqa: F811
    s = scenario(base_url)
    if case == "conflict":
        s["containers"]["aegisrmf-minio-recovery"]["inspect"]["State"]["Running"] = True
        s["containers"]["aegisrmf-minio-recovery"]["inspect"]["NetworkSettings"]["Ports"] = {"9000/tcp": [{"HostIp": "0.0.0.0", "HostPort": "443"}]}
    (shim.tmp / "scenario.json").write_text(json.dumps(s))
    env = _env(tmp_path)
    original = env.read_bytes()
    e = {**os.environ, "RECOVERY_DIR": str(tmp_path / "recovery"), "APPLY_DEMO_PROBE_ISSUER": "http://127.0.0.1:1/realms/x", "READY_TIMEOUT": "5"}
    r = subprocess.run([str(ROOT / "deploy.sh"), str(env), "--demo-without-recovery", "--no-systemd", "--skip-edge-check"],
                       cwd="/", env=e, capture_output=True, text=True, timeout=180)
    out = r.stdout + r.stderr
    lf = shim.tmp / "docker.log"
    log = lf.read_text().splitlines() if lf.exists() else []
    assert log, out[-2500:]                                                 # really ran into the docker part of the deploy
    assert not destructive_calls(log) and not [c for c in log if c.split()[0] in ("stop", "kill", "rm")], log
    assert r.returncode != 0 and "ROLLBACK" in out, out[-2500:]
    assert env.read_bytes() == original                                     # env restored byte-exact from the snapshot
    assert "legacy containers, volumes, /root/ironvision-predeploy" in out
    if case == "safe":
        assert "RETAINED for recovery" in out and "PORT_CONFLICT" not in out, out[-2500:]
        assert "DEPLOYMENT FAILED" in out                                     # shim stops later (no real compose) → rollback ran
    else:
        assert "PORT_CONFLICT" in out, out[-2500:]


def test_backup_verify_detects_tampering(tmp_path):
    out = tmp_path / "ironvision-x"
    out.mkdir()
    u = os.environ["DATABASE_URL"].replace("+psycopg", "")
    subprocess.run(["pg_dump", "--format=custom", "--schema-only", f"--file={out / 'db.dump'}", u], check=True, timeout=120)
    arts = {"db.dump": {"sha256": hashlib.sha256((out / "db.dump").read_bytes()).hexdigest()}}
    (out / "manifest.json").write_text(json.dumps({"artifacts": arts, "alembic_revision": "0013"}))
    v = lambda: subprocess.run([PY, str(ROOT / "scripts/verify_backup.py"), str(out)], capture_output=True, text=True)  # noqa: E731
    r = v()
    assert r.returncode == 0 and "pg_restore TOC" in r.stdout, r.stderr
    with open(out / "db.dump", "ab") as fh:
        fh.write(b"x")
    assert v().returncode == 1


def _guard(tmp_path, rows):
    p = tmp_path / "report.json"
    p.write_text(json.dumps({"plan_hash": "h123", "users": rows}))
    return subprocess.run([PY, str(ROOT / "scripts/demo_link_guard.py"), str(p)], capture_output=True, text=True)


def _row(email, action):
    return {"email": email, "action": action, "reason": "", "keycloak_user_id": None}


def test_link_guard_launcher_only_and_idempotent(tmp_path):
    admin = _row("admin@ironvision.ai", "create")       # no Keycloak identity: never created by this path
    first = _guard(tmp_path, [_row("demo@ironvision.ai", "link"), admin])
    assert first.returncode == 0 and first.stdout.strip() == "apply h123"
    second = _guard(tmp_path, [_row("demo@ironvision.ai", "ok"), admin])       # re-run after apply → nothing to do
    assert second.returncode == 0 and second.stdout.strip() == "skip"
    restored = [_row(f"u{i}@aegisrmf.demo", "link") for i in range(8)]
    r = _guard(tmp_path, [_row("demo@ironvision.ai", "link"), *restored])
    assert r.returncode == 1 and "8 non-launcher user(s)" in r.stderr
    assert _guard(tmp_path, [admin]).returncode == 1                           # demo seed missing → refuse


def test_demo_seed_idempotent_twice():
    from app.db import SessionLocal
    from app.models import Organization, System, User
    from app.seed import ensure_demo_launcher_sandbox

    def state(db):
        return (db.scalar(select(func.count()).select_from(User)), db.scalar(select(func.count()).select_from(Organization)),
                db.scalar(select(func.count()).select_from(System)))
    with SessionLocal() as db:
        a = ensure_demo_launcher_sandbox(db)
        s1 = state(db)
        b = ensure_demo_launcher_sandbox(db)
        assert b["created"] is False and b["org_id"] == a["org_id"] and b["sandbox_status"] == "ready"
        assert state(db) == s1


class _Fake(BaseHTTPRequestHandler):
    reg = True

    def log_message(self, *a):
        pass

    def _send(self, code, body=b"", headers=None):
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/api/v1/health", "/api/v1/ready"):
            return self._send(200, b"{}")
        if p == "/api/v1/auth/provider":
            return self._send(200, json.dumps({"registration_enabled": self.reg, "demo_login_enabled": True, "signup_enabled": False}).encode())
        if p == "/api/v1/auth/oidc/register":
            return self._send(302, headers={"Location": f"http://127.0.0.1:{self.server.server_port}/realms/d/protocol/openid-connect/registrations?x=1"})
        if p.endswith("/registrations"):
            return self._send(200, b"<form id='kc-register-form'>Register</form>")
        self._send(404)

    def do_POST(self):
        if self.path == "/api/v1/auth/demo-login":
            return self._send(200, json.dumps({"access_token": "t", "user": {"acting_role": "isso"}}).encode())
        if self.path == "/api/v1/sandbox/act-as":
            role = json.loads(self.rfile.read(int(self.headers["Content-Length"])))["role"]
            return self._send(200, json.dumps({"access_token": "t2", "user": {"acting_role": role}}).encode())
        self._send(404)


@pytest.mark.parametrize("registration", [True, False])
def test_smoke(registration):
    handler = type("H", (_Fake,), {"reg": registration})
    srv = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        r = subprocess.run([PY, str(ROOT / "scripts/demo_smoke.py"), f"http://127.0.0.1:{srv.server_port}"], capture_output=True, text=True, timeout=60)
    finally:
        srv.shutdown()
    if registration:
        assert r.returncode == 0 and "role switch → ISSM" in r.stdout and "no temporary user was created" in r.stdout, r.stdout
    else:
        assert r.returncode == 1 and "FAIL provider: registration_enabled" in r.stdout, r.stdout


def test_smoke_against_preview_backend_with_registration_off():
    """The pod backend runs dev_password auth (no Keycloak registration) → the smoke test must FAIL, never pass silently."""
    r = subprocess.run([PY, str(ROOT / "scripts/demo_smoke.py"), "http://127.0.0.1:8001"], capture_output=True, text=True, timeout=90)
    if "/api/v1/health – HTTP 200" not in r.stdout:
        pytest.skip("local backend not running")
    assert r.returncode == 1 and "FAIL provider: registration_enabled" in r.stdout, r.stdout
