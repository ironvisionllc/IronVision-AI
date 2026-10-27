import requests
API = "https://aegis-rmf-demo.preview.emergentagent.com/api/v1"
LTP = "3630fca0-4fb1-45d5-b020-a93156344bb4"
t = requests.post(f"{API}/auth/login", json={"email": "demo@ironvision.ai", "password": "IronVisionDemo!2026"}).json()["access_token"]
h = {"Authorization": f"Bearer {t}"}
print("desc now:", requests.get(f"{API}/systems/{LTP}", headers=h).json().get("description"))
a = requests.get(f"{API}/audit-events", headers=h, params={"limit": 20}).json()
for e in a[:20]:
    if e.get("action") == "system.updated":
        print("audit:", e["action"], e.get("details", {}).get("source")); break
r = requests.patch(f"{API}/systems/{LTP}", headers=h, json={"description": "Logistics Tracking Platform (SYNTHETIC)"})
print("restore", r.status_code, requests.get(f"{API}/systems/{LTP}", headers=h).json().get("description"))
