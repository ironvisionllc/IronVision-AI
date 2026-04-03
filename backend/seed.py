from datetime import datetime, timezone, timedelta
import uuid
import random

from database import db
from utils import hash_password

DEMO_ADMIN_EMAIL = "demo-admin@grc.com"
DEMO_ADMIN_PASSWORD = "DemoAdmin123!"
DEMO_USER_EMAIL = "demo-user@grc.com"
DEMO_USER_PASSWORD = "DemoUser123!"
DEMO_ORG_NAME = "Demo Organization"


async def seed_demo_accounts():
    """Seed permanent demo accounts and rich sample data on startup"""
    demo_org_id = "demo-org-001"
    now = datetime.now(timezone.utc)

    # Ensure demo organization exists
    existing_org = await db.organizations.find_one({"id": demo_org_id})
    if not existing_org:
        org_doc = {
            "id": demo_org_id,
            "name": DEMO_ORG_NAME,
            "trial_start_date": now.isoformat(),
            "trial_end_date": (now + timedelta(days=365)).isoformat(),
            "subscription_status": "active",
            "created_at": now.isoformat()
        }
        await db.organizations.insert_one(org_doc)

    # Seed demo admin
    existing_admin = await db.users.find_one({"email": DEMO_ADMIN_EMAIL})
    if not existing_admin:
        await db.users.insert_one({
            "id": "demo-admin-001", "email": DEMO_ADMIN_EMAIL, "name": "Demo Admin",
            "roles": [{"role": "admin", "organization_id": demo_org_id}],
            "password_hash": hash_password(DEMO_ADMIN_PASSWORD),
            "created_at": now.isoformat()
        })

    # Seed demo user
    existing_user = await db.users.find_one({"email": DEMO_USER_EMAIL})
    if not existing_user:
        await db.users.insert_one({
            "id": "demo-user-001", "email": DEMO_USER_EMAIL, "name": "Demo Viewer",
            "roles": [{"role": "viewer", "organization_id": demo_org_id}],
            "password_hash": hash_password(DEMO_USER_PASSWORD),
            "created_at": now.isoformat()
        })

    # Auto-reset: wipe all demo org data and re-seed fresh on every startup
    for coll_name in ["policies", "risks", "tasks", "vendors", "evidence_library", "audits", "training", "mappings", "activity_log", "cross_framework_mappings"]:
        await db[coll_name].delete_many({"organization_id": demo_org_id})
    # Also clean global cross-framework mappings (they aren't org-scoped)
    await db.cross_framework_mappings.delete_many({})

    # --- POLICIES ---
    demo_policies = [
        {"id": "demo-pol-001", "title": "Information Security Policy", "content": "Establishes the framework for managing information security across the organization. Covers access controls, data classification, encryption requirements, and security awareness.", "version": "3.2", "status": "active"},
        {"id": "demo-pol-002", "title": "Data Protection & Privacy Policy", "content": "Defines requirements for personal data handling, GDPR compliance, data subject rights, breach notification, and cross-border data transfer safeguards.", "version": "2.1", "status": "active"},
        {"id": "demo-pol-003", "title": "Incident Response Plan", "content": "Outlines procedures for identifying, containing, eradicating, and recovering from security incidents. Includes escalation matrix and communication protocols.", "version": "4.0", "status": "active"},
        {"id": "demo-pol-004", "title": "Access Control Policy", "content": "Defines authentication standards, authorization levels, least-privilege access, MFA requirements, and periodic access reviews.", "version": "2.5", "status": "active"},
        {"id": "demo-pol-005", "title": "Vendor Risk Management Policy", "content": "Establishes third-party risk assessment procedures, due diligence requirements, contractual security obligations, and ongoing monitoring.", "version": "1.3", "status": "active"},
        {"id": "demo-pol-006", "title": "Business Continuity Policy", "content": "Framework for ensuring critical business functions can continue during disruptions. Covers disaster recovery, RTO/RPO targets, and testing schedules.", "version": "2.0", "status": "draft"},
    ]
    for p in demo_policies:
        await db.policies.insert_one({**p, "organization_id": demo_org_id, "created_by": "demo-admin-001", "created_at": now.isoformat(), "updated_at": now.isoformat()})

    # --- RISKS ---
    demo_risks = [
        {"id": "demo-risk-001", "title": "Ransomware Attack on Production Systems", "description": "Critical systems could be encrypted by ransomware, leading to operational downtime and data loss.", "category": "security", "likelihood": 3, "impact": 5, "risk_score": 15, "status": "open", "owner": "CISO"},
        {"id": "demo-risk-002", "title": "Third-Party Data Breach", "description": "A key vendor handling PII suffers a data breach, exposing customer information.", "category": "compliance", "likelihood": 3, "impact": 4, "risk_score": 12, "status": "open", "owner": "Vendor Manager"},
        {"id": "demo-risk-003", "title": "GDPR Non-Compliance Penalty", "description": "Failure to meet data subject access requests within mandated timeframes.", "category": "compliance", "likelihood": 2, "impact": 5, "risk_score": 10, "status": "open", "owner": "DPO"},
        {"id": "demo-risk-004", "title": "Insider Threat - Privileged Access Abuse", "description": "System administrators could misuse elevated privileges to access sensitive data.", "category": "security", "likelihood": 2, "impact": 4, "risk_score": 8, "status": "mitigated", "owner": "Security Lead"},
        {"id": "demo-risk-005", "title": "Cloud Misconfiguration Exposure", "description": "S3 buckets or cloud storage left publicly accessible, exposing sensitive documents.", "category": "operational", "likelihood": 3, "impact": 3, "risk_score": 9, "status": "open", "owner": "Cloud Architect"},
        {"id": "demo-risk-006", "title": "Phishing Campaign Targeting Executives", "description": "Spear-phishing attacks aimed at C-suite could lead to credential compromise.", "category": "security", "likelihood": 4, "impact": 3, "risk_score": 12, "status": "open", "owner": "Security Awareness"},
        {"id": "demo-risk-007", "title": "SOC 2 Audit Finding Remediation Delay", "description": "Delayed remediation of audit findings could impact SOC 2 Type II certification.", "category": "compliance", "likelihood": 2, "impact": 3, "risk_score": 6, "status": "accepted", "owner": "Compliance Lead"},
    ]
    for r in demo_risks:
        await db.risks.insert_one({**r, "organization_id": demo_org_id, "created_at": now.isoformat(), "updated_at": now.isoformat()})

    # --- TASKS ---
    demo_tasks = [
        {"id": "demo-task-001", "title": "Complete quarterly access review", "description": "Review all user access rights across production systems and revoke stale permissions.", "status": "in_progress", "priority": "high", "assignee_id": "demo-admin-001", "assignee_name": "Demo Admin", "due_date": (now + timedelta(days=7)).strftime("%Y-%m-%d"), "tags": ["access-control", "quarterly"]},
        {"id": "demo-task-002", "title": "Update incident response runbook", "description": "Incorporate lessons learned from Q4 tabletop exercise into the IR runbook.", "status": "todo", "priority": "medium", "assignee_id": "demo-admin-001", "assignee_name": "Demo Admin", "due_date": (now + timedelta(days=14)).strftime("%Y-%m-%d"), "tags": ["incident-response"]},
        {"id": "demo-task-003", "title": "Vendor security questionnaire - CloudSync", "description": "Send and review the annual security assessment questionnaire for CloudSync Inc.", "status": "review", "priority": "high", "assignee_id": None, "assignee_name": None, "due_date": (now + timedelta(days=3)).strftime("%Y-%m-%d"), "tags": ["vendor", "assessment"]},
        {"id": "demo-task-004", "title": "Deploy MFA for all admin accounts", "description": "Enforce multi-factor authentication for all administrative and privileged accounts.", "status": "done", "priority": "critical", "assignee_id": "demo-admin-001", "assignee_name": "Demo Admin", "due_date": (now - timedelta(days=5)).strftime("%Y-%m-%d"), "tags": ["access-control", "mfa"]},
        {"id": "demo-task-005", "title": "Remediate SOC 2 finding: logging gaps", "description": "Address audit finding #F2024-07 regarding insufficient logging on API gateway.", "status": "in_progress", "priority": "high", "assignee_id": None, "assignee_name": None, "due_date": (now + timedelta(days=10)).strftime("%Y-%m-%d"), "tags": ["soc2", "audit-finding"]},
        {"id": "demo-task-006", "title": "Annual security awareness training", "description": "Ensure all employees complete mandatory security awareness training by Q1 end.", "status": "todo", "priority": "medium", "assignee_id": None, "assignee_name": None, "due_date": (now + timedelta(days=30)).strftime("%Y-%m-%d"), "tags": ["training", "awareness"]},
    ]
    for t in demo_tasks:
        await db.tasks.insert_one({**t, "organization_id": demo_org_id, "created_by": "demo-admin-001", "created_at": now.isoformat(), "updated_at": now.isoformat()})

    # --- VENDORS ---
    demo_vendors = [
        {"id": "demo-vendor-001", "name": "CloudSync Inc.", "contact_email": "security@cloudsync.io", "risk_level": "high", "assessment_status": "in_progress"},
        {"id": "demo-vendor-002", "name": "DataVault Pro", "contact_email": "compliance@datavault.com", "risk_level": "medium", "assessment_status": "completed"},
        {"id": "demo-vendor-003", "name": "SecureAuth Solutions", "contact_email": "info@secureauth.dev", "risk_level": "low", "assessment_status": "completed"},
        {"id": "demo-vendor-004", "name": "PayStream Global", "contact_email": "risk@paystream.com", "risk_level": "critical", "assessment_status": "pending"},
    ]
    for v in demo_vendors:
        await db.vendors.insert_one({**v, "organization_id": demo_org_id, "created_at": now.isoformat()})

    # --- EVIDENCE ---
    demo_evidence = [
        {"id": "demo-ev-001", "description": "SOC 2 Type II Audit Report - 2025", "evidence_type": "report", "framework_name": "SOC 2", "control_id": "CC6.1", "tags": ["annual", "audit", "soc2"]},
        {"id": "demo-ev-002", "description": "Penetration Test Results - Q4 2025", "evidence_type": "report", "framework_name": "NIST CSF", "control_id": "PR.PT-1", "tags": ["pentest", "quarterly"]},
        {"id": "demo-ev-003", "description": "Access Review Completion Certificate", "evidence_type": "certificate", "framework_name": "ISO 27001", "control_id": "A.9.2.5", "tags": ["access-review", "quarterly"]},
        {"id": "demo-ev-004", "description": "Employee Security Training Attestation", "evidence_type": "attestation", "framework_name": "HIPAA", "control_id": "", "tags": ["training", "annual"]},
        {"id": "demo-ev-005", "description": "Firewall Configuration Screenshot", "evidence_type": "screenshot", "framework_name": "NIST SP 800-53", "control_id": "SC-7", "tags": ["network", "firewall"]},
    ]
    for e in demo_evidence:
        await db.evidence_library.insert_one({**e, "organization_id": demo_org_id, "uploaded_by": "demo-admin-001", "uploaded_by_name": "Demo Admin", "created_at": now.isoformat()})

    # --- AUDITS ---
    demo_audits = [
        {"id": "demo-audit-001", "title": "SOC 2 Type II Annual Audit", "framework_ids": [], "audit_type": "external", "status": "in_progress", "scheduled_date": now.isoformat(), "auditor": "Deloitte"},
        {"id": "demo-audit-002", "title": "ISO 27001 Internal Audit", "framework_ids": [], "audit_type": "internal", "status": "completed", "scheduled_date": (now - timedelta(days=30)).isoformat(), "completion_date": (now - timedelta(days=10)).isoformat(), "auditor": "Internal Audit Team"},
    ]
    for a in demo_audits:
        doc = {**a, "organization_id": demo_org_id, "findings": [], "created_at": now.isoformat()}
        await db.audits.insert_one(doc)

    # --- TRAINING ---
    from training_data import TRAINING_MODULES
    await db.quizzes.delete_many({"organization_id": demo_org_id})
    await db.training_progress.delete_many({"organization_id": demo_org_id})
    for mod in TRAINING_MODULES:
        quiz_data = mod.pop("quiz", None)
        await db.training.insert_one({**mod, "organization_id": demo_org_id, "created_at": now.isoformat()})
        if quiz_data:
            await db.quizzes.insert_one({
                "id": f"quiz-{mod['id']}",
                "training_id": mod["id"],
                "organization_id": demo_org_id,
                "questions": quiz_data["questions"],
                "passing_score": quiz_data["passing_score"],
                "created_at": now.isoformat()
            })

    # --- CONTROL MAPPINGS (aiming for ~78% overall = B+ grade) ---
    # First, seed CCIs for NIST 800-53 controls
    from cci_data import NIST_800_53_CCIS
    await db.ccis.delete_many({})  # Clean and re-seed CCIs
    nist_800_53_fw = await db.frameworks.find_one({"name": "NIST SP 800-53"}, {"_id": 0})
    if nist_800_53_fw:
        for ctrl_id, ccis in NIST_800_53_CCIS.items():
            for cci in ccis:
                await db.ccis.insert_one({
                    "id": cci["cci_id"],
                    "cci_id": cci["cci_id"],
                    "parent_control_id": ctrl_id,
                    "framework_id": nist_800_53_fw["id"],
                    "framework_name": "NIST SP 800-53",
                    "definition": cci["definition"],
                    "status": cci["status"],
                    "type": cci["type"],
                    "created_at": now.isoformat()
                })

    frameworks = await db.frameworks.find({}, {"_id": 0}).to_list(100)
    fw_name_map = {fw["id"]: fw["name"] for fw in frameworks}
    random.seed(42)

    coverage_targets = {
        0: 0.92, 1: 0.88, 2: 0.85, 3: 0.90, 4: 0.82,
        5: 0.86, 6: 0.91, 7: 0.72, 8: 0.68, 9: 0.55, 10: 0.48, 11: 0.78,
    }

    for idx, fw in enumerate(frameworks):
        controls = await db.controls.find({"framework_id": fw["id"]}, {"_id": 0}).to_list(500)
        target = coverage_targets.get(idx, 0.75)
        num_to_map = int(len(controls) * target)

        for i in range(num_to_map):
            ctrl = controls[i]
            pol = demo_policies[i % len(demo_policies)]
            confidence = round(random.uniform(0.78, 0.98), 2)
            is_ai = random.random() < 0.3
            await db.mappings.insert_one({
                "id": str(uuid.uuid4()), "organization_id": demo_org_id,
                "policy_id": pol["id"], "policy_name": pol["title"],
                "control_id": ctrl.get("control_id", ctrl.get("id", "")),
                "control_title": ctrl.get("title", ""),
                "framework_id": fw["id"], "framework_name": fw_name_map.get(fw["id"], ""),
                "confidence_score": confidence,
                "status": "approved" if not is_ai else random.choice(["approved", "pending"]),
                "source": "ai" if is_ai else "manual",
                "notes": "", "ai_reason": "AI-suggested mapping based on policy analysis" if is_ai else "",
                "mapped_by": "demo-admin-001",
                "created_at": now.isoformat()
            })

    # --- CROSS-FRAMEWORK CONTROL MAPPINGS ---
    all_fws = await db.frameworks.find({}, {"_id": 0}).to_list(100)
    fw_id_map = {fw["name"]: fw["id"] for fw in all_fws}
    fw_controls = {}
    for fw in all_fws:
        ctrls = await db.controls.find({"framework_id": fw["id"]}, {"_id": 0}).to_list(500)
        fw_controls[fw["name"]] = ctrls

    cross_mappings_data = [
        ("NIST Cybersecurity Framework", "ID.AM-1", "ISO 27001", "A.8.1.1", "equivalent", 0.95),
        ("NIST Cybersecurity Framework", "ID.AM-2", "ISO 27001", "A.8.1.2", "equivalent", 0.92),
        ("NIST Cybersecurity Framework", "PR.AC-1", "ISO 27001", "A.9.1.1", "equivalent", 0.90),
        ("NIST Cybersecurity Framework", "PR.AC-3", "ISO 27001", "A.9.4.1", "related", 0.85),
        ("NIST Cybersecurity Framework", "PR.DS-1", "ISO 27001", "A.10.1.1", "related", 0.88),
        ("NIST Cybersecurity Framework", "DE.CM-1", "ISO 27001", "A.12.4.1", "related", 0.82),
        ("NIST Cybersecurity Framework", "RS.RP-1", "ISO 27001", "A.16.1.5", "equivalent", 0.93),
        ("NIST Cybersecurity Framework", "PR.AC-1", "SOC 2", "CC6.1", "equivalent", 0.94),
        ("NIST Cybersecurity Framework", "PR.DS-1", "SOC 2", "CC6.7", "related", 0.87),
        ("NIST Cybersecurity Framework", "DE.CM-1", "SOC 2", "CC7.2", "equivalent", 0.91),
        ("NIST Cybersecurity Framework", "RS.RP-1", "SOC 2", "CC7.4", "equivalent", 0.92),
        ("NIST Cybersecurity Framework", "ID.GV-1", "SOC 2", "CC1.1", "related", 0.84),
        ("NIST SP 800-53", "AC-1", "ISO 27001", "A.9.1.1", "equivalent", 0.96),
        ("NIST SP 800-53", "AC-2", "ISO 27001", "A.9.2.1", "equivalent", 0.94),
        ("NIST SP 800-53", "AU-1", "ISO 27001", "A.12.4.1", "equivalent", 0.93),
        ("NIST SP 800-53", "CM-1", "ISO 27001", "A.12.1.2", "related", 0.85),
        ("NIST SP 800-53", "IR-1", "ISO 27001", "A.16.1.1", "equivalent", 0.95),
        ("NIST SP 800-53", "SC-1", "ISO 27001", "A.10.1.1", "related", 0.86),
        ("NIST SP 800-53", "AC-1", "HIPAA", "164.312(a)(1)", "related", 0.88),
        ("NIST SP 800-53", "AC-2", "HIPAA", "164.312(a)(2)(i)", "related", 0.85),
        ("NIST SP 800-53", "AU-1", "HIPAA", "164.312(b)", "equivalent", 0.91),
        ("NIST SP 800-53", "SC-1", "HIPAA", "164.312(e)(1)", "related", 0.87),
        ("NIST SP 800-53", "IR-1", "HIPAA", "164.308(a)(6)", "equivalent", 0.92),
        ("ISO 27001", "A.9.1.1", "SOC 2", "CC6.1", "equivalent", 0.93),
        ("ISO 27001", "A.9.2.1", "SOC 2", "CC6.2", "equivalent", 0.91),
        ("ISO 27001", "A.12.4.1", "SOC 2", "CC7.2", "related", 0.86),
        ("ISO 27001", "A.16.1.1", "SOC 2", "CC7.3", "equivalent", 0.94),
        ("ISO 27001", "A.10.1.1", "SOC 2", "CC6.7", "related", 0.84),
        ("ISO 27001", "A.18.1.4", "GDPR", "Art. 32", "equivalent", 0.95),
        ("ISO 27001", "A.18.1.1", "GDPR", "Art. 5(1)(f)", "related", 0.88),
        ("ISO 27001", "A.9.1.1", "GDPR", "Art. 25", "related", 0.82),
        ("HIPAA", "164.312(a)(1)", "SOC 2", "CC6.1", "related", 0.87),
        ("HIPAA", "164.312(b)", "SOC 2", "CC7.2", "equivalent", 0.90),
        ("HIPAA", "164.308(a)(6)", "SOC 2", "CC7.3", "equivalent", 0.91),
        ("NIST SP 800-53", "AC-1", "CMMC", "AC.L2-3.1.1", "equivalent", 0.97),
        ("NIST SP 800-53", "AC-2", "CMMC", "AC.L2-3.1.2", "equivalent", 0.96),
        ("NIST SP 800-53", "AU-1", "CMMC", "AU.L2-3.3.1", "equivalent", 0.95),
        ("NIST SP 800-53", "IR-1", "CMMC", "IR.L2-3.6.1", "equivalent", 0.96),
        ("NIST SP 800-53", "AC-1", "StateRAMP", "SR-AC-1", "equivalent", 0.98),
        ("NIST SP 800-53", "AC-2", "StateRAMP", "SR-AC-2", "equivalent", 0.98),
        ("NIST SP 800-53", "AC-3", "StateRAMP", "SR-AC-3", "equivalent", 0.97),
        ("NIST SP 800-53", "AC-5", "StateRAMP", "SR-AC-5", "equivalent", 0.97),
        ("NIST SP 800-53", "AC-6", "StateRAMP", "SR-AC-6", "equivalent", 0.98),
        ("NIST SP 800-53", "AU-1", "StateRAMP", "SR-AU-1", "equivalent", 0.98),
        ("NIST SP 800-53", "AU-2", "StateRAMP", "SR-AU-2", "equivalent", 0.97),
        ("NIST SP 800-53", "CM-1", "StateRAMP", "SR-CM-1", "equivalent", 0.98),
        ("NIST SP 800-53", "IR-1", "StateRAMP", "SR-IR-1", "equivalent", 0.98),
        ("NIST SP 800-53", "SC-1", "StateRAMP", "SR-SC-1", "equivalent", 0.97),
        ("NIST SP 800-53", "SI-1", "StateRAMP", "SR-SI-1", "equivalent", 0.98),
        ("StateRAMP", "SR-AC-1", "SOC 2", "CC6.1", "related", 0.88),
        ("StateRAMP", "SR-AU-1", "SOC 2", "CC7.2", "related", 0.85),
        ("StateRAMP", "SR-IR-1", "SOC 2", "CC7.3", "related", 0.86),
        ("StateRAMP", "SR-CM-1", "SOC 2", "CC8.1", "related", 0.83),
        ("StateRAMP", "SR-AC-1", "ISO 27001", "A.9.1.1", "related", 0.87),
        ("StateRAMP", "SR-AU-1", "ISO 27001", "A.12.4.1", "related", 0.86),
        ("StateRAMP", "SR-IR-1", "ISO 27001", "A.16.1.1", "related", 0.88),
        ("NIST SP 800-53", "IR-1", "NIS2", "Art10-IR", "related", 0.84),
        ("NIST SP 800-53", "AC-1", "NIS2", "Art21-SC", "related", 0.80),
        ("GDPR", "Art. 32", "HIPAA", "164.312(a)(1)", "related", 0.82),
        ("GDPR", "Art. 33", "HIPAA", "164.308(a)(6)", "related", 0.85),
    ]

    for src_fw, src_ctrl, tgt_fw, tgt_ctrl, rel_type, conf in cross_mappings_data:
        src_fw_id = fw_id_map.get(src_fw, "")
        tgt_fw_id = fw_id_map.get(tgt_fw, "")

        src_ctrl_obj = next((c for c in fw_controls.get(src_fw, []) if c.get("control_id") == src_ctrl), None)
        tgt_ctrl_obj = next((c for c in fw_controls.get(tgt_fw, []) if c.get("control_id") == tgt_ctrl), None)

        if src_fw_id and tgt_fw_id:
            await db.cross_framework_mappings.insert_one({
                "id": str(uuid.uuid4()),
                "source_framework_id": src_fw_id,
                "source_framework_name": src_fw,
                "source_control_id": src_ctrl,
                "source_control_title": src_ctrl_obj.get("title", "") if src_ctrl_obj else "",
                "target_framework_id": tgt_fw_id,
                "target_framework_name": tgt_fw,
                "target_control_id": tgt_ctrl,
                "target_control_title": tgt_ctrl_obj.get("title", "") if tgt_ctrl_obj else "",
                "relationship_type": rel_type,
                "confidence_score": conf,
                "created_at": now.isoformat()
            })

    # --- ACTIVITY LOG ---
    demo_activities = [
        {"action": "policy_created", "details": "Created policy: Information Security Policy"},
        {"action": "risk_created", "details": "Created risk: Ransomware Attack on Production Systems"},
        {"action": "task_created", "details": "Created task: Complete quarterly access review"},
        {"action": "vendor_created", "details": "Added vendor: CloudSync Inc."},
        {"action": "evidence_added", "details": "Added evidence: SOC 2 Type II Audit Report"},
        {"action": "task_updated", "details": "Updated task: Deploy MFA for all admin accounts"},
    ]
    for i, act in enumerate(demo_activities):
        await db.activity_log.insert_one({
            "id": str(uuid.uuid4()), "organization_id": demo_org_id,
            "user_id": "demo-admin-001", "user_name": "Demo Admin",
            "action": act["action"], "details": act["details"],
            "timestamp": (now - timedelta(hours=len(demo_activities) - i)).isoformat()
        })

    # --- NOTIFICATIONS ---
    await db.notifications.delete_many({"organization_id": demo_org_id})
    demo_notifications = [
        {"title": "High-Risk Alert", "message": "Ransomware Attack on Production Systems scored 15 (Critical)", "type": "warning", "link": "/risks", "read": False},
        {"title": "Task Overdue", "message": "Vendor security questionnaire - CloudSync is past due", "type": "alert", "link": "/tasks", "read": False},
        {"title": "Audit Scheduled", "message": "SOC 2 Type II Annual Audit has been scheduled", "type": "info", "link": "/audits", "read": True},
        {"title": "New Policy Published", "message": "Information Security Policy v3.2 is now active", "type": "info", "link": "/policies", "read": True},
        {"title": "Training Reminder", "message": "Security Awareness Fundamentals training is pending", "type": "info", "link": "/training", "read": False},
    ]
    for i, n in enumerate(demo_notifications):
        await db.notifications.insert_one({
            "id": str(uuid.uuid4()),
            "organization_id": demo_org_id,
            "user_id": "demo-admin-001",
            "title": n["title"],
            "message": n["message"],
            "type": n["type"],
            "link": n["link"],
            "read": n["read"],
            "created_at": (now - timedelta(hours=len(demo_notifications) - i)).isoformat()
        })
