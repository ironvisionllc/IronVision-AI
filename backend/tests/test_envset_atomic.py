"""scripts/envset.py: atomic env writes (temp + fsync + rename, mode 600) – a failure at any point leaves the original byte-identical."""
import hashlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ENVSET = ROOT / "scripts" / "envset.py"
ORIG = b'POSTGRES_USER=u\nDATABASE_URL="postgresql+psycopg://u:p@postgres:5432/ironvision"\n# comment \xc3\xa9\nX=1\n'


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _run(*args, stdin="", **env):
    return subprocess.run([sys.executable, str(ENVSET), *args], input=stdin, capture_output=True, text=True, check=False,
                          env={"PATH": os.environ["PATH"], **env})


@pytest.fixture
def envf(tmp_path):
    p = tmp_path / ".env.production"
    p.write_bytes(ORIG)
    os.chmod(p, 0o640)
    return p


def _leftovers(p: Path) -> list:
    return [x.name for x in p.parent.iterdir() if "envsettmp" in x.name]


def test_set_is_atomic_mode_600_and_backs_up_byte_exact(envf):
    r = _run(str(envf), "DATABASE_URL", stdin="postgresql+psycopg://u:p@postgres:5432/ironvision_recovered_x")
    assert r.returncode == 0 and "ironvision_recovered_x" not in r.stdout          # never prints the value
    assert "ironvision_recovered_x" in envf.read_text() and oct(envf.stat().st_mode & 0o777) == "0o600"
    bk = [x for x in envf.parent.iterdir() if ".bak-" in x.name]
    assert len(bk) == 1 and bk[0].read_bytes() == ORIG and oct(bk[0].stat().st_mode & 0o777) == "0o600"
    assert _leftovers(envf) == []


def test_fault_before_rename_leaves_the_original_byte_identical_and_no_temp(envf):
    sha = _sha(envf)
    r = _run(str(envf), "DATABASE_URL", stdin="postgresql+psycopg://u:p@h/new", RECOVER_LOCAL="1", ENVSET_FAULT="before-rename")
    assert r.returncode != 0 and "injected fault" in r.stderr
    assert _sha(envf) == sha and _leftovers(envf) == []


def test_fault_hook_is_inert_outside_test_mode(envf):
    r = _run(str(envf), "DATABASE_URL", stdin="postgresql+psycopg://u:p@h/new", ENVSET_FAULT="before-rename")
    assert r.returncode == 0 and "/new" in envf.read_text()


def test_crash_during_write_or_fsync_keeps_the_original(envf, monkeypatch):
    spec = importlib.util.spec_from_file_location("envset_mod", ENVSET)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    sha = _sha(envf)

    def boom(fd):
        raise OSError("disk full (simulated)")
    monkeypatch.setattr(m.os, "fsync", boom)
    with pytest.raises(OSError, match="disk full"):
        m.atomic_write(envf, b"DATABASE_URL=half-written")
    assert _sha(envf) == sha and _leftovers(envf) == []


def test_copy_is_byte_exact_and_600(envf, tmp_path):
    dst = tmp_path / "restored.env"
    dst.write_bytes(b"something else")
    assert _run("--copy", str(envf), str(dst)).returncode == 0
    assert dst.read_bytes() == ORIG and oct(dst.stat().st_mode & 0o777) == "0o600" and _leftovers(dst) == []
