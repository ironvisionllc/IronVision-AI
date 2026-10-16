"""Legacy containers (scripts/legacy_project.py) against a docker SHIM: verdicts, preserve-and-stop never removes anything,
refusal when production depends on a legacy container. The legacy Postgres is backed by the REAL local PostgreSQL."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from tests.docker_safety import destructive_calls

ROOT = Path(__file__).resolve().parents[2]
SHIM = Path(__file__).with_name("docker_shim.py")
DIGEST = ROOT / "scripts" / "image_digest.py"


def ctr(name, image, service="", project="aegisrmf", ports=None, nets=None, mounts=None, env=None, running=True):
    return {"inspect": {"Name": "/" + name, "Config": {"Image": image, "Env": env or [], "Labels": {
        "com.docker.compose.project": project, "com.docker.compose.service": service} if project else {}},
        "State": {"Running": running, "Status": "running" if running else "exited"},
        "NetworkSettings": {"Ports": ports or {}, "Networks": nets or {}}, "Mounts": mounts or []}}


def scenario(base_url: str, **over) -> dict:
    s = {"containers": {
        "aegisrmf-postgres-1": ctr("aegisrmf-postgres-1", "postgres:16-alpine", "postgres", ports={"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "5433"}]},
                                   nets={"aegisrmf_default": {"Aliases": ["postgres"], "IPAddress": "172.30.0.2"}},
                                   mounts=[{"Type": "volume", "Name": "aegisrmf_pgdata", "Destination": "/var/lib/postgresql/data"}],
                                   env=["POSTGRES_USER=aegis", "POSTGRES_PASSWORD=never-printed-1"]),
        "aegisrmf-minio-recovery": ctr("aegisrmf-minio-recovery", "minio/minio:RELEASE.2024-01-01", project="",
                                       nets={"bridge": {"Aliases": [], "IPAddress": "172.17.0.3"}},
                                       env=["MINIO_ROOT_USER=legacyminio", "MINIO_ROOT_PASSWORD=legacy-minio-secret-0123456789"],
                                       running=False),  # S3 export: see test_recover_orchestration_e2e
        "ironvision-backend-1": ctr("ironvision-backend-1", "ironvision-backend", "backend", "ironvision", nets={"ironvision_default": {"Aliases": ["backend"], "IPAddress": "172.31.0.5"}}),
        "ironvision-postgres-1": ctr("ironvision-postgres-1", "postgres:16-alpine", "postgres", "ironvision", nets={"ironvision_default": {"Aliases": ["postgres"], "IPAddress": "172.31.0.2"}},
                                     mounts=[{"Type": "bind", "Source": "/srv/ironvision/postgres", "Destination": "/var/lib/postgresql/data"}]),
        "ironvision-edge-1": ctr("ironvision-edge-1", "nginx:1.27-alpine", "edge", "ironvision", ports={"443/tcp": [{"HostIp": "0.0.0.0", "HostPort": "443"}]})},
        "pg": {"container": "aegisrmf-postgres-1", "url": base_url, "dbmap": {"aegisrmf": make_url(base_url).database, "postgres": EMPTY_DB}},
        "s3": {"from": "http://172.17.0.3:9000", "to": "http://127.0.0.1:1"}}
    for k, v in over.items():
        s["containers"][k] = v
    return s


@pytest.fixture
def shim(tmp_path, monkeypatch):
    b = tmp_path / "bin"
    b.mkdir()
    (b / "docker").write_text(f"#!/bin/sh\nexec {sys.executable} {SHIM} \"$@\"\n")
    (b / "docker").chmod(0o755)
    monkeypatch.setenv("PATH", f"{b}:{os.environ['PATH']}")
    monkeypatch.setenv("DOCKER_SHIM_LOG", str(tmp_path / "docker.log"))
    monkeypatch.setenv("DOCKER_SHIM_SCENARIO", str(tmp_path / "scenario.json"))
    monkeypatch.setenv("RECOVER_PREDEPLOY_DIR", str(tmp_path / "predeploy"))
    envf = tmp_path / ".env.production"
    envf.write_text("APP_ENV=production\nDEPLOYMENT_KIND=demo\nDATABASE_URL=postgresql+psycopg://iv:pw@postgres:5432/ironvision\n")

    def run(*args, scen=None):
        (tmp_path / "scenario.json").write_text(json.dumps(scen))
        r = subprocess.run([sys.executable, str(ROOT / "scripts/legacy_project.py"), *args, "--env-file", str(envf)],
                           capture_output=True, text=True, cwd=ROOT, timeout=120, check=False)
        return r, (tmp_path / "docker.log").read_text() if (tmp_path / "docker.log").exists() else ""
    run.envf, run.tmp = envf, tmp_path
    return run


EMPTY_DB = "legacy_maint_empty"


@pytest.fixture
def base_url():
    u = os.environ["DATABASE_URL"]
    eng = create_engine(make_url(u).set(database="postgres"), isolation_level="AUTOCOMMIT")
    with eng.connect() as c:
        if not c.execute(text("select 1 from pg_database where datname = :d"), {"d": EMPTY_DB}).first():
            c.execute(text(f'CREATE DATABASE "{EMPTY_DB}" TEMPLATE template0'))
    eng.dispose()
    return u


def test_inspect_safe_lists_dbs_and_never_prints_secrets(shim, base_url):
    r, log = shim("inspect", "aegisrmf", scen=scenario(base_url))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "VERDICT: SAFE_TO_STOP" in r.stdout and "db aegisrmf:" in r.stdout and "alembic" in r.stdout
    assert "aegisrmf-minio-recovery" in r.stdout and "127.0.0.1:5433->5432/tcp" in r.stdout
    assert "never-printed-1" not in r.stdout and "legacy-minio-secret" not in r.stdout and '"POSTGRES_PASSWORD": "***"' in r.stdout


def test_inspect_port_conflict(shim, base_url):
    s = scenario(base_url)
    s["containers"]["aegisrmf-minio-recovery"]["inspect"]["State"]["Running"] = True
    s["containers"]["aegisrmf-minio-recovery"]["inspect"]["NetworkSettings"]["Ports"] = {"9000/tcp": [{"HostIp": "0.0.0.0", "HostPort": "443"}]}
    r, _ = shim("inspect", scen=s)
    assert r.returncode == 10 and "VERDICT: PORT_CONFLICT" in r.stdout and "!! PORT CONFLICT 0.0.0.0:443" in r.stdout


@pytest.mark.parametrize("how", ["host", "network", "mount"])
def test_inspect_production_depends_on_legacy(shim, base_url, how):
    s = scenario(base_url)
    if how == "host":
        shim.envf.write_text("DATABASE_URL=postgresql+psycopg://iv:pw@aegisrmf-postgres-1:5432/ironvision\n")
    elif how == "network":  # live backend shares the legacy network, where the legacy Postgres answers to "postgres"
        s["containers"]["ironvision-backend-1"]["inspect"]["NetworkSettings"]["Networks"]["aegisrmf_default"] = {"Aliases": [], "IPAddress": "172.30.0.9"}
    else:
        s["containers"]["ironvision-postgres-1"]["inspect"]["Mounts"] = [{"Type": "volume", "Name": "aegisrmf_pgdata", "Destination": "/var/lib/postgresql/data"}]
    r, _ = shim("inspect", scen=s)
    assert r.returncode == 11 and "PRODUCTION_DEPENDS_ON_LEGACY" in r.stdout and "!!" in r.stdout


def test_preserve_and_stop_refuses_when_production_depends(shim, base_url):
    shim.envf.write_text("DATABASE_URL=postgresql+psycopg://iv:pw@aegisrmf-postgres-1:5432/ironvision\n")
    r, log = shim("preserve-and-stop", "aegisrmf", "--yes", scen=scenario(base_url))
    assert r.returncode == 11 and "REFUSED" in r.stdout
    assert "stop " not in log and "pg_dump " not in log


def test_preserve_and_stop_needs_yes(shim, base_url):
    r, log = shim("preserve-and-stop", scen=scenario(base_url))
    assert r.returncode == 2 and "stop " not in log


def test_preserve_and_stop_backs_up_verifies_then_only_stops(shim, base_url):
    s = scenario(base_url)
    out = shim.tmp / "predeploy" / "legacy-x"
    r, log = shim("preserve-and-stop", "aegisrmf", "--yes", "--out", str(out), scen=s)
    assert r.returncode == 0, r.stdout + r.stderr
    m = json.loads((out / "manifest.json").read_text())
    dumps = [f for f in m["files"] if f["kind"] == "pg-dump"]
    assert dumps and dumps[0]["database"] == "aegisrmf" and dumps[0]["toc_entries"] > 10
    assert {f["kind"] for f in m["files"]} >= {"pg-dump", "pg-globals", "docker-inspect"}
    import hashlib
    for f in m["files"]:
        assert hashlib.sha256((out / f["file"]).read_bytes()).hexdigest() == f["sha256"]
    assert "stop aegisrmf-postgres-1" in log and "docker start aegisrmf-postgres-1" in r.stdout
    calls = log.splitlines()
    assert not destructive_calls(calls), log
    assert m["stopped"][0]["restart_command"] == "docker start aegisrmf-postgres-1"


def test_stop_refuses_without_verified_backup(shim, base_url, tmp_path):
    bad = tmp_path / "nobackup"
    bad.mkdir()
    r, log = shim("stop", "--backup", str(bad), "--yes", scen=scenario(base_url))
    assert r.returncode == 2 and "not verified" in r.stdout and "stop aegisrmf" not in log


def test_tampered_backup_blocks_stop(shim, base_url):
    s = scenario(base_url)
    out = shim.tmp / "predeploy" / "legacy-y"
    shim("backup", "--out", str(out), scen=s)
    victim = next(out.glob("*.dump"))
    victim.write_bytes(victim.read_bytes() + b"x")
    r, log = shim("stop", "--backup", str(out), "--yes", scen=s)
    assert r.returncode == 2 and "sha256 mismatch" in r.stdout and "stop aegisrmf" not in log


def test_image_digest_check_logic():
    pinned = "chrislusf/seaweedfs:4.48@sha256:aaa"
    run = lambda *a: subprocess.run([sys.executable, str(DIGEST), "check", *a], capture_output=True, text=True, check=False)  # noqa: E731
    assert run(pinned, "chrislusf/seaweedfs@sha256:aaa").returncode == 0
    assert run("chrislusf/seaweedfs:4.48", "chrislusf/seaweedfs@sha256:aaa").returncode == 3
    import importlib.util
    spec = importlib.util.spec_from_file_location("image_digest", DIGEST)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.matches("sha256:idx", ["sha256:arm", "sha256:amd"], ["x@sha256:arm"]) and not m.matches("sha256:idx", ["sha256:arm"], ["x@sha256:zzz"])
    assert m.split("quay.io/keycloak/keycloak:26.8.1@sha256:abc") == ("quay.io", "keycloak/keycloak", "26.8.1", "sha256:abc")
    assert m.split("postgres:16-alpine") == ("registry-1.docker.io", "library/postgres", "16-alpine", None)


def test_templates_pin_images_by_digest_and_customer_requires_it():
    from app.check_env import validate
    for t in ("env.production.template", "env.customer-production.template", "env.staging.template"):
        txt = (ROOT / "deploy/digitalocean" / t).read_text()
        for k in ("SEAWEEDFS_IMAGE", "POSTGRES_IMAGE", "EDGE_NGINX_IMAGE", "CERTBOT_IMAGE", "KEYCLOAK_BASE_IMAGE"):
            assert f"{k}=" in txt and "@sha256:" in txt.split(f"\n{k}=", 1)[1].split("\n", 1)[0], (t, k)
    base = {"APP_ENV": "production", "SEAWEEDFS_IMAGE": "chrislusf/seaweedfs:4.48"}
    e_demo, w_demo = validate({**base, "DEPLOYMENT_KIND": "demo"})
    e_cust, _ = validate({**base, "DEPLOYMENT_KIND": "customer"})
    assert any("SEAWEEDFS_IMAGE is tag-only" in w for w in w_demo) and not any("SEAWEEDFS_IMAGE" in e for e in e_demo)
    assert any("SEAWEEDFS_IMAGE is tag-only" in e for e in e_cust)


def test_verify_backup_checks_nested_bucket_manifests_and_every_object(tmp_path):
    import hashlib
    import importlib.util
    spec = importlib.util.spec_from_file_location("lp", ROOT / "scripts" / "legacy_project.py")
    lp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lp)
    files = []
    for b in ("evidence", "exports"):  # two buckets: same manifest file name, different dirs
        od = tmp_path / "objects" / b
        (od / "k").mkdir(parents=True)
        (od / "k" / "o.bin").write_bytes(b.encode())
        mf = od / ".objsync-manifest.json"
        mf.write_text(json.dumps({"objects": {"k/o.bin": {"sha256": hashlib.sha256(b.encode()).hexdigest(), "bytes": len(b)}}}))
        files.append({"file": f"objects/{b}/.objsync-manifest.json", "kind": "objsync-manifest",
                      "sha256": hashlib.sha256(mf.read_bytes()).hexdigest()})
    (tmp_path / "manifest.json").write_text(json.dumps({"files": files}))
    assert lp.verify_backup(tmp_path) == []
    (tmp_path / "objects/exports/k/o.bin").write_bytes(b"tampered")
    assert lp.verify_backup(tmp_path) == ["objects/exports/.objsync-manifest.json: object k/o.bin missing or changed"]


@pytest.mark.parametrize("case", ["safe", "conflict", "depends"])
def test_deploy_sh_legacy_gate(shim, base_url, case):
    s = scenario(base_url)
    if case == "conflict":
        s["containers"]["aegisrmf-minio-recovery"]["inspect"]["State"]["Running"] = True
        s["containers"]["aegisrmf-minio-recovery"]["inspect"]["NetworkSettings"]["Ports"] = {"9000/tcp": [{"HostIp": "0.0.0.0", "HostPort": "443"}]}
    if case == "depends":
        shim.envf.write_text("DATABASE_URL=postgresql+psycopg://iv:pw@aegisrmf-postgres-1:5432/ironvision\n")
    (shim.tmp / "scenario.json").write_text(json.dumps(s))
    r = subprocess.run(["bash", str(ROOT / "scripts/deploy.sh"), str(shim.envf)], capture_output=True, text=True, cwd=ROOT,
                       timeout=120, check=False)
    out = r.stdout + r.stderr
    log = (shim.tmp / "docker.log").read_text()
    assert "stop " not in log and not destructive_calls(log.splitlines()), log
    if case == "safe":  # proceeds past the gate (later steps fail on this minimal env file – irrelevant here)
        assert "RETAINED for recovery" in out and "check_env" in out, out[-1500:]
    elif case == "conflict":
        assert r.returncode != 0 and "PORT_CONFLICT" in out and "sudo ./recover.sh resolve-conflict" in out, out[-1500:]
    else:
        assert r.returncode != 0 and "PRODUCTION_DEPENDS_ON_LEGACY" in out and "do NOT stop it" in out, out[-1500:]


def _lp():
    import importlib.util
    spec = importlib.util.spec_from_file_location("lp", ROOT / "scripts" / "legacy_project.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _pg(lp, s):
    raw = s["containers"]["aegisrmf-postgres-1"]["inspect"]
    return lp.info(raw)


def test_backup_empty_maintenance_db_verified_and_globals_recorded(shim, base_url):
    out = shim.tmp / "bk"
    r, log = shim("backup", "--out", str(out), scen=scenario(base_url))
    assert r.returncode == 0, r.stdout + r.stderr
    m = json.loads((out / "manifest.json").read_text())
    d = {f["database"]: f for f in m["files"] if f["kind"] == "pg-dump"}
    assert d["postgres"]["class"] == "maintenance_db" and d["postgres"]["toc_entries"] == 0
    assert d["postgres"]["note"] == "verified, empty maintenance DB, no application data"
    assert d["postgres"]["user_objects"] == {"schemas": 0, "tables": 0, "large_objects": 0, "functions": 0, "extensions": 0}
    assert d["aegisrmf"]["class"] == "application" and d["aegisrmf"]["toc_entries"] > 10
    assert d["aegisrmf"]["dumped_by"].startswith("16") and "PostgreSQL 16" in d["aegisrmf"]["tool"]
    g = next(f for f in m["files"] if f["kind"] == "pg-globals")
    assert g["roles"] >= 1 and g["role_passwords"] is False
    txt = (out / g["file"]).read_text()
    assert "SCRAM-SHA-256$" not in txt and "PASSWORD '" not in txt
    for f in d.values():
        assert (out / f["file"]).read_bytes()[:5] == b"PGDMP"
    pg_calls = [c for c in log.splitlines() if c.startswith("exec") and " aegisrmf-postgres-1 " in f" {c} "]
    assert pg_calls and not any(c.split()[1] in ("-t", "-it", "-ti") for c in pg_calls)  # never a TTY
    for c in pg_calls:
        if " psql " in c or " pg_dump " in c and "--version" not in c or " pg_dumpall " in c:
            assert "PGOPTIONS=-c default_transaction_read_only=on" in c, c  # every legacy session read-only
    assert "Explicitly empty" not in r.stdout and "maintenance_db" in r.stdout


def test_empty_dump_of_db_with_user_objects_is_rejected(shim, base_url, monkeypatch):
    lp = _lp()
    s = scenario(base_url)
    (shim.tmp / "scenario.json").write_text(json.dumps(s))
    i = _pg(lp, s)
    tools = lp.PgTools(i)
    monkeypatch.setattr(lp, "user_objects", lambda i, db: {"schemas": 0, "tables": 3, "large_objects": 0, "functions": 0, "extensions": 0})
    with pytest.raises(RuntimeError, match="no TOC entries but the DB has user objects"):
        lp.dump_db(i, {"name": "postgres"}, tools, shim.tmp / "x.dump")


def test_tty_mangled_dump_is_rejected(shim, base_url):
    lp = _lp()
    s = scenario(base_url)
    (shim.tmp / "scenario.json").write_text(json.dumps(s))
    p = shim.tmp / "tty.dump"
    with open(p, "wb") as f:  # what `docker exec -t … pg_dump -Fc > file` produces
        subprocess.run(["docker", "exec", "-t", "aegisrmf-postgres-1", "pg_dump", "-Fc", "-d", "aegisrmf"], stdout=f, check=True)
    assert b"\r\n" in p.read_bytes()
    with pytest.raises(RuntimeError, match="pg_restore -l failed|TTY"):
        lp.validate_dump(p, lp.PgTools(_pg(lp, s)))


def test_version_mismatch_needs_same_major_tools(shim, base_url):
    s = scenario(base_url)
    s["pg"]["client_version"] = "15.8"
    s["images"] = ["ironvision/recovery:local"]
    r, log = shim("backup", "--out", str(shim.tmp / "bk1"), scen=s)
    assert r.returncode == 1 and "server is PostgreSQL 16 but the container's pg_dump is 15" in r.stdout and "docker pull postgres:16-alpine" in r.stdout
    assert not (shim.tmp / "bk1" / "manifest.json").exists()
    s["images"].append("postgres:16-alpine")
    r, log = shim("backup", "--out", str(shim.tmp / "bk2"), scen=s)
    assert r.returncode == 0, r.stdout + r.stderr
    runs = [c for c in log.splitlines() if c.startswith("run ") and "postgres:16-alpine" in c]
    assert runs and all("--pull never" in c and "-e PGPASSWORD " in c and "never-printed" not in c for c in runs)
    m = json.loads((shim.tmp / "bk2" / "manifest.json").read_text())
    assert all("image postgres:16-alpine" in f["tool"] for f in m["files"] if f["kind"] in ("pg-dump", "pg-globals"))


def test_archive_version_mismatch_is_rejected(shim, base_url):
    lp = _lp()
    s = scenario(base_url)
    (shim.tmp / "scenario.json").write_text(json.dumps(s))
    tools = lp.PgTools(_pg(lp, s))
    p = shim.tmp / "ok.dump"
    with open(p, "wb") as f:
        tools.run("pg_dump", "-Fc", "-d", "aegisrmf", stdout=f)
    assert lp.validate_dump(p, tools)["toc_entries"] > 10
    tools.server = 15  # an archive from a different major than the server must never pass
    with pytest.raises(RuntimeError, match="version mismatch"):
        lp.validate_dump(p, tools)


REPO = "/opt/ironvision/IronVision-AI"


def _app(name, project, svc, mounts, env=(), nets=None):
    c = ctr(name, "img-" + project, svc, project, nets=nets or {f"{project}_default": {"Aliases": [svc], "IPAddress": "10.0.0.9"}}, env=list(env))
    c["inspect"]["Mounts"] = mounts
    c["inspect"]["Config"]["Labels"]["com.docker.compose.project.working_dir"] = REPO
    return c


def test_shared_readonly_repo_binds_are_evidence_not_dependency(shim, base_url):
    s = scenario(base_url)
    docs = [{"Type": "bind", "Source": f"{REPO}/docs", "Destination": "/app/docs", "RW": False},
            {"Type": "bind", "Source": f"{REPO}/samples", "Destination": "/samples", "RW": False}]
    for svc in ("backend", "worker", "migrate"):
        s["containers"][f"aegisrmf-{svc}-1"] = _app(f"aegisrmf-{svc}-1", "aegisrmf", svc, docs)
    s["containers"]["ironvision-backend-1"]["inspect"]["Mounts"] = docs
    r, log = shim("inspect", scen=s)
    assert r.returncode == 0 and "VERDICT: SAFE_TO_STOP" in r.stdout, r.stdout
    assert f"ok (no dep.) [mount] bind {REPO}/docs -> /app/docs (live ironvision-backend-1 -> /app/docs; legacy ro, live ro)" in r.stdout
    assert r.stdout.count("NOT a recovery source") == 3 and "stop " not in log


@pytest.mark.parametrize("how", ["data-volume", "rw-unknown-bind", "env-on-shared-net", "published-port", "storage-endpoint"])
def test_real_dependencies_are_never_downgraded(shim, base_url, how):
    s = scenario(base_url)
    live = s["containers"]["ironvision-backend-1"]["inspect"]
    if how == "data-volume":
        live["Mounts"] = [{"Type": "volume", "Name": "aegisrmf_pgdata", "Destination": "/var/lib/postgresql/data", "RW": True}]
        s["containers"]["ironvision-backend-1"]["inspect"] = live
    elif how == "rw-unknown-bind":
        b = {"Type": "bind", "Source": "/srv/shared/uploads", "Destination": "/uploads", "RW": True}
        s["containers"]["aegisrmf-backend-1"] = _app("aegisrmf-backend-1", "aegisrmf", "backend", [b])
        live["Mounts"] = [b]
    elif how == "env-on-shared-net":  # the live backend is on the legacy network AND its DATABASE_URL names a legacy service
        live["NetworkSettings"]["Networks"]["aegisrmf_default"] = {"Aliases": [], "IPAddress": "172.30.0.9"}
        live["Config"]["Env"] = ["DATABASE_URL=postgresql+psycopg://iv:pw@postgres:5432/ironvision"]
    elif how == "published-port":
        live["Config"]["Env"] = ["DATABASE_URL=postgresql+psycopg://iv:pw@172.17.0.1:5433/ironvision"]
    else:
        s["containers"]["aegisrmf-minio-recovery"]["inspect"]["State"]["Running"] = True
        shim.envf.write_text("DATABASE_URL=postgresql+psycopg://iv:pw@postgres:5432/ironvision\nS3_ENDPOINT_URL=http://172.17.0.3:9000\n")
        s["images"] = []  # keep this case about the verdict (no S3 probe)
    r, _ = shim("inspect", scen=s)
    assert r.returncode == 11 and "VERDICT: PRODUCTION_DEPENDS_ON_LEGACY" in r.stdout and "!! DEPENDENCY" in r.stdout, r.stdout
    assert "pw@" not in r.stdout and "never-printed" not in r.stdout  # env KEY names only


def test_shared_network_without_reference_is_not_a_dependency(shim, base_url):
    s = scenario(base_url)
    live = s["containers"]["ironvision-backend-1"]["inspect"]
    live["NetworkSettings"]["Networks"]["aegisrmf_default"] = {"Aliases": [], "IPAddress": "172.30.0.9"}
    live["Config"]["Env"] = ["DATABASE_URL=postgresql+psycopg://iv:pw@ironvision-db:5432/ironvision"]
    shim.envf.write_text("DATABASE_URL=postgresql+psycopg://iv:pw@ironvision-db:5432/ironvision\n")
    r, _ = shim("inspect", scen=s)
    assert r.returncode == 0 and "ok (no dep.) [network] shares network aegisrmf_default" in r.stdout, r.stdout


def _minio(s, env, running=True):
    m = s["containers"]["aegisrmf-minio-recovery"]["inspect"]
    m["State"]["Running"] = running
    m["Config"]["Env"] = env
    return s


def test_minio_diagnosis_without_credentials(shim, base_url):
    s = _minio(scenario(base_url), ["MINIO_BROWSER=off"])
    r, _ = shim("inspect", scen=s)
    assert "minio endpoint http://172.17.0.3:9000 (network bridge, internal port 9000" in r.stdout
    assert "no usable credentials in the container env (key names found: none)" in r.stdout and "evidence NOT verified" in r.stdout


def test_minio_diagnosis_helper_image_missing(shim, base_url):
    s = _minio(scenario(base_url), ["MINIO_ROOT_USER=legacyminio", "MINIO_ROOT_PASSWORD=legacy-minio-secret-0123456789"])
    s["images"] = []
    r, _ = shim("inspect", scen=s)
    assert "no local helper image with app.tools.objsync" in r.stdout and "legacy-minio-secret" not in r.stdout


def test_minio_unreachable_falls_back_to_mc_listing_and_says_not_verified(shim, base_url):
    s = _minio(scenario(base_url), ["MINIO_ACCESS_KEY_FILE=ak", "MINIO_SECRET_KEY_FILE=/run/secrets/sk"])
    s["containers"]["aegisrmf-minio-recovery"]["inspect"]["Config"]["Cmd"] = ["server", "/data", "--address", ":9100"]
    s["files"] = {"aegisrmf-minio-recovery": {"/run/secrets/ak": "oldkey\n", "/run/secrets/sk": "old-secret-value-0123\n"}}
    s["mc"] = {"aegisrmf-minio-recovery": {"host": "http://oldkey:old-secret-value-0123@127.0.0.1:9100", "buckets": {"evidence": 38}}}
    r, _ = shim("inspect", scen=s)
    assert "minio endpoint http://172.17.0.3:9100" in r.stdout and "credential key names: MINIO_ACCESS_KEY_FILE, MINIO_SECRET_KEY_FILE" in r.stdout
    assert "reachable no" in r.stdout and '"name": "evidence", "objects": 38' in r.stdout and "listed by mc inside the MinIO container" in r.stdout
    assert "evidence NOT verified" in r.stdout and "old-secret-value" not in r.stdout and "oldkey" not in r.stdout
    out = shim.tmp / "bk"
    r, log = shim("backup", "--out", str(out), scen=s)
    m = json.loads((out / "manifest.json").read_text())
    assert r.returncode == 0 and not m["buckets"] and any("objects NOT exported" in w for w in m["warnings"])
    assert "old-secret-value" not in (out / "manifest.json").read_text() and "old-secret-value" not in log


SEAWEED = "http://127.0.0.1:18333"


def _seaweed_up() -> bool:
    import urllib.request
    try:
        urllib.request.urlopen(SEAWEED, timeout=2)
    except Exception as e:  # noqa: BLE001
        return getattr(e, "code", None) is not None
    return True


def test_minio_wrong_credentials_reachable_but_auth_fails(shim, base_url):
    assert _seaweed_up(), "SeaweedFS (S3 stand-in) must run: bash scripts/pod_seaweedfs.sh"
    s = _minio(scenario(base_url), ["MINIO_ROOT_USER=legacyminio", "MINIO_ROOT_PASSWORD=wrong-password-xyz"])
    s["s3"]["to"] = SEAWEED
    r, _ = shim("inspect", scen=s)
    assert "reachable yes, auth no" in r.stdout and "wrong-password" not in r.stdout, r.stdout
