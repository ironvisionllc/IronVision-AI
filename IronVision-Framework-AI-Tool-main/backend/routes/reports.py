from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from typing import Dict
from datetime import datetime, timezone
import io

from database import db
from utils import get_current_user, get_compliance_grade

router = APIRouter()


@router.get("/reports/executive-summary")
async def get_executive_summary(current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    frameworks = await db.frameworks.find({}, {"_id": 0}).to_list(100)
    framework_scores = []
    total_mapped = 0
    total_controls = 0

    for fw in frameworks:
        controls_count = await db.controls.count_documents({"framework_id": fw["id"]})
        mappings = await db.mappings.find({"organization_id": org_id, "framework_id": fw["id"]}, {"_id": 0, "control_id": 1}).to_list(10000)
        mapped_count = len(set(m["control_id"] for m in mappings))
        score = int((mapped_count / controls_count) * 100) if controls_count > 0 else 0

        total_mapped += mapped_count
        total_controls += controls_count

        framework_scores.append({
            "framework_id": fw["id"],
            "framework_name": fw["name"],
            "total_controls": controls_count,
            "mapped_controls": mapped_count,
            "score": score,
            "grade": get_compliance_grade(score)
        })

    overall_score = int((total_mapped / total_controls) * 100) if total_controls > 0 else 0

    risks = await db.risks.find({"organization_id": org_id}, {"_id": 0}).to_list(1000)
    risk_summary = {"total": len(risks), "open": 0, "critical_high": 0, "avg_score": 0}
    if risks:
        risk_summary["open"] = sum(1 for r in risks if r.get("status") == "open")
        risk_summary["critical_high"] = sum(1 for r in risks if r.get("risk_score", 0) > 12)
        risk_summary["avg_score"] = round(sum(r.get("risk_score", 0) for r in risks) / len(risks), 1)

    tasks = await db.tasks.find({"organization_id": org_id}, {"_id": 0}).to_list(1000)
    task_summary = {"total": len(tasks), "done": 0, "overdue": 0}
    now_str = datetime.now(timezone.utc).isoformat()[:10]
    for t in tasks:
        if t.get("status") == "done":
            task_summary["done"] += 1
        if t.get("due_date") and t["due_date"] < now_str and t.get("status") != "done":
            task_summary["overdue"] += 1

    vendors = await db.vendors.find({"organization_id": org_id}, {"_id": 0}).to_list(1000)
    vendor_summary = {"total": len(vendors), "high_risk": sum(1 for v in vendors if v.get("risk_level") in ["high", "critical"])}

    audits = await db.audits.find({"organization_id": org_id}, {"_id": 0}).to_list(1000)
    audit_summary = {"total": len(audits), "completed": sum(1 for a in audits if a.get("status") == "completed")}

    policies_count = await db.policies.count_documents({"organization_id": org_id})

    return {
        "overall_compliance_score": overall_score,
        "overall_grade": get_compliance_grade(overall_score),
        "total_frameworks": len(frameworks),
        "total_controls": total_controls,
        "total_mapped": total_mapped,
        "framework_scores": framework_scores,
        "risk_summary": risk_summary,
        "task_summary": task_summary,
        "vendor_summary": vendor_summary,
        "audit_summary": audit_summary,
        "policies_count": policies_count
    }


@router.get("/reports/executive-pdf")
async def get_executive_pdf(current_user: Dict = Depends(get_current_user)):
    """Generate a downloadable PDF executive compliance report."""
    from fpdf import FPDF

    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})
    org_name = org.get("name", "Organization") if org else "Organization"

    # Gather all data
    frameworks = await db.frameworks.find({}, {"_id": 0}).to_list(100)
    total_mapped = 0
    total_controls = 0
    framework_rows = []

    for fw in frameworks:
        controls_count = await db.controls.count_documents({"framework_id": fw["id"]})
        mappings = await db.mappings.find({"organization_id": org_id, "framework_id": fw["id"]}, {"_id": 0, "control_id": 1}).to_list(10000)
        mapped_count = len(set(m["control_id"] for m in mappings))
        score = int((mapped_count / controls_count) * 100) if controls_count > 0 else 0
        total_mapped += mapped_count
        total_controls += controls_count
        framework_rows.append((fw["name"], controls_count, mapped_count, score, get_compliance_grade(score)))

    overall_score = int((total_mapped / total_controls) * 100) if total_controls > 0 else 0
    overall_grade = get_compliance_grade(overall_score)

    risks = await db.risks.find({"organization_id": org_id}, {"_id": 0}).to_list(1000)
    open_risks = sum(1 for r in risks if r.get("status") == "open")
    critical_risks = sum(1 for r in risks if r.get("risk_score", 0) > 12)

    tasks = await db.tasks.find({"organization_id": org_id}, {"_id": 0}).to_list(1000)
    now_str = datetime.now(timezone.utc).isoformat()[:10]
    tasks_done = sum(1 for t in tasks if t.get("status") == "done")
    tasks_overdue = sum(1 for t in tasks if t.get("due_date") and t["due_date"] < now_str and t.get("status") != "done")

    vendors = await db.vendors.find({"organization_id": org_id}, {"_id": 0}).to_list(1000)
    high_risk_vendors = sum(1 for v in vendors if v.get("risk_level") in ["high", "critical"])

    policies_count = await db.policies.count_documents({"organization_id": org_id})

    # Build PDF
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # Title
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(15, 81, 86)
    pdf.cell(0, 14, "Executive Compliance Report", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6, f"{org_name}  |  Generated {datetime.now(timezone.utc).strftime('%B %d, %Y %H:%M UTC')}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    # Overall Score
    pdf.set_draw_color(229, 231, 235)
    pdf.set_fill_color(249, 250, 251)
    pdf.rect(10, pdf.get_y(), 190, 28, style="FD")
    y = pdf.get_y() + 4
    pdf.set_xy(15, y)
    pdf.set_font("Helvetica", "B", 28)
    pdf.set_text_color(15, 81, 86)
    pdf.cell(30, 12, f"{overall_score}%")
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(0, 12, f"Overall Compliance Score (Grade: {overall_grade})")
    pdf.set_xy(15, y + 14)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6, f"{total_mapped} of {total_controls} controls mapped across {len(frameworks)} frameworks")
    pdf.ln(22)

    # Key Metrics
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(17, 24, 39)
    pdf.cell(0, 10, "Key Metrics", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(60, 60, 60)
    metrics = [
        f"Policies: {policies_count}",
        f"Open Risks: {open_risks} ({critical_risks} critical/high)",
        f"Tasks: {len(tasks)} total, {tasks_done} completed, {tasks_overdue} overdue",
        f"Vendors: {len(vendors)} ({high_risk_vendors} high-risk)",
    ]
    for m in metrics:
        pdf.cell(0, 7, f"  {m}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Framework Compliance Table
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(17, 24, 39)
    pdf.cell(0, 10, "Framework Compliance Breakdown", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # Table header
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(15, 81, 86)
    pdf.set_text_color(255, 255, 255)
    col_w = [70, 30, 30, 30, 30]
    headers = ["Framework", "Controls", "Mapped", "Score", "Grade"]
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 8, h, border=1, fill=True, align="C")
    pdf.ln()

    # Table rows
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(60, 60, 60)
    for row in framework_rows:
        name = row[0][:32] + "..." if len(row[0]) > 32 else row[0]
        pdf.set_fill_color(255, 255, 255)
        pdf.cell(col_w[0], 7, name, border=1)
        pdf.cell(col_w[1], 7, str(row[1]), border=1, align="C")
        pdf.cell(col_w[2], 7, str(row[2]), border=1, align="C")
        pdf.cell(col_w[3], 7, f"{row[3]}%", border=1, align="C")
        pdf.cell(col_w[4], 7, row[4], border=1, align="C")
        pdf.ln()

    pdf.ln(6)

    # Open Risks Section
    if risks:
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(17, 24, 39)
        pdf.cell(0, 10, "Open Risk Register", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(15, 81, 86)
        pdf.set_text_color(255, 255, 255)
        r_col_w = [80, 30, 25, 25, 30]
        r_headers = ["Risk", "Category", "Score", "Status", "Owner"]
        for i, h in enumerate(r_headers):
            pdf.cell(r_col_w[i], 8, h, border=1, fill=True, align="C")
        pdf.ln()
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(60, 60, 60)
        for r in sorted(risks, key=lambda x: x.get("risk_score", 0), reverse=True)[:15]:
            title = r.get("title", "")[:40] + ("..." if len(r.get("title", "")) > 40 else "")
            pdf.cell(r_col_w[0], 7, title, border=1)
            pdf.cell(r_col_w[1], 7, r.get("category", ""), border=1, align="C")
            pdf.cell(r_col_w[2], 7, str(r.get("risk_score", 0)), border=1, align="C")
            pdf.cell(r_col_w[3], 7, r.get("status", ""), border=1, align="C")
            pdf.cell(r_col_w[4], 7, (r.get("owner", "")[:14]) , border=1, align="C")
            pdf.ln()

    # Footer
    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 6, "This report is confidential and intended for authorized personnel only.", new_x="LMARGIN", new_y="NEXT")

    buf = io.BytesIO()
    pdf.output(buf)
    buf.seek(0)

    filename = f"compliance_report_{datetime.now(timezone.utc).strftime('%Y%m%d')}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
