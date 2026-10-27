from fastapi import APIRouter

from app.api.v1 import admin, ai, auth, authz, content, controls, docs_center, emass_fields, emass_import, evidence, import_center, iscm, health, phase3, phase4, poams, processing, public, records, tr, inventory, reviews, rmf_accuracy, rmf_steps, sandbox, workbench

router = APIRouter()
for module in (health, auth, controls, content, records, evidence, workbench, emass_fields, emass_import, import_center, iscm, poams, reviews, phase3, phase4, authz, ai, admin, docs_center, sandbox, rmf_accuracy, rmf_steps, processing, tr, inventory, public):
    router.include_router(module.router)
