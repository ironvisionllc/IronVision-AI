from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import WorkerHeartbeat
from app.schemas import HealthComponent, HealthOut
from app.services.ai.service import get_ai_service
from app.services.storage import get_storage

router = APIRouter(tags=["health"])
VERSION = "0.1.0-phase0"


def _check(fn) -> HealthComponent:
    try:
        return fn()
    except Exception as exc:
        return HealthComponent(ok=False, detail={"error": str(exc)[:300]})


@router.get("/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)) -> HealthOut:
    s = get_settings()

    def database():
        version = db.execute(text("SHOW server_version")).scalar()
        rev = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        return HealthComponent(ok=True, detail={"engine": "postgresql", "server_version": version, "alembic_revision": rev})

    def storage():
        result = get_storage().health()
        return HealthComponent(ok=result["ok"], detail=result)

    def worker():
        last = db.scalar(select(func.max(WorkerHeartbeat.last_seen_at)))
        stale = timedelta(seconds=s.worker_heartbeat_stale_seconds)
        ok = bool(last and datetime.now(timezone.utc) - last < stale)
        return HealthComponent(ok=ok, detail={"last_heartbeat": last.isoformat() if last else None,
                                              "stale_after_seconds": s.worker_heartbeat_stale_seconds})

    def ai():
        info = get_ai_service().describe()
        return HealthComponent(ok=info["configured"], detail=info)

    components = {"database": _check(database), "storage": _check(storage), "worker": _check(worker), "ai": _check(ai)}
    status = "ok" if all(c.ok for c in components.values()) else "degraded"
    from app.build_info import build_info
    return HealthOut(status=status, version=VERSION, build=build_info(), components=components)
