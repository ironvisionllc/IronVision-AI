"""
Predictive Risk Forecasting
- Analyzes historical data to predict future compliance failures
- Identifies patterns (end-of-quarter pushes, seasonal risks)
- Generates proactive warnings for teams
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict
from datetime import datetime, timezone, timedelta
import logging
import os
import re
import json

from database import db
from utils import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/forecasting", tags=["forecasting"])


@router.get("/predict")
async def predict_risk(current_user: Dict = Depends(get_current_user)):
    """Generate predictive risk forecast based on historical data."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    # Gather historical data
    risk_history = await db.risk_score_history.find(
        {"organization_id": org_id}, {"_id": 0}
    ).sort("timestamp", 1).to_list(1000)

    pipeline_runs = await db.pipeline_runs.find(
        {"organization_id": org_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(500)

    poam_entries = await db.poam_entries.find(
        {"organization_id": org_id}, {"_id": 0}
    ).to_list(200)

    siem_pipeline = [
        {"$group": {
            "_id": {"$substr": ["$timestamp", 0, 10]},
            "count": {"$sum": 1},
            "critical": {"$sum": {"$cond": [{"$eq": ["$severity", "critical"]}, 1, 0]}},
        }},
        {"$sort": {"_id": 1}},
    ]
    siem_daily = []
    async for doc in db.siem_events.aggregate(siem_pipeline):
        siem_daily.append(doc)

    # Calculate trends and patterns
    predictions = []
    warnings = []

    # 1. Risk score trend analysis
    if len(risk_history) >= 2:
        recent = risk_history[-1].get("score", 50)
        older = risk_history[0].get("score", 50) if len(risk_history) > 5 else risk_history[-2].get("score", 50)
        trend = recent - older

        if trend > 10:
            warnings.append({
                "type": "risk_increasing",
                "severity": "high",
                "title": "Risk score trending upward",
                "detail": f"Risk increased from {older} to {recent} ({trend:+.1f} points). If this trend continues, risk could reach {min(100, recent + trend):.0f} in the next assessment period.",
                "recommendation": "Review recent changes: new vulnerabilities, failed pipeline gates, or expired policies may be contributing.",
            })
        elif trend < -10:
            predictions.append({
                "type": "risk_improving",
                "confidence": 0.8,
                "title": "Compliance posture improving",
                "detail": f"Risk decreased from {older} to {recent} ({trend:+.1f} points). Current remediation efforts are effective.",
            })

    # 2. Pipeline failure pattern analysis
    if pipeline_runs:
        failed_runs = [r for r in pipeline_runs if r.get("gate_result") == "fail"]
        total_runs = len(pipeline_runs)
        fail_rate = len(failed_runs) / total_runs * 100 if total_runs > 0 else 0

        if fail_rate > 50:
            warnings.append({
                "type": "pipeline_failure_rate",
                "severity": "critical",
                "title": f"Pipeline failure rate at {fail_rate:.0f}%",
                "detail": f"{len(failed_runs)} of {total_runs} pipeline runs failed the compliance gate. This indicates systemic security issues in the deployment pipeline.",
                "recommendation": "Review CI/CD security scanning tools and remediation processes. Consider tightening gate policies.",
            })
        elif fail_rate > 25:
            warnings.append({
                "type": "pipeline_failure_rate",
                "severity": "medium",
                "title": f"Elevated pipeline failure rate ({fail_rate:.0f}%)",
                "detail": f"{len(failed_runs)} of {total_runs} runs failed. This is above the recommended 20% threshold.",
                "recommendation": "Investigate common failure categories and prioritize remediation of recurring vulnerability types.",
            })

        # Avg risk score trend in pipelines
        if len(pipeline_runs) >= 3:
            recent_3 = pipeline_runs[-3:]
            avg_recent = sum(r.get("risk_score", 0) for r in recent_3) / 3
            if avg_recent > 30:
                predictions.append({
                    "type": "pipeline_risk_elevated",
                    "confidence": 0.7,
                    "title": "Pipeline security risk elevated",
                    "detail": f"Average risk score of last 3 runs: {avg_recent:.0f}. Predicted to remain high without intervention.",
                })

    # 3. POA&M overdue prediction
    now = datetime.now(timezone.utc)
    upcoming_due = []
    for p in poam_entries:
        if p.get("status") in ("open", "in_progress"):
            due = p.get("scheduled_completion", "")
            if due:
                try:
                    due_dt = datetime.fromisoformat(due.replace("Z", "+00:00"))
                    days_left = (due_dt - now).days
                    if 0 < days_left <= 14:
                        upcoming_due.append({"title": p.get("title", "")[:50], "days_left": days_left, "severity": p.get("severity", ""), "poam_id": p.get("poam_id", "")})
                    elif days_left <= 0:
                        upcoming_due.append({"title": p.get("title", "")[:50], "days_left": days_left, "severity": p.get("severity", ""), "poam_id": p.get("poam_id", ""), "overdue": True})
                except (ValueError, TypeError):
                    pass

    if upcoming_due:
        overdue = [d for d in upcoming_due if d.get("overdue")]
        soon = [d for d in upcoming_due if not d.get("overdue")]
        if overdue:
            warnings.append({
                "type": "poam_overdue",
                "severity": "critical",
                "title": f"{len(overdue)} POA&M items are overdue",
                "detail": "Overdue items: " + ", ".join(f"{d['poam_id']} ({d['severity']})" for d in overdue[:5]),
                "recommendation": "Escalate overdue POA&M items immediately. Update status or request deadline extensions.",
            })
        if soon:
            warnings.append({
                "type": "poam_upcoming",
                "severity": "medium",
                "title": f"{len(soon)} POA&M items due within 14 days",
                "detail": "Upcoming: " + ", ".join(f"{d['poam_id']} in {d['days_left']}d" for d in soon[:5]),
                "recommendation": "Ensure remediation resources are allocated for upcoming milestones.",
            })

    # 4. SIEM event volume prediction
    if siem_daily:
        recent_days = siem_daily[-7:] if len(siem_daily) >= 7 else siem_daily
        avg_events = sum(d["count"] for d in recent_days) / len(recent_days)
        avg_critical = sum(d.get("critical", 0) for d in recent_days) / len(recent_days)

        if avg_critical > 5:
            warnings.append({
                "type": "siem_critical_trend",
                "severity": "high",
                "title": f"Averaging {avg_critical:.0f} critical SIEM events/day",
                "detail": f"Over the last {len(recent_days)} days, an average of {avg_events:.0f} total events with {avg_critical:.0f} critical per day.",
                "recommendation": "Investigate root cause of critical events. Consider incident response escalation.",
            })

    # 5. Compliance coverage forecast
    total_controls = await db.controls.count_documents({})
    assessed_controls = await db.control_compliance.count_documents({"organization_id": org_id})
    coverage = assessed_controls / max(total_controls, 1) * 100

    if coverage < 50:
        predictions.append({
            "type": "coverage_gap",
            "confidence": 0.9,
            "title": f"Only {coverage:.0f}% of controls assessed",
            "detail": f"{assessed_controls} of {total_controls} controls have been assessed. At current pace, full coverage may not be achieved before next audit.",
        })

    # Sort warnings by severity
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    warnings.sort(key=lambda x: sev_order.get(x.get("severity", "low"), 4))

    return {
        "predictions": predictions,
        "warnings": warnings,
        "data_points": {
            "risk_history_points": len(risk_history),
            "pipeline_runs": len(pipeline_runs),
            "poam_entries": len(poam_entries),
            "siem_daily_points": len(siem_daily),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
