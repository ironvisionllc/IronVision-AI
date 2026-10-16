"""objsync – copy/verify objects between a local directory and any S3 endpoint, with a SHA-256 manifest.
Replaces `mc mirror` / `aws s3 sync` in backup, restore, off-site copy and MinIO migration.

  python -m app.tools.objsync ls     SRC
  python -m app.tools.objsync copy   SRC DST [--manifest FILE]
  python -m app.tools.objsync verify SRC --manifest FILE

Targets:
  dir:/path                local directory (manifest written to /path/.objsync-manifest.json when it is the destination)
  s3                       the application bucket from S3_ENDPOINT_URL/S3_BUCKET/S3_REGION/S3_ACCESS_KEY_ID/S3_SECRET_ACCESS_KEY
  s3:OLD                   same variables with prefix, e.g. OLD_S3_ENDPOINT_URL, OLD_S3_BUCKET … (migration source, off-site target)
  …@key/prefix/            optional key prefix, e.g. s3:OFFSITE@ironvision-20260101T000000Z/
Every copied object is re-read from the destination and its SHA-256 compared; any mismatch → exit 1."""
import argparse
import hashlib
import json
import os
import pathlib
import sys

MANIFEST = ".objsync-manifest.json"


class DirTarget:
    def __init__(self, root: str, prefix: str = ""):
        self.root, self.prefix = pathlib.Path(root), prefix

    def keys(self):
        if not self.root.exists():
            return
        for p in sorted(self.root.rglob("*")):
            if p.is_file() and not p.is_symlink() and p.name != MANIFEST:
                yield p.relative_to(self.root).as_posix()

    def _path(self, key: str) -> pathlib.Path:
        p = (self.root / key).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError(f"unsafe key {key!r}")
        return p

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def put(self, key: str, data: bytes) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def label(self) -> str:
        return f"dir:{self.root}"


class S3Target:
    def __init__(self, env_prefix: str = "", key_prefix: str = ""):
        from app.services.storage.s3 import s3_client

        e = lambda k: os.environ.get(f"{env_prefix}{k}")  # noqa: E731
        self.bucket, self.prefix, self.env_prefix = e("S3_BUCKET"), key_prefix, env_prefix
        if not self.bucket:
            raise SystemExit(f"{env_prefix}S3_BUCKET is required")
        self.endpoint = e("S3_ENDPOINT_URL")
        self.c = s3_client(self.endpoint, e("S3_REGION") or "us-east-1", e("S3_ACCESS_KEY_ID"), e("S3_SECRET_ACCESS_KEY"),
                           e("S3_ADDRESSING_STYLE") or "path")

    def keys(self):
        for page in self.c.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=self.prefix):
            for o in page.get("Contents", []):
                k = o["Key"][len(self.prefix):]
                if k and not k.endswith("/") and not k.startswith("_bootstrap/"):
                    yield k

    def get(self, key: str) -> bytes:
        return self.c.get_object(Bucket=self.bucket, Key=self.prefix + key)["Body"].read()

    def put(self, key: str, data: bytes) -> None:
        self.c.put_object(Bucket=self.bucket, Key=self.prefix + key, Body=data)

    def label(self) -> str:
        return f"s3://{self.bucket}/{self.prefix} ({self.endpoint or 'AWS'})"


def target(spec: str):
    spec, _, key_prefix = spec.partition("@")
    if spec.startswith("dir:"):
        return DirTarget(spec[4:], key_prefix)
    if spec == "s3" or spec.startswith("s3:"):
        env = spec[3:]
        return S3Target(f"{env}_" if env else "", key_prefix)
    raise SystemExit(f"unknown target {spec!r} (use dir:/path, s3 or s3:ENVPREFIX)")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def copy(src, dst, manifest_path: str | None) -> int:
    pre = {}
    if isinstance(src, DirTarget) and (src.root / MANIFEST).exists():
        pre = json.loads((src.root / MANIFEST).read_text())["objects"]
    out, bad, seen = {}, 0, set()
    for k in src.keys():
        seen.add(k)
        data = src.get(k)
        h = sha(data)
        if pre and k in pre and pre[k]["sha256"] != h:
            print(f"[objsync] FAIL source object differs from its manifest: {k}")
            bad += 1
            continue
        dst.put(k, data)
        if sha(dst.get(k)) != h:
            print(f"[objsync] FAIL destination hash mismatch: {k}")
            bad += 1
            continue
        out[k] = {"sha256": h, "bytes": len(data)}
    if pre and (missing := sorted(set(pre) - seen)):
        print(f"[objsync] FAIL {len(missing)} manifest objects missing from source, e.g. {missing[:3]}")
        bad += len(missing)
    doc = {"source": src.label(), "destination": dst.label(), "count": len(out), "objects": out}
    if isinstance(dst, DirTarget):
        dst.root.mkdir(parents=True, exist_ok=True)
        (dst.root / MANIFEST).write_text(json.dumps(doc, indent=1, sort_keys=True))
    if manifest_path:
        pathlib.Path(manifest_path).write_text(json.dumps(doc, indent=1, sort_keys=True))
    print(f"[objsync] copied {len(out)} objects {src.label()} -> {dst.label()}, verified SHA-256; failures={bad}")
    return 1 if bad else 0


def probe(spec: str) -> dict:
    from botocore.exceptions import BotoCoreError, ClientError, EndpointConnectionError
    os.environ.setdefault(f"{spec[3:]}_S3_BUCKET" if spec.startswith("s3:") else "S3_BUCKET", "_")
    t = target(spec)
    from app.services.storage.s3 import s3_client
    e = lambda k: os.environ.get(f"{t.env_prefix}{k}")  # noqa: E731
    t.c = s3_client(t.endpoint, e("S3_REGION") or "us-east-1", e("S3_ACCESS_KEY_ID"), e("S3_SECRET_ACCESS_KEY"),
                    e("S3_ADDRESSING_STYLE") or "path", quick=True)
    res = {"endpoint": t.endpoint, "reachable": False, "auth": False, "buckets": None, "error": None}
    try:
        names = [b["Name"] for b in t.c.list_buckets().get("Buckets", [])]
    except ClientError as e:
        res["reachable"], res["error"] = True, e.response.get("Error", {}).get("Code") or str(e)[:200]
        return res
    except (EndpointConnectionError, BotoCoreError, OSError) as e:
        res["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        return res
    res["reachable"] = res["auth"] = True
    res["buckets"] = []
    for n in names:
        t.bucket, cnt, size = n, 0, 0
        for page in t.c.get_paginator("list_objects_v2").paginate(Bucket=n):
            for o in page.get("Contents", []):
                if o["Key"].endswith("/") or o["Key"].startswith("_bootstrap/"):  # same filter as S3Target.keys()
                    continue
                cnt, size = cnt + 1, size + o.get("Size", 0)
        res["buckets"].append({"name": n, "objects": cnt, "bytes": size})
    return res


def verify(src, manifest_path: str) -> int:
    objs = json.loads(pathlib.Path(manifest_path).read_text())["objects"]
    bad = 0
    for k, m in objs.items():
        try:
            ok = sha(src.get(k)) == m["sha256"]
        except Exception:
            ok = False
        if not ok:
            bad += 1
            print(f"[objsync] MISMATCH {k}")
    print(f"[objsync] verified {len(objs) - bad}/{len(objs)} objects in {src.label()} against {manifest_path}")
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="objsync", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ls"); a.add_argument("src")  # noqa: E702
    c = sub.add_parser("copy"); c.add_argument("src"); c.add_argument("dst"); c.add_argument("--manifest")  # noqa: E702
    v = sub.add_parser("verify"); v.add_argument("src"); v.add_argument("--manifest", required=True)  # noqa: E702
    sub.add_parser("buckets").add_argument("src")
    sub.add_parser("probe").add_argument("src")
    ns = ap.parse_args(argv)
    if ns.cmd == "probe":  # read-only diagnosis as JSON: reachable / auth / buckets + object counts
        print(json.dumps(probe(ns.src)))
        return 0
    if ns.cmd == "buckets":  # read-only: names of all buckets visible to the source credentials
        for b in target(ns.src).c.list_buckets().get("Buckets", []):
            print(b["Name"])
        return 0
    if ns.cmd == "ls":
        n = 0
        for k in target(ns.src).keys():
            print(k)
            n += 1
        print(f"[objsync] {n} objects", file=sys.stderr)
        return 0
    if ns.cmd == "copy":
        return copy(target(ns.src), target(ns.dst), ns.manifest)
    return verify(target(ns.src), ns.manifest)


if __name__ == "__main__":
    sys.exit(main())
