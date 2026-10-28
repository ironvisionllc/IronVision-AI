"""Resolve demo-sandbox system ids by acronym (the nightly sandbox reset re-creates systems with new UUIDs)."""
import requests


def system_id(api: str, acronym: str, fallback: str) -> str:
    try:
        t = requests.post(f"{api}/auth/login", json={"email": "demo@ironvision.ai", "password": "IronVisionDemo!2026"}, timeout=30).json()["access_token"]
        rows = requests.get(f"{api}/systems", headers={"Authorization": f"Bearer {t}"}, timeout=30).json()
        return next((r["id"] for r in rows if r.get("acronym") == acronym and not r.get("archived_at")), fallback)
    except Exception:
        return fallback
