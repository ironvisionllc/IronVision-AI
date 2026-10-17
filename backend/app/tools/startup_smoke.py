"""Prod-image startup smoke for `selfcheck --startup` (backend/Dockerfile = live + rehearsal backend image). Not part of the
recovery import closure: the recovery image never runs uvicorn."""
import asyncio

import httpx
import uvicorn


def run() -> dict:
    """uvicorn resolves the container CMD's `app.main:app` exactly as `uvicorn app.main:app` does, then one in-process ASGI
    request to /api/v1/health/live (lifespan off: no DB; the caller has blocked the network)."""
    cfg = uvicorn.Config("app.main:app", lifespan="off", log_level="warning")
    cfg.load()

    async def go() -> int:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=cfg.loaded_app), base_url="http://selfcheck.invalid") as c:
            return (await c.get("/api/v1/health/live")).status_code
    st = asyncio.run(go())
    return {"ok": st == 200, "status": st, "uvicorn": uvicorn.__version__}
