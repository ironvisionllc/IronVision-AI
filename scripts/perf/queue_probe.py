#!/usr/bin/env python3
"""Review Queue responsiveness while a policy analysis runs: GET /mapping-review (UAT sandbox ISSO) every 2 s for N seconds → p50/p95/max."""
import json
import sys
import time

import httpx

API = "http://localhost:8001/api/v1"
st = json.load(open("/tmp/uat942.json"))
c = httpx.Client(timeout=60)
t = c.post(f"{API}/auth/login", json={"email": st["email"], "password": st["password"]}).json()["access_token"]
h = {"Authorization": "Bearer " + c.post(f"{API}/sandbox/act-as", json={"role": "isso"}, headers={"Authorization": f"Bearer {t}"}).json()["access_token"]}
lat, end = [], time.time() + int(sys.argv[1] if len(sys.argv) > 1 else 120)
while time.time() < end:
    t0 = time.perf_counter()
    r = c.get(f"{API}/mapping-review", params={"system_id": st["system_id"]}, headers=h)
    lat.append((time.perf_counter() - t0) * 1000)
    assert r.status_code == 200, r.text[:200]
    time.sleep(2)
lat.sort()
print(json.dumps({"requests": len(lat), "p50_ms": round(lat[len(lat) // 2]), "p95_ms": round(lat[int(len(lat) * .95) - 1]), "max_ms": round(lat[-1])}))
