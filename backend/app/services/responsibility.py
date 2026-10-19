"""Customer responsibility matrix (CRM): provider vs system responsibility text per provider control.
Seeded text is a SYNTHETIC demo matrix by control family; real FedRAMP CRMs are imported via CSV."""
import csv
import io

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ControlAssignment, ProviderControl

SYNTHETIC_LABEL = "synthetic demo responsibility matrix"
FAMILY = {
    "pe": ("Provider operates and protects the data centers: physical access, visitors, power, fire, environmental controls.", "None – fully provided."),
    "mp": ("Provider sanitizes and destroys physical media in its facilities.", "System sanitizes exported data and removable media it handles."),
    "ac": ("Provider/IdP manages enterprise account lifecycle, MFA and directory groups.", "System manages application-level accounts, roles and inactivity disablement."),
    "ia": ("IdP provides authenticators, PIV/MFA and credential lifecycle.", "System enforces identifier binding and authenticator use in the application."),
    "au": ("Provider logs infrastructure/hypervisor and API events and retains them.", "System generates, reviews and retains application and OS audit logs."),
    "sc": ("Provider protects the physical network boundary and backbone encryption.", "System configures security groups, TLS, segmentation and app-layer boundary protection."),
    "cp": ("Provider supplies redundant regions and infrastructure recovery.", "System defines backups, restore tests and its contingency plan."),
    "ir": ("Provider SOC detects and reports infrastructure incidents to customers.", "System reports and handles incidents affecting its components and data."),
    "si": ("Provider patches and monitors underlying infrastructure.", "System patches OS/applications, runs malware protection and monitors its own components."),
    "cm": ("Provider hardens and baselines infrastructure services.", "System maintains its own baselines, configuration settings and change control."),
    "ma": ("Provider performs hardware and facility maintenance.", "System maintains its own software and virtual components."),
    "ra": ("Provider scans its infrastructure.", "System scans its hosts, images and applications."),
    "ca": ("Provider maintains its P-ATO and continuous monitoring deliverables.", "System assesses and monitors its own controls."),
}
DEFAULT = ("Provider implements the portion described in its package.", "System implements the system-specific portion.")


def synthetic_text(control_id: str, responsibility: str) -> tuple[str, str]:
    prov, sysp = FAMILY.get(control_id.split("-")[0], DEFAULT)
    return prov, ("None – fully inherited from the provider." if responsibility == "inherited" else sysp)


def seed_matrix(db: Session, org_id) -> None:
    from app.models import CommonControlProvider

    own = select(CommonControlProvider.id).where(CommonControlProvider.org_id == org_id)
    for pc in db.scalars(select(ProviderControl).where(ProviderControl.provider_responsibility.is_(None), ProviderControl.provider_id.in_(own))):
        pc.provider_responsibility, pc.system_responsibility = synthetic_text(pc.control_id, pc.responsibility)
        pc.matrix_source = SYNTHETIC_LABEL
    db.flush()


def apply_to_system(db: Session, system_id) -> int:
    """Fill missing provider/system responsibility text on assignments from the provider's matrix (never overwrites ISSO edits)."""
    n = 0
    for a in db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == system_id, ControlAssignment.provider_id.is_not(None))):
        pc = db.scalar(select(ProviderControl).where(ProviderControl.provider_id == a.provider_id, ProviderControl.control_id == a.control_id))
        if pc is None:
            continue
        if not a.provider_responsibility_text and pc.provider_responsibility:
            a.provider_responsibility_text, n = pc.provider_responsibility, n + 1
        if not a.system_responsibility_text and pc.system_responsibility:
            a.system_responsibility_text = pc.system_responsibility
    db.flush()
    return n


def split_missing(a: ControlAssignment) -> bool:
    if a.responsibility == "shared":
        return not (a.provider_responsibility_text and a.system_responsibility_text)
    if a.responsibility == "inherited":
        return not a.provider_responsibility_text
    return False


def import_csv(db: Session, provider_id, data: bytes, label: str) -> dict:
    """CRM CSV columns: control_id, responsibility (inherited|shared|system), provider_responsibility, customer_responsibility."""
    rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
    need = {"control_id", "responsibility", "provider_responsibility", "customer_responsibility"}
    if not rows or not need <= {k.strip().lower() for k in rows[0]}:
        raise ValueError(f"CSV must have columns: {', '.join(sorted(need))}")
    created = updated = 0
    errors = []
    for i, r in enumerate(rows, start=2):
        r = {k.strip().lower(): (v or "").strip() for k, v in r.items()}
        cid = r["control_id"].lower().replace("(", ".").replace(")", "")
        if r["responsibility"] not in ("inherited", "shared", "system"):
            errors.append(f"row {i}: responsibility must be inherited|shared|system")
            continue
        pc = db.scalar(select(ProviderControl).where(ProviderControl.provider_id == provider_id, ProviderControl.control_id == cid))
        if pc is None:
            pc = ProviderControl(provider_id=provider_id, control_id=cid, responsibility=r["responsibility"])
            db.add(pc)
            created += 1
        else:
            updated += 1
        pc.responsibility, pc.provider_responsibility, pc.system_responsibility = r["responsibility"], r["provider_responsibility"], r["customer_responsibility"]
        pc.matrix_source = label
    db.flush()
    return {"created": created, "updated": updated, "errors": errors}
