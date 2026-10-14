"""One-shot, idempotent object-store bootstrap (objectstore-init; replaces the old `mc` init container).

    python -m app.tools.s3_bootstrap

STORAGE_DRIVER=local → nothing to do (exit 0). STORAGE_DRIVER=s3 → required variables, endpoint reachable (with retries),
bucket (created with the admin identity if missing), versioning, optional policy, SHA-256 put/get/delete round-trip with the
application identity. Every failure names the setting to fix. Secrets are never printed. Exit 0 = ready, 1 = not usable."""
import hashlib
import json
import os
import socket
import sys
import time
import uuid
from urllib.parse import urlparse

from botocore.exceptions import BotoCoreError, ClientError

from app.services.storage.s3 import s3_client

P = "[s3-bootstrap]"
BUILTIN_HOST = "seaweedfs"
BUILTIN_HINT = ("COMPOSE_PROFILES=seaweedfs is required when using the built-in object store (STORAGE_DRIVER=s3 with "
                "S3_ENDPOINT_URL empty). Add it to your env file and deploy with scripts/deploy.sh <env-file>, or set "
                "S3_ENDPOINT_URL to an external S3 endpoint, or use STORAGE_DRIVER=local.")
AUTH_CODES = {
    "InvalidAccessKeyId": "the access key is not known to the object store",
    "SignatureDoesNotMatch": "the secret key does not match the access key",
    "AccessDenied": "the key is valid but not allowed to perform this operation",
    "403": "forbidden – wrong keys, or the key has no access to the bucket",
    "InvalidToken": "the credentials are invalid",
    "ExpiredToken": "the credentials have expired",
}


def _env(k: str, *aliases: str) -> str | None:
    for name in (k, *aliases):
        if os.environ.get(name):
            if name != k:
                print(f"{P} WARNING {name} is deprecated – use {k}")
            return os.environ[name]
    return None


def _code(e: ClientError) -> str:
    return str(e.response.get("Error", {}).get("Code", ""))


def fail(msg: str) -> int:
    print(f"{P} FAIL {msg}", flush=True)
    return 1


def wait_for_endpoint(url: str, timeout: int) -> str | None:
    """TCP-level wait; returns None when reachable, otherwise the last error text."""
    u = urlparse(url)
    host, port = u.hostname, u.port or (443 if u.scheme == "https" else 80)
    deadline, attempt = time.monotonic() + timeout, 0
    while True:
        attempt += 1
        try:
            socket.create_connection((host, port), timeout=5).close()
            print(f"{P} endpoint {host}:{port} reachable (attempt {attempt})")
            return None
        except socket.gaierror as e:
            last = f"cannot resolve host {host!r} ({e.strerror or e})"
        except OSError as e:
            last = f"cannot connect to {host}:{port} ({e.strerror or e})"
        if time.monotonic() >= deadline:
            return last
        print(f"{P} waiting for {host}:{port} – {last}", flush=True)
        time.sleep(3)


def auth_error(code: str, who: str, ids: tuple[str, str], builtin: bool) -> int:
    hint = ("With the built-in SeaweedFS the identities are created from the env file when the seaweedfs container starts; "
            "after changing keys re-run scripts/deploy.sh <env-file> (it recreates seaweedfs)." if builtin else
            "Check the key pair and that it has access to S3_BUCKET (DO Spaces: a Spaces key with access to the bucket; "
            "AWS: the IAM policy). For DO Spaces also check S3_REGION and S3_ADDRESSING_STYLE=virtual.")
    return fail(f"authentication failed for the {who} identity ({ids[0]} / {ids[1]}): {AUTH_CODES[code]} [{code}]. {hint}")


def run() -> int:
    driver = (os.environ.get("STORAGE_DRIVER") or "").strip().lower()
    if driver == "local":
        print(f"{P} local storage driver – nothing to initialize")
        return 0
    if driver != "s3":
        return fail(f"STORAGE_DRIVER must be 's3' or 'local' (got {driver!r}). Set it in your env file.")

    endpoint = os.environ.get("S3_ENDPOINT_URL") or ""
    builtin = urlparse(endpoint).hostname == BUILTIN_HOST
    missing = [k for k in ("S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY") if not os.environ.get(k)]
    if builtin:
        for k, alias in (("S3_ADMIN_ACCESS_KEY_ID", "MINIO_ROOT_USER"), ("S3_ADMIN_SECRET_ACCESS_KEY", "MINIO_ROOT_PASSWORD")):
            if not os.environ.get(k) and not os.environ.get(alias):
                missing.append(k)
    if missing:
        return fail("missing required variable(s): " + ", ".join(missing) + ". Set them in your env file "
                    "(python3 scripts/gen_env_secrets.py <env-file> fills empty secrets for the built-in store) and deploy "
                    "with scripts/deploy.sh <env-file> – plain `docker compose up` without --env-file leaves them blank.")

    bucket = os.environ["S3_BUCKET"]
    common = {"endpoint_url": endpoint or None, "region": os.environ.get("S3_REGION") or "us-east-1",
              "addressing_style": os.environ.get("S3_ADDRESSING_STYLE") or "path"}
    print(f"{P} endpoint={endpoint or 'AWS default'} bucket={bucket} addressing={common['addressing_style']}")
    if endpoint:
        err = wait_for_endpoint(endpoint, int(os.environ.get("S3_BOOTSTRAP_WAIT_SECONDS") or 90))
        if err:
            hint = BUILTIN_HINT if builtin else "Check S3_ENDPOINT_URL, DNS and firewall rules from the Droplet."
            return fail(f"object store endpoint {endpoint} unreachable: {err}. {hint}")

    app_ids = ("S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY")
    admin_key = _env("S3_ADMIN_ACCESS_KEY_ID", "MINIO_ROOT_USER")
    admin_ids = ("S3_ADMIN_ACCESS_KEY_ID", "S3_ADMIN_SECRET_ACCESS_KEY") if admin_key else app_ids
    app = s3_client(access_key_id=os.environ["S3_ACCESS_KEY_ID"], secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"], **common)
    admin = s3_client(access_key_id=admin_key or os.environ["S3_ACCESS_KEY_ID"],
                      secret_access_key=_env("S3_ADMIN_SECRET_ACCESS_KEY", "MINIO_ROOT_PASSWORD") or os.environ["S3_SECRET_ACCESS_KEY"],
                      **common)
    try:
        return _bootstrap(admin, app, bucket, common, builtin, admin_ids, app_ids)
    except BotoCoreError as e:
        return fail(f"object store error ({type(e).__name__}): {e}. Check S3_ENDPOINT_URL / S3_REGION / S3_ADDRESSING_STYLE.")


def _bootstrap(admin, app, bucket, common, builtin, admin_ids, app_ids) -> int:
    try:
        admin.head_bucket(Bucket=bucket)
        print(f"{P} bucket exists")
    except ClientError as e:
        code = _code(e)
        if code in AUTH_CODES:
            return auth_error(code, "admin", admin_ids, builtin)
        if code not in ("404", "NoSuchBucket", "NotFound"):
            return fail(f"head_bucket {bucket}: {code} {e}")
        kw = {}
        if common["region"] != "us-east-1" and not common["endpoint_url"]:
            kw["CreateBucketConfiguration"] = {"LocationConstraint": common["region"]}
        try:
            admin.create_bucket(Bucket=bucket, **kw)
        except ClientError as e2:
            if _code(e2) in AUTH_CODES:
                return auth_error(_code(e2), "admin", admin_ids, builtin)
            return fail(f"cannot create bucket {bucket}: {_code(e2)} {e2}. Create it in the provider console or check S3_BUCKET.")
        print(f"{P} bucket created")

    if (os.environ.get("S3_BUCKET_VERSIONING") or "true").lower() == "true":
        try:
            admin.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})
            print(f"{P} versioning: {admin.get_bucket_versioning(Bucket=bucket).get('Status', 'unknown')}")
        except ClientError as e:
            print(f"{P} versioning not supported by this backend ({_code(e)}) – continuing")

    pol = os.environ.get("S3_BUCKET_POLICY_FILE")
    if pol:
        try:
            with open(pol) as fh:
                admin.put_bucket_policy(Bucket=bucket, Policy=json.dumps(json.load(fh)))
            print(f"{P} bucket policy applied")
        except ClientError as e:
            print(f"{P} bucket policy not supported by this backend ({_code(e)}) – access is enforced by identities")
    else:
        print(f"{P} no bucket policy configured (access is enforced by the S3 identities)")

    key, body = f"_bootstrap/roundtrip-{uuid.uuid4().hex}", os.urandom(4096)
    want = hashlib.sha256(body).hexdigest()
    try:
        put = app.put_object(Bucket=bucket, Key=key, Body=body)
        got = hashlib.sha256(app.get_object(Bucket=bucket, Key=key)["Body"].read()).hexdigest()
        app.delete_object(Bucket=bucket, Key=key)
        if put.get("VersionId"):
            try:
                admin.delete_object(Bucket=bucket, Key=key, VersionId=put["VersionId"])
            except ClientError:
                pass
    except ClientError as e:
        if _code(e) in AUTH_CODES:
            return auth_error(_code(e), "application", app_ids, builtin)
        return fail(f"round-trip with the application identity: {_code(e)} {e}")
    if got != want:
        return fail("round-trip SHA-256 mismatch – the object store returned different bytes")
    print(f"{P} round-trip put/get/delete OK sha256={want[:16]}…")
    print(f"{P} READY")
    return 0


if __name__ == "__main__":
    sys.exit(run())
