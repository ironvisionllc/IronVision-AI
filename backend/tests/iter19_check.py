import collections
import requests
API = "https://aegis-rmf-demo.preview.emergentagent.com/api/v1"
LTP = "3630fca0-4fb1-45d5-b020-a93156344bb4"
t = requests.post(f"{API}/auth/login", json={"email": "demo@ironvision.ai", "password": "IronVisionDemo!2026"}).json()["access_token"]
h = {"Authorization": f"Bearer {t}"}
r = requests.get(f"{API}/tr/workbooks/633bf62e-e1f8-4246-958e-a478d50c0247/rows", headers=h)
print("rows", r.status_code)
d = r.json()
rows = d if isinstance(d, list) else d.get("items") or d.get("rows") or []
print(len(rows), rows[0].keys() if rows else None)
print(collections.Counter(str(x.get("status") or x.get("review_status") or x.get("approved")) for x in rows))
s = requests.get(f"{API}/systems/{LTP}", headers=h).json()
print("LTP emass_id", s.get("emass_id"), s.get("description")[:60] if s.get("description") else None)
for p in ("/audit", "/audit-events", "/audit/events", "/admin/audit"):
    a = requests.get(f"{API}{p}", headers=h, params={"limit": 30})
    print(p, a.status_code)
    if a.status_code == 200:
        txt = a.text
        i = txt.find("eMASS ")
        print(txt[i - 100:i + 250] if i >= 0 else "no eMASS source found")
        break
print(collections.Counter(str(x.get("state")) for x in rows), collections.Counter(str(x.get("decided_by")) for x in rows))
