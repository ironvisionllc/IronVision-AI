"""Smoke + security tests for the Docs Center endpoints. Run via requests against the live preview URL."""
import os
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://aegis-rmf-demo.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api/v1"
EMAIL = "isso@aegisrmf.demo"
PASSWORD = "AegisDemo!2026"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def hdr(token):
    return {"Authorization": f"Bearer {token}"}


# --- auth gating ---
def test_list_requires_auth():
    r = requests.get(f"{API}/docs-center", timeout=20)
    assert r.status_code == 401


def test_doc_requires_auth():
    r = requests.get(f"{API}/docs-center/digitalocean", timeout=20)
    assert r.status_code == 401


def test_download_requires_auth():
    r = requests.get(f"{API}/docs-center/digitalocean/download", timeout=20)
    assert r.status_code == 401


def test_archive_requires_auth():
    r = requests.get(f"{API}/docs-center/archive.zip", timeout=20)
    assert r.status_code == 401


# --- happy path ---
def test_list_authed(hdr):
    r = requests.get(f"{API}/docs-center", headers=hdr, timeout=20)
    assert r.status_code == 200
    items = r.json()["items"]
    slugs = {i["slug"] for i in items}
    assert "digitalocean" in slugs
    assert "readme" in slugs
    # all expected titles must be strings
    for it in items:
        assert isinstance(it["title"], str) and it["title"]


def test_get_digitalocean_doc(hdr):
    r = requests.get(f"{API}/docs-center/digitalocean", headers=hdr, timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert data["slug"] == "digitalocean"
    md = data["markdown"]
    assert "documentation only" in md.lower()
    # Count numbered H2s
    lines = [ln for ln in md.splitlines() if ln.startswith("## ")]
    # Expect 13 numbered sections
    numbered = [ln for ln in lines if any(ln.startswith(f"## {n}") or ln.startswith(f"## {n}.") for n in range(1, 20))]
    assert len(numbered) >= 13, f"Expected >=13 numbered sections, got {len(numbered)}: {numbered}"


def test_download_digitalocean_md(hdr):
    r = requests.get(f"{API}/docs-center/digitalocean/download", headers=hdr, timeout=20)
    assert r.status_code == 200
    assert "text/markdown" in r.headers.get("content-type", "")
    assert "attachment" in r.headers.get("content-disposition", "").lower()
    assert b"documentation only" in r.content.lower() or b"DigitalOcean" in r.content


def test_archive_zip(hdr):
    r = requests.get(f"{API}/docs-center/archive.zip", headers=hdr, timeout=30)
    assert r.status_code == 200
    assert r.headers.get("content-type") == "application/zip"
    assert r.content[:2] == b"PK"  # zip magic
    assert len(r.content) > 1000


# --- security: unknown slugs & traversal ---
@pytest.mark.parametrize("slug", [
    "etc-passwd",
    "unknown-slug",
    "..%2F..%2Fbackend%2F.env",
    "../../backend/.env",
    "....//....//etc/passwd",
    "readme%00.md",
])
def test_bad_slugs_return_404(hdr, slug):
    r = requests.get(f"{API}/docs-center/{slug}", headers=hdr, timeout=20)
    assert r.status_code in (404, 400), f"{slug} -> {r.status_code}"
    body = r.text.lower()
    # must never leak sensitive content
    assert "jwt_secret" not in body
    assert "mongo_url" not in body
    assert "postgres" not in body or "deployment" in body  # avoid false positive from json error "postgres"
    assert "root:x:" not in body


def test_bad_slug_download_404(hdr):
    r = requests.get(f"{API}/docs-center/etc-passwd/download", headers=hdr, timeout=20)
    assert r.status_code in (404, 400)
