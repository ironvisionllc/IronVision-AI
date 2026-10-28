"""Live-preview sign-in for regression tests: demo-login is rate limited (30/h per IP), so fall back to the demo account password
(documented in /app/memory/test_credentials.md) instead of failing the whole serial suite."""
import os

import requests


def demo_token(api: str) -> str:
    """api = '<preview>/api/v1'."""
    r = requests.post(f"{api}/auth/demo-login", json={}, timeout=30)
    if r.status_code == 429:
        r = requests.post(f"{api}/auth/login", json={"email": "demo@ironvision.ai", "password": os.environ.get("DEMO_PASSWORD", "IronVisionDemo!2026")},
                          timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]
