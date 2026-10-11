import os
import tempfile
from pathlib import Path

from dotenv import dotenv_values

_BACKEND = Path(__file__).resolve().parent.parent
_file_env = dotenv_values(_BACKEND / ".env")
_test_db = os.environ.get("TEST_DATABASE_URL") or _file_env.get("TEST_DATABASE_URL")
if not _test_db:
    raise RuntimeError("TEST_DATABASE_URL must be set (a disposable Postgres database; it is wiped by the test run)")
os.environ["DATABASE_URL"] = _test_db
os.environ["STORAGE_DRIVER"] = "local"
os.environ["STORAGE_LOCAL_ROOT"] = tempfile.mkdtemp(prefix="aegis-test-storage-")
os.environ["SEED_DEMO_DATA"] = "false"
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("DEMO_USER_PASSWORD", "AegisDemo!2026")

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

PASSWORD = os.environ["DEMO_USER_PASSWORD"]


@pytest.fixture(scope="session", autouse=True)
def database():
    eng = create_engine(_test_db)
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    eng.dispose()
    cfg = Config(str(_BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND / "alembic"))
    cfg.attributes["database_url"] = _test_db
    command.upgrade(cfg, "head")

    from app.db import SessionLocal
    from app.seed import seed_demo
    from app.services.content.loader import load_reference_content

    from app.seed_phase1 import seed_phase1

    with SessionLocal() as db:
        org = seed_demo(db, PASSWORD)
        load_reference_content(db)
        db.commit()
        seed_phase1(db, org, os.environ.get("SAMPLES_DIR", str(_BACKEND.parent / "samples")))
        db.commit()
    yield


@pytest.fixture(scope="session")
def client(database):
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def token(client):
    cache: dict[str, str] = {}

    def get(email: str) -> str:
        if email not in cache:
            r = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
            assert r.status_code == 200, r.text
            cache[email] = r.json()["access_token"]
        return cache[email]

    return get


def auth(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}
