import threading
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_lock = threading.Lock()
_engine: Engine | None = None
_factory: sessionmaker | None = None


def get_engine() -> Engine:
    """Created on first use (settings resolved then – a missing DATABASE_URL still fails with a clear message), not at import."""
    global _engine, _factory
    with _lock:
        if _engine is None:
            _engine = create_engine(get_settings().database_url, pool_pre_ping=True, pool_size=10, max_overflow=10,
                                    connect_args={"application_name": "ironvision-app"})  # recovery health: which DB the app is on
            _factory = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)
    return _engine


class _LazySessionLocal:
    """`SessionLocal()` behaves exactly like the sessionmaker it wraps; the engine is built on the first call."""

    def __call__(self, *a, **kw) -> Session:
        get_engine()
        return _factory(*a, **kw)

    def __getattr__(self, name):
        get_engine()
        return getattr(_factory, name)


SessionLocal = _LazySessionLocal()


def __getattr__(name: str):  # PEP 562: app.db.engine keeps working, resolved lazily
    if name == "engine":
        return get_engine()
    raise AttributeError(f"module 'app.db' has no attribute {name!r}")


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
