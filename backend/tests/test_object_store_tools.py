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
