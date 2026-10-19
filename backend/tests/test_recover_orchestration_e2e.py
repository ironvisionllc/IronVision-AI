"""Full operator flow through ./recover.sh (RECOVER_LOCAL=1) with FAKE legacy containers behind a docker shim:
aegisrmf-postgres-1 = REAL local PostgreSQL holding replica DBs aegisrmf + aegisrmf_backup_test; aegisrmf-minio-recovery =
SeaweedFS 4.48 STANDING IN for the legacy MinIO S3 API; REAL Keycloak 26.8.1; live bucket on SeaweedFS.
run → cutover → rollback → run → cutover (failing live check → AUTOMATIC rollback) → run → cutover → finalize.
Run: RECOVERY_E2E=1 KEYCLOAK_LIVE_URL=… pytest -n 0 -s tests/test_recover_orchestration_e2e.py"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.skipif(os.environ.get("RECOVERY_E2E") != "1" or not os.environ.get("KEYCLOAK_LIVE_URL"),
                                reason="RECOVERY_E2E=1 + KEYCLOAK_LIVE_URL (pod replicas, SeaweedFS, real Keycloak) only")
BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
REP = Path("/tmp/recrep")
W = Path("/tmp/recorch")
RUN, PRE = W / "recovery", W / "predeploy"
BASE = os.environ.get("RECOVERY_BASE_DATABASE_URL", "")
LIVE, REH, SCRATCH_KC = 8014, 8015, 8091
ROWS: list[tuple[str, str, str]] = []
ADMIN_S3 = ("recadmin", "rec-admin-secret-0123456789abcdef")


def u(db: str, host: str | None = None) -> str:
    x = make_url(BASE).set(database=db)
    return (x.set(host=host) if host else x).render_as_string(hide_password=False)


def s3(key=ADMIN_S3):
    from app.services.storage.s3 import s3_client
    return s3_client("http://127.0.0.1:18333", "us-east-1", key[0], key[1], "path")


def step(name: str, ok: bool, detail: str = "") -> None:
    ROWS.append((name, "PASS" if ok else "FAIL", detail[-220:]))
    (W / "orchestration-table.json").write_text(json.dumps(ROWS, indent=1))
    assert ok, f"{name}: {detail[-1500:]}"


def sql(db: str, q: str):
    eng = create_engine(u(db))
    with eng.connect() as c:
        r = c.execute(text(q)).fetchall()
    eng.dispose()
    return r


def recreate(db: str, template: str) -> None:
    eng = create_engine(u("postgres"), isolation_level="AUTOCOMMIT")
    with eng.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{db}" TEMPLATE "{template}"'))
    eng.dispose()


def live_env(db_url: str, port: int, **kw) -> dict:
    # explicit, not the pod env: PATH/HOME/LANG + the Keycloak/OIDC settings kcenv.sh exports (stand-in for the env file)
    base = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "JAVA_HOME") or k.startswith(("KEYCLOAK_", "OIDC_", "KC_"))}
    e = {**base, "DATABASE_URL": db_url, "SAMPLES_DIR": str(BACKEND.parent / "samples"), "AUTH_PROVIDERS": "oidc", "ALLOW_DEMO_LOGIN": "true", "DEPLOYMENT_KIND": "demo",
         "KEYCLOAK_ALLOW_REGISTRATION": "true", "DEMO_LOGIN_RATE_LIMIT": "1000/3600", "DEMO_LOGIN_GLOBAL_RATE_LIMIT": "1000/3600",
         "SIGNUP_RATE_LIMIT": "1000/3600", "WORKER_ENABLED": "false", "OIDC_REDIRECT_URI": f"http://127.0.0.1:{LIVE}/api/v1/auth/oidc/callback",
         "FRONTEND_URL": f"http://127.0.0.1:{LIVE}", "OIDC_POST_LOGOUT_REDIRECT_URI": f"http://127.0.0.1:{LIVE}/login",
         "STORAGE_DRIVER": "s3", "S3_ENDPOINT_URL": "http://127.0.0.1:18333", "S3_BUCKET": "evidence-live", "S3_REGION": "us-east-1",
         "S3_ADDRESSING_STYLE": "path", "S3_ACCESS_KEY_ID": "recapp", "S3_SECRET_ACCESS_KEY": "rec-app-secret-0123456789abcdef", "PYTHONPATH": str(BACKEND)}
    e.update(kw)
    return e


def write_scripts() -> None:
    """Pod stand-ins for `./deploy.sh` (migrate + seed + restart backend) and the private rehearsal backend."""
    py = sys.executable
    (W / "redeploy.sh").write_text(f"""#!/bin/bash
set -e
cd {BACKEND}
DB=$(python3 {ROOT}/scripts/envget.py {W}/env.production DATABASE_URL)
pkill -f "uvicorn app.main:app --host 127.0.0.1 --port {LIVE}" || true; sleep 1
export DATABASE_URL="$DB"
{py} -m alembic upgrade head >/dev/null 2>&1
{py} -m app.seed >/dev/null 2>&1 || true
setsid nohup {py} -m uvicorn app.main:app --host 127.0.0.1 --port {LIVE} > {W}/live.log 2>&1 < /dev/null &
for _ in $(seq 1 60); do curl -sf -o /dev/null http://127.0.0.1:{LIVE}/api/v1/health/live && exit 0; sleep 1; done; exit 1
""")
    (W / "rehearsal-backend.sh").write_text(f"""#!/bin/bash
cd {BACKEND}
pkill -f "uvicorn app.main:app --host 127.0.0.1 --port {REH}" || true; sleep 1
# test-only: record every scratch secret (values exist only in this process env / 0600 files) so the test can grep all outputs
printf '%s\\n' "$KC_DB_PASSWORD" "$KC_BOOTSTRAP_ADMIN_PASSWORD" "$SCRATCH_OIDC_CLIENT_SECRET" "$SCRATCH_DEMO_PASSWORD" \\
  "$SCRATCH_DEMO_LAUNCHER_CLIENT_SECRET" "$SCRATCH_BACKEND_CLIENT_SECRET" "$(sed -n 2p "$RECOVERY_DIR/.e2e-credentials" 2>/dev/null)" >> {W}/captured-secrets
DATABASE_URL="$(python3 -c 'import sys;from sqlalchemy.engine import make_url;print(make_url(sys.argv[1]).set(database=sys.argv[2]).render_as_string(hide_password=False))' "$RECOVERY_BASE" "$REHEARSAL_DB")" \\
  S3_BUCKET="$REHEARSAL_BUCKET" S3_ACCESS_KEY_ID={ADMIN_S3[0]} S3_SECRET_ACCESS_KEY={ADMIN_S3[1]} SEED_DEMO_DATA=false \\
  KEYCLOAK_URL="$SCRATCH_KC_URL" OIDC_ISSUER="$SCRATCH_OIDC_ISSUER" OIDC_CLIENT_ID=ironvision-app OIDC_CLIENT_SECRET="$SCRATCH_OIDC_CLIENT_SECRET" \\
  OIDC_REDIRECT_URI="$SCRATCH_APP_URL/api/v1/auth/oidc/callback" OIDC_POST_LOGOUT_REDIRECT_URI="$SCRATCH_APP_URL/login" FRONTEND_URL="$SCRATCH_APP_URL" \\
  KEYCLOAK_DEMO_LAUNCHER_CLIENT_ID=ironvision-demo-launcher KEYCLOAK_DEMO_LAUNCHER_CLIENT_SECRET="$SCRATCH_DEMO_LAUNCHER_CLIENT_SECRET" \\
  KEYCLOAK_DEMO_USERNAME="$SCRATCH_DEMO_USERNAME" KEYCLOAK_DEMO_PASSWORD="$SCRATCH_DEMO_PASSWORD" KEYCLOAK_BACKEND_CLIENT_SECRET="$SCRATCH_BACKEND_CLIENT_SECRET" \\
  KEYCLOAK_CONFIGURATOR_CLIENT_SECRET= ALLOW_DEMO_LOGIN=true DEPLOYMENT_KIND=demo \\
  setsid nohup {py} -m uvicorn app.main:app --host 127.0.0.1 --port {REH} > {W}/rehearsal.log 2>&1 < /dev/null &
for _ in $(seq 1 60); do curl -sf -o /dev/null http://127.0.0.1:{REH}/api/v1/health/live && exit 0; sleep 1; done; exit 1
""")
    (W / "scratch-kc.sh").write_text(f"""#!/bin/bash
# local stand-in for the rehearsal-keycloak compose service: a SECOND Keycloak 26.8.1 process (scratch DB via KC_DB_* env)
case $1 in
start) JAVA_HOME="$(. /opt/kc/kcenv.sh >/dev/null; echo "$JAVA_HOME")"; export JAVA_HOME; cd /opt/kc/keycloak  # ONLY JAVA_HOME: kcenv also exports the production pod Keycloak's KC_DB_*/bootstrap secrets
  setsid nohup bin/kc.sh start-dev --http-port {SCRATCH_KC} --http-management-port 9091 --health-enabled=true > {W}/scratch-kc.log 2>&1 < /dev/null &
  for _ in $(seq 1 150); do curl -sf -o /dev/null http://127.0.0.1:{SCRATCH_KC}/realms/master && exit 0; sleep 2; done; exit 1;;
stop) pkill -f -- "--http-port {SCRATCH_KC}"; for _ in $(seq 1 40); do pgrep -f -- "--http-port {SCRATCH_KC}" >/dev/null || exit 0; sleep 1; done; exit 1;;
esac
""")


@pytest.fixture(scope="module")
def world():
    shutil.rmtree(W, ignore_errors=True)
    for d in (RUN, PRE, W / "bin"):
        d.mkdir(parents=True)
    subprocess.run([sys.executable, str(BACKEND / "tests" / "recovery_replicas.py"), str(REP)], cwd=BACKEND, check=True, timeout=900,
                   env={**os.environ, "DATABASE_URL": BASE, "PYTHONPATH": str(BACKEND)})
    recreate("rec_legacy_aegisrmf", "rec_replica_source")
    recreate("rec_legacy_backup_test", "rec_replica_source")
    recreate("rec_legacy_maint", "template0")  # the legacy server's empty `postgres` maintenance DB
    shutil.copy(REP / "ironvision-production-before-restore.backup", PRE)
    # "legacy MinIO" (SeaweedFS stand-in) bucket evidence: the decoded objects of the archive (incl. the known corrupt one)
    from app.tools.recovery import scan_archive
    leg = s3(("legacyminio", "legacy-minio-secret-0123456789"))
    for cli, b in ((leg, "evidence"), (s3(), "evidence-live")):
        try:
            cli.create_bucket(Bucket=b)
        except Exception:  # noqa: BLE001, S110 - exists
            pass
        for o in cli.list_objects_v2(Bucket=b).get("Contents", []):
            cli.delete_object(Bucket=b, Key=o["Key"])
    idx = scan_archive(REP / "aegisrmf-minio-backup.tar.gz", W / "unpacked")["index"]
    n = 0
    for k, read in idx.items():
        try:
            leg.put_object(Bucket="evidence", Key=k.split("/", 1)[1], Body=read())
            n += 1
        except Exception:  # noqa: BLE001, S112 - unreadable in the archive, so it is missing in "legacy MinIO" too
            continue
    s3().put_object(Bucket="evidence-live", Key="existing/unrelated.txt", Body=b"pre-existing production object")
    # the Droplet's production already runs the demo deployment: seed the prod replica like ./deploy.sh does
    seed_env = live_env(u("rec_live_prod"), LIVE)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=seed_env, check=True, capture_output=True, timeout=300)
    sr = subprocess.run([sys.executable, "-m", "app.seed"], cwd=BACKEND, env=seed_env, capture_output=True, text=True, timeout=300, check=False)
    assert sr.returncode == 0, sr.stderr[-2500:]
    # Keycloak app client redirect → the pod's live backend (restored at the end)
    kc = {**os.environ, "OIDC_REDIRECT_URI": seed_env["OIDC_REDIRECT_URI"], "FRONTEND_URL": seed_env["FRONTEND_URL"],
          "OIDC_POST_LOGOUT_REDIRECT_URI": seed_env["OIDC_POST_LOGOUT_REDIRECT_URI"]}
    subprocess.run([sys.executable, "-m", "app.tools.keycloak_config", "apply", "--yes"], cwd=BACKEND, env=kc, check=True, capture_output=True, timeout=300)
    # the Droplet's production has NO demo@ironvision.ai (rehearsal 2026-10-18): the cutover step demo_account must create it
    eng = create_engine(u("rec_live_prod"))
    with eng.begin() as c:
        c.execute(text("delete from auth_identities where user_id in (select id from users where email = 'demo@ironvision.ai')"))
        c.execute(text("update users set email = 'demo-predeploy@removed.invalid' where email = 'demo@ironvision.ai'"))
    eng.dispose()
    # test realm hygiene: identities left by earlier test runs (incl. test_recovery_e2e's deliberate conflict user) are removed
    tok = httpx.post(f"{os.environ['KEYCLOAK_URL']}/realms/master/protocol/openid-connect/token", data={
        "grant_type": "client_credentials", "client_id": os.environ["KEYCLOAK_CONFIGURATOR_CLIENT_ID"],
        "client_secret": os.environ["KEYCLOAK_CONFIGURATOR_CLIENT_SECRET"]}).json()["access_token"]
    adm = f"{os.environ['KEYCLOAK_URL']}/admin/realms/ironvision-demo/users"
    for ku in httpx.get(adm, params={"max": 1000}, headers={"Authorization": f"Bearer {tok}"}).json():
        if (ku.get("username") or "").endswith("@aegisrmf.demo") or (ku.get("email") or "").endswith("@aegisrmf.demo"):
            httpx.delete(f"{adm}/{ku['id']}", headers={"Authorization": f"Bearer {tok}"})
    pg = make_url(BASE)
    (W / "env.production").write_text(f"APP_ENV=production\nDEPLOYMENT_KIND=demo\nALLOW_DEMO_LOGIN=true\nAUTH_PROVIDERS=oidc\n"
                                      f"KEYCLOAK_DEMO_USERNAME={os.environ.get('KEYCLOAK_DEMO_USERNAME', '')}\n"
                                      f"POSTGRES_USER={pg.username}\nPOSTGRES_PASSWORD={pg.password}\n"
                                      f"DATABASE_URL={u('rec_live_prod')}\n")
    os.chmod(W / "env.production", 0o600)
    repo = "/opt/ironvision/IronVision-AI"

    def ctr(name, image, env, svc="", project="aegisrmf", nets=None, mounts=(), running=True):
        return {"inspect": {"Name": "/" + name, "Config": {"Image": image, "Env": env, "Labels": {
            "com.docker.compose.project": project, "com.docker.compose.service": svc,
            "com.docker.compose.project.working_dir": repo} if project else {}},
            "State": {"Running": running, "Status": "running" if running else "exited"},
            "NetworkSettings": {"Ports": {}, "Networks": nets or {}}, "Mounts": list(mounts)}}
    ro_docs = [{"Type": "bind", "Source": f"{repo}/docs", "Destination": "/app/docs", "RW": False},
               {"Type": "bind", "Source": f"{repo}/content", "Destination": "/content", "RW": False}]
    legacy_net = {"aegisrmf_default": {"Aliases": [], "IPAddress": "172.30.0.5"}}
    (W / "scenario.json").write_text(json.dumps({"containers": {
        "aegisrmf-postgres-1": ctr("aegisrmf-postgres-1", "postgres:16-alpine", ["POSTGRES_USER=aegis"], "postgres",
                                   nets={"aegisrmf_default": {"Aliases": ["postgres"], "IPAddress": "172.30.0.2"}}),
        # Droplet layout: `docker run --network none` (no IP on any network), credentials as *_FILE secrets, mc bundled
        "aegisrmf-minio-recovery": ctr("aegisrmf-minio-recovery", "minio/minio:RELEASE.2024-01-01T00-00-00Z",
                                       ["MINIO_ROOT_USER_FILE=minio_user", "MINIO_ROOT_PASSWORD_FILE=/run/secrets/minio_password"],
                                       project="", nets={}),
        "aegisrmf-backend-1": ctr("aegisrmf-backend-1", "aegisrmf-backend", ["DATABASE_URL=postgresql://aegis:x@postgres:5432/aegisrmf"],
                                  "backend", nets=legacy_net, mounts=ro_docs),
        "aegisrmf-worker-1": ctr("aegisrmf-worker-1", "aegisrmf-backend", [], "worker", nets=legacy_net, mounts=ro_docs),
        "aegisrmf-migrate-1": ctr("aegisrmf-migrate-1", "aegisrmf-backend", [], "migrate", nets=legacy_net, mounts=ro_docs, running=False),
        "ironvision-backend-1": ctr("ironvision-backend-1", "ironvision-backend", ["DATABASE_URL=postgresql+psycopg://iv:x@postgres:5432/ironvision",
                                    "S3_ENDPOINT_URL=http://seaweedfs:8333"], "backend", project="ironvision",
                                    nets={"ironvision_default": {"Aliases": ["backend"], "IPAddress": "172.31.0.5"}}, mounts=ro_docs)},
        "files": {"aegisrmf-minio-recovery": {"/run/secrets/minio_user": "legacyminio\n",
                                              "/run/secrets/minio_password": "legacy-minio-secret-0123456789\n"}},
        "pg": {"container": "aegisrmf-postgres-1", "url": BASE,
               "dbmap": {"aegisrmf": "rec_legacy_aegisrmf", "aegisrmf_backup_test": "rec_legacy_backup_test", "postgres": "rec_legacy_maint"}},
        "mc": {"aegisrmf-minio-recovery": {"host": "http://legacyminio:legacy-minio-secret-0123456789@127.0.0.1:9000",
                                           "s3": {"endpoint": "http://127.0.0.1:18333", "key": "legacyminio",
                                                  "secret": "legacy-minio-secret-0123456789", "buckets": ["evidence"]}}},
        "s3": {"from": "http://172.17.0.3:9000", "to": "http://127.0.0.1:18333"}}))
    sc = json.loads((W / "scenario.json").read_text())
    sc["containers"]["aegisrmf-minio-recovery"]["inspect"]["HostConfig"] = {"NetworkMode": "none"}
    (W / "scenario.json").write_text(json.dumps(sc))
    (W / "bin" / "docker").write_text(f"#!/bin/sh\nexec {sys.executable} {BACKEND / 'tests' / 'docker_shim.py'} \"$@\"\n")
    (W / "bin" / "docker").chmod(0o755)
    write_scripts()
    yield {"legacy_objects": n}
    for p in (LIVE, REH):
        subprocess.run(["pkill", "-f", f"uvicorn app.main:app --host 127.0.0.1 --port {p}"], check=False)
    subprocess.run([sys.executable, "-m", "app.tools.keycloak_config", "apply", "--yes"], cwd=BACKEND, check=False, capture_output=True, timeout=300)


def recover_env(**kw) -> dict:
    # scrubbed (env -i equivalent): recover.sh must not pass thanks to pod env (DATABASE_URL, secrets, …) – everything is explicit
    e = {"HOME": os.environ.get("HOME", "/root"), "LANG": "C.UTF-8", "RECOVER_LOCAL": "1", "SAMPLES_DIR": str(BACKEND.parent / "samples"), "RECOVERY_DIR": str(RUN), "RECOVER_PREDEPLOY_DIR": str(PRE),
         "RECOVER_ENV_FILE": str(W / "env.production"), "DOCKER_SHIM_SCENARIO": str(W / "scenario.json"), "DOCKER_SHIM_LOG": str(W / "docker.log"),
         "RECOVER_DB_HOST": make_url(BASE).host, "RECOVER_DB_PORT": str(make_url(BASE).port or 5432), "RECOVERY_BASE": BASE,
         "RECOVER_ADMIN_DATABASE_URL": u("postgres"), "RECOVER_PROD_ROLLBACK_BACKUP": str(PRE / "ironvision-production-before-restore.backup"),
         "RECOVER_DEFAULT_SOURCE_BACKUP": str(REP / "aegisrmf-old-db.backup"), "RECOVER_DEFAULT_OBJECT_ARCHIVE": str(REP / "aegisrmf-minio-backup.tar.gz"),
         "RECOVER_SOURCE_INSPECT_URL": u("rec_legacy_aegisrmf"), "RECOVER_REDEPLOY_CMD": f"bash {W}/redeploy.sh",
         "RECOVER_LOCAL_REHEARSAL_BACKEND_CMD": f"bash {W}/rehearsal-backend.sh", "RECOVER_REHEARSAL_URL": f"http://127.0.0.1:{REH}",
         "RECOVER_LIVE_URL": f"http://127.0.0.1:{LIVE}", "RECOVER_HEALTH_URL": f"http://127.0.0.1:{LIVE}", "RECOVER_E2E_INSECURE": "1", "RECOVER_LOCAL_RESTART_CMD": f"bash {ROOT}/scripts/pod_seaweedfs.sh",
         "RECOVER_KEYCLOAK_DATABASE_URL": f"postgresql+psycopg://keycloak_test:{os.environ['KC_DB_PASSWORD']}@127.0.0.1:5432/keycloak_test",
         "RECOVER_S3_ADMIN_ACCESS_KEY_ID": ADMIN_S3[0], "RECOVER_S3_ADMIN_SECRET_ACCESS_KEY": ADMIN_S3[1],
         "RECOVER_SCRATCH_KC_URL": f"http://127.0.0.1:{SCRATCH_KC}", "RECOVER_LOCAL_SCRATCH_KC_START": f"bash {W}/scratch-kc.sh start",
         "RECOVER_LOCAL_SCRATCH_KC_STOP": f"bash {W}/scratch-kc.sh stop", "RECOVER_FORBIDDEN_HOSTS": f"{PROD_KC},127.0.0.1:{LIVE}",
         **live_env(u("rec_live_prod"), LIVE)}
    e.pop("DATABASE_URL", None)  # recover.sh follows the env file
    venv = os.environ.get("RECOVERY_VENV")  # the clean recovery-image venv (requirements.recovery.txt only)
    e["PATH"] = f"{W / 'bin'}:" + (f"{venv}/bin:" if venv else "") + os.environ["PATH"]  # docker shim first
    if venv:
        e["RECOVER_SHIM_PYTHON"] = f"{venv}/bin/python"
    e.update(kw)
    return e


def recover(*args, **kw) -> subprocess.CompletedProcess:
    e = recover_env(**kw)
    r = subprocess.run([str(ROOT / "recover.sh"), *args], env=e, cwd=ROOT, capture_output=True, text=True, timeout=1500, check=False)
    (W / f"out-{len(ROWS):02d}-{args[0]}.log").write_text(r.stdout + r.stderr)
    return r


def snapshot() -> dict:
    t = ("users", "organizations", "systems", "evidence", "findings", "audit_events", "auth_identities")
    return {"db": {x: sql("rec_live_prod", f"select count(*) from {x}")[0][0] for x in t},
            "rev": sql("rec_live_prod", "select version_num from alembic_version")[0][0],
            "bucket": sorted(o["Key"] for o in s3().list_objects_v2(Bucket="evidence-live").get("Contents", []))}


def kc_users() -> list:
    """Fingerprint of every user in the PRODUCTION stand-in Keycloak (id, username, email, enabled, names) – must not change."""
    us = httpx.get(f"{os.environ['KEYCLOAK_URL']}/admin/realms/ironvision-demo/users", headers=kc_admin(), params={"max": 1000}).json()
    return sorted((x["id"], x["username"], x.get("email"), x.get("enabled"), x.get("firstName"), x.get("lastName")) for x in us)


def kc_admin() -> dict:
    tok = httpx.post(f"{os.environ['KEYCLOAK_URL']}/realms/master/protocol/openid-connect/token", data={
        "grant_type": "client_credentials", "client_id": os.environ["KEYCLOAK_CONFIGURATOR_CLIENT_ID"],
        "client_secret": os.environ["KEYCLOAK_CONFIGURATOR_CLIENT_SECRET"]}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


PROD_KC = urlparse(os.environ.get("KEYCLOAK_URL", "http://localhost:8090")).netloc


def db_name() -> str:
    from_env = subprocess.run(["python3", str(ROOT / "scripts/envget.py"), str(W / "env.production"), "DATABASE_URL"], capture_output=True, text=True, check=True).stdout
    return make_url(from_env).database


def run_and_hash(label: str) -> str:
    before, kcb, log0 = snapshot(), kc_users(), (W / "docker.log").read_text() if (W / "docker.log").exists() else ""
    r = recover("run")
    subprocess.run(["pkill", "-f", f"uvicorn app.main:app --host 127.0.0.1 --port {REH}"], check=False)
    step(f"{label}: run (inspect + backups + preflight + rehearsal + SSO probe)", r.returncode == 0 and "PLAN-HASH" in r.stdout, r.stdout + r.stderr)
    after = snapshot()
    step(f"{label}: run is read-only vs production DB / bucket / Keycloak users", before == after and kc_users() == kcb, json.dumps([before, after]))
    newlog = ((W / "docker.log").read_text())[len(log0):]
    step(f"{label}: legacy containers left running by run", "\nstop " not in "\n" + newlog, newlog[-300:])
    h = [ln for ln in r.stdout.splitlines() if "PLAN-HASH" in ln][-1].split()[-1]
    ACK[h] = re.findall(r"--accept-evidence-exceptions (\w+)", r.stdout)[-1:]
    return h


ACK: dict[str, list[str]] = {}


def env_sha() -> str:
    import hashlib
    return hashlib.sha256((W / "env.production").read_bytes()).hexdigest()


def cutover(h: str, **kw) -> subprocess.CompletedProcess:
    """The operator's cutover incl. the documented evidence-exception acknowledgement `run` printed."""
    return recover("cutover", "--plan-hash", h, *(["--accept-evidence-exceptions", ACK[h][0]] if ACK.get(h) else []), **kw)


def test_recover_operator_flow(world):
    h = run_and_hash("1")
    src = (RUN / "sources.env").read_text()
    step("sources: running legacy aegisrmf-postgres-1/aegisrmf preferred (matches stated facts)",
         "RECOVER_SOURCE_ORIGIN=running legacy aegisrmf-postgres-1/aegisrmf" in src and "matches the stated facts" in src, src)
    step("sources: running legacy MinIO export used for objects", "RECOVER_OBJECT_DIR=" in src and "aegisrmf-minio-recovery bucket evidence" in src, src)
    lb = next(PRE.glob("legacy-*"))
    m = json.loads((lb / "manifest.json").read_text())
    ev = next(b for b in m["buckets"] if b["bucket"] == "evidence")
    step("legacy backups: 3 DB dumps (header + pg_restore -l + same-major version verified) + MinIO export with SHA-256 manifest",
         len(m["databases"]) == 3 and ev["objects"] == world["legacy_objects"], json.dumps(m["databases"]) + json.dumps(m["buckets"]))
    pgd = {f["database"]: f for f in m["files"] if f["kind"] == "pg-dump"}
    rh = json.loads(sorted(RUN.glob("rehearsal-*.json"))[-1].read_text())
    osum = ((rh.get("result") or {}).get("objects") or {}).get("summary") or {}
    step("evidence accounting: legacy objects SHA-256-matched; production-only evidence = present_in_production (read-only check), not 'missing'",
         osum.get("recovered", 0) >= 36 and osum.get("present_in_production", 0) >= 1 and osum.get("missing", 0) <= 1, json.dumps(osum))
    step("failure case 1: empty `postgres` maintenance DB = verified maintenance_db (0 TOC entries, no user objects), dump kept",
         pgd["postgres"]["class"] == "maintenance_db" and pgd["postgres"]["toc_entries"] == 0 and "no application data" in pgd["postgres"]["note"]
         and pgd["aegisrmf"]["class"] == "application" and pgd["aegisrmf"]["toc_entries"] > 10, json.dumps(pgd["postgres"]))
    gl = [f for f in m["files"] if f["kind"] == "pg-globals"]
    step("globals: pg_dumpall --globals-only verified (roles, no passwords) and recorded", gl and gl[0]["roles"] >= 1 and gl[0]["role_passwords"] is False,
         json.dumps(gl))
    out = (RUN / "out-00-run.log").read_text() if (RUN / "out-00-run.log").exists() else ""
    insp = subprocess.run([sys.executable, str(ROOT / "scripts/legacy_project.py"), "inspect", "aegisrmf", "--env-file", str(W / "env.production")],
                          env=recover_env(), capture_output=True, text=True, cwd=ROOT, timeout=300, check=False)
    step("failure case 2: legacy backend/worker/migrate sharing read-only repo bind mounts = no dependency (evidence listed), roles reported",
         insp.returncode == 0 and "VERDICT: SAFE_TO_STOP" in insp.stdout and "ok (no dep.) [mount] bind /opt/ironvision/IronVision-AI/docs" in insp.stdout
         and "NOT a recovery source" in insp.stdout, insp.stdout[-2500:] + out[-200:])
    mi = m["minio"][0]
    step("failure case 3: MinIO with NO network (--network none) + *_FILE secrets: diagnosed, exported via docker exec -i mc cat with SHA-256 manifest",
         mi["endpoint"] == "" and mi["network_mode"] == "none" and mi.get("listed_by") and ev.get("method") == "mc cat (docker exec -i)"
         and mi["credential_keys"] == ["MINIO_ROOT_PASSWORD_FILE", "MINIO_ROOT_USER_FILE"]
         and "legacy-minio-secret" not in json.dumps(m) + insp.stdout, json.dumps(mi)[:1500])
    rh = json.loads(max(RUN.glob("rehearsal-*.json")).read_text())
    da = (rh.get("result") or {}).get("demo_account") or {}
    plans = [json.loads(p.read_text()) for p in RUN.glob("plan-*.json")]
    runlog = (W / "out-00-run.log").read_text() if (W / "out-00-run.log").exists() else ""
    i_demo, i_sso = runlog.find("[demo_account] OK"), runlog.find("[scratch-sso]")
    step("order: py rehearse (build_target → evidence → demo_account) BEFORE sso_up/scratch link; decision from the production env file "
         "with the Droplet tool env (x-recovery-env only)",
         0 <= i_demo < i_sso and str(W / "env.production") in (da.get("decision_inputs") or {}).get("source", ""),
         f"demo@{i_demo} sso@{i_sso} " + json.dumps(da.get("decision_inputs"))[:300])
    step("rehearsal ran the cutover step demo_account on the scratch copy: production has no demo@ironvision.ai → created by "
         "app.seed.ensure_demo_launcher_sandbox; restored users/orgs unchanged; step is part of the plan (hash)",
         da.get("ran") is True and da.get("ok") is True and (da.get("result") or {}).get("created") is True
         and da.get("restored_users_and_orgs_unchanged") is True and bool(plans) and all(p.get("demo_account", {}).get("required") for p in plans),
         json.dumps(da)[:600] + f" plans={len(plans)}")
    step("rehearsal passed; source counts cross-checked against the stated facts", rh["passed"] and all(x["ok"] for x in rh["source_facts"].values()),
         json.dumps(rh.get("source_facts")))
    e2e = rh.get("backend_probe", {}).get("e2e_sso", {})
    names = {s["step"] for s in e2e.get("steps", []) if s["pass"]}
    need = {"login: Keycloak accepted credentials → callback", "callback → one-time code exchange", "authenticated access: /auth/me",
            "authorization denial: /api/v1/admin/identity-mappings → 403", "logout: app token rejected",
            "demo login (Explore Demo, Option B launcher)", "role switch → ISSM", "rehearsal: production backend never contacted"}
    need = {"login: Keycloak accepted credentials → callback (auth code + PKCE)", "callback → one-time code exchange", "authenticated access: /auth/me",
            "authorization denial: /api/v1/admin/identity-mappings → 403", "session handling: same session valid on a later request",
            "logout: old app session rejected afterwards", "logout: Keycloak session ended (same browser must log in again, no silent SSO)",
            "negative: wrong password rejected by Keycloak (expected rejection, NOT a login)",
            "demo login (Explore Demo, Option B launcher)", "role switch → ISSM", "production Keycloak + backend never contacted"}
    step("rehearsal SSO e2e against the ISOLATED scratch Keycloak: every step passed for real (nothing skipped, no existing account)",
         e2e.get("rc") == 0 and need <= names and all(s["pass"] for s in e2e["steps"]) and rh["probe_passed"] and rh["tool_version"]
         and sum("accepted credentials" in s["step"] for s in e2e["steps"]) == 1, json.dumps(e2e)[:1500])
    ss = rh.get("scratch_sso") or {}
    step("scratch SSO: same keycloak_config code, ephemeral rehearsal-e2e-* user + scratch demo launcher, issuer = scratch Keycloak",
         ss.get("keycloak_config", {}).get("rc") == 0 and ss["kc_users"]["e2e"]["username"].startswith("rehearsal-e2e-")
         and ss.get("issuer", "").startswith(f"http://127.0.0.1:{SCRATCH_KC}/") and PROD_KC not in json.dumps(ss), json.dumps(ss)[:800])
    step("scratch SSO cleanup recorded and complete (users → container → KC DB + role → app records → secrets LAST); restored users untouched",
         ss.get("cleanup_ok") and ss["restored_before"]["sha256"] == ss["restored_after"]["sha256"] and ss["restored_before"]["users"] >= 9
         and all(v["status"] in ("done", "already-gone") for v in ss["cleanup_steps"].values())
         and list(ss["cleanup_steps"])[-1].startswith("6 ") and ss["demo_launcher_link"]["rc"] == 0
         and not list(RUN.glob("scratch-sso-*/")) and sql("postgres", f"select count(*) from pg_roles where rolname = 'rec_kc_{rh['ts']}'")[0][0] == 0
         and sql("postgres", f"select count(*) from pg_database where datname = 'rec_kc_{rh['ts']}'")[0][0] == 0
         and subprocess.run(["pgrep", "-f", "--", f"--http-port {SCRATCH_KC}"], capture_output=True).returncode == 1, json.dumps(ss.get("cleanup_steps")))
    secrets_ = [s for s in (W / "captured-secrets").read_text().splitlines() if len(s) >= 12]
    blobs = {str(p): p.read_bytes() for p in [*RUN.rglob("*"), *W.glob("*.log")] if p.is_file()}
    leaks = [(f, s[:4]) for f, b in blobs.items() for s in secrets_ if s.encode() in b]
    step("no scratch secret / generated password in any report, transcript, json or log", len(secrets_) >= 7 and not leaks, json.dumps(leaks[:5]))
    tr = Path(e2e.get("transcript", "/nonexistent"))
    step("rehearsal e2e transcript + stdout/stderr saved in the report dir, secrets redacted",
         tr.is_file() and Path(e2e["stdout_stderr"]).is_file() and "access_token\": \"ey" not in tr.read_text()
         and not [ln for ln in tr.read_text().splitlines() if PROD_KC in ln and not ln.startswith("STEP ")]
         and not (RUN / ".e2e-credentials").exists(), str(tr))
    ig = rh["result"]["objects"]["integrity"]
    step("evidence integrity: every record mapped + SHA-256-checked; the replica's 2 planted defects are exact exceptions, not silently passed",
         ig["records"] == ig["verified"] + 2 and ig["missing"] == 1 and ig["mismatch"] == 1 and not ig["complete"] and ig["exceptions_hash"]
         and ig["verified_from_source"] >= 36 and ig["verified_in_production"] >= 1 and ACK[h] == [ig["exceptions_hash"]]
         and "## Evidence integrity" in max(RUN.glob("report-*.md")).read_text(),
         json.dumps({k: v for k, v in ig.items() if k != "per_record"})[:800])
    # production DB read-only during run (incl. audit_events from the rehearsal e2e) is asserted by run_and_hash → snapshot()
    prod = db_name()
    r = recover("cutover", "--plan-hash", "0" * 16)
    step("cutover refuses a wrong plan-hash, production unchanged", r.returncode != 0 and db_name() == prod, r.stdout[-300:])
    for extra in ([], ["--accept-evidence-exceptions", "0" * 16]):
        r = recover("cutover", "--plan-hash", h, *extra)
        step(f"cutover refuses incomplete evidence without the exact acknowledgement {extra[1:] or '(none)'}, production unchanged",
             r.returncode != 0 and "INCOMPLETE" in r.stdout + r.stderr and db_name() == prod, (r.stdout + r.stderr)[-500:])
    sha0 = env_sha()   # the pre-cutover env file; every rollback must restore exactly these bytes
    r = cutover(h)
    step("cutover 1: apply → switch → deploy → Keycloak link → verify + live SSO + doctor + SeaweedFS restart",
         r.returncode == 0 and "CUTOVER SUCCEEDED" in r.stdout and db_name().startswith("ironvision_recovered_"), r.stdout + r.stderr)
    rec_db = db_name()
    ap = json.loads(max(RUN.glob("apply-*.json")).read_text())
    da = (ap.get("result") or {}).get("demo_account") or {}
    step("cutover 1: step demo_account created demo@ironvision.ai in the recovered DB before the switch, strict link mapped the production "
         "launcher, Explore Demo check PASS",
         da.get("ok") is True and (da.get("result") or {}).get("created") is True and "[demo-check] PASS" in r.stdout
         and sql(rec_db, "select count(*) from auth_identities ai join users u on u.id = ai.user_id "
                         "where u.email = 'demo@ironvision.ai' and ai.provider = 'oidc'")[0][0] == 1, json.dumps(da)[:500] + r.stdout[-300:])
    n_users = sql(rec_db, "select count(*) from users where email like '%@aegisrmf.demo'")[0][0]
    step("recovered DB: original users present + identities linked", n_users >= 8 and sql(rec_db, "select count(*) from auth_identities")[0][0] >= 8, str(n_users))
    step("live e2e SSO incl. self-registration + launcher + role switch + logout", "PASS  self-registration" in r.stdout and "PASS  role switch" in r.stdout
         and "FAIL  " not in r.stdout, r.stdout[-1500:])
    r = recover("rollback", RECOVER_REDEPLOY_CMD="false")
    step("(d) rollback interrupted at redeploy → fails clearly; env already back to the pre-cutover checksum",
         r.returncode != 0 and "rollback step 'redeploy' failed" in r.stdout and env_sha() == sha0, r.stdout[-600:])
    r = recover("rollback")
    step("(d) re-run converges: env restore SKIPPED (no double-apply), redeploy, health VERIFIED on the previous DB, recovered DB kept",
         r.returncode == 0 and "env-restore: SKIP" in r.stdout and "[health] PASS app on db=" + prod in r.stdout and "ROLLBACK COMPLETE" in r.stdout
         and env_sha() == sha0 and db_name() == prod and sql(rec_db, "select count(*) from users")[0][0] > 0
         and json.loads(max(RUN.glob("rollback-*.json")).read_text())["passed"], r.stdout[-900:])
    r = recover("rollback")
    step("(e) rollback with no un-rolled-back switch → clear no-op, env unchanged",
         r.returncode == 0 and "nothing to roll back" in r.stdout and env_sha() == sha0, r.stdout[-300:])
    _scratch_failure_paths()   # production back on the original DB; run 2 below creates the next passing rehearsal for cutover 2
    h2 = run_and_hash("2")
    r = cutover(h2, ENVSET_FAULT="before-rename")
    step("(a) envset fails mid-write → env intact, AUTOMATIC rollback converges, env checksum = pre-cutover",
         r.returncode != 0 and "envset failed mid-write" in r.stdout and "automatic rollback" in r.stdout and "ROLLBACK COMPLETE" in r.stdout
         and env_sha() == sha0 and db_name() == prod, r.stdout[-900:])
    (W / "redeploy-fail-recovered.sh").write_text(f"""#!/bin/bash
case "$(python3 {ROOT}/scripts/envget.py {W}/env.production DATABASE_URL)" in *ironvision_recovered_*) echo "redeploy FAILED (injected)"; exit 1;; esac
exec bash {W}/redeploy.sh
""")
    r = cutover(h2, RECOVER_REDEPLOY_CMD=f"bash {W}/redeploy-fail-recovered.sh")
    step("(b) redeploy fails after the switch → AUTOMATIC rollback → redeploy on the previous DB → health verified",
         r.returncode != 0 and "redeploy failed after the DATABASE_URL switch" in r.stdout and "ROLLBACK COMPLETE" in r.stdout
         and "[health] PASS app on db=" + prod in r.stdout and env_sha() == sha0 and db_name() == prod, r.stdout[-900:])
    r = cutover(h2, RECOVER_LIVE_URL="http://127.0.0.1:1")
    step("(c) cutover 2 with a failing live check → AUTOMATIC rollback to the previous env/DB, env checksum restored, health verified",
         r.returncode != 0 and "automatic rollback" in r.stdout and "ROLLBACK COMPLETE" in r.stdout and env_sha() == sha0 and db_name() == prod,
         r.stdout[-800:])
    r = cutover(h2, RECOVER_CUTOVER_FAULT="demo-403")
    step("cutover with a forced Explore Demo 403 → Explore Demo check FAILS → AUTOMATIC rollback to the previous env/DB",
         r.returncode != 0 and "[demo-check] FAIL" in r.stdout and "demo-login 403" in r.stdout and "Explore Demo check" in r.stdout
         and "automatic rollback" in r.stdout and "ROLLBACK COMPLETE" in r.stdout and env_sha() == sha0 and db_name() == prod, r.stdout[-900:])
    h3 = run_and_hash("3")
    r = cutover(h3)
    step("cutover 3 (re-cutover after rollback) succeeds", r.returncode == 0 and "CUTOVER SUCCEEDED" in r.stdout, r.stdout[-1500:])
    r = recover("finalize", RECOVER_BOOT_EPOCH=str(int(time.time()) - 10 ** 6))
    step("finalize without a reboot: reminder, legacy stopped gracefully", r.returncode == 0 and "REMINDER" in r.stdout
         and "docker start aegisrmf-backend-1 aegisrmf-minio-recovery aegisrmf-postgres-1 aegisrmf-worker-1" in r.stdout, r.stdout[-600:])
    r = recover("finalize", RECOVER_BOOT_EPOCH=str(int(time.time()) + 10))
    step("finalize after a (simulated) reboot: reboot persistence OK, nothing left to stop", r.returncode == 0 and "OK   reboot persistence" in r.stdout, r.stdout[-400:])
    calls = (W / "docker.log").read_text().splitlines()
    from tests.docker_safety import destructive_calls
    bad = destructive_calls(calls)
    step("docker never asked to rm / down / volume -v / prune / kill (only stop at finalize; run = recovery helper only)",
         not bad and sum(c.startswith("stop ") for c in calls) == 1, f"{len(calls)} calls; destructive={bad[:3]}")


def _scratch_clean(ts: str) -> bool:
    return (not (RUN / f"scratch-sso-{ts}").exists() and not (RUN / ".e2e-credentials").exists()
            and sql("postgres", f"select count(*) from pg_roles where rolname = 'rec_kc_{ts}'")[0][0] == 0
            and sql("postgres", f"select count(*) from pg_database where datname = 'rec_kc_{ts}'")[0][0] == 0
            and subprocess.run(["pgrep", "-f", "--", f"--http-port {SCRATCH_KC}"], capture_output=True, check=False).returncode == 1)


def _scratch_failure_paths() -> None:
    """Real pod Postgres + a real scratch Keycloak 26.8.1 per case. Every failure → cleanup ran, JSON accurate, nothing left."""
    prod_kc = kc_users()
    bk = f"bash {W}/rehearsal-backend.sh"
    cases = {
        "backend fails to start": ({"RECOVER_LOCAL_REHEARSAL_BACKEND_CMD": "false"}, "rehearsal backend"),
        "keycloak-migrate fails (JWT_SECRET removed = Droplet bug 2)": ({"RECOVER_SCRATCH_FAULT": "migrate"}, "setup failed"),
        "login fails (wrong scratch password)": ({"RECOVER_SCRATCH_FAULT": "login"}, "login"),
        "admin.env deleted mid-run (Droplet bug 3)": ({"RECOVER_LOCAL_REHEARSAL_BACKEND_CMD": f"rm -f {RUN}/scratch-sso-*/admin.env; {bk}"}, None),
    }
    for name, (env, why) in cases.items():
        before = {p.name for p in RUN.glob("rehearsal-*.json")}
        r = recover("rehearse", "--e2e", **env)
        new = sorted({p.name for p in RUN.glob("rehearsal-*.json")} - before)
        rh = json.loads((RUN / new[-1]).read_text()) if new else {}
        ss = rh.get("scratch_sso") or {}
        st = {k: v["status"] for k, v in (ss.get("cleanup_steps") or {}).items()}
        fails = " | ".join(rh.get("failures", []))
        if why:
            ok = rh.get("passed") is False and why.lower() in fails.lower()
        else:   # users cannot be deleted without admin.env → `moot` because the scratch Keycloak + its DB were removed
            ok = st.get("1 scratch Keycloak users deleted") == "moot" and "admin.env missing" in ss["cleanup_steps"]["1 scratch Keycloak users deleted"]["detail"]
        if "migrate" in name:
            ok = ok and "JWT_SECRET is not set" in (ss.get("demo_launcher_link") or {}).get("output_tail", "") and ss["steps"].get("setup") is not True
        step(f"failure path – {name}: cleanup ran, every step recorded, nothing left, restored users unchanged",
             ok and ss.get("cleanup_ok") is True and len(st) == 6 and list(st)[-1].startswith("6 ") and _scratch_clean(rh["ts"])
             and st.get("5 restored users unchanged (before == after)") in ("done", "already-gone") and kc_users() == prod_kc,
             json.dumps({"st": st, "fails": fails[:500], "rc": r.returncode}) + r.stdout[-600:])
    from app.tools import recovery as rv
    # Droplet: the tool container could not see the sample files → the samples gate must stop the rehearsal BEFORE anything runs
    partial = W / "samples-missing-one"
    shutil.rmtree(partial, ignore_errors=True)
    shutil.copytree(BACKEND.parent / "samples", partial)
    (partial / "stig" / "mpp_mpp-app-01.ckl").unlink()
    before = {p.name for p in RUN.glob("rehearsal-*.json")}
    r = recover("rehearse", "--e2e", SAMPLES_DIR=str(partial))
    step("samples gate: a required sample file missing for the tool → rehearse refused before any DB/Keycloak work, path named",
         r.returncode != 0 and "[samples-check] FAIL" in r.stdout and str(partial / "stig" / "mpp_mpp-app-01.ckl") in r.stdout
         and {p.name for p in RUN.glob("rehearsal-*.json")} == before and kc_users() == prod_kc, r.stdout[-600:])
    # production env file says demo + launcher, but ALLOW_DEMO_LOGIN=false: the demo_account step must FAIL loudly (not "not a demo")
    bad_env = W / "env.production.inconsistent"
    bad_env.write_text((W / "env.production").read_text().replace("ALLOW_DEMO_LOGIN=true", "ALLOW_DEMO_LOGIN=false"))
    os.chmod(bad_env, 0o600)
    demo_cases = (("production env file demo + launcher but step not required (ALLOW_DEMO_LOGIN=false) → demo_account FAILS",
                   {"RECOVER_ENV_FILE": str(bad_env)}),
                  ("demo mapping removed after verification → e2e demo login 403", {"RECOVER_SCRATCH_FAULT": "demo-unmap"}))
    for name, env in demo_cases:
        before = {p.name for p in RUN.glob("rehearsal-*.json")}
        r = recover("rehearse", "--e2e", **env)
        rh = json.loads((RUN / sorted({p.name for p in RUN.glob("rehearsal-*.json")} - before)[-1]).read_text())
        ss = rh.get("scratch_sso") or {}
        bp = rh.get("backend_probe") if isinstance(rh.get("backend_probe"), dict) else {}   # str when the probe did not run
        steps = [s for s in (bp.get("e2e_sso") or {}).get("steps", []) if s["step"].startswith("demo login (Explore Demo")]
        fails = " | ".join(rh.get("failures", []))
        try:
            rv.rehearsal_gate(rh, rh["plan_hash"])
            gate = "ELIGIBLE"
        except rv.RecoveryError as exc:
            gate = str(exc)
        if "RECOVER_ENV_FILE" in env:
            da = (rh.get("result") or {}).get("demo_account") or {}
            ok = da.get("ok") is False and "refusing" in da.get("error", "") and "demo account step failed" in fails and str(bad_env) in json.dumps(da)
        else:
            ok = bool(steps) and not steps[0]["pass"] and "403" in steps[0]["detail"] and "demo login" in fails
        clean = (ss.get("cleanup_ok") is True and ss["cleanup_steps"]["5 restored users unchanged (before == after)"]["status"] == "done") if ss else True
        step(f"demo path – {name}: rehearsal FAILS (listed, plan hash not cutover-eligible); cleanup complete",
             ok and rh["passed"] is False and "did not pass" in gate and clean and _scratch_clean(rh["ts"]) and kc_users() == prod_kc,
             json.dumps({"steps": steps, "fails": fails[:400], "demo": (rh.get("result") or {}).get("demo_account")}, default=str)[:900] + r.stdout[-400:])
    # interrupted run (like Droplet scratch-sso-20261017t214603): scratch DB/role + secret dir left, admin.env never written
    ts = "20261017t214603"
    e = recover_env()
    subprocess.run([sys.executable, "-m", "app.tools.recovery", "scratch-sso", "prepare", "--ts", ts], cwd=BACKEND, env=e, check=True,
                   capture_output=True)
    (RUN / f"scratch-sso-{ts}.json").write_text(json.dumps({**json.loads((RUN / f"scratch-sso-{ts}.json").read_text()),
                                                            "kc_users": {"e2e": {"username": "rehearsal-e2e-interrupted", "id": "x"}}}))
    r = recover("scratch-cleanup")
    st = json.loads((RUN / f"scratch-sso-{ts}.json").read_text())["cleanup_steps"]
    step("recover.sh scratch-cleanup finishes an interrupted scratch run (scratch resources only); 2nd call: nothing left",
         r.returncode == 0 and st["1 scratch Keycloak users deleted"]["status"] == "moot" and _scratch_clean(ts)
         and "no unfinished scratch SSO run" in recover("scratch-cleanup").stdout and kc_users() == prod_kc,
         json.dumps(st) + r.stdout[-800:])
