"""Full operator flow through ./recover.sh (RECOVER_LOCAL=1) with FAKE legacy containers behind a docker shim:
aegisrmf-postgres-1 = REAL local PostgreSQL holding replica DBs aegisrmf + aegisrmf_backup_test; aegisrmf-minio-recovery =
SeaweedFS 4.48 STANDING IN for the legacy MinIO S3 API; REAL Keycloak 26.8.1; live bucket on SeaweedFS.
run → cutover → rollback → run → cutover (failing live check → AUTOMATIC rollback) → run → cutover → finalize.
Run: RECOVERY_E2E=1 KEYCLOAK_LIVE_URL=… pytest -n 0 -s tests/test_recover_orchestration_e2e.py"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

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
LIVE, REH = 8014, 8015
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
    e = {**os.environ, "DATABASE_URL": db_url, "AUTH_PROVIDERS": "oidc", "ALLOW_DEMO_LOGIN": "true", "DEPLOYMENT_KIND": "demo",
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
DATABASE_URL="$(python3 -c 'import sys;from sqlalchemy.engine import make_url;print(make_url(sys.argv[1]).set(database=sys.argv[2]).render_as_string(hide_password=False))' "$RECOVERY_BASE" "$REHEARSAL_DB")" \\
  S3_BUCKET="$REHEARSAL_BUCKET" S3_ACCESS_KEY_ID={ADMIN_S3[0]} S3_SECRET_ACCESS_KEY={ADMIN_S3[1]} \\
  setsid nohup {py} -m uvicorn app.main:app --host 127.0.0.1 --port {REH} > {W}/rehearsal.log 2>&1 < /dev/null &
for _ in $(seq 1 60); do curl -sf -o /dev/null http://127.0.0.1:{REH}/api/v1/health/live && exit 0; sleep 1; done; exit 1
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
    pg = make_url(BASE)
    (W / "env.production").write_text(f"APP_ENV=production\nDEPLOYMENT_KIND=demo\nPOSTGRES_USER={pg.username}\nPOSTGRES_PASSWORD={pg.password}\n"
                                      f"DATABASE_URL={u('rec_live_prod')}\n")
    os.chmod(W / "env.production", 0o600)
    ctr = lambda name, image, env, svc="": {"inspect": {"Name": "/" + name, "Config": {"Image": image, "Env": env, "Labels": {  # noqa: E731
        "com.docker.compose.project": "aegisrmf", "com.docker.compose.service": svc} if svc else {}}, "State": {"Running": True, "Status": "running"},
        "NetworkSettings": {"Ports": {}, "Networks": {"aegisrmf_default": {"Aliases": [svc] if svc else [], "IPAddress": ""}}}, "Mounts": []}}
    (W / "scenario.json").write_text(json.dumps({"containers": {
        "aegisrmf-postgres-1": ctr("aegisrmf-postgres-1", "postgres:16-alpine", ["POSTGRES_USER=aegis"], "postgres"),
        "aegisrmf-minio-recovery": ctr("aegisrmf-minio-recovery", "minio/minio:RELEASE.2024-01-01T00-00-00Z",
                                       ["MINIO_ROOT_USER=legacyminio", "MINIO_ROOT_PASSWORD=legacy-minio-secret-0123456789"])},
        "pg": {"container": "aegisrmf-postgres-1", "url": BASE, "dbmap": {"aegisrmf": "rec_legacy_aegisrmf", "aegisrmf_backup_test": "rec_legacy_backup_test"}},
        "s3": {"from": "http://aegisrmf-minio-recovery:9000", "to": "http://127.0.0.1:18333"}}))
    (W / "bin" / "docker").write_text(f"#!/bin/sh\nexec {sys.executable} {BACKEND / 'tests' / 'docker_shim.py'} \"$@\"\n")
    (W / "bin" / "docker").chmod(0o755)
    write_scripts()
    yield {"legacy_objects": n}
    for p in (LIVE, REH):
        subprocess.run(["pkill", "-f", f"uvicorn app.main:app --host 127.0.0.1 --port {p}"], check=False)
    subprocess.run([sys.executable, "-m", "app.tools.keycloak_config", "apply", "--yes"], cwd=BACKEND, check=False, capture_output=True, timeout=300)


def recover(*args, **kw) -> subprocess.CompletedProcess:
    e = {**os.environ, "PATH": f"{W / 'bin'}:{os.environ['PATH']}", "RECOVER_LOCAL": "1", "RECOVERY_DIR": str(RUN), "RECOVER_PREDEPLOY_DIR": str(PRE),
         "RECOVER_ENV_FILE": str(W / "env.production"), "DOCKER_SHIM_SCENARIO": str(W / "scenario.json"), "DOCKER_SHIM_LOG": str(W / "docker.log"),
         "RECOVER_DB_HOST": make_url(BASE).host, "RECOVER_DB_PORT": str(make_url(BASE).port or 5432), "RECOVERY_BASE": BASE,
         "RECOVER_ADMIN_DATABASE_URL": u("postgres"), "RECOVER_PROD_ROLLBACK_BACKUP": str(PRE / "ironvision-production-before-restore.backup"),
         "RECOVER_DEFAULT_SOURCE_BACKUP": str(REP / "aegisrmf-old-db.backup"), "RECOVER_DEFAULT_OBJECT_ARCHIVE": str(REP / "aegisrmf-minio-backup.tar.gz"),
         "RECOVER_SOURCE_INSPECT_URL": u("rec_legacy_aegisrmf"), "RECOVER_REDEPLOY_CMD": f"bash {W}/redeploy.sh",
         "RECOVER_LOCAL_REHEARSAL_BACKEND_CMD": f"bash {W}/rehearsal-backend.sh", "RECOVER_REHEARSAL_URL": f"http://127.0.0.1:{REH}",
         "RECOVER_LIVE_URL": f"http://127.0.0.1:{LIVE}", "RECOVER_E2E_INSECURE": "1", "RECOVER_LOCAL_RESTART_CMD": f"bash {ROOT}/scripts/pod_seaweedfs.sh",
         "RECOVER_KEYCLOAK_DATABASE_URL": f"postgresql+psycopg://keycloak_test:{os.environ['KC_DB_PASSWORD']}@127.0.0.1:5432/keycloak_test",
         "RECOVER_S3_ADMIN_ACCESS_KEY_ID": ADMIN_S3[0], "RECOVER_S3_ADMIN_SECRET_ACCESS_KEY": ADMIN_S3[1], **live_env(u("rec_live_prod"), LIVE)}
    e.pop("DATABASE_URL")  # recover.sh follows the env file
    e["PATH"] = f"{W / 'bin'}:{os.environ['PATH']}"  # docker shim first
    e.update(kw)
    r = subprocess.run([str(ROOT / "recover.sh"), *args], env=e, cwd=ROOT, capture_output=True, text=True, timeout=1500, check=False)
    (W / f"out-{len(ROWS):02d}-{args[0]}.log").write_text(r.stdout + r.stderr)
    return r


def snapshot() -> dict:
    t = ("users", "organizations", "systems", "evidence", "findings", "audit_events", "auth_identities")
    return {"db": {x: sql("rec_live_prod", f"select count(*) from {x}")[0][0] for x in t},
            "rev": sql("rec_live_prod", "select version_num from alembic_version")[0][0],
            "bucket": sorted(o["Key"] for o in s3().list_objects_v2(Bucket="evidence-live").get("Contents", []))}


def kc_users() -> int:
    tok = httpx.post(f"{os.environ['KEYCLOAK_URL']}/realms/master/protocol/openid-connect/token", data={
        "grant_type": "client_credentials", "client_id": os.environ["KEYCLOAK_CONFIGURATOR_CLIENT_ID"],
        "client_secret": os.environ["KEYCLOAK_CONFIGURATOR_CLIENT_SECRET"]}).json()["access_token"]
    return httpx.get(f"{os.environ['KEYCLOAK_URL']}/admin/realms/ironvision-demo/users/count", headers={"Authorization": f"Bearer {tok}"}).json()


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
    return [ln for ln in r.stdout.splitlines() if "PLAN-HASH" in ln][-1].split()[-1]


def test_recover_operator_flow(world):
    h = run_and_hash("1")
    src = (RUN / "sources.env").read_text()
    step("sources: running legacy aegisrmf-postgres-1/aegisrmf preferred (matches stated facts)",
         "RECOVER_SOURCE_ORIGIN=running legacy aegisrmf-postgres-1/aegisrmf" in src and "matches the stated facts" in src, src)
    step("sources: running legacy MinIO export used for objects", "RECOVER_OBJECT_DIR=" in src and "aegisrmf-minio-recovery bucket evidence" in src, src)
    lb = next(PRE.glob("legacy-*"))
    m = json.loads((lb / "manifest.json").read_text())
    step("legacy backups: 2 DB dumps (pg_restore -l verified) + MinIO export with SHA-256 manifest",
         len(m["databases"]) == 2 and m["buckets"] and m["buckets"][0]["objects"] == world["legacy_objects"], json.dumps(m["buckets"]))
    rh = json.loads(max(RUN.glob("rehearsal-*.json")).read_text())
    step("rehearsal passed; source counts cross-checked against the stated facts", rh["passed"] and all(x["ok"] for x in rh["source_facts"].values()),
         json.dumps(rh.get("source_facts")))
    step("rehearsal SSO probe ran (demo launcher unmapped in prod = reported warning, not a failure)", rh.get("backend_probe", {}).get("e2e_sso", {}).get("rc") == 0,
         json.dumps(rh.get("backend_probe"))[:400])
    prod = db_name()
    r = recover("cutover", "--plan-hash", "0" * 16)
    step("cutover refuses a wrong plan-hash, production unchanged", r.returncode != 0 and db_name() == prod, r.stdout[-300:])
    r = recover("cutover", "--plan-hash", h)
    step("cutover 1: apply → switch → deploy → Keycloak link → verify + live SSO + doctor + SeaweedFS restart",
         r.returncode == 0 and "CUTOVER SUCCEEDED" in r.stdout and db_name().startswith("ironvision_recovered_"), r.stdout + r.stderr)
    rec_db = db_name()
    n_users = sql(rec_db, "select count(*) from users where email like '%@aegisrmf.demo'")[0][0]
    step("recovered DB: original users present + identities linked", n_users >= 8 and sql(rec_db, "select count(*) from auth_identities")[0][0] >= 8, str(n_users))
    step("live e2e SSO incl. self-registration + launcher + role switch + logout", "PASS  self-registration" in r.stdout and "PASS  role switch" in r.stdout
         and "FAIL  " not in r.stdout, r.stdout[-1500:])
    r = recover("rollback")
    step("rollback → original DB, recovered DB kept", r.returncode == 0 and db_name() == prod and sql(rec_db, "select count(*) from users")[0][0] > 0, r.stdout[-400:])
    h2 = run_and_hash("2")
    r = recover("cutover", "--plan-hash", h2, RECOVER_LIVE_URL="http://127.0.0.1:1")
    step("cutover 2 with a failing live check → AUTOMATIC rollback to the previous env/DB",
         r.returncode != 0 and "automatic rollback" in r.stdout and db_name() == prod, r.stdout[-800:])
    h3 = run_and_hash("3")
    r = recover("cutover", "--plan-hash", h3)
    step("cutover 3 (re-cutover after rollback) succeeds", r.returncode == 0 and "CUTOVER SUCCEEDED" in r.stdout, r.stdout[-1500:])
    r = recover("finalize", RECOVER_BOOT_EPOCH=str(int(time.time()) - 10 ** 6))
    step("finalize without a reboot: reminder, legacy stopped gracefully", r.returncode == 0 and "REMINDER" in r.stdout
         and "docker start aegisrmf-minio-recovery aegisrmf-postgres-1" in r.stdout, r.stdout[-600:])
    r = recover("finalize", RECOVER_BOOT_EPOCH=str(int(time.time()) + 10))
    step("finalize after a (simulated) reboot: reboot persistence OK, nothing left to stop", r.returncode == 0 and "OK   reboot persistence" in r.stdout, r.stdout[-400:])
    calls = (W / "docker.log").read_text().splitlines()
    from tests.docker_safety import destructive_calls
    bad = destructive_calls(calls)
    step("docker never asked to rm / down / volume -v / prune / kill (only stop at finalize; run = recovery helper only)",
         not bad and sum(c.startswith("stop ") for c in calls) == 1, f"{len(calls)} calls; destructive={bad[:3]}")
