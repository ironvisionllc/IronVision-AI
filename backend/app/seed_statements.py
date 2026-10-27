"""SYNTHETIC implementation statements for the demo / sandbox seed ONLY (called from seed_phase1, which never runs for real orgs).
Fills the empty v1 statement of a subset of base controls so the demo SSP/SAR have content; every statement is marked SYNTHETIC."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Control, ControlAssignment, Implementation, System

FAMILIES = ("ac", "au", "cm", "ia", "ir", "ra", "sc", "si", "ca", "cp", "pl", "sa")
HOW = {
    "ac": "Access is enforced through Active Directory groups mapped to application roles; accounts are requested in the ticketing system, approved by the system owner and reviewed quarterly by the ISSO.",
    "au": "Audit records from servers, network devices and the application are forwarded to the central SIEM, retained for one year and reviewed weekly by the ISSO; alerts page the on-call administrator.",
    "cm": "The baseline configuration is defined in version-controlled hardening scripts aligned to the applicable STIGs; changes go through the change advisory board and are verified by scheduled compliance scans.",
    "ia": "Users authenticate with DoD CAC/PIV (PKI) and multifactor authentication; service accounts use managed credentials rotated every 60 days.",
    "ir": "Incidents are handled under the organization's incident response plan; the ISSO reports to the CSSP within required timelines and lessons learned are captured after each event.",
    "ra": "Vulnerability scans run weekly with ACAS; findings are triaged within five business days, tracked in the POA&M and the risk assessment is updated annually.",
    "sc": "Boundary protection is provided by the enterprise firewall and web proxy; data in transit uses TLS 1.2+ with FIPS-validated modules and data at rest is encrypted on the storage array.",
    "si": "Endpoint protection and host-based intrusion prevention are deployed on all hosts; patches are applied monthly and critical patches within the IAVM deadlines.",
    "ca": "Controls are assessed by the independent SCA per the security assessment plan; results are recorded in the SAR and continuous monitoring follows the ISCM strategy.",
    "cp": "Backups are taken nightly and replicated to the alternate site; the contingency plan is tested annually and recovery objectives are documented in the BIA.",
    "pl": "The system security plan is maintained by the ISSO, reviewed annually and updated after significant changes; rules of behavior are signed by every user before access is granted.",
    "sa": "Acquisitions include security requirements in contract language; developers follow the organization's secure SDLC with code review and static analysis before release.",
}


def seed_statements(db: Session, org_id, per_family: int = 4) -> int:
    n = 0
    for s in db.scalars(select(System).where(System.org_id == org_id)):
        rows = db.execute(select(ControlAssignment, Implementation, Control.title).join(Implementation, Implementation.assignment_id == ControlAssignment.id)
                          .join(Control, Control.control_id == ControlAssignment.control_id)
                          .where(ControlAssignment.system_id == s.id, Implementation.version == 1)
                          .order_by(ControlAssignment.control_id)).all()
        used: dict = {}
        for a, impl, title in rows:
            fam = a.control_id.split("-")[0]
            if fam not in FAMILIES or "." in a.control_id or (impl.narrative or "").strip() or used.get(fam, 0) >= per_family:
                continue
            used[fam] = used.get(fam, 0) + 1
            impl.narrative = (f"SYNTHETIC demo statement – {a.control_id.upper()} {title}. For {s.name} ({s.acronym}): {HOW[fam]} "
                              f"Responsibility: {a.responsibility or 'system'}-specific. Evidence: see the linked SYNTHETIC artifacts.")
            n += 1
    db.flush()
    return n
