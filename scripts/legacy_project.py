#!/usr/bin/env python3
"""Legacy compose project next to the ironvision stack (default project aegisrmf). Host-side, stdlib only, never sources env files.
  inspect [PROJECT] [--env-file F] [--json]       read-only: containers, mounts, networks, env (redacted), DBs (size, alembic
                                                  revision, key counts), MinIO buckets + object counts, dependency/port verdicts
  backup  [PROJECT] --out DIR                     pg_dumpall --globals-only --no-role-passwords + pg_dump -Fc of every DB with
                                                  same-major tools (header, pg_restore -l, archive version, sha256 verified),
                                                  read-only objsync export of every MinIO bucket, docker inspect records, sha256 manifest
  stop    [PROJECT] --backup DIR --yes [--only-conflicting]   graceful `docker stop` (never rm / down / -v); refuses on dependency
  preserve-and-stop [PROJECT] --yes [--out DIR]   backup + stop
Exit: 0 SAFE_TO_STOP (or no legacy containers) · 10 PORT_CONFLICT · 11 PRODUCTION_DEPENDS_ON_LEGACY · 1 error · 2 usage/refused."""
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("envfile", ROOT / "backend" / "app" / "envfile.py")
envfile = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(envfile)
SAFE, PORT, DEPENDS = "SAFE_TO_STOP", "PORT_CONFLICT", "PRODUCTION_DEPENDS_ON_LEGACY"
CODES = {SAFE: 0, PORT: 10, DEPENDS: 11}
FACT_TABLES = ("users", "organizations", "systems", "role_assignments", "evidence", "findings", "jobs", "audit_events")
FACTS = dict(zip(FACT_TABLES, (8, 1, 4, 25, 38, 111, 1624, 1772)))
SECRETISH = ("PASSWORD", "SECRET", "TOKEN", "KEY", "ROOT_USER", "ACCESS")
TOOL_IMAGE = os.environ.get("RECOVER_TOOL_IMAGE") or "ironvision/recovery:local"


def docker(*args: str, stdin=None, stdout=None, check: bool = True, env: dict | None = None) -> subprocess.CompletedProcess:
    bad = {"rm", "down", "-v", "--volumes", "prune", "kill", "rmi"} & set(args[:3])
    if bad or (args and args[0] == "volume"):
        raise SystemExit(f"legacy_project: refusing destructive docker call {args[:3]}")
    r = subprocess.run(["docker", *args], stdin=stdin, stdout=stdout or subprocess.PIPE, stderr=subprocess.PIPE, check=False,
                       env={**os.environ, **env} if env else None)
    if check and r.returncode:
        raise RuntimeError(f"docker {' '.join(args[:3])} failed: {r.stderr.decode(errors='replace')[-300:]}")
    return r


def out(*args: str, check: bool = True) -> str:
    r = docker(*args, check=check)
    return r.stdout.decode(errors="replace") if r.returncode == 0 else ""


def names(project: str) -> list[str]:
    s: set[str] = set()
    for f in (f"label=com.docker.compose.project={project}", f"name=^{project}-"):
        s |= set(out("ps", "-a", "--filter", f, "--format", "{{.Names}}").split())
    return sorted(s)


def info(c: dict) -> dict:
    lab = c["Config"].get("Labels") or {}
    env = dict(e.split("=", 1) for e in c["Config"].get("Env") or [] if "=" in e)
    ports = [{"container": cp, "host_ip": b.get("HostIp") or "0.0.0.0", "host_port": str(b.get("HostPort"))}
             for cp, bs in (c["NetworkSettings"].get("Ports") or {}).items() for b in (bs or [])]
    nets = {n: {"aliases": v.get("Aliases") or [], "ip": v.get("IPAddress") or ""} for n, v in (c["NetworkSettings"].get("Networks") or {}).items()}
    mounts = [{"type": m.get("Type"), "name": m.get("Name") or "", "source": m.get("Source") or "", "dest": m.get("Destination"),
               "rw": bool(m.get("RW", True))} for m in c.get("Mounts") or []]
    i = {"name": c["Name"].lstrip("/"), "service": lab.get("com.docker.compose.service", ""), "project": lab.get("com.docker.compose.project", ""),
         "image": c["Config"].get("Image", ""), "running": bool(c["State"].get("Running")), "status": c["State"].get("Status", ""),
         "ports": ports, "networks": nets, "mounts": mounts, "_env": env,
         "env_redacted": {k: ("***" if any(s in k for s in SECRETISH) else v) for k, v in env.items() if not k.startswith(("PATH", "GOSU", "PG_", "LANG"))}}
    img = i["image"].split("/")[-1]
    i["kind"] = "postgres" if img.startswith("postgres") or i["service"] in ("postgres", "db") else "minio" if "minio" in i["image"] or "minio" in i["name"] else "other"
    i["working_dir"] = lab.get("com.docker.compose.project.working_dir", "")
    i["network_mode"] = (c.get("HostConfig") or {}).get("NetworkMode") or ""
    i["_cmd"] = (c["Config"].get("Cmd") or []) + (c.get("Args") or [])
    i["role"] = {"postgres": "recovery source (database, read-only pg_dump)", "minio": "recovery source (objects, read-only S3 export)"}.get(
        i["kind"], "legacy application container – NOT a recovery source; stopped by finalize after verified backups "
                   "(or resolve-conflict if it holds a port); never stopped by run")
    return i


def containers(project: str) -> tuple[list[dict], list[dict]]:
    ns = names(project)
    raw = json.loads(out("inspect", *ns)) if ns else []
    return [info(c) for c in raw], raw


def pg_user(i: dict) -> str:
    return os.environ.get("LEGACY_PG_USER") or i["_env"].get("POSTGRES_USER") or "postgres"


PGRO = "PGOPTIONS=-c default_transaction_read_only=on"  # every legacy session is read-only
MAINTENANCE_DBS = ("postgres",)
USER_OBJECTS_SQL = """select
 (select count(*) from pg_namespace where nspname not in ('pg_catalog','information_schema','public') and nspname not like 'pg\\_toast%' and nspname not like 'pg\\_temp%'),
 (select count(*) from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname not in ('pg_catalog','information_schema')
    and n.nspname not like 'pg\\_toast%' and c.relkind in ('r','p','v','m','S','f')),
 (select count(*) from pg_largeobject_metadata),
 (select count(*) from pg_proc p join pg_namespace n on n.oid = p.pronamespace where n.nspname not in ('pg_catalog','information_schema')),
 (select count(*) from pg_extension where extname <> 'plpgsql')"""


def psql(i: dict, db: str, sql: str) -> str | None:
    r = docker("exec", "-e", PGRO, i["name"], "psql", "-U", pg_user(i), "-d", db, "-Atc", sql, check=False)
    return r.stdout.decode().strip() if r.returncode == 0 else None


def user_objects(i: dict, db: str) -> dict | None:
    v = psql(i, db, USER_OBJECTS_SQL)
    if not v or len(v.split("|")) != 5:
        return None
    return dict(zip(("schemas", "tables", "large_objects", "functions", "extensions"), map(int, v.split("|"))))


def classify(name: str, revision: str | None, objs: dict | None) -> str:
    if revision:
        return "application"
    if objs is None:
        return "unknown"
    if not any(objs.values()):
        return "maintenance_db" if name in MAINTENANCE_DBS else "empty_db"
    return "other_user_data"


def pg_databases(i: dict) -> list[dict]:
    lst = psql(i, "postgres", "select datname from pg_database where not datistemplate order by 1")
    res = []
    for db in (lst or "").split():
        d = {"name": db, "size": int(psql(i, db, "select pg_database_size(current_database())") or 0),
             "revision": psql(i, db, "select version_num from alembic_version")}
        if d["revision"]:
            d["counts"] = {t: int(v) if (v := psql(i, db, f"select count(*) from {t}")) and v.isdigit() else None for t in FACT_TABLES}
        d["user_objects"] = user_objects(i, db)
        d["class"] = classify(db, d["revision"], d["user_objects"])
        res.append(d)
    return res


def major(text: str) -> int | None:
    m = re.search(r"(\d+)(?:\.\d+)?", text or "")
    return int(m.group(1)) if m else None


class PgTools:
    """pg_dump / pg_dumpall / pg_restore of the SAME major version as the legacy server: the container's own client, or a
    local postgres:<major> image (--pull never) on the legacy network. Never a TTY; output goes straight to a file."""

    def __init__(self, i: dict):
        self.i = i
        self.server = int(psql(i, "postgres", "show server_version_num") or 0) // 10000
        if not self.server:
            raise RuntimeError(f"{i['name']}: cannot read server_version_num (psql as {pg_user(i)})")
        r = docker("exec", i["name"], "pg_dump", "--version", check=False)
        self.client = major(r.stdout.decode(errors="replace")) if r.returncode == 0 else None
        self.image = None
        if self.client != self.server:
            img = os.environ.get("LEGACY_PG_TOOL_IMAGE") or f"postgres:{self.server}-alpine"
            if docker("image", "inspect", img, check=False).returncode:
                raise RuntimeError(f"{i['name']}: server is PostgreSQL {self.server} but the container's pg_dump is "
                                   f"{self.client or 'missing'}; same-major tools required. Fix: docker pull {img} (then re-run)")
            self.image = img
            self.net, self.host = next(((n, v["ip"]) for n, v in i["networks"].items() if v["ip"]), (None, None))
        self.label = f"{'container ' + i['name'] if not self.image else 'image ' + self.image} (PostgreSQL {self.server})"

    def run(self, *cmd: str, stdin=None, stdout=None) -> subprocess.CompletedProcess:
        if not self.image:
            return docker("exec", *(["-i"] if stdin else []), "-e", PGRO, self.i["name"], *cmd, stdin=stdin, stdout=stdout, check=False)
        conn = [] if cmd[0] == "pg_restore" else ["-h", self.host]  # password by NAME (-e PGPASSWORD), never on argv
        return docker("run", "--rm", *(["-i"] if stdin else []), "--pull", "never", "--network", self.net,
                      "-e", "PGPASSWORD", "-e", PGRO, self.image, cmd[0], *conn, *cmd[1:], stdin=stdin, stdout=stdout, check=False,
                      env={"PGPASSWORD": self.i["_env"].get("POSTGRES_PASSWORD", "")})


def validate_dump(p: Path, tools: PgTools) -> dict:
    """Header + pg_restore -l exit code + archive versions (same major as the server); TOC entry count."""
    with open(p, "rb") as f:
        head = f.read(64)
    if not head.startswith(b"PGDMP"):
        hint = " (CR/LF bytes: looks like a TTY-mangled stream)" if b"\r\n" in head else ""
        raise RuntimeError(f"{p.name}: not a pg_dump custom-format archive{hint}")
    with open(p, "rb") as f:
        toc = tools.run("pg_restore", "-l", stdin=f)
    txt = toc.stdout.decode(errors="replace")
    if toc.returncode:
        raise RuntimeError(f"{p.name}: pg_restore -l failed (exit {toc.returncode}): {toc.stderr.decode(errors='replace')[-300:]}")
    hdr = {k: (m.group(1).strip() if (m := re.search(rf";\s+{k}:\s*(.+)", txt)) else None)
           for k in ("Dumped from database version", "Dumped by pg_dump version", "TOC Entries", "Format")}
    if hdr["Format"] != "CUSTOM":
        raise RuntimeError(f"{p.name}: archive format {hdr['Format']!r}, expected CUSTOM")
    vf, vb = major(hdr["Dumped from database version"]), major(hdr["Dumped by pg_dump version"])
    if vf is None or vb is None:  # newer pg_restore lists a mangled archive with exit 0 but no readable versions
        with open(p, "rb") as f:
            hint = " (CR/LF bytes: looks like a TTY-mangled stream – dump without `-t`)" if b"\r\n" in f.read(1 << 20) else ""
        raise RuntimeError(f"{p.name}: pg_restore -l failed to read the archive versions{hint}")
    if vf != tools.server or vb != tools.server:
        raise RuntimeError(f"{p.name}: archive dumped from PostgreSQL {vf} by pg_dump {vb}, server is {tools.server} – version mismatch")
    entries = sum(1 for ln in txt.splitlines() if ln.strip() and not ln.startswith(";"))
    return {"toc_entries": entries, "dumped_from": hdr["Dumped from database version"], "dumped_by": hdr["Dumped by pg_dump version"]}


def dump_db(i: dict, d: dict, tools: PgTools, p: Path) -> dict:
    with open(p, "wb") as f:
        r = tools.run("pg_dump", "-U", pg_user(i), "-Fc", "-d", d["name"], stdout=f)
    if r.returncode:
        raise RuntimeError(f"pg_dump {i['name']}/{d['name']} failed (exit {r.returncode}): {r.stderr.decode(errors='replace')[-300:]}")
    v = validate_dump(p, tools)
    if v["toc_entries"] == 0:
        objs = user_objects(i, d["name"])  # re-checked now, not trusted from inspect
        if objs is None or any(objs.values()):
            raise RuntimeError(f"{i['name']}/{d['name']}: dump has no TOC entries but the DB has user objects {objs} – incomplete dump")
        v["class"] = classify(d["name"], None, objs)
        v["note"] = ("verified, empty maintenance DB, no application data" if v["class"] == "maintenance_db"
                     else "verified, empty database, no application data")
        v["user_objects"] = objs
    else:
        v["class"] = d.get("class") or "unknown"
    return v


def dump_globals(i: dict, tools: PgTools, g: Path) -> dict:
    """Roles + tablespaces; role passwords are never written (--no-role-passwords) and the file is never printed."""
    with open(g, "wb") as f:
        r = tools.run("pg_dumpall", "-U", pg_user(i), "--globals-only", "--no-role-passwords", stdout=f)
    txt = g.read_bytes().decode(errors="replace")
    if r.returncode:
        raise RuntimeError(f"pg_dumpall --globals-only on {i['name']} failed (exit {r.returncode}): {r.stderr.decode(errors='replace')[-300:]}")
    roles = txt.count("CREATE ROLE ")
    if "PostgreSQL database cluster dump" not in txt or not roles:
        raise RuntimeError(f"{g.name}: globals dump incomplete ({roles} roles)")
    if re.search(r"PASSWORD '|SCRAM-SHA-256\$|md5[0-9a-f]{32}", txt):
        raise RuntimeError(f"{g.name}: contains password material – refusing to keep it")
    return {"roles": roles}


MINIO_CRED_KEYS = (("MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD"), ("MINIO_ACCESS_KEY", "MINIO_SECRET_KEY"))


def minio_target(i: dict, live: list[dict]) -> dict:
    """Endpoint from docker inspect (container IP on its network + MinIO's internal port, never localhost), credentials from the
    container env or its *_FILE secrets (values never printed), and a local helper image that has app.tools.objsync."""
    e = i["_env"]

    def val(k: str) -> str:
        if e.get(k):
            return e[k]
        f = e.get(f"{k}_FILE")
        if f:
            r = docker("exec", i["name"], "cat", f if f.startswith("/") else f"/run/secrets/{f}", check=False)
            return r.stdout.decode(errors="replace").strip() if r.returncode == 0 else ""
        return ""
    user = pw = ""
    for uk, pk in MINIO_CRED_KEYS:
        user, pw = val(uk), val(pk)
        if user and pw:
            break
    cmd = i["_cmd"]
    addr = cmd[cmd.index("--address") + 1] if "--address" in cmd[:-1] else e.get("MINIO_ADDRESS", "")
    port = addr.rsplit(":", 1)[-1] if addr and addr.rsplit(":", 1)[-1].isdigit() else "9000"
    net, ip = next(((n, v["ip"]) for n, v in i["networks"].items() if v["ip"]), ("", ""))
    if i["network_mode"] == "host":  # host networking: MinIO listens on the Droplet's own loopback
        net, ip = "host", "127.0.0.1"
    data = next((cmd[k + 1] for k, a in enumerate(cmd[:-1]) if a == "server" and cmd[k + 1].startswith("/")), None) \
        or next((m["dest"] for m in i["mounts"] if m["dest"] in ("/data", "/export")), "/data")
    cands = [TOOL_IMAGE] + [c["image"] for c in live if c["service"] in ("backend", "worker")]
    helper = next((im for im in dict.fromkeys(cands) if docker("image", "inspect", im, check=False).returncode == 0), None)
    return {"endpoint": os.environ.get("LEGACY_MINIO_ENDPOINT") or (f"http://{ip}:{port}" if ip else ""), "network": net,
            "internal_port": port, "network_mode": i["network_mode"] or "default", "data_dir": data, "published": [f"{p['host_ip']}:{p['host_port']}->{p['container']}" for p in i["ports"]],
            "credential_keys": sorted(k for k in e if k.startswith("MINIO_") and k.endswith(("_USER", "_PASSWORD", "_ACCESS_KEY", "_SECRET_KEY", "_FILE"))),
            "credentials_found": bool(user and pw), "helper_image": helper, "_user": user, "_pw": pw}


def objsync(t: dict, *args: str, bucket: str = "_", vol: str | None = None) -> subprocess.CompletedProcess:
    """Read-only: the helper container on the legacy network talks to MinIO's S3 API (credentials passed by NAME, not on argv)."""
    env = {"OLD_S3_ENDPOINT_URL": t["endpoint"], "OLD_S3_ACCESS_KEY_ID": t["_user"], "OLD_S3_SECRET_ACCESS_KEY": t["_pw"],
           "OLD_S3_REGION": "us-east-1", "OLD_S3_ADDRESSING_STYLE": "path", "OLD_S3_BUCKET": bucket}
    cmd = ["run", "--rm", "--pull", "never", "--network", t["network"]] + [x for k in env for x in ("-e", k)]
    if vol:
        cmd += ["-v", f"{vol}:/out"]
    return docker(*cmd, t["helper_image"], "python", "-m", "app.tools.objsync", *args, env=env, check=False)


def mc_list(i: dict, t: dict) -> dict | None:
    """Fallback listing with the mc client bundled in the MinIO container (read-only `mc ls`), when present."""
    if not t["credentials_found"] or docker("exec", i["name"], "sh", "-c", "command -v mc", check=False).returncode:
        return None
    q = urllib.parse.quote
    env = {"MC_HOST_legacy": f"http://{q(t['_user'], safe='')}:{q(t['_pw'], safe='')}@127.0.0.1:{t['internal_port']}"}
    r = docker("exec", "-e", "MC_HOST_legacy", i["name"], "mc", "ls", "--json", "legacy", env=env, check=False)
    if r.returncode:
        return {"error": f"mc ls failed: {r.stderr.decode(errors='replace')[-200:]}"}
    bks = []
    for ln in r.stdout.decode(errors="replace").splitlines():
        name = (json.loads(ln).get("key") or "").rstrip("/") if ln.strip().startswith("{") else ""
        if name:
            rr = docker("exec", "-e", "MC_HOST_legacy", i["name"], "mc", "ls", "--recursive", "--json", f"legacy/{name}", env=env, check=False)
            files = [json.loads(x) for x in rr.stdout.decode(errors="replace").splitlines() if x.strip().startswith("{")]
            bks.append({"name": name, "objects": sum(1 for f in files if f.get("type") == "file") if rr.returncode == 0 else None})
    return {"buckets": bks}


def _mc_env(t: dict) -> dict:
    q = urllib.parse.quote
    return {"MC_HOST_legacy": f"http://{q(t['_user'], safe='')}:{q(t['_pw'], safe='')}@127.0.0.1:{t['internal_port']}"}


def _safe_key(k: str) -> bool:
    return bool(k) and not k.startswith("/") and ".." not in k.split("/")


def export_mc(i: dict, t: dict, bucket: str, od: Path) -> int:
    """Stream every current object with the MinIO container's own mc (`docker exec -i`, never -t; stdout straight to a file),
    check its size against the listing and record SHA-256 in an objsync-format manifest."""
    env = _mc_env(t)
    r = docker("exec", "-e", "MC_HOST_legacy", i["name"], "mc", "ls", "--recursive", "--json", f"legacy/{bucket}", env=env, check=False)
    if r.returncode:
        raise RuntimeError(f"mc ls legacy/{bucket} failed: {r.stderr.decode(errors='replace')[-200:]}")
    items = [json.loads(x) for x in r.stdout.decode(errors="replace").splitlines() if x.strip().startswith("{")]
    objs = {}
    for it in (x for x in items if x.get("type") == "file"):
        k = it["key"]
        if not _safe_key(k):
            raise RuntimeError(f"refusing unsafe object key {k!r} in bucket {bucket}")
        f = od / k
        f.parent.mkdir(parents=True, exist_ok=True)
        with open(f, "wb") as fh:
            rr = docker("exec", "-i", "-e", "MC_HOST_legacy", i["name"], "mc", "cat", f"legacy/{bucket}/{k}", stdout=fh, env=env, check=False)
        if rr.returncode or f.stat().st_size != int(it.get("size", -1)):
            raise RuntimeError(f"mc cat legacy/{bucket}/{k}: exit {rr.returncode}, {f.stat().st_size} bytes vs listed {it.get('size')}")
        objs[k] = {"sha256": sha(f), "bytes": f.stat().st_size}
    (od / ".objsync-manifest.json").write_text(json.dumps({"bucket": bucket, "source": "mc cat (docker exec -i)", "objects": objs},
                                                          indent=1, sort_keys=True))
    return len(objs)


def export_cp(i: dict, t: dict, dst: Path) -> Path:
    """Read-only copy of the MinIO data directory (`docker cp <ctr>:<dir> -` writes a tar stream; nothing in the container
    changes). Parsed later by the recovery image's xl-single reader; evidence counts only on SHA-256 match."""
    out = dst / f"{i['name']}-data.tar"
    with open(out, "wb") as fh:
        r = docker("cp", f"{i['name']}:{t['data_dir']}", "-", stdout=fh, check=False)
    import tarfile
    if r.returncode or not tarfile.is_tarfile(out):
        raise RuntimeError(f"docker cp {i['name']}:{t['data_dir']} failed: {r.stderr.decode(errors='replace')[-200:]}")
    with tarfile.open(out) as tf:
        names = tf.getnames()
    if not any(n.endswith("/xl.meta") for n in names):
        raise RuntimeError(f"{out.name}: no xl.meta objects in {t['data_dir']} (not a MinIO data directory?)")
    return out


def minio_probe(i: dict, t: dict) -> dict:
    d = {k: v for k, v in t.items() if not k.startswith("_")}
    d.update(method=None, reachable=None, auth=None, buckets=None, exportable=False, error=None)
    if not t["endpoint"]:
        d["error"] = (f"container has no IP address on any network (network mode {t['network_mode']}) – S3 over the network is "
                      "impossible; objects are exported with `docker exec -i … mc cat` or a read-only `docker cp` of the data dir")
    elif not t["credentials_found"]:
        d["error"] = f"no usable credentials in the container env (key names found: {', '.join(t['credential_keys']) or 'none'})"
    elif not t["helper_image"]:
        d["error"] = f"no local helper image with app.tools.objsync ({TOOL_IMAGE} or the live backend image) – build it: docker compose build backend"
    else:
        r = objsync(t, "probe", "s3:OLD")
        d["method"] = f"objsync helper {t['helper_image']} on network {t['network']} → {t['endpoint']}"
        lines = r.stdout.decode(errors="replace").strip().splitlines()
        try:
            p = json.loads(lines[-1])
        except (ValueError, IndexError):
            p = {"error": f"helper container failed (exit {r.returncode}): {r.stderr.decode(errors='replace')[-200:]}"}
        d.update(reachable=p.get("reachable"), auth=p.get("auth"), buckets=p.get("buckets"), error=p.get("error"))
        d["exportable"] = bool(p.get("auth"))
    if not d["exportable"]:
        mc = mc_list(i, t)
        if mc:
            d["mc_fallback"] = mc
            if mc.get("buckets") is not None:
                d["buckets"], d["listed_by"] = mc["buckets"], "mc inside the MinIO container (export: docker exec -i … mc cat)"
    return d


def env_hosts(env_file: str | None) -> tuple[dict, dict]:
    env = envfile.parse_env_file(env_file) if env_file and Path(env_file).is_file() else {}
    h = lambda u, d: (urllib.parse.urlsplit(u).hostname if u else None) or d  # noqa: E731
    return {"database": h(env.get("DATABASE_URL"), "postgres"), "object storage": h(env.get("S3_ENDPOINT_URL"), "seaweedfs")}, env


def overlap(a: str, b: str) -> bool:
    return a in ("0.0.0.0", "::", "") or b in ("0.0.0.0", "::", "") or a == b


DATA_DESTS = ("/var/lib/postgresql", "/data", "/export", "/minio", "/seaweedfs", "/var/lib/minio")
DATA_SOURCES = ("/srv/ironvision/postgres", "/srv/ironvision/objects", "/srv/ironvision/seaweedfs", "/var/lib/docker/volumes/")
HOST_KEYS = ("_URL", "_HOST", "_ENDPOINT", "_ADDR", "_ADDRESS", "_DSN")
GATEWAYS = ("host.docker.internal", "172.17.0.1", "localhost", "127.0.0.1", "gateway.docker.internal")
SKIP_MOUNTS = ("/etc/", "/var/run", "/run/", "/proc", "/sys", "/dev")


def host_refs(env: dict) -> list[tuple[str, str, str | None]]:
    """(env KEY, hostname, port) for every URL/host-like setting; values themselves are never reported."""
    res = []
    for k, v in env.items():
        if not k.endswith(HOST_KEYS) or not v or k.endswith("_FILE"):
            continue
        u = urllib.parse.urlsplit(v if "://" in v else f"x://{v}")
        try:
            port = str(u.port) if u.port else None
        except ValueError:
            port = None
        if u.hostname:
            res.append((k, u.hostname, port))
    return res


def evidence(i: dict, refs: list, live: list[dict], live_mounts: dict, repo_roots: list[str]) -> list[dict]:
    ev = []

    def add(kind: str, detail: str, dep: bool, why: str):
        ev.append({"container": i["name"], "kind": kind, "detail": detail, "dependency": dep, "why": why})
    ips = {v["ip"] for v in i["networks"].values() if v["ip"]}
    for src, src_nets, k, h, port in refs:
        aliases = {n for n, v in i["networks"].items() if h in v["aliases"] or h in (i["service"], i["name"])}
        if h == i["name"] or h in ips:
            add("env", f"{src}: {k} host is this container ({'IP' if h in ips else 'name'})", True, "a live setting points directly at the legacy container")
        elif aliases & src_nets:
            add("env", f"{src}: {k} host '{h}' on shared network {sorted(aliases & src_nets)[0]}", True,
                "the live container resolves this hostname to the legacy container")
        elif aliases:
            add("env", f"{src}: {k} host '{h}'", False, "same name as a legacy service but no shared network – resolves to the live service")
        elif h in GATEWAYS and port and any(p["host_port"] == port for p in i["ports"]):
            add("env", f"{src}: {k} → host port {port}", True, "a live setting reaches the legacy container through its published port")
    referenced = {e["detail"].split(" on shared network ")[-1] for e in ev if e["dependency"]}
    for n in sorted(set(i["networks"]) & {n for c in live for n in c["networks"]}):
        if n not in referenced:
            add("network", f"shares network {n} with {', '.join(c['name'] for c in live if n in c['networks'])}", False,
                "a shared network alone is not a dependency (no live setting references this container)")
    for m in i["mounts"]:
        key = m["name"] or m["source"]
        if (m["source"] or "").startswith(SKIP_MOUNTS):
            continue
        for lc, lm in live_mounts.get(key, []):
            rw = m["rw"] or lm["rw"]
            d = f"{m['type']} {key} -> {m['dest']} (live {lc} -> {lm['dest']}; legacy {'rw' if m['rw'] else 'ro'}, live {'rw' if lm['rw'] else 'ro'})"
            data = m["type"] == "volume" or any((x or "").startswith(DATA_DESTS) for x in (m["dest"], lm["dest"])) \
                or (m["source"] or "").startswith(DATA_SOURCES)
            repo = any(r and (m["source"] or "").startswith(r.rstrip("/") + "/") for r in repo_roots)
            if data and rw:
                add("mount", d, True, "shared writable data (named volume / database or object data directory)")
            elif data:
                add("mount", d, False, "shared data, read-only on both sides")
            elif repo:
                add("mount", d, False, "shared repository files (docs/samples/content) – stopping the legacy container does not change them")
            elif not rw:
                add("mount", d, False, "shared read-only bind mount")
            else:
                add("mount", d, True, "unclassified shared writable bind mount – treated as a dependency (fail-safe)")
    return ev


def analyse(project: str, env_file: str | None, deep: bool = True) -> dict:
    legacy, raw = containers(project)
    hosts, env = env_hosts(env_file)
    cur_proj = os.environ.get("IRONVISION_PROJECT") or "ironvision"
    current, _ = containers(cur_proj)
    current = [c for c in current if c["project"] == cur_proj]
    app_nets = {n for c in current if c["service"] in ("backend", "worker", "migrate") for n in c["networks"]}
    refs = [(f"env file {Path(env_file).name}" if env_file else "env file", app_nets, k, h, p) for k, h, p in host_refs(env)]
    refs += [(f"defaults ({kind})", app_nets, kind, h, None) for kind, h in hosts.items() if not any(r[3] == h for r in refs)]
    refs += [(c["name"], set(c["networks"]), k, h, p) for c in current for k, h, p in host_refs(c["_env"])]
    live_mounts: dict = {}
    for c in current:
        for m in c["mounts"]:
            live_mounts.setdefault(m["name"] or m["source"], []).append((c["name"], m))
    repo_roots = [str(ROOT), os.environ.get("IRONVISION_REPO", "")] + [c["working_dir"] for c in legacy + current]
    want = {("0.0.0.0", "80"), ("0.0.0.0", "443")} | {(p["host_ip"], p["host_port"]) for c in current for p in c["ports"]}
    for i in legacy:
        i["evidence"] = evidence(i, refs, current, live_mounts, repo_roots)
        i["depends"] = [f"[{e['kind']}] {e['detail']} – {e['why']}" for e in i["evidence"] if e["dependency"]]
        i["conflicts"] = [f"{p['host_ip']}:{p['host_port']}" for p in i["ports"]
                          if i["running"] and any(p["host_port"] == wp and overlap(p["host_ip"], wi) for wi, wp in want)]
        i["verdict"] = DEPENDS if i["depends"] else PORT if i["conflicts"] else SAFE
        if deep and i["running"] and i["kind"] == "postgres":
            i["databases"] = pg_databases(i)
        if deep and i["running"] and i["kind"] == "minio":
            i["_minio"] = minio_target(i, current)
            i["minio"] = minio_probe(i, i["_minio"])
            i["buckets"] = i["minio"]["buckets"]
    verdict = DEPENDS if any(i["verdict"] == DEPENDS for i in legacy) else PORT if any(i["verdict"] == PORT for i in legacy) else SAFE
    return {"project": project, "hosts": hosts, "current_project": cur_proj, "containers": legacy, "verdict": verdict,
            "_raw": {r["Name"].lstrip("/"): r for r in raw}, "none": not legacy}


def yn(v) -> str:
    return "?" if v is None else "yes" if v else "no"


def show(rep: dict) -> None:
    print(f"[legacy] project {rep['project']}: {len(rep['containers'])} container(s); live stack '{rep['current_project']}' uses "
          f"database host '{rep['hosts']['database']}', object storage host '{rep['hosts']['object storage']}'")
    for i in rep["containers"]:
        ports = ", ".join(f"{p['host_ip']}:{p['host_port']}->{p['container']}" for p in i["ports"]) or "none"
        print(f"  {i['name']}  service={i['service'] or '-'} image={i['image']} status={i['status']} ports={ports}  → {i['verdict']}")
        print(f"     role: {i['role']}")
        for m in i["mounts"]:
            print(f"     mount {m['type']} {m['name'] or m['source']} -> {m['dest']} ({'rw' if m['rw'] else 'ro'})")
        print(f"     networks: {', '.join(i['networks']) or '-'}; env: {json.dumps(i['env_redacted'])}")
        for d in i.get("databases") or []:
            print(f"     db {d['name']}: {d['size'] >> 20} MiB, class {d['class']}, alembic {d['revision'] or '-'}"
                  + (f", counts {json.dumps(d['counts'])}" if d.get("counts") else "")
                  + (f", user objects {json.dumps(d['user_objects'])}" if not d.get("counts") else ""))
        if i["kind"] == "minio" and i.get("minio"):
            m = i["minio"]
            print(f"     minio endpoint {m['endpoint'] or '-'} (network {m['network'] or '-'}, internal port {m['internal_port']}, "
                  f"published {', '.join(m['published']) or 'none'}); credential key names: {', '.join(m['credential_keys']) or 'none'}; "
                  f"helper image: {m['helper_image'] or 'none'}")
            print(f"     minio reachable {yn(m['reachable'])}, auth {yn(m['auth'])}, method {m['method'] or '-'}"
                  + (f", error: {m['error']}" if m["error"] else ""))
            print(f"     buckets: {json.dumps(m['buckets']) if m['buckets'] is not None else 'NOT listable'}"
                  + (f" (listed by {m['listed_by']})" if m.get("listed_by") else "")
                  + ("" if m["exportable"] else " – objects cannot be exported/verified from this container; tarball fallback, evidence NOT verified"))
        for e in i["evidence"]:
            print(f"     {'!! DEPENDENCY' if e['dependency'] else 'ok (no dep.)'} [{e['kind']}] {e['detail']} – {e['why']}")
        for c in i["conflicts"]:
            print(f"     !! PORT CONFLICT {c}")
    print(f"VERDICT: {'SAFE_TO_STOP (no legacy containers)' if rep['none'] else rep['verdict']}")


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def backup(rep: dict, dst: Path) -> dict:
    dst.mkdir(parents=True, exist_ok=True, mode=0o700)
    files, man = [], {"project": rep["project"], "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "databases": [], "buckets": []}

    def add(p: Path, **kw):
        os.chmod(p, 0o600)
        files.append({"file": p.relative_to(dst).as_posix(), "size": p.stat().st_size, "sha256": sha(p), **kw})
    for i in rep["containers"]:
        (dst / f"inspect-{i['name']}.json").write_text(json.dumps(rep["_raw"][i["name"]], indent=1))
        add(dst / f"inspect-{i['name']}.json", kind="docker-inspect", container=i["name"])
        if not i["running"]:
            continue
        if i["kind"] == "postgres":
            tools = PgTools(i)
            g = dst / f"{i['name']}-globals.sql"
            gl = dump_globals(i, tools, g)
            add(g, kind="pg-globals", container=i["name"], roles=gl["roles"], role_passwords=False, tool=tools.label)
            print(f"[legacy] {i['name']} globals: {gl['roles']} roles (no passwords), tools {tools.label}")
            for d in i.get("databases") or []:
                p = dst / f"{i['name']}-{d['name']}.dump"
                v = dump_db(i, d, tools, p)
                add(p, kind="pg-dump", container=i["name"], database=d["name"], revision=d["revision"], counts=d.get("counts"), tool=tools.label, **v)
                man["databases"].append({"container": i["name"], "database": d["name"], "file": p.name, "revision": d["revision"],
                                         "counts": d.get("counts"), "class": v["class"]})
                print(f"[legacy] {i['name']}/{d['name']}: {v['class']}, {v['toc_entries']} TOC entries, header + pg_restore -l + "
                      f"version {v['dumped_by']} verified" + (f" – {v['note']}" if v.get("note") else ""))
        if i["kind"] == "minio":
            diag = i.get("minio") or {}
            man.setdefault("minio", []).append({"container": i["name"], **diag})
            t = i.get("_minio") or {}
            if diag.get("exportable"):  # 1) S3 API through the helper image on the legacy network
                for b in i.get("buckets") or []:
                    od = dst / "objects" / b["name"]
                    od.mkdir(parents=True, exist_ok=True)
                    r = objsync(t, "copy", "s3:OLD", "dir:/out", bucket=b["name"], vol=str(od))
                    mf = od / ".objsync-manifest.json"
                    if r.returncode or not mf.exists():
                        raise RuntimeError(f"MinIO export of bucket {b['name']} failed: {r.stderr.decode(errors='replace')[-300:]}")
                    n = len(json.loads(mf.read_text())["objects"])
                    if n != b["objects"]:
                        raise RuntimeError(f"MinIO export of bucket {b['name']}: {n} objects exported, {b['objects']} listed")
                    add(mf, kind="objsync-manifest", container=i["name"], bucket=b["name"], objects=n, method="objsync (S3 API)")
                    man["buckets"].append({"container": i["name"], "bucket": b["name"], "dir": f"objects/{b['name']}", "objects": n,
                                           "method": "objsync (S3 API)"})
                continue
            if diag.get("listed_by") and diag.get("buckets"):  # 2) no network: mc inside the container, streamed via docker exec -i
                for b in diag["buckets"]:
                    od = dst / "objects" / b["name"]
                    od.mkdir(parents=True, exist_ok=True)
                    n = export_mc(i, t, b["name"], od)
                    if b.get("objects") is not None and n != b["objects"]:
                        raise RuntimeError(f"mc export of bucket {b['name']}: {n} objects exported, {b['objects']} listed")
                    add(od / ".objsync-manifest.json", kind="objsync-manifest", container=i["name"], bucket=b["name"], objects=n,
                        method="mc cat (docker exec -i)")
                    man["buckets"].append({"container": i["name"], "bucket": b["name"], "dir": f"objects/{b['name']}", "objects": n,
                                           "method": "mc cat (docker exec -i)"})
                    print(f"[legacy] {i['name']} bucket {b['name']}: {n} objects exported via mc cat, SHA-256 manifest written")
                continue
            try:  # 3) read-only copy of the data directory for the xl-single reader
                tar = export_cp(i, t, dst)
                add(tar, kind="minio-data-dir", container=i["name"], data_dir=t["data_dir"], method="docker cp (read-only)")
                man["minio_data"] = {"container": i["name"], "file": tar.name, "data_dir": t["data_dir"]}
                print(f"[legacy] {i['name']}: data dir {t['data_dir']} copied read-only ({tar.stat().st_size} bytes) – objects are read by the "
                      "xl-single reader during rehearsal; evidence NOT verified until each SHA-256 matches")
            except RuntimeError as e:
                man.setdefault("warnings", []).append(
                    f"{i['name']}: objects NOT exported ({diag.get('error')}; {e}) – recovery uses the tarball; evidence is NOT verified until the "
                    "rehearsal reads every object and SHA-256-matches it to the evidence records")
                print(f"[legacy] WARN {man['warnings'][-1]}")
    man["files"], man["verified"] = files, True
    (dst / "manifest.json").write_text(json.dumps(man, indent=1))
    os.chmod(dst / "manifest.json", 0o600)
    return man


def verify_backup(d: Path) -> list[str]:
    m = d / "manifest.json"
    if not m.is_file():
        return [f"{m} missing"]
    files = json.loads(m.read_text())["files"]
    probs = [f"{f['file']}: sha256 mismatch" for f in files if not (d / f["file"]).is_file() or sha(d / f["file"]) != f["sha256"]]
    for f in files:  # every exported object must still match its objsync SHA-256 manifest
        if f.get("kind") == "objsync-manifest" and (d / f["file"]).is_file():
            od = (d / f["file"]).parent
            for k, o in json.loads((d / f["file"]).read_text())["objects"].items():
                if not (od / k).is_file() or sha(od / k) != o["sha256"]:
                    probs.append(f"{f['file']}: object {k} missing or changed")
    return probs


def stop(rep: dict, bdir: Path, only_conflicting: bool) -> int:
    if rep["verdict"] == DEPENDS:
        print("REFUSED: the live stack depends on a legacy container – nothing stopped (see !! lines)")
        return 11
    probs = verify_backup(bdir)
    if probs:
        print(f"REFUSED: legacy backup {bdir} not verified ({'; '.join(probs)}) – nothing stopped")
        return 2
    sel = [i["name"] for i in rep["containers"] if i["running"] and (i["conflicts"] or not only_conflicting)]
    if not sel:
        print("[legacy] nothing to stop")
        return 0
    docker("stop", *sel)
    restart = "docker start " + " ".join(sel)
    m = json.loads((bdir / "manifest.json").read_text())
    m.setdefault("stopped", []).append({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "containers": sel, "restart_command": restart})
    (bdir / "manifest.json").write_text(json.dumps(m, indent=1))
    print(f"[legacy] stopped gracefully (no rm, no down, volumes untouched): {', '.join(sel)}\n[legacy] restart with: {restart}")
    return 0


def sources(bdir: Path | None, default_db: str, default_archive: str) -> int:
    """Pick recovery sources: a legacy DB snapshot whose key counts match the stated facts (prefer RECOVER_LEGACY_SOURCE_DB,
    default aegisrmf), else the backup file; a legacy MinIO export (prefer RECOVER_LEGACY_BUCKET), else the tarball."""
    m = json.loads((bdir / "manifest.json").read_text()) if bdir and (bdir / "manifest.json").is_file() else {"databases": [], "buckets": []}
    pref = os.environ.get("RECOVER_LEGACY_SOURCE_DB") or "aegisrmf"
    dbs = sorted(m["databases"], key=lambda d: d["database"] != pref)
    out, notes = {"RECOVER_LEGACY_BACKUP": str(bdir or "")}, []
    match = None
    for d in dbs:
        if d.get("counts"):
            diff = {k: [v, d["counts"].get(k)] for k, v in FACTS.items() if d["counts"].get(k) != v}
            notes.append(f"legacy DB {d['container']}/{d['database']} @ {d['revision']}: " + ("matches the stated facts" if not diff else f"differs from the stated facts (expected, actual) {json.dumps(diff)}"))
            match = match or (d if not diff else None)
    if match:
        out["RECOVER_SOURCE_BACKUP"] = str(bdir / match["file"])
        out["RECOVER_SOURCE_ORIGIN"] = f"running legacy {match['container']}/{match['database']} (read-only pg_dump snapshot, pg_restore -l verified)"
    elif Path(default_db).is_file():
        out["RECOVER_SOURCE_BACKUP"], out["RECOVER_SOURCE_ORIGIN"] = default_db, "backup file " + default_db
        notes.append("no legacy DB matches the stated facts – using the backup file")
    else:
        notes.append(f"WARN no legacy DB matches the stated facts and {default_db} is missing")
    bpref = os.environ.get("RECOVER_LEGACY_BUCKET") or "evidence"
    bks = sorted((b for b in m["buckets"] if b.get("objects")), key=lambda b: b["bucket"] != bpref)
    if len(bks) > 1:  # several exported buckets: give the rehearsal ALL of them (keys matched per evidence record, then SHA-256)
        out["RECOVER_OBJECT_DIR"] = str(bdir / "objects")
        out["RECOVER_OBJECT_ORIGIN"] = "running legacy MinIO buckets " + ", ".join(f"{b['bucket']} ({b['objects']})" for b in bks) + " (read-only export, SHA-256 manifests)"
        notes.append("objects: exported buckets " + ", ".join(b["bucket"] for b in bks) + " – the rehearsal maps every evidence record by storage key and verifies its SHA-256 (report §Evidence integrity)")
    elif bks:
        out["RECOVER_OBJECT_DIR"] = str(bdir / bks[0]["dir"])
        out["RECOVER_OBJECT_ORIGIN"] = f"running legacy {bks[0]['container']} bucket {bks[0]['bucket']} (read-only {bks[0].get('method') or 'objsync'} export, SHA-256 manifest)"
    elif m.get("minio_data"):
        out["RECOVER_OBJECT_ARCHIVE"] = str(bdir / m["minio_data"]["file"])
        out["RECOVER_OBJECT_ORIGIN"] = f"legacy {m['minio_data']['container']} data dir {m['minio_data']['data_dir']} (read-only docker cp, xl-single reader)"
        notes.append("objects: MinIO data dir copy – verification PENDING: the rehearsal maps every evidence record by storage key and verifies its SHA-256 (report §Evidence integrity)")
    else:
        out["RECOVER_OBJECT_ARCHIVE"], out["RECOVER_OBJECT_ORIGIN"] = default_archive, "archive " + default_archive
        notes.append("objects: no verified legacy MinIO export – tarball fallback; verification PENDING: the rehearsal maps every "
                     "evidence record by storage key and verifies its SHA-256 (report §Evidence integrity)")
    for n in notes:
        print(f"# {n}")
    for k, v in out.items():
        print(f"{k}={v}")
    return 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["sources"]:
        opt = lambda k: argv[argv.index(k) + 1] if k in argv and argv[argv.index(k) + 1] else None  # noqa: E731
        return sources(Path(opt("--backup")) if opt("--backup") else None, opt("--default-db") or "", opt("--default-archive") or "")
    if not argv or argv[0] not in ("inspect", "backup", "stop", "preserve-and-stop"):
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    opt = lambda k: rest[rest.index(k) + 1] if k in rest else None  # noqa: E731
    vals = {opt(k) for k in ("--env-file", "--out", "--backup")}
    pos = [a for a in rest if not a.startswith("--") and a not in vals]
    project = pos[0] if pos else "aegisrmf"
    env_file = opt("--env-file") or os.environ.get("ENV_FILE") or "deploy/digitalocean/.env.production"
    try:
        rep = analyse(project, env_file, deep=cmd != "stop")
        if cmd == "inspect":
            if "--json" in rest:
                print(json.dumps({**{k: v for k, v in rep.items() if k != "_raw"},
                                  "containers": [{k: v for k, v in i.items() if not k.startswith("_")} for i in rep["containers"]]}, indent=1))
            else:
                show(rep)
            return CODES[rep["verdict"]]
        show(rep)
        pre = Path(os.environ.get("RECOVER_PREDEPLOY_DIR") or "/root/ironvision-predeploy")
        if cmd == "backup":
            m = backup(rep, Path(opt("--out") or pre / f"legacy-{time.strftime('%Y%m%dt%H%M%S', time.gmtime())}"))
            print(f"[legacy] backup verified: {len(m['databases'])} database(s), {len(m['buckets'])} bucket(s), {len(m['files'])} file(s)")
            return 0
        if "--yes" not in rest:
            print("REFUSED: add --yes (backups are taken and verified first; containers are only stopped, never removed)")
            return 2
        if cmd == "preserve-and-stop":
            if rep["verdict"] == DEPENDS:
                print("REFUSED: the live stack depends on a legacy container – no backup taken, nothing stopped")
                return 11
            bdir = Path(opt("--out") or pre / f"legacy-{time.strftime('%Y%m%dt%H%M%S', time.gmtime())}")
            backup(rep, bdir)
            return stop(rep, bdir, False)
        if not opt("--backup"):
            print("REFUSED: stop needs --backup <verified legacy backup dir>")
            return 2
        return stop(rep, Path(opt("--backup")), "--only-conflicting" in rest)
    except (RuntimeError, OSError, ValueError) as e:
        print(f"[legacy] ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
