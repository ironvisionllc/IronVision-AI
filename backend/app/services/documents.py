"""SSP / SAR / RAR documents from the system's actual records (DOCX + PDF). Never fabricated: blank fields say "Not recorded", assessment
results come only from SCA Assessment records, the authorization decision only from an AO AuthorizationDecision. A missing-information check
runs first; any gap labels the document DRAFT – INCOMPLETE on every page and lists what is missing."""
import io
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Assessment, AuthorizationDecision, ControlAssignment, Implementation, Poam, System

KINDS = {"ssp": "System Security Plan (SSP)", "sar": "Security Assessment Report (SAR)", "rar": "Risk Assessment Report (RAR)"}
NR = "Not recorded"


def _cid(c: str) -> str:
    return c.upper().replace(".", "(") + (")" if "." in c else "")


def _impls(db: Session, s: System) -> dict:
    out = {}
    for a, i in db.execute(select(ControlAssignment, Implementation).outerjoin(Implementation, Implementation.assignment_id == ControlAssignment.id)
                           .where(ControlAssignment.system_id == s.id).order_by(ControlAssignment.control_id, Implementation.version.desc())):
        e = out.setdefault(a.control_id, {"a": a, "approved": None, "latest": None})
        if i is not None:
            e["latest"] = e["latest"] or i
            if i.review_status == "approved" and e["approved"] is None:
                e["approved"] = i
    return out


def build(db: Session, s: System, kind: str) -> dict:
    ctl = _impls(db, s)
    missing: list[str] = []
    head = [("System", f"{s.name} ({s.acronym})"), ("eMASS ID", s.emass_id or NR), ("Organization", s.organization_name or NR),
            ("Categorization", (s.categorization or NR).title() + f" (C {s.confidentiality_impact or '—'} / I {s.integrity_impact or '—'} / A {s.availability_impact or '—'})"),
            ("Categorization framework", "CNSSI 1253" if s.categorization_mode == "cnssi1253" else "FIPS 199 / SP 800-60"),
            ("Baseline", (s.baseline_key or NR) + (" + privacy" if s.include_privacy else "")), ("Overlays", ", ".join(s.overlay_keys or []) or "None applied"),
            ("Authorization status", s.authorization_status or NR)]
    for label, v in (("system description", s.description), ("authorization boundary", s.boundary_description), ("operating environment", s.operating_environment),
                     ("categorization", s.categorization)):
        if not (v or "").strip():
            missing.append(f"The {label} is not recorded (Categorize / system record)")
    sections: list[tuple[str, list]] = []
    if kind == "ssp":
        no_stmt = [c for c, e in ctl.items() if not (e["latest"] and (e["latest"].narrative or "").strip())]
        not_appr = [c for c, e in ctl.items() if e["approved"] is None]
        if no_stmt:
            missing.append(f"{len(no_stmt)} of {len(ctl)} controls have no implementation statement (e.g. {', '.join(_cid(c) for c in no_stmt[:5])})")
        if not_appr:
            missing.append(f"{len(not_appr)} of {len(ctl)} implementation statements are not approved")
        sections = [("1. System description", [s.description or NR, f"Authorization boundary: {s.boundary_description or NR}",
                                                 f"Operating environment: {s.operating_environment or NR}"]),
                    ("2. Control implementation (Implementation Plan)", [
                        (_cid(c), f"Implementation status: {e['a'].implementation_status} · responsibility: {e['a'].responsibility} · statement "
                                  + ("approved v%d" % e["approved"].version if e["approved"] else "DRAFT v%d (not approved)" % e["latest"].version if e["latest"] else "none"),
                         ((e["approved"] or e["latest"]).narrative if (e["approved"] or e["latest"]) and ((e["approved"] or e["latest"]).narrative or "").strip()
                          else "No statement recorded")) for c, e in ctl.items()])]
    elif kind == "sar":
        res = {r.control_id: r for r in db.scalars(select(Assessment).where(Assessment.system_id == s.id).order_by(Assessment.created_at.desc()))}
        latest = {}
        for r in res.values():
            latest.setdefault(r.control_id, r)
        not_assessed = [c for c in ctl if c not in latest]
        if not_assessed:
            missing.append(f"{len(not_assessed)} of {len(ctl)} controls have no SCA assessment record (e.g. {', '.join(_cid(c) for c in not_assessed[:5])})")
        counts: dict = {}
        for c in ctl:
            k = latest[c].result if c in latest else "not assessed"
            counts[k] = counts.get(k, 0) + 1
        sections = [("1. Summary of results (from SCA assessment records only)", [f"{k}: {v}" for k, v in sorted(counts.items())]),
                    ("2. Control results", [(_cid(c), f"Result: {r.result} · methods: {', '.join(r.methods or []) or NR} · assessed {r.created_at:%Y-%m-%d}",
                                             r.findings_text or "No findings text recorded") for c, r in sorted(latest.items()) if c in ctl]
                     or ["No SCA assessment results are recorded for this system."]),
                    ("3. Controls not yet assessed", [", ".join(_cid(c) for c in not_assessed) or "None"])]
    else:
        poams = list(db.scalars(select(Poam).where(Poam.system_id == s.id).order_by(Poam.seq)))
        open_p = [p for p in poams if p.status not in ("closed", "risk_accepted")]
        dec = db.scalar(select(AuthorizationDecision).where(AuthorizationDecision.system_id == s.id).order_by(AuthorizationDecision.created_at.desc()))
        if not poams:
            missing.append("No POA&M items are recorded – the risk picture may be incomplete")
        no_risk = [p.human_id for p in open_p if not p.residual_risk_level]
        if no_risk:
            missing.append(f"{len(no_risk)} open POA&M item(s) have no Residual Risk Level recorded (e.g. {', '.join(no_risk[:5])})")
        sections = [("1. Open weaknesses (POA&M)", [(p.human_id, f"Technical severity: {p.severity or NR} · status {p.status} · due {p.due_date or NR} · controls "
                                                               + (", ".join(_cid(c) for c in p.control_ids or []) or NR)
                                                               + f" · Raw Severity {p.raw_severity or NR} · Likelihood {p.likelihood or NR} · Impact {p.impact or NR} · Residual Risk Level {p.residual_risk_level or NR}",
                                                    p.weakness or NR) for p in open_p] or ["No open POA&M items."]),
                    ("2. Accepted risks", [(p.human_id, f"Risk accepted · expires {p.risk_acceptance_expiration or NR}", p.weakness or NR)
                                           for p in poams if p.status == "risk_accepted"] or ["None recorded."]),
                    ("3. Authorization decision", [f"{dec.decision} recorded {dec.created_at:%Y-%m-%d}; expires {dec.expiration or NR}. Rationale: {dec.rationale}"
                                                   if dec else "No authorization decision has been recorded by the AO. This report makes no risk determination on the AO's behalf."])]
    status = "DRAFT – INCOMPLETE" if missing else "DRAFT"
    return {"kind": kind, "title": KINDS[kind], "status": status, "missing": missing, "header": head, "sections": sections,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "system": s.acronym,
            "oscal_model": {"ssp": "ssp", "sar": "assessment-results"}.get(kind)}


def docx_bytes(d: dict) -> bytes:
    import docx

    doc = docx.Document()
    for sec in doc.sections:
        sec.header.paragraphs[0].text = f"{d['status']} – {d['title']} – {d['system']} – not an official record until approved"
    doc.add_heading(f"{d['title']} – {d['system']}", 0)
    doc.add_paragraph(f"{d['status']} · generated {d['generated_at']} from the system's recorded data")
    t = doc.add_table(rows=0, cols=2)
    for k, v in d["header"]:
        r = t.add_row().cells
        r[0].text, r[1].text = k, str(v)
    if d["missing"]:
        doc.add_heading("Missing information", 1)
        for m in d["missing"]:
            doc.add_paragraph(m, style="List Bullet")
    for title, items in d["sections"]:
        doc.add_heading(title, 1)
        for it in items:
            if isinstance(it, tuple):
                doc.add_heading(it[0], 3)
                doc.add_paragraph(it[1]).italic = True
                doc.add_paragraph(it[2])
            else:
                doc.add_paragraph(str(it))
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def pdf_bytes(d: dict) -> bytes:
    from xml.sax.saxutils import escape

    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    st = getSampleStyleSheet()
    P = lambda x, s="BodyText": Paragraph(escape(str(x)).replace("\n", "<br/>"), st[s])  # noqa: E731
    flow = [P(f"{d['title']} – {d['system']}", "Title"), P(f"{d['status']} · generated {d['generated_at']} from the system's recorded data")]
    flow += [P(f"<b>{k}:</b> {v}") for k, v in []] + [P(f"{k}: {v}") for k, v in d["header"]]
    if d["missing"]:
        flow += [Spacer(1, 8), P("Missing information", "Heading2")] + [P(f"• {m}") for m in d["missing"]]
    for title, items in d["sections"]:
        flow += [Spacer(1, 8), P(title, "Heading2")]
        for it in items:
            flow += [P(it[0], "Heading4"), P(it[1], "Italic"), P(it[2])] if isinstance(it, tuple) else [P(it)]

    def mark(c, _doc):
        c.saveState()
        c.setFont("Helvetica-Bold", 9)
        c.drawString(40, 770, f"{d['status']} – {d['title']} – {d['system']}")
        c.restoreState()

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=letter, topMargin=50).build(flow, onFirstPage=mark, onLaterPages=mark)
    return buf.getvalue()
