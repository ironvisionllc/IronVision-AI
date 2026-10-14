"""One-shot, idempotent object-store bootstrap (replaces the old `mc`-based init container).

    python -m app.tools.s3_bootstrap

1. bucket S3_BUCKET exists (created with the admin identity if missing)
2. versioning enabled when the backend supports it (S3_BUCKET_VERSIONING=true, default)
3. optional bucket policy from S3_BUCKET_POLICY_FILE (JSON) when the backend supports it
4. put/get/delete round-trip with the *application* identity, verified by SHA-256
Admin identity: S3_ADMIN_ACCESS_KEY_ID / S3_ADMIN_SECRET_ACCESS_KEY (falls back to the app identity, e.g. Spaces/AWS keys).
Exit 0 = ready; 1 = not usable. STORAGE_DRIVER=local → nothing to do (exit 0)."""
import hashlib
import json
import os
import sys
import uuid

from botocore.exceptions import ClientError

from app.services.storage.s3 import s3_client


def _env(k: str, *aliases: str) -> str | None:
    for name in (k, *aliases):
        if os.environ.get(name):
            if name != k:
                print(f"[s3-bootstrap] WARNING {name} is deprecated – use {k}")
            return os.environ[name]
    return None


def _code(e: ClientError) -> str:
    return str(e.response.get("Error", {}).get("Code", ""))


def run() -> int:
    if (os.environ.get("STORAGE_DRIVER") or "s3") != "s3":
        print("[s3-bootstrap] STORAGE_DRIVER is not s3 – nothing to bootstrap")
        return 0
    bucket = os.environ.get("S3_BUCKET")
    if not bucket:
        print("[s3-bootstrap] FAIL S3_BUCKET is required")
        return 1
    common = {"endpoint_url": os.environ.get("S3_ENDPOINT_URL"), "region": os.environ.get("S3_REGION") or "us-east-1",
              "addressing_style": os.environ.get("S3_ADDRESSING_STYLE") or "path"}
    app_key = _env("S3_ACCESS_KEY_ID")
    app_secret = _env("S3_SECRET_ACCESS_KEY")
    admin = s3_client(access_key_id=_env("S3_ADMIN_ACCESS_KEY_ID", "MINIO_ROOT_USER") or app_key,
                      secret_access_key=_env("S3_ADMIN_SECRET_ACCESS_KEY", "MINIO_ROOT_PASSWORD") or app_secret, **common)
    app = s3_client(access_key_id=app_key, secret_access_key=app_secret, **common)
    print(f"[s3-bootstrap] endpoint={common['endpoint_url'] or 'AWS default'} bucket={bucket} addressing={common['addressing_style']}")

    try:
        admin.head_bucket(Bucket=bucket)
        print("[s3-bootstrap] bucket exists")
    except ClientError as e:
        if _code(e) not in ("404", "NoSuchBucket", "NotFound"):
            print(f"[s3-bootstrap] FAIL head_bucket: {_code(e)} {e}")
            return 1
        kw = {}
        if common["region"] != "us-east-1" and not common["endpoint_url"]:
            kw["CreateBucketConfiguration"] = {"LocationConstraint": common["region"]}
        admin.create_bucket(Bucket=bucket, **kw)
        print("[s3-bootstrap] bucket created")

    if (os.environ.get("S3_BUCKET_VERSIONING") or "true").lower() == "true":
        try:
            admin.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})
            st = admin.get_bucket_versioning(Bucket=bucket).get("Status", "unknown")
            print(f"[s3-bootstrap] versioning: {st}")
        except ClientError as e:
            print(f"[s3-bootstrap] versioning not supported by this backend ({_code(e)}) – continuing")

    pol = os.environ.get("S3_BUCKET_POLICY_FILE")
    if pol:
        try:
            with open(pol) as fh:
                admin.put_bucket_policy(Bucket=bucket, Policy=json.dumps(json.load(fh)))
            print("[s3-bootstrap] bucket policy applied")
        except ClientError as e:
            print(f"[s3-bootstrap] bucket policy not supported by this backend ({_code(e)}) – access is enforced by identities")
    else:
        print("[s3-bootstrap] no bucket policy configured (access is enforced by the S3 identities)")

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
        print(f"[s3-bootstrap] FAIL round-trip with the application identity: {_code(e)} {e}")
        return 1
    if got != want:
        print("[s3-bootstrap] FAIL round-trip SHA-256 mismatch")
        return 1
    print(f"[s3-bootstrap] round-trip put/get/delete OK sha256={want[:16]}…")
    print("[s3-bootstrap] READY")
    return 0


if __name__ == "__main__":
    sys.exit(run())
