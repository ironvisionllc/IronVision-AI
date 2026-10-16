"""selfcheck under a scrubbed environment (env -i): the image-build check must not pass thanks to pod/developer env or backend/.env."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]


def _tree(tmp_path: Path) -> Path:
    d = tmp_path / "img"
    shutil.copytree(BACKEND / "app", d / "app", ignore=shutil.ignore_patterns("__pycache__"))
    if (BACKEND / "worker").is_dir():
        shutil.copytree(BACKEND / "worker", d / "worker", ignore=shutil.ignore_patterns("__pycache__"))
    # a .env exactly like the pod's: must be IGNORED by the selfcheck
    (d / ".env").write_text("DATABASE_URL=postgresql://leak@localhost/leak\nJWT_SECRET=leak\nNEW_REQUIRED_SETTING=leak\n")
    return d


def _run(d: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["env", "-i", "PATH=/usr/local/bin:/usr/bin:/bin", "HOME=/tmp", sys.executable, "-m", "app.tools.selfcheck", *args],
                          cwd=d, capture_output=True, text=True, timeout=300)


def _append(d: Path, rel: str, code: str) -> None:
    p = d / rel
    p.write_text(p.read_text() + "\n" + code + "\n")


@pytest.mark.parametrize("target", [["--recovery"], []])
def test_clean_scrubbed_env_passes(tmp_path, target):
    r = _run(_tree(tmp_path), *target)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "RESULT: PASS" in r.stdout or "RESULT: PASS" in r.stdout.splitlines()[-1]
    assert "network blocked" in r.stdout


def test_hidden_real_package_fails_naming_it(tmp_path):
    d = _tree(tmp_path)
    (d / "msgpack").mkdir()
    (d / "msgpack" / "__init__.py").write_text("raise ModuleNotFoundError(\"No module named 'msgpack'\", name='msgpack')\n")
    r = _run(d, "--recovery")
    assert r.returncode == 1
    assert "[missing-module]" in r.stdout and "msgpack" in r.stdout and "RESULT: FAIL" in r.stdout


def test_syntax_error_in_app_module_fails(tmp_path):
    d = _tree(tmp_path)
    _append(d, "app/tools/minio_xl.py", "def broken(:\n    pass")
    r = _run(d, "--recovery")
    assert r.returncode == 1 and "app.tools.minio_xl" in r.stdout and "SyntaxError" in r.stdout


def test_internal_import_error_fails(tmp_path):
    d = _tree(tmp_path)
    _append(d, "app/tools/minio_xl.py", "import app.tools.does_not_exist_xyz  # noqa")
    r = _run(d, "--recovery")
    assert r.returncode == 1 and "[missing-module]" in r.stdout and "does_not_exist_xyz" in r.stdout


@pytest.mark.parametrize("target", [["--recovery"], []])
def test_network_at_import_fails(tmp_path, target):
    d = _tree(tmp_path)
    _append(d, "app/tools/minio_xl.py", "import socket as _s\n_s.create_connection(('example.com', 80), timeout=1)")
    r = _run(d, *target)
    assert r.returncode == 1 and "[import-network]" in r.stdout and "app.tools.minio_xl" in r.stdout


@pytest.mark.parametrize("target", [["--recovery"], []])
def test_new_required_setting_at_import_fails_even_if_in_dotenv(tmp_path, target):
    d = _tree(tmp_path)
    _append(d, "app/tools/minio_xl.py", "from app.config import _req as _r\n_r('NEW_REQUIRED_SETTING')")
    r = _run(d, *target)
    assert r.returncode == 1
    assert "[import-config]" in r.stdout and "NEW_REQUIRED_SETTING" in r.stdout and "not in the build profile" in r.stdout


def test_db_engine_is_lazy_and_still_fails_fast_on_use(tmp_path):
    d = _tree(tmp_path)
    code = ("import app.db as db\nassert db._engine is None\n"
            "try:\n    db.SessionLocal()\nexcept RuntimeError as e:\n    print('FAILFAST', e)\n")
    r = subprocess.run(["env", "-i", "PATH=/usr/bin:/bin", "HOME=/tmp", "IRONVISION_SELFCHECK=1", sys.executable, "-c", code],
                       cwd=d, capture_output=True, text=True, timeout=60)
    assert "FAILFAST Required environment variable DATABASE_URL is not set" in r.stdout, r.stdout + r.stderr
