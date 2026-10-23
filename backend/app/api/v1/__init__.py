from fastapi import APIRouter

from app.api.v1 import admin, ai, auth, authz, content, controls, docs_center, evidence, health, phase3, phase4, poams, records, reviews, rmf_steps, sandbox, workbench

router = APIRouter()
for module in (health, auth, controls, content, records, evidence, workbench, poams, reviews, phase3, phase4, authz, ai, admin, docs_center, sandbox, rmf_steps):
    router.include_router(module.router)
