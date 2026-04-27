from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware
import os
import logging

from database import client
from seed import seed_demo_accounts

from routes.auth import router as auth_router
from routes.frameworks import router as frameworks_router
from routes.policies import router as policies_router
from routes.mappings import router as mappings_router
from routes.risks import router as risks_router
from routes.vendors import router as vendors_router
from routes.audits import router as audits_router
from routes.training import router as training_router
from routes.analytics import router as analytics_router
from routes.compliance import router as compliance_router
from routes.admin import router as admin_router
from routes.tasks import router as tasks_router
from routes.activity import router as activity_router
from routes.reports import router as reports_router
from routes.evidence import router as evidence_router
from routes.exports import router as exports_router
from routes.controls import router as controls_detail_router
from routes.notifications import router as notifications_router
from routes.ironvision import router as ironvision_router
from routes.policy_builder import router as policy_builder_router
from routes.documents import router as documents_router
from routes.compliance_trends import router as compliance_trends_router
from routes.email_notifications import router as email_notifications_router
from routes.copilot import router as copilot_router
from routes.slack_integration import router as slack_router
from routes.control_effectiveness import router as effectiveness_router
from routes.siem import router as siem_router
from routes.control_compliance import router as control_compliance_router
from routes.policy_templates import router as policy_templates_router
from routes.ingestion import router as ingestion_router
from routes.oscal import router as oscal_router
from routes.pipeline import router as pipeline_router
from routes.risk_scoring import router as risk_scoring_router
from routes.policy_engine import router as policy_engine_router
from routes.evidence_collection import router as evidence_collection_router
from routes.tenable import router as tenable_router
from routes.remediation import router as remediation_router
from routes.rbac import router as rbac_router
from routes.interrogation import router as interrogation_router
from routes.forecasting import router as forecasting_router
from routes.tprm import router as tprm_router
from routes.assets import router as assets_router

# Create the main app
app = FastAPI()
api_router = APIRouter(prefix="/api")

# Include all route modules
api_router.include_router(auth_router)
api_router.include_router(frameworks_router)
api_router.include_router(policies_router)
api_router.include_router(mappings_router)
api_router.include_router(risks_router)
api_router.include_router(vendors_router)
api_router.include_router(audits_router)
api_router.include_router(training_router)
api_router.include_router(analytics_router)
api_router.include_router(compliance_router)
api_router.include_router(admin_router)
api_router.include_router(tasks_router)
api_router.include_router(activity_router)
api_router.include_router(reports_router)
api_router.include_router(evidence_router)
api_router.include_router(exports_router)
api_router.include_router(controls_detail_router)
api_router.include_router(notifications_router)
api_router.include_router(ironvision_router)
api_router.include_router(policy_builder_router)
api_router.include_router(documents_router)
api_router.include_router(compliance_trends_router)
api_router.include_router(email_notifications_router)
api_router.include_router(copilot_router)
api_router.include_router(slack_router)
api_router.include_router(effectiveness_router)
api_router.include_router(siem_router)
api_router.include_router(control_compliance_router)
api_router.include_router(policy_templates_router)
api_router.include_router(ingestion_router)
api_router.include_router(oscal_router)
api_router.include_router(pipeline_router)
api_router.include_router(risk_scoring_router)
api_router.include_router(policy_engine_router)
api_router.include_router(evidence_collection_router)
api_router.include_router(tenable_router)
api_router.include_router(remediation_router)
api_router.include_router(rbac_router)
api_router.include_router(interrogation_router)
api_router.include_router(forecasting_router)
api_router.include_router(tprm_router)
api_router.include_router(assets_router)

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def startup_event():
    # Sync framework controls from source data
    from routes.frameworks import seed_frameworks
    await seed_frameworks()
    # Seed demo accounts and data
    await seed_demo_accounts()
    logger.info("Demo accounts seeded successfully")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
    from ironvision_db import close_ironvision_db
    close_ironvision_db()
