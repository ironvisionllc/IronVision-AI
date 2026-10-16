#!/usr/bin/env python3
"""TEST SHIM for `docker` (no daemon). Simulates legacy containers from the scenario JSON in $DOCKER_SHIM_SCENARIO:
  {"containers": {NAME: {"inspect": {...docker inspect...}}}, "pg": {"container": NAME, "url": postgresql://...local,
   "dbmap": {"legacy db": "real local db"}}, "s3": {"from": "http://aegisrmf-minio-recovery:9000", "to": "http://127.0.0.1:18333"},
   "repo_digests": {IMAGE: [...]}}
`exec <pg> psql/pg_dump/pg_dumpall/pg_restore` run the REAL local PostgreSQL binaries against the mapped DBs; `run IMAGE python -m
app.tools.objsync …` runs objsync locally (SeaweedFS stands in for the legacy MinIO S3 API). `stop`/`start` flip State.Running.
Every call is appended to $DOCKER_SHIM_LOG. Anything destructive (rm, down, -v, volume, prune) exits 99."""
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

BACKEND = Path(__file__).resolve().parents[1]
SCN = Path(os.environ["DOCKER_SHIM_SCENARIO"])
PG_BIN = os.environ.get("RECOVER_PG_BIN", "/usr/lib/postgresql/16/bin")


def load() -> dict:
    return json.loads(SCN.read_text())


def pg_env(s: dict) -> dict:
    u = urlsplit(s["pg"]["url"].replace("+psycopg", ""))
    return {**os.environ, "PGHOST": u.hostname, "PGPORT": str(u.port or 5432), "PGUSER": u.username or "postgres", "PGPASSWORD": u.password or ""}


def pg_exec(s: dict, cmd: list[str], extra: dict, tty: bool) -> int:
    """Real local PostgreSQL client binaries against the mapped DBs; -U/-h dropped (the shim connects as the test role).
    tty=True simulates `docker exec -t`: LF is turned into CRLF on stdout, as a pseudo-terminal does."""
    cmd = list(cmd)
    for flag in ("-U", "-h"):
        if flag in cmd:
            del cmd[cmd.index(flag):cmd.index(flag) + 2]
    if "-d" in cmd:
        k = cmd.index("-d") + 1
        cmd[k] = s["pg"]["dbmap"].get(cmd[k], cmd[k])
    if cmd[0] == "psql" and "from pg_database" in cmd[-1]:
        print("\n".join(sorted(s["pg"]["dbmap"])))
        return 0
    env = {**pg_env(s), **{k: v for k, v in extra.items() if k == "PGOPTIONS"}}
    if not tty:
        return subprocess.run([f"{PG_BIN}/{cmd[0]}", *cmd[1:]], env=env, check=False).returncode
    r = subprocess.run([f"{PG_BIN}/{cmd[0]}", *cmd[1:]], env=env, capture_output=True, check=False)
    sys.stdout.buffer.write(r.stdout.replace(b"\n", b"\r\n"))
    sys.stderr.buffer.write(r.stderr)
    return r.returncode


def fake_mc(mc: dict, args: list[str]) -> int:
    """mc ls [--recursive] --json legacy[/bucket] and mc cat legacy/bucket/key, from static objects or an S3 stand-in."""
    if mc.get("s3"):
        import boto3
        c = boto3.client("s3", endpoint_url=mc["s3"]["endpoint"], aws_access_key_id=mc["s3"]["key"], aws_secret_access_key=mc["s3"]["secret"],
                         region_name="us-east-1")
        buckets = {b: None for b in mc["s3"]["buckets"]}

        def keys(b):
            out = {}
            for page in c.get_paginator("list_objects_v2").paginate(Bucket=b):
                out.update({o["Key"]: o["Size"] for o in page.get("Contents", []) if not o["Key"].endswith("/")})
            return out
        get = lambda b, k: c.get_object(Bucket=b, Key=k)["Body"].read()  # noqa: E731
    else:
        buckets = {b: (v if isinstance(v, dict) else {f"o{n}": f"o{n}" for n in range(v)}) for b, v in mc["buckets"].items()}
        keys = lambda b: {k: len(v.encode()) for k, v in buckets[b].items()}  # noqa: E731
        get = lambda b, k: buckets[b][k].encode()  # noqa: E731
    target = args[-1]
    if args[0] == "ls" and target == "legacy":
        print("\n".join(json.dumps({"status": "success", "type": "folder", "key": b + "/"}) for b in buckets))
        return 0
    parts = target.split("/", 2)
    b, k = parts[1], parts[2] if len(parts) > 2 else ""
    if args[0] == "ls":
        print("\n".join(json.dumps({"status": "success", "type": "file", "key": key, "size": size}) for key, size in sorted(keys(b).items())))
        return 0
    if args[0] == "cat":
        sys.stdout.buffer.write(get(b, k))
        return 0
    return 2


def main(a: list[str]) -> int:
    with open(os.environ["DOCKER_SHIM_LOG"], "a") as f:
        f.write(" ".join(a) + "\n")
    if not a or a[0] in ("rm", "volume", "rmi") or "down" in a[:3] or "-v" in a[:2] or "--volumes" in a or "prune" in a:
        return 99
    s = load()
    if a[0] == "info":
        return 0
    if a[:2] == ["compose", "version"]:
        print("2.29.1")
        return 0
    cs = s["containers"]
    if a[0] == "ps":
        flt = a[a.index("--filter") + 1] if "--filter" in a else ""
        for n, c in cs.items():
            lab = c["inspect"]["Config"].get("Labels") or {}
            ok = (flt.startswith("label=com.docker.compose.project=") and lab.get("com.docker.compose.project") == flt.split("=", 2)[2]) \
                or (flt.startswith("name=^") and n.startswith(flt[6:]))
            if ok and ("-a" in a or c["inspect"]["State"]["Running"]):
                print(n if "--format" in a else n[:12])
        return 0
    if a[0] == "inspect":
        print(json.dumps([cs[n]["inspect"] for n in a[1:] if n in cs]))
        return 0 if all(n in cs for n in a[1:]) else 1
    if a[0] in ("stop", "start"):
        for n in a[1:]:
            cs[n]["inspect"]["State"]["Running"] = a[0] == "start"
            cs[n]["inspect"]["State"]["Status"] = "running" if a[0] == "start" else "exited"
        SCN.write_text(json.dumps(s))
        return 0
    if a[0] == "image" and a[1] == "inspect":
        if "images" in s and a[2] not in s["images"]:
            print(f"Error: No such image: {a[2]}", file=sys.stderr)
            return 1
        print(" ".join(s.get("repo_digests", {}).get(a[2], [])))
        return 0
    if a[0] == "cp":  # docker cp <ctr>:<dir> -  → tar stream of the scenario's directory
        ctr_name, _, path = a[1].partition(":")
        src = s.get("cp", {}).get(ctr_name, {}).get(path)
        if not src or a[2] != "-":
            print(f"Error: No such container:path: {a[1]}", file=sys.stderr)
            return 1
        import tarfile
        with tarfile.open(fileobj=sys.stdout.buffer, mode="w|") as tf:
            tf.add(src, arcname=Path(path).name)
        return 0
    if a[0] == "exec":
        rest, extra, tty = a[1:], {}, False
        while rest[0].startswith("-"):
            if rest[0] == "-e":
                k, _, v = rest[1].partition("=")
                extra[k] = v if _ else os.environ.get(k, "")
                rest = rest[2:]
            else:
                tty = tty or "t" in rest[0]
                rest = rest[1:]
        name, cmd = rest[0], rest[1:]
        if name not in cs or not cs[name]["inspect"]["State"]["Running"]:
            print("Error: container not running", file=sys.stderr)
            return 1
        if cmd[0] == "printenv":
            env = dict(e.split("=", 1) for e in cs[name]["inspect"]["Config"]["Env"])
            print(env.get(cmd[1], ""))
            return 0 if cmd[1] in env else 1
        if cmd[0] == "cat":
            f = s.get("files", {}).get(name, {}).get(cmd[1])
            if f is None:
                print(f"cat: {cmd[1]}: No such file or directory", file=sys.stderr)
                return 1
            sys.stdout.write(f)
            return 0
        if cmd[:2] == ["sh", "-c"] and "command -v mc" in cmd[2]:
            return 0 if s.get("mc", {}).get(name) else 1
        if cmd[0] == "mc":
            mc = s.get("mc", {}).get(name) or {}
            if extra.get("MC_HOST_legacy") != mc.get("host"):
                print("mc: <ERROR> Access Denied.", file=sys.stderr)
                return 1
            return fake_mc(mc, cmd[1:])
        if name != s["pg"]["container"]:
            print(f"OCI runtime exec failed: {cmd[0]}: not found", file=sys.stderr)
            return 127
        if cmd[0] in ("pg_dump", "pg_restore", "pg_dumpall") and cmd[1:] == ["--version"] and s["pg"].get("client_version"):
            print(f"{cmd[0]} (PostgreSQL) {s['pg']['client_version']}")
            return 0
        return pg_exec(s, cmd, extra, tty)
    if a[0] == "run":
        i, env, vols, image_at = 1, dict(os.environ), {}, None
        while a[i].startswith("-"):
            if a[i] == "-e":
                k = a[i + 1].split("=", 1)
                if len(k) == 2:
                    env[k[0]] = k[1]
                i += 2
            elif a[i] == "-v":
                h, c = a[i + 1].split(":", 1)
                vols[c] = h
                i += 2
            elif a[i] in ("--network", "--pull"):
                i += 2
            else:
                i += 1
        image_at, cmd = a[i], a[i + 1:]
        if image_at.startswith("postgres:"):
            if "images" in s and image_at not in s["images"]:
                print(f"Unable to find image '{image_at}' locally (--pull never)", file=sys.stderr)
                return 125
            return pg_exec(s, cmd, {"PGOPTIONS": env.get("PGOPTIONS", "")}, False)
        for k, v in list(env.items()):
            if k.endswith("S3_ENDPOINT_URL") and s.get("s3") and v == s["s3"]["from"]:
                env[k] = s["s3"]["to"]
        cmd = [next((x.replace(f"dir:{c}", f"dir:{h}", 1) for c, h in vols.items() if x.startswith(f"dir:{c}")), x) for x in cmd]
        if cmd[:1] == ["python"]:  # the "recovery image": the clean recovery venv when given
            cmd[0] = os.environ.get("RECOVER_SHIM_PYTHON") or sys.executable
        return subprocess.run(cmd, env={**env, "PYTHONPATH": str(BACKEND)}, cwd=BACKEND, check=False).returncode
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

