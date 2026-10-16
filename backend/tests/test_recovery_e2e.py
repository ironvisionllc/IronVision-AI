"""End-to-end recovery rehearsal in the pod: real PostgreSQL 16, SeaweedFS 4.48, Keycloak 26.8.1, replicas from
tests/recovery_replicas.py. Run: RECOVERY_E2E=1 pytest -n 0 tests/test_recovery_e2e.py (see docs/RECOVERY_REPORT.md)."""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.skipif(os.environ.get("RECOVERY_E2E") != "1", reason="RECOVERY_E2E=1 (pod replicas + SeaweedFS) only")
BACKEND = Path(__file__).resolve().parents[1]
REP = Path(os.environ.get("RECOVERY_REPLICAS", "/tmp/recrep"))
RUN = Path(os.environ.get("RECOVERY_RUN_DIR", "/tmp/recrun"))
BASE = os.environ.get("RECOVERY_BASE_DATABASE_URL", "")
ROWS: list[tuple[str, str, str]] = []


def u(db: str) -> str:
    return make_url(BASE).set(database=db).render_as_string(hide_password=False)


def env(**kw) -> dict:
    e = {**os.environ, "RECOVERY_DIR": str(RUN), "DATABASE_URL": u("rec_live_prod"), "RECOVER_ADMIN_DATABASE_URL": u("postgres"),
         "RECOVER_SOURCE_BACKUP": str(REP / "aegisrmf-old-db.backup"), "RECOVER_PROD_ROLLBACK_BACKUP": str(REP / "ironvision-production-before-restore.backup"),
         "RECOVER_OBJECT_ARCHIVE": str(REP / "aegisrmf-minio-backup.tar.gz"), "RECOVER_SOURCE_INSPECT_URL": u("rec_replica_source"),
         "STORAGE_DRIVER": "s3", "S3_ENDPOINT_URL": "http://127.0.0.1:18333", "S3_BUCKET": "evidence-live", "S3_REGION": "us-east-1",
         "S3_ADDRESSING_STYLE": "path", "S3_ACCESS_KEY_ID": "recapp", "S3_SECRET_ACCESS_KEY": "rec-app-secret-0123456789abcdef",
         "RECOVER_S3_ADMIN_ACCESS_KEY_ID": "recadmin", "RECOVER_S3_ADMIN_SECRET_ACCESS_KEY": "rec-admin-secret-0123456789abcdef", "PYTHONPATH": str(BACKEND)}
    e.update(kw)
    return e


def rec(*args, **kw) -> subprocess.CompletedProcess:
    r = subprocess.run([sys.executable, "-m", "app.tools.recovery", *args], env=env(**kw), cwd=BACKEND, capture_output=True, text=True, timeout=600, check=False)
    print(r.stdout[-3000:], r.stderr[-3000:])
    return r


def step(name: str, ok: bool, detail: str = "") -> None:
    ROWS.append((name, "PASS" if ok else "FAIL", detail))
    (RUN / "e2e-table.json").write_text(json.dumps(ROWS, indent=1))
    assert ok, f"{name}: {detail}"


def latest(kind: str) -> dict:
    return json.loads(max(RUN.glob(f"{kind}-*.json")).read_text())


def admin_s3():
    from app.services.storage.s3 import s3_client
    return s3_client("http://127.0.0.1:18333", "us-east-1", "recadmin", "rec-admin-secret-0123456789abcdef", "path")


@pytest.fixture(scope="module", autouse=True)
def fresh_replicas():
    """Every run starts from a fresh source/prod replica (the rollback step migrates rec_live_prod, like a redeploy)."""
    subprocess.run([sys.executable, str(BACKEND / "tests" / "recovery_replicas.py"), str(REP)], cwd=BACKEND, check=True, timeout=900,
                   env={**os.environ, "DATABASE_URL": BASE, "PYTHONPATH": str(BACKEND)})


def probe_rehearsal(label: str) -> None:
    rh, port = latest("rehearsal"), 8012
    be = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)], cwd=BACKEND,
                          env=env(DATABASE_URL=u(rh["result"]["target_db"]), S3_BUCKET=rh["scratch"]["bucket"], S3_ACCESS_KEY_ID="recadmin",
                                  S3_SECRET_ACCESS_KEY="rec-admin-secret-0123456789abcdef", WORKER_ENABLED="false"),
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                if httpx.get(f"http://127.0.0.1:{port}/api/v1/health/live", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(1)
        r = rec("rehearse-probe", "--url", f"http://127.0.0.1:{port}")
        step(label, r.returncode == 0, r.stdout.strip().splitlines()[-1][-200:])
    finally:
        be.terminate()
        be.wait()


def test_recovery_end_to_end():
    import shutil
    shutil.rmtree(RUN, ignore_errors=True)
    RUN.mkdir(parents=True)
    ev = json.loads((REP / "evidence.json").read_text())
    arch = json.loads((REP / "archive-plan.json").read_text())
    s3 = admin_s3()
    try:
        s3.create_bucket(Bucket="evidence-live")
    except Exception:  # noqa: BLE001, S110 - bucket already exists
        pass
    for o in s3.list_objects_v2(Bucket="evidence-live").get("Contents", []):
        s3.delete_object(Bucket="evidence-live", Key=o["Key"])
    s3.put_object(Bucket="evidence-live", Key="existing/unrelated.txt", Body=b"pre-existing production object")
    same = next(e for e in ev if e["key"] not in (arch["missing"], arch["corrupted"]))
    s3.put_object(Bucket="evidence-live", Key=same["key"], Body=(REP / "store" / same["key"]).read_bytes())  # identical → kept, not overwritten

    r = rec("preflight")
    step("preflight (read-only) incl. SeaweedFS checks", r.returncode == 0, re.findall(r"plan-hash \w+", r.stdout)[-1] if r.returncode == 0 else r.stdout[-300:])
    plan_hash = rec("plan-hash").stdout.strip().splitlines()[-1]
    pf = latest("plan")
    step("SeaweedFS app key scoped to evidence bucket", any(c[1] == "app key scope" and c[0] == "OK" for c in pf["checks"]), json.dumps(pf["checks"][-4:])[:300])

    r = rec("rehearse")
    rh = latest("rehearsal")
    res = rh.get("result") or {}
    step("rehearse: isolated scratch DBs + bucket, no failures", r.returncode == 0, json.dumps(rh.get("failures")))
    summ = res["objects"]["summary"]
    step("objects: 36 recovered, 1 missing, 1 hash mismatch (MinIO inline + part.1)",
         summ == {"recovered": 36, "missing": 1, "hash_mismatch": 1, "unreadable": 0} and res["objects"]["layout"].startswith("minio-xl-single"), json.dumps(summ))
    step("row-count reconciliation all explained", all(x["ok"] for x in res["reconciliation"]), "")
    tgt = {x["table"]: x["target"] for x in res["reconciliation"]}
    step("restored shape", (tgt["users"], tgt["organizations"], tgt["systems"], tgt["role_assignments"], tgt["evidence"], tgt["findings"]) == (9, 2, 4, 26, 38, 111),
         f"users {tgt['users']} orgs {tgt['organizations']} (8+1 / 1+1 production-only admin), jobs {tgt['jobs']}, audit {tgt['audit_events']}")
    step("audit hash chain valid after 0009→0013", res["audit_chain"]["valid"] and res["audit_chain"]["checked"] == tgt["audit_events"], json.dumps(res["audit_chain"])[:120])
    step("FK integrity: no orphans", len(res["fk"]) == 1, json.dumps(res["fk"][0]))
    step("Keycloak migration dry-run in report (not applied)", "dry" in (rh.get("keycloak_migrate_dry_run") or "").lower() or "plan" in (rh.get("keycloak_migrate_dry_run") or "").lower(),
         (rh.get("keycloak_migrate_dry_run") or "")[-160:])

    probe_rehearsal("rehearsal backend (separate instance on rec_target) probe")

    step("apply refuses a wrong plan-hash", rec("apply", "--plan-hash", "deadbeefdeadbeef").returncode == 2, "")
    kc = {"RECOVER_KEYCLOAK_DATABASE_URL": os.environ["RECOVERY_KEYCLOAK_DB_URL"]}
    r = rec("apply", "--plan-hash", plan_hash, **kc)
    db1 = re.search(r"RECOVERED_DB=(\S+)", r.stdout)
    ap = latest("apply")
    step("apply: fresh backups (prod, keycloak, bucket manifest) + new recovered DB", r.returncode == 0 and db1 and all(Path(p).exists() for p in ap["backups"].values()),
         f"{db1.group(1) if db1 else '-'}; backups {sorted(ap['backups'])}")
    cp = ap["result"]["objects"]["copy"]
    step("copy-only: existing identical key kept, unrelated object untouched", len(cp["added"]) == 35 and cp["present_identical"] == [same["key"]] and not cp["conflict_existing_differs"],
         f"added {len(cp['added'])}, identical {len(cp['present_identical'])}")
    eng = create_engine(u("rec_live_prod"))
    with eng.connect() as c:
        step("live production DB untouched by apply", c.execute(text("select count(*) from users")).scalar() == 1 and c.execute(text("select version_num from alembic_version")).scalar() == "0012", "")
    eng.dispose()

    r = rec("verify", DATABASE_URL=u(db1.group(1)))
    vf = latest("verify")
    step("verify on recovered DB (objects, chain, FK, integrity job, round-trip)", r.returncode == 0 and vf["checks"]["storage_roundtrip"],
         f"objects {vf['checks']['objects']['verified']}/{vf['checks']['objects']['evidence']} known-unrecoverable {len(vf['checks']['objects']['known_unrecoverable'])}; integrity {vf['checks']['integrity_job']}")

    from sqlalchemy.orm import Session

    from app.models import Organization
    from app.services import sandbox as sbx
    e1 = create_engine(u(db1.group(1)))
    with Session(e1) as db:
        org = db.query(Organization).filter(Organization.is_sandbox.is_(False), Organization.slug != "ironvision-ops").one()
        why = sbx.purge_refusal(db, org)
        org.is_sandbox, org.source = True, sbx.SANDBOX_SOURCE  # even if mis-flagged as a sandbox: protected + real roles still refuse
        why2 = sbx.purge_refusal(db, org)
        db.rollback()
        with pytest.raises(PermissionError):
            sbx.purge(db, db.get(Organization, org.id), "test")
    e1.dispose()
    step("restored tenant protected: purge hard-refused", why == "not a sandbox tenant" and why2 == "tenant is protected", f"{why} / {why2}")

    r = rec("remove-recovered-objects")
    keys = {o["Key"] for o in s3.list_objects_v2(Bucket="evidence-live").get("Contents", [])}
    step("rollback --remove-recovered-objects removes ONLY recovery-added keys", r.returncode == 0 and keys == {"existing/unrelated.txt", same["key"]}, f"{len(keys)} keys left")
    from app.tools.recovery import upgrade
    upgrade(u("rec_live_prod"))  # = the rollback redeploy's migrate step (additive 0013 on the original DB)
    r = rec("verify")
    step("verify after rollback (DATABASE_URL back to original, redeployed)", r.returncode == 0, "")

    step("plan-hash changes after rollback redeploy (stale approval unusable)", rec("apply", "--plan-hash", plan_hash, **kc).returncode == 2, "")
    plan_hash = rec("plan-hash").stdout.strip().splitlines()[-1]
    step("re-rehearse with --cleanup-ready report", rec("rehearse").returncode == 0, plan_hash)
    probe_rehearsal("re-rehearsal backend probe")
    r = rec("apply", "--plan-hash", plan_hash, **kc)
    step("re-apply after rollback", r.returncode == 0 and len(latest("apply")["result"]["objects"]["copy"]["added"]) == 35, "")
    r = rec("cleanup-rehearsal")
    step("rehearsal --cleanup drops only rec_* scratch DBs + rehearsal bucket", r.returncode == 0, "")
    r = rec("apply", "--plan-hash", plan_hash, **kc)
    cp = latest("apply")["result"]["objects"]["copy"]
    step("idempotent: second apply adds nothing, all identical", r.returncode == 0 and not cp["added"] and len(cp["present_identical"]) == 36, f"identical {len(cp['present_identical'])}")

    subprocess.run(["bash", str(BACKEND.parent / "scripts" / "pod_seaweedfs.sh")], check=True)
    r = rec("verify", DATABASE_URL=u(db1.group(1)))
    step("SeaweedFS restart: objects intact", r.returncode == 0, "")
    print(rec("status").stdout)


def test_merge_conflict_same_email_different_id_stops():
    import uuid

    from app.tools import recovery as R
    os.environ.update({k: v for k, v in env().items() if k.startswith(("RECOVER", "DATABASE_URL", "RECOVERY_DIR"))})
    R.RDIR = RUN
    t = R.ts()
    prod = f"rec_prod_{t}"
    R.restore(REP / "ironvision-production-before-restore.backup", R.create_db(prod))
    eng = create_engine(u(prod))
    with eng.begin() as c:
        oid = c.execute(text("select id from organizations limit 1")).scalar()
        c.execute(text("insert into users (id, org_id, email, display_name) "
                       "values (:i, :o, 'isso@aegisrmf.demo', 'Impostor')"), {"i": uuid.uuid4(), "o": oid})
    eng.dispose()
    with pytest.raises(R.RecoveryError, match="CONFLICT"):
        R.build_target(f"rec_target_{t}", u(prod), {})
    R.drop_scratch_db(prod)
    R.drop_scratch_db(f"rec_target_{t}")
