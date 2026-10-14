import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def _req(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def _opt(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    environment: str
    log_level: str
    database_url: str
    jwt_secret: str
    jwt_ttl_minutes: int
    auth_provider: str
    cors_origins: list[str]
    storage_driver: str
    storage_local_root: str | None
    s3_endpoint_url: str | None
    s3_bucket: str | None
    s3_region: str | None
    s3_access_key_id: str | None
    s3_secret_access_key: str | None
    ai_provider: str
    ai_model: str | None
    ai_timeout_seconds: int
    content_dir: str
    content_fetch_remote: bool
    seed_demo_data: bool
    demo_user_password: str | None
    allow_signup: bool
    demo_password: str | None
    worker_poll_seconds: float
    worker_heartbeat_stale_seconds: int


@lru_cache
def get_settings() -> Settings:
    return Settings(
        environment=_opt("APP_ENV", "development"),
        log_level=_opt("LOG_LEVEL", "INFO"),
        database_url=_req("DATABASE_URL"),
        jwt_secret=_req("JWT_SECRET"),
        jwt_ttl_minutes=int(_opt("JWT_TTL_MINUTES", "60")),
        auth_provider=_opt("AUTH_PROVIDER", "dev_password"),
        cors_origins=[o.strip() for o in (_opt("CORS_ORIGINS", "") or "").split(",") if o.strip()],
        storage_driver=_req("STORAGE_DRIVER"),
        storage_local_root=_opt("STORAGE_LOCAL_ROOT"),
        s3_endpoint_url=_opt("S3_ENDPOINT_URL"),
        s3_bucket=_opt("S3_BUCKET"),
        s3_region=_opt("S3_REGION"),
        s3_access_key_id=_opt("S3_ACCESS_KEY_ID"),
        s3_secret_access_key=_opt("S3_SECRET_ACCESS_KEY"),
        ai_provider=_opt("AI_PROVIDER", "none"),
        ai_model=_opt("AI_MODEL"),
        ai_timeout_seconds=int(_opt("AI_TIMEOUT_SECONDS", "60")),
        content_dir=_opt("CONTENT_DIR", str(BACKEND_DIR / "content")),
        content_fetch_remote=_bool("CONTENT_FETCH_REMOTE"),
        seed_demo_data=_bool("SEED_DEMO_DATA"),
        demo_user_password=_opt("DEMO_USER_PASSWORD"),
        allow_signup=_bool("ALLOW_SIGNUP"),
        demo_password=_opt("DEMO_PASSWORD"),
        worker_poll_seconds=float(_opt("WORKER_POLL_SECONDS", "2")),
        worker_heartbeat_stale_seconds=int(_opt("WORKER_HEARTBEAT_STALE_SECONDS", "30")),
    )
