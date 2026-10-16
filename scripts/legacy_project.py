#!/usr/bin/env python3
"""Legacy compose project next to the ironvision stack (default project aegisrmf). Host-side, stdlib only, never sources env files.
  inspect [PROJECT] [--env-file F] [--json]       read-only: containers, mounts, networks, env (redacted), DBs (size, alembic
                                                  revision, key counts), MinIO buckets + object counts, dependency/port verdicts
  backup  [PROJECT] --out DIR                     pg_dumpall --globals-only + pg_dump -Fc of every DB (pg_restore -l verified),
                                                  read-only objsync export of every MinIO bucket, docker inspect records, sha256 manifest
  stop    [PROJECT] --backup DIR --yes [--only-conflicting]   graceful `docker stop` (never rm / down / -v); refuses on dependency
  preserve-and-stop [PROJECT] --yes [--out DIR]   backup + stop
Exit: 0 SAFE_TO_STOP (or no legacy containers) · 10 PORT_CONFLICT · 11 PRODUCTION_DEPENDS_ON_LEGACY · 1 error · 2 usage/refused."""
import hashlib
import importlib.util
import json
import os
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


def docker(*args: str, stdin=None, stdout=None, check: bool = True) -> subprocess.CompletedProcess:
    bad = {"rm", "down", "-v", "--volumes", "prune", "kill", "rmi"} & set(args[:3])
    if bad or (args and args[0] == "volume"):
        raise SystemExit(f"legacy_project: refusing destructive docker call {args[:3]}")
    r = subprocess.run(["docker", *args], stdin=stdin, stdout=stdout or subprocess.PIPE, stderr=subprocess.PIPE, check=False)
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
    mounts = [{"type": m.get("Type"), "name": m.get("Name") or "", "source": m.get("Source") or "", "dest": m.get("Destination")} for m in c.get("Mounts") or []]
    i = {"name": c["Name"].lstrip("/"), "service": lab.get("com.docker.compose.service", ""), "project": lab.get("com.docker.compose.project", ""),
         "image": c["Config"].get("Image", ""), "running": bool(c["State"].get("Running")), "status": c["State"].get("Status", ""),
         "ports": ports, "networks": nets, "mounts": mounts, "_env": env,
         "env_redacted": {k: ("***" if any(s in k for s in SECRETISH) else v) for k, v in env.items() if not k.startswith(("PATH", "GOSU", "PG_", "LANG"))}}
    img = i["image"].split("/")[-1]
    i["kind"] = "postgres" if img.startswith("postgres") or i["service"] in ("postgres", "db") else "minio" if "minio" in i["image"] or "minio" in i["name"] else "other"
    return i


def containers(project: str) -> tuple[list[dict], list[dict]]:
    ns = names(project)
    raw = json.loads(out("inspect", *ns)) if ns else []
    return [info(c) for c in raw], raw


def pg_user(i: dict) -> str:
    return os.environ.get("LEGACY_PG_USER") or i["_env"].get("POSTGRES_USER") or "postgres"


def psql(i: dict, db: str, sql: str) -> str | None:
    r = docker("exec", i["name"], "psql", "-U", pg_user(i), "-d", db, "-Atc", sql, check=False)
    return r.stdout.decode().strip() if r.returncode == 0 else None


def pg_databases(i: dict) -> list[dict]:
    lst = psql(i, "postgres", "select datname from pg_database where not datistemplate order by 1")
    res = []
    for db in (lst or "").split():
        d = {"name": db, "size": int(psql(i, db, "select pg_database_size(current_database())") or 0),
             "revision": psql(i, db, "select version_num from alembic_version")}
        if d["revision"]:
            d["counts"] = {t: int(v) if (v := psql(i, db, f"select count(*) from {t}")) and v.isdigit() else None for t in FACT_TABLES}
        res.append(d)
    return res


def minio_env(i: dict) -> dict:
    e = i["_env"]
    net = next(iter(i["networks"]), "")
    return {"OLD_S3_ENDPOINT_URL": os.environ.get("LEGACY_MINIO_ENDPOINT") or f"http://{i['name']}:9000",
            "OLD_S3_ACCESS_KEY_ID": e.get("MINIO_ROOT_USER") or e.get("MINIO_ACCESS_KEY") or "",
            "OLD_S3_SECRET_ACCESS_KEY": e.get("MINIO_ROOT_PASSWORD") or e.get("MINIO_SECRET_KEY") or "",
            "OLD_S3_REGION": "us-east-1", "OLD_S3_ADDRESSING_STYLE": "path", "_network": net}


def objsync(i: dict, *args: str, bucket: str = "_", vol: str | None = None) -> subprocess.CompletedProcess:
    """Read-only: the tool container on the legacy network talks to MinIO's S3 API (credentials passed by name, not on argv)."""
    me = minio_env(i)
    env = {**os.environ, **{k: v for k, v in me.items() if not k.startswith("_")}, "OLD_S3_BUCKET": bucket}
    cmd = ["docker", "run", "--rm", "--pull", "never", "--network", me["_network"]] + [x for k in env if k.startswith("OLD_S3_") for x in ("-e", k)]
    if vol:
        cmd += ["-v", f"{vol}:/out"]
    cmd += [TOOL_IMAGE, "python", "-m", "app.tools.objsync", *args]
    return subprocess.run(cmd, env=env, capture_output=True, check=False)


def minio_buckets(i: dict) -> list[dict] | None:
    r = objsync(i, "buckets", "s3:OLD")
    if r.returncode:
        return None
    res = []
    for b in r.stdout.decode().split():
        ls = objsync(i, "ls", "s3:OLD", bucket=b)
        res.append({"name": b, "objects": len(ls.stdout.decode().split("\n")) - 1 if ls.returncode == 0 else None})
    return res


def env_hosts(env_file: str | None) -> tuple[dict, dict]:
    env = envfile.parse_env_file(env_file) if env_file and Path(env_file).is_file() else {}
    h = lambda u, d: (urllib.parse.urlsplit(u).hostname if u else None) or d  # noqa: E731
    return {"database": h(env.get("DATABASE_URL"), "postgres"), "object storage": h(env.get("S3_ENDPOINT_URL"), "seaweedfs")}, env


def overlap(a: str, b: str) -> bool:
    return a in ("0.0.0.0", "::", "") or b in ("0.0.0.0", "::", "") or a == b


def analyse(project: str, env_file: str | None, deep: bool = True) -> dict:
    legacy, raw = containers(project)
    hosts, env = env_hosts(env_file)
    cur_proj = os.environ.get("IRONVISION_PROJECT") or "ironvision"
    current, _ = containers(cur_proj)
    current = [c for c in current if c["project"] == cur_proj]
    nets = {n for c in current if c["service"] in ("backend", "worker", "migrate") for n in c["networks"]}
    skip = ("/etc/", "/var/run", "/run/", "/proc", "/sys", "/dev")
    cur_mounts = {m["name"] or m["source"]: c["name"] for c in current for m in c["mounts"] if not (m["source"] or "").startswith(skip)}
    want = {("0.0.0.0", "80"), ("0.0.0.0", "443")} | {(p["host_ip"], p["host_port"]) for c in current for p in c["ports"]}
    for i in legacy:
        i["depends"], i["conflicts"] = [], []
        for kind, h in hosts.items():
            if h == i["name"] or h in {v["ip"] for v in i["networks"].values() if v["ip"]}:
                i["depends"].append(f"{kind} host '{h}' IS this legacy container")
            for n in set(i["networks"]) & nets:
                if h in i["networks"][n]["aliases"] or h == i["service"]:
                    i["depends"].append(f"{kind} host '{h}' resolves to this container on shared network {n}")
        for m in i["mounts"]:
            k = m["name"] or m["source"]
            if k in cur_mounts and not (m["source"] or "").startswith(skip):
                i["depends"].append(f"shares {m['type']} {k} with live container {cur_mounts[k]}")
        if i["running"]:
            i["conflicts"] = [f"{p['host_ip']}:{p['host_port']}" for p in i["ports"] if any(p["host_port"] == wp and overlap(p["host_ip"], wi) for wi, wp in want)]
        i["verdict"] = DEPENDS if i["depends"] else PORT if i["conflicts"] else SAFE
        if deep and i["running"] and i["kind"] == "postgres":
            i["databases"] = pg_databases(i)
        if deep and i["running"] and i["kind"] == "minio":
            i["buckets"] = minio_buckets(i)
    verdict = DEPENDS if any(i["verdict"] == DEPENDS for i in legacy) else PORT if any(i["verdict"] == PORT for i in legacy) else SAFE
    return {"project": project, "hosts": hosts, "current_project": cur_proj, "containers": legacy, "verdict": verdict,
            "_raw": {r["Name"].lstrip("/"): r for r in raw}, "none": not legacy}


def show(rep: dict) -> None:
    print(f"[legacy] project {rep['project']}: {len(rep['containers'])} container(s); live stack '{rep['current_project']}' uses "
          f"database host '{rep['hosts']['database']}', object storage host '{rep['hosts']['object storage']}'")
    for i in rep["containers"]:
        ports = ", ".join(f"{p['host_ip']}:{p['host_port']}->{p['container']}" for p in i["ports"]) or "none"
        print(f"  {i['name']}  service={i['service'] or '-'} image={i['image']} status={i['status']} ports={ports}  → {i['verdict']}")
        for m in i["mounts"]:
            print(f"     mount {m['type']} {m['name'] or m['source']} -> {m['dest']}")
        print(f"     networks: {', '.join(i['networks']) or '-'}; env: {json.dumps(i['env_redacted'])}")
        for d in i.get("databases") or []:
            print(f"     db {d['name']}: {d['size'] >> 20} MiB, alembic {d['revision'] or '-'}" + (f", counts {json.dumps(d['counts'])}" if d.get("counts") else ""))
        if i["kind"] == "minio":
            print(f"     buckets: {json.dumps(i.get('buckets')) if i.get('buckets') is not None else 'not listable (S3 API unreachable or no credentials)'}")
        for r in i["depends"] + [f"port conflict {c}" for c in i["conflicts"]]:
            print(f"     !! {r}")
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
            g = dst / f"{i['name']}-globals.sql"
            with open(g, "wb") as f:
                r = docker("exec", i["name"], "pg_dumpall", "-U", pg_user(i), "--globals-only", stdout=f, check=False)
            if r.returncode:  # non-superuser: roles without password hashes (pg_roles instead of pg_authid)
                with open(g, "wb") as f:
                    r = docker("exec", i["name"], "pg_dumpall", "-U", pg_user(i), "--globals-only", "--no-role-passwords", stdout=f, check=False)
            if r.returncode:
                g.unlink(missing_ok=True)
                man.setdefault("warnings", []).append(f"{i['name']}: roles/globals not dumped ({r.stderr.decode(errors='replace')[-120:]}) – databases are")
            else:
                add(g, kind="pg-globals", container=i["name"])
            for d in i.get("databases") or []:
                p = dst / f"{i['name']}-{d['name']}.dump"
                with open(p, "wb") as f:
                    docker("exec", i["name"], "pg_dump", "-U", pg_user(i), "-Fc", "-d", d["name"], stdout=f)
                with open(p, "rb") as f:
                    toc = docker("exec", "-i", i["name"], "pg_restore", "-l", stdin=f, check=False)
                entries = sum(1 for ln in toc.stdout.decode(errors="replace").splitlines() if ln and not ln.startswith(";"))
                if toc.returncode or not entries:
                    raise RuntimeError(f"backup of {i['name']}/{d['name']} is unreadable (pg_restore -l) – nothing stopped")
                add(p, kind="pg-dump", container=i["name"], database=d["name"], toc_entries=entries, revision=d["revision"], counts=d.get("counts"))
                man["databases"].append({"container": i["name"], "database": d["name"], "file": p.name, "revision": d["revision"], "counts": d.get("counts")})
        if i["kind"] == "minio":
            for b in i.get("buckets") or []:
                od = dst / "objects" / b["name"]
                od.mkdir(parents=True, exist_ok=True)
                r = objsync(i, "copy", "s3:OLD", "dir:/out", bucket=b["name"], vol=str(od))
                mf = od / ".objsync-manifest.json"
                if r.returncode or not mf.exists():
                    raise RuntimeError(f"MinIO export of bucket {b['name']} failed: {r.stderr.decode(errors='replace')[-300:]}")
                add(mf, kind="objsync-manifest", container=i["name"], bucket=b["name"], objects=len(json.loads(mf.read_text())["objects"]))
                man["buckets"].append({"container": i["name"], "bucket": b["name"], "dir": f"objects/{b['name']}", "objects": b["objects"]})
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
    if bks:
        out["RECOVER_OBJECT_DIR"] = str(bdir / bks[0]["dir"])
        out["RECOVER_OBJECT_ORIGIN"] = f"running legacy {bks[0]['container']} bucket {bks[0]['bucket']} (read-only objsync export, SHA-256 manifest)"
    else:
        out["RECOVER_OBJECT_ARCHIVE"], out["RECOVER_OBJECT_ORIGIN"] = default_archive, "archive " + default_archive
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
                                  "containers": [{k: v for k, v in i.items() if k != "_env"} for i in rep["containers"]]}, indent=1))
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
