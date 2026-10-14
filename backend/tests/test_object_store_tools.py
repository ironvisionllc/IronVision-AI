"""Object-store tooling without MinIO/mc: objsync (dir <-> S3 with SHA-256 manifest), s3_bootstrap, config flags, compose files."""
import json
import os
import pathlib
import subprocess

import pytest

from app.tools import objsync

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_objsync_dir_to_dir_manifest_and_tamper_detection(tmp_path):
    src = tmp_path / "src"
    (src / "a/b").mkdir(parents=True)
    (src / "a/b/one.ckl").write_bytes(b"<CHECKLIST/>")
    (src / "two.nessus").write_bytes(os.urandom(2048))
    assert objsync.main(["copy", f"dir:{src}", f"dir:{tmp_path / 'dst'}"]) == 0
    man = json.loads((tmp_path / "dst" / objsync.MANIFEST).read_text())
    assert man["count"] == 2 and set(man["objects"]) == {"a/b/one.ckl", "two.nessus"}
    assert objsync.main(["verify", f"dir:{tmp_path / 'dst'}", "--manifest", str(tmp_path / "dst" / objsync.MANIFEST)]) == 0
    (tmp_path / "dst" / "two.nessus").write_bytes(b"tampered")
    assert objsync.main(["verify", f"dir:{tmp_path / 'dst'}", "--manifest", str(tmp_path / "dst" / objsync.MANIFEST)]) == 1
    # copying a tampered backup dir onward fails (source differs from its own manifest)
    assert objsync.main(["copy", f"dir:{tmp_path / 'dst'}", f"dir:{tmp_path / 'again'}"]) == 1


def test_objsync_rejects_path_traversal(tmp_path):
    with pytest.raises(ValueError):
        objsync.DirTarget(str(tmp_path)).put("../escape", b"x")


def test_s3_bootstrap_skips_for_local_driver(monkeypatch):
    from app.tools import s3_bootstrap
    monkeypatch.setenv("STORAGE_DRIVER", "local")
    assert s3_bootstrap.run() == 0


def test_s3_client_addressing_style_flag():
    from app.services.storage.s3 import s3_client
    assert s3_client("https://nyc3.digitaloceanspaces.com", "nyc3", "k", "s", "virtual").meta.config.s3["addressing_style"] == "virtual"
    assert s3_client("http://seaweedfs:8333", "us-east-1", "k", "s", None).meta.config.s3["addressing_style"] == "path"
    assert s3_client(None, "us-east-1", "k", "s", "path").meta.config.signature_version == "s3v4"
    with pytest.raises(RuntimeError):
        s3_client(None, None, None, None, "sideways")


def test_check_env_storage_profiles():
    from app.check_env import validate
    base = {"APP_ENV": "development", "POSTGRES_DB": "x", "POSTGRES_USER": "x", "POSTGRES_PASSWORD": "x", "JWT_SECRET": "x",
            "SECRET_STORE_KEY": "x", "CORS_ORIGINS": "http://localhost:3000", "FRONTEND_URL": "x", "AUTH_PROVIDERS": "dev_password"}
    errs, _ = validate({**base, "STORAGE_DRIVER": "local"}, deployed=False)
    assert not [e for e in errs if "S3" in e]
    errs, _ = validate({**base, "STORAGE_DRIVER": "s3", "COMPOSE_PROFILES": "seaweedfs", "S3_BUCKET": "b", "S3_REGION": "r",
                        "S3_ACCESS_KEY_ID": "same", "S3_SECRET_ACCESS_KEY": "s", "S3_ADMIN_ACCESS_KEY_ID": "same",
                        "S3_ADMIN_SECRET_ACCESS_KEY": "t"}, deployed=False)
    assert any("must differ" in e for e in errs)
    errs, warns = validate({**base, "STORAGE_DRIVER": "s3", "S3_BUCKET": "b", "S3_REGION": "nyc3", "MINIO_ROOT_USER": "u",
                            "MINIO_ROOT_PASSWORD": "p", "S3_ENDPOINT_URL": "http://nyc3.digitaloceanspaces.com"}, deployed=False)
    assert any("S3_ACCESS_KEY_ID is required" in e for e in errs)  # the app identity must be a new key, never the old MinIO root
    assert any("MINIO_ROOT_USER is deprecated" in w for w in warns)
    assert any("plain http" in w for w in warns) and any("S3_ADDRESSING_STYLE=virtual" in w for w in warns)
    _, warns = validate({**base, "STORAGE_DRIVER": "s3", "S3_BUCKET": "b", "S3_REGION": "r", "S3_ACCESS_KEY_ID": "a",
                         "S3_SECRET_ACCESS_KEY": "s", "S3_ENDPOINT_URL": "http://seaweedfs:8333"}, deployed=False)
    assert not any("plain http" in w for w in warns)


def test_no_minio_or_mc_left_in_deploy_artifacts():
    files = [ROOT / "docker-compose.yml", ROOT / "docker-compose.prod.yml", *sorted((ROOT / "deploy").rglob("*")), *sorted((ROOT / "scripts").glob("*.sh"))]
    bad = []
    for f in files:
        if f.is_file() and f.suffix in ("", ".yml", ".yaml", ".sh", ".example", ".conf", ".service", ".timer", ".template", ".json"):
            for n, line in enumerate(f.read_text(errors="ignore").splitlines(), 1):
                low = line.lower()
                if ("minio/" in low or "minio:" in low or "quay.io/minio" in low or "registry.min.io" in low
                        or low.strip().startswith("mc ") or " mc alias" in low or " mc mirror" in low or "\"mc\"" in low):
                    bad.append(f"{f.relative_to(ROOT)}:{n}: {line.strip()[:90]}")
    assert not bad, bad


def test_seaweedfs_image_is_pinned():
    txt = (ROOT / "docker-compose.yml").read_text()
    assert "chrislusf/seaweedfs:4.48" in txt and ":latest" not in txt


def test_seaweedfs_entrypoint_refuses_unsafe_credentials(tmp_path):
    env = {"PATH": os.environ["PATH"], "WEED_BIN": "/bin/true", "DATA_DIR": str(tmp_path / "d"), "S3_CONFIG_PATH": str(tmp_path / "s3.json"),
           "S3_BUCKET": "ev", "S3_ADMIN_ACCESS_KEY_ID": "adm", "S3_ADMIN_SECRET_ACCESS_KEY": 'bad"quote', "S3_ACCESS_KEY_ID": "app",
           "S3_SECRET_ACCESS_KEY": "secret"}
    sh = str(ROOT / "deploy/seaweedfs/entrypoint.sh")
    assert subprocess.run(["sh", sh], env=env, capture_output=True).returncode == 2
    env["S3_ADMIN_SECRET_ACCESS_KEY"] = "GoodSecret123"
    assert subprocess.run(["sh", sh], env=env, capture_output=True).returncode == 0
    conf = json.loads((tmp_path / "s3.json").read_text())
    app = next(i for i in conf["identities"] if i["name"] == "ironvision-app")
    assert app["actions"] == ["Read:ev", "Write:ev", "List:ev", "Tagging:ev"]
    assert oct((tmp_path / "s3.json").stat().st_mode)[-3:] == "600"


# ---- deploy hardening: objectstore-init messages, check_env profile consistency, env-secret helper, deploy.sh, overlays

def _boot_env(monkeypatch, **kv):
    for k in ("STORAGE_DRIVER", "S3_ENDPOINT_URL", "S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY", "S3_ADMIN_ACCESS_KEY_ID",
              "S3_ADMIN_SECRET_ACCESS_KEY", "MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("S3_BOOTSTRAP_WAIT_SECONDS", "0")
    for k, v in kv.items():
        monkeypatch.setenv(k, v)


def test_bootstrap_local_is_noop(monkeypatch, capsys):
    from app.tools import s3_bootstrap
    _boot_env(monkeypatch, STORAGE_DRIVER="local")
    assert s3_bootstrap.run() == 0
    assert "local storage driver – nothing to initialize" in capsys.readouterr().out


def test_bootstrap_requires_driver_and_names_missing_vars(monkeypatch, capsys):
    from app.tools import s3_bootstrap
    _boot_env(monkeypatch)
    assert s3_bootstrap.run() == 1
    assert "STORAGE_DRIVER must be 's3' or 'local'" in capsys.readouterr().out
    _boot_env(monkeypatch, STORAGE_DRIVER="s3", S3_ENDPOINT_URL="http://seaweedfs:8333", S3_BUCKET="b")
    assert s3_bootstrap.run() == 1
    out = capsys.readouterr().out
    for k in ("S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY", "S3_ADMIN_ACCESS_KEY_ID", "S3_ADMIN_SECRET_ACCESS_KEY"):
        assert k in out
    assert "scripts/deploy.sh" in out


def test_bootstrap_builtin_store_not_running_says_profile_required(monkeypatch, capsys):
    import socket
    from app.tools import s3_bootstrap

    def nores(*a, **k):
        raise socket.gaierror(-2, "Name or service not known")
    _boot_env(monkeypatch, STORAGE_DRIVER="s3", S3_ENDPOINT_URL="http://seaweedfs:8333", S3_BUCKET="b", S3_ACCESS_KEY_ID="a",
              S3_SECRET_ACCESS_KEY="s", S3_ADMIN_ACCESS_KEY_ID="ad", S3_ADMIN_SECRET_ACCESS_KEY="as")
    monkeypatch.setattr(socket, "create_connection", nores)
    assert s3_bootstrap.run() == 1
    out = capsys.readouterr().out
    assert "cannot resolve host 'seaweedfs'" in out and "COMPOSE_PROFILES=seaweedfs is required" in out


def test_bootstrap_external_endpoint_unreachable(monkeypatch, capsys):
    from app.tools import s3_bootstrap
    _boot_env(monkeypatch, STORAGE_DRIVER="s3", S3_ENDPOINT_URL="http://127.0.0.1:9", S3_BUCKET="b", S3_ACCESS_KEY_ID="a",
              S3_SECRET_ACCESS_KEY="topsecretvalue")
    assert s3_bootstrap.run() == 1
    out = capsys.readouterr().out
    assert "unreachable" in out and "Check S3_ENDPOINT_URL" in out and "topsecretvalue" not in out


def test_bootstrap_auth_failure_is_explained(monkeypatch, capsys):
    from botocore.exceptions import ClientError
    from app.tools import s3_bootstrap

    class Fake:
        def head_bucket(self, **k):
            raise ClientError({"Error": {"Code": "SignatureDoesNotMatch", "Message": "x"}}, "HeadBucket")
    _boot_env(monkeypatch, STORAGE_DRIVER="s3", S3_ENDPOINT_URL="", S3_BUCKET="b", S3_ACCESS_KEY_ID="a", S3_SECRET_ACCESS_KEY="s")
    monkeypatch.setattr(s3_bootstrap, "s3_client", lambda **k: Fake())
    assert s3_bootstrap.run() == 1
    out = capsys.readouterr().out
    assert "authentication failed for the admin identity (S3_ACCESS_KEY_ID / S3_SECRET_ACCESS_KEY)" in out
    assert "secret key does not match" in out


def test_check_env_object_store_profile_consistency():
    from app.check_env import validate
    base = {"APP_ENV": "development", "POSTGRES_DB": "x", "POSTGRES_USER": "x", "POSTGRES_PASSWORD": "x", "JWT_SECRET": "x",
            "SECRET_STORE_KEY": "x", "CORS_ORIGINS": "http://localhost:3000", "FRONTEND_URL": "x", "AUTH_PROVIDERS": "dev_password"}
    s3 = {**base, "STORAGE_DRIVER": "s3", "S3_BUCKET": "b", "S3_REGION": "r", "S3_ACCESS_KEY_ID": "a", "S3_SECRET_ACCESS_KEY": "s",
          "S3_ADMIN_ACCESS_KEY_ID": "ad", "S3_ADMIN_SECRET_ACCESS_KEY": "as"}
    errs, _ = validate(s3, deployed=False)
    assert any("COMPOSE_PROFILES=seaweedfs is required" in e for e in errs)
    errs, _ = validate({**s3, "COMPOSE_PROFILES": "seaweedfs"}, deployed=False)
    assert not [e for e in errs if "COMPOSE_PROFILES" in e or "S3" in e]
    errs, _ = validate({**s3, "COMPOSE_PROFILES": "seaweedfs", "S3_ENDPOINT_URL": "https://nyc3.digitaloceanspaces.com"}, deployed=False)
    assert any("remove seaweedfs from COMPOSE_PROFILES" in e for e in errs)
    errs, _ = validate({**base, "STORAGE_DRIVER": "local", "COMPOSE_PROFILES": "seaweedfs"}, deployed=False)
    assert any("remove seaweedfs" in e for e in errs)
    errs, _ = validate(base, deployed=False)
    assert any("STORAGE_DRIVER is required" in e for e in errs)


def test_gen_env_secrets_fills_only_empty(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("gen_env_secrets", ROOT / "scripts" / "gen_env_secrets.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    f = tmp_path / ".env.production"
    f.write_text("# c\nSTORAGE_DRIVER=s3\nS3_ENDPOINT_URL=\nPOSTGRES_PASSWORD=keepme\nJWT_SECRET=\nS3_ACCESS_KEY_ID=\nS3_SECRET_ACCESS_KEY=\"\"\n")
    filled, kept = mod.fill(f)
    env = dict(line.split("=", 1) for line in f.read_text().splitlines() if line and not line.startswith("#"))
    assert env["POSTGRES_PASSWORD"] == "keepme" and "POSTGRES_PASSWORD" in kept
    assert len(env["JWT_SECRET"]) == 48 and env["S3_ACCESS_KEY_ID"].startswith("ivapp") and len(env["S3_SECRET_ACCESS_KEY"]) == 48
    assert env["S3_ADMIN_ACCESS_KEY_ID"].startswith("ivadmin") and env["S3_ADMIN_ACCESS_KEY_ID"] != env["S3_ACCESS_KEY_ID"]
    assert set(filled) >= {"JWT_SECRET", "S3_ACCESS_KEY_ID", "S3_ADMIN_SECRET_ACCESS_KEY", "SECRET_STORE_KEY"}
    assert oct(f.stat().st_mode & 0o777) == "0o600"
    before = f.read_text()
    assert mod.fill(f)[0] == [] and f.read_text() == before          # idempotent: never overwrites
    ext = tmp_path / "ext.env"
    ext.write_text("STORAGE_DRIVER=s3\nS3_ENDPOINT_URL=https://nyc3.digitaloceanspaces.com\nS3_ACCESS_KEY_ID=\n")
    mod.fill(ext)
    assert "S3_ACCESS_KEY_ID=\n" in ext.read_text()                  # provider keys are never invented


def test_deploy_script_is_fail_fast_and_ordered():
    import subprocess
    p = ROOT / "scripts" / "deploy.sh"
    s = p.read_text()
    assert p.stat().st_mode & 0o111 and "set -Eeuo pipefail" in s and subprocess.run(["bash", "-n", str(p)]).returncode == 0
    assert 'LEGACY_PROJECT="aegisrmf"' in s and 'PROJECT="${PROJECT:-ironvision}"' in s and "--env-file \"$ENV_FILE\"" in s
    assert s.count("#### DEPLOYMENT SUCCEEDED") == 1
    order = ["python3 scripts/check_env.py", "config -q", "pull --ignore-buildable", "build", "-T backend python -m app.tools.selfcheck", "-T worker python -m app.tools.selfcheck", "--wait-timeout 180 postgres",
             "--wait-timeout 180 seaweedfs", "run --rm --no-deps objectstore-init", "run --rm --no-deps migrate",
             "up -d --no-deps", "/api/v1/ready", "#### DEPLOYMENT SUCCEEDED"]
    body = s[s.index("# ---------------------------------------------------------------- preflight"):]
    pos = [body.index(o) for o in order]
    assert pos == sorted(pos)
    assert "Deployment complete" not in s


def test_storage_overlays_require_variables():
    s3 = (ROOT / "deploy/compose/storage-s3.yml").read_text()
    sw = (ROOT / "deploy/compose/storage-seaweedfs.yml").read_text()
    assert "${S3_ACCESS_KEY_ID:?" in s3 and "${S3_SECRET_ACCESS_KEY:?" in s3 and "${S3_BUCKET:?" in s3
    assert "MINIO_ROOT_USER:?S3_ADMIN_ACCESS_KEY_ID must be set" in sw and "required: true" in sw
    for f in ("docker-compose.yml", "deploy/digitalocean/docker-compose.do.yml"):
        assert "${STORAGE_DRIVER:?STORAGE_DRIVER must be set" in (ROOT / f).read_text()
