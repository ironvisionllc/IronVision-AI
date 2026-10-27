#!/usr/bin/env python3
"""UAT watcher for the 942 UI run: when the ISSO's bulk job starts, decide the LAST queued item individually (→ the job must
report it as skipped, not decide it twice); when the job finishes, restore the SYN-FAIL policy so "Retry failed only" can succeed."""
import json
import subprocess
import sys
import time
import uuid

import httpx

sys.path.insert(0, "/app/backend")
from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Job  # noqa: E402
import os  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

API = "http://localhost:8001/api/v1"
st = json.load(open("/tmp/uat942.json"))
c = httpx.Client(timeout=60)
t = c.post(f"{API}/auth/login", json={"email": st["email"], "password": st["password"]}).json()["access_token"]
h = {"Authorization": f"Bearer {c.post(f'{API}/sandbox/act-as', json={'role': 'isso'}, headers={'Authorization': f'Bearer {t}'}).json()['access_token']}"}
log = {"started": time.time()}
t0 = datetime.now(timezone.utc)
concurrent = os.environ.get("NO_CONCURRENT") != "1"
job = None
while time.time() - log["started"] < 900:
    with SessionLocal() as db:
        job = db.scalar(select(Job).where(Job.job_type == "review.bulk", Job.payload["system_id"].astext == st["system_id"], Job.created_at > t0,
                                          Job.payload["retry_of"].astext.is_(None) | (Job.payload["retry_of"].astext == "null")).order_by(Job.created_at.desc()).limit(1))
        if job is not None:
            jid, last = str(job.id), job.payload["items"][-1]
            break
    time.sleep(0.2)
r = None if not concurrent else c.post(f"{API}/mapping-review/decide", json={"system_id": st["system_id"], "action": "approve", "justification": "SYNTHETIC concurrent single decision",
                                                 "items": [{k: last.get(k) for k in ("kind", "key", "ids", "control_id", "evidence_fp")}]}, headers=h)
log.update(job_id=jid, concurrent_decided=last["key"], concurrent_status=r.status_code if r else None)
if not concurrent:
    log["concurrent_decided"] = None
while True:
    with SessionLocal() as db:
        j = db.get(Job, uuid.UUID(jid))
        if j.status in ("succeeded", "failed"):
            log["result"] = {k: (len(v) if isinstance(v, list) else v) for k, v in (j.result or {}).items() if k != "succeeded_keys"}
            break
    time.sleep(0.5)
time.sleep(3)
subprocess.run([sys.executable, "/app/scripts/uat_seed_942.py", "restore", "/tmp/uat942.json"], check=True)
log["restored_at"] = time.time()
json.dump(log, open("/tmp/uat942_watch.json", "w"), indent=1)
print(json.dumps(log))
