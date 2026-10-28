import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from starlette.middleware.cors import CORSMiddleware

from app.api.v1 import router as v1_router
from app.config import get_settings
from app.security import web
from app.logging_setup import configure_logging, correlation_id_var

settings = get_settings()
configure_logging(settings.log_level)
log = logging.getLogger("aegis.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    from app.check_env import production_guard

    production_guard()
    if settings.seed_demo_data:
        try:
            from app.seed import run as run_seed

            run_seed()
        except Exception:
            log.exception("Demo seed failed (have migrations been applied? run `alembic upgrade head`)")
    yield


app = FastAPI(
    title="IronVision AI API",
    description="IronVision AI – Intelligent Risk. Continuous Assurance. (Phase 0 foundation, SYNTHETIC DATA ONLY)",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Correlation-ID"],
    expose_headers=["X-Correlation-ID"],
)


@app.middleware("http")
async def correlation_and_access_log(request: Request, call_next):
    cid = request.headers.get("x-correlation-id") or str(uuid.uuid4())
    token = correlation_id_var.set(cid[:100])
    from app.services.audit import operator_var
    operator_var.set({})
    started = time.perf_counter()
    try:
        response = web.rate_limited(request) or await call_next(request)
    finally:
        correlation_id_var.reset(token)
    web.security_headers(request, response)
    route = request.scope.get("route")
    web.REQ_LATENCY.labels(request.method, getattr(route, "path", "unmatched"), response.status_code).observe(time.perf_counter() - started)
    response.headers["X-Correlation-ID"] = cid[:100]
    log.info("request", extra={"method": request.method, "path": request.url.path, "status": response.status_code,
                               "duration_ms": round((time.perf_counter() - started) * 1000, 1), "correlation_id": cid[:100],
                               **({"query_keys": sorted(request.query_params.keys())[:20]} if response.status_code == 422 else {})})
    return response


app.include_router(v1_router, prefix="/api/v1")


@app.get("/api/v1/ready", tags=["health"])
def ready():
    """Readiness: DB reachable and migrations at head. Liveness is /api/v1/health/live."""
    from sqlalchemy import text as _t
    from fastapi.responses import JSONResponse
    from app.db import SessionLocal
    try:
        with SessionLocal() as db:
            rev = db.execute(_t("select version_num from alembic_version")).scalar()
        return {"ready": True, "migration": rev}
    except Exception as exc:
        return JSONResponse({"ready": False, "error": str(exc)[:200]}, status_code=503)


@app.get("/api/v1/health/live", tags=["health"])
def live():
    return {"alive": True}


@app.get("/api/v1/metrics", include_in_schema=False)
def metrics():
    """Prometheus exposition. DB-derived series are computed per scrape so worker metrics are multi-process safe."""
    from fastapi.responses import Response
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    from prometheus_client.core import GaugeMetricFamily
    from prometheus_client.registry import REGISTRY, Collector
    from sqlalchemy import text as _t
    from app.db import SessionLocal

    class DbCollector(Collector):
        def collect(self):
            with SessionLocal() as db:
                jobs = GaugeMetricFamily("aegis_jobs_total", "Jobs by type/status", labels=["job_type", "status"])
                dur = GaugeMetricFamily("aegis_job_avg_duration_seconds", "Avg job duration (last 24h)", labels=["job_type"])
                for jt, st, n in db.execute(_t("select job_type, status, count(*) from jobs group by 1,2")):
                    jobs.add_metric([jt, st], n)
                for jt, d in db.execute(_t("select job_type, avg(extract(epoch from finished_at-started_at)) from jobs where finished_at > now()-interval '1 day' group by 1")):
                    dur.add_metric([jt], float(d or 0))
                ing = GaugeMetricFamily("aegis_ingest_runs_by_status", "Ingest runs by format/status", labels=["format", "status"])
                for f, st, n in db.execute(_t("select file_format, status, count(*) from ingest_runs group by 1,2")):
                    ing.add_metric([f or "unknown", st], n)
                em = GaugeMetricFamily("aegis_emass_queue", "eMASS outbound changes by status", labels=["status"])
                for st, n in db.execute(_t("select status, count(*) from emass_changes group by 1")):
                    em.add_metric([st], n)
            yield from (jobs, dur, ing, em)

    if not getattr(app.state, "db_collector", None):
        app.state.db_collector = DbCollector()
        REGISTRY.register(app.state.db_collector)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
