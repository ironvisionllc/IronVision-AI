"""Parameter (ODP) comparison for a system: catalog ODPs of the assigned controls next to the policy value, the approved system ODP
value and overlay values. One calculation feeds the on-screen table and every CSV export, so they always match."""
import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Control, ControlAssignment, OdpValue, Policy, System
from app.services.content.loader import active_catalog_id

COLUMNS = [("control_id", "Control ID"), ("enhancement", "Enhancement"), ("parameter_id", "Parameter ID"), ("description", "Parameter description"),
           ("policy_value", "Organization-defined value (policy)"), ("system_value", "System ODP value (approved)"), ("overlay_value", "Overlay value"),
           ("effective_value", "Effective value"), ("status_label", "Comparison status"), ("source", "Source"), ("last_modified", "Last modified"),
           ("last_modified_by", "Last modified by")]
OMITTED = {"Baseline value": "NIST SP 800-53B baselines select controls but do not assign ODP values; values come from the organization "
                             "(policy / approved system ODP) or from overlays, which have their own columns."}
STATUS = {"conflict": "Conflict – policy and system value differ", "consistent": "Consistent", "system_only": "System value set (no policy value)",
          "policy_only": "Policy value only – system ODP not set", "overlay": "Overlay-defined", "not_set": "Not set – organizational decision required"}


def _norm(v) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip().lower()


def _alt(p: dict) -> str | None:
    return next((x["value"] for x in p.get("props") or [] if x.get("name") == "alt-identifier"), None)


def _desc(p: dict) -> str:
    g = "; ".join(x.get("prose", "") for x in p.get("guidelines") or [])
    return f"{p.get('label') or ''}{' – ' + g if g else ''}".strip(" –")


def _row(c_id: str, pid: str, desc: str, pol: dict | None, sysv: OdpValue | None, ov: OdpValue | None, policy_title: str | None) -> dict:
    pv, sv, oval = (pol or {}).get("value"), sysv.value if sysv else None, ov.value if ov else None
    if pv and sv:
        st = "consistent" if _norm(pv) == _norm(sv) else "conflict"
    else:
        st = "system_only" if sv else "policy_only" if pv else "overlay" if oval else "not_set"
    eff, src, mod = (sv, f"System ODP: {sysv.source}", sysv) if sv else (oval, f"Overlay: {ov.source}", ov) if oval else \
        (pv, f"Policy: {policy_title}", None) if pv else (None, "", None)
    base = c_id.split(".")[0]
    return {"control_id": base.upper(), "enhancement": c_id.upper() if "." in c_id else "", "parameter_id": pid, "description": desc,
            "policy_value": pv, "system_value": sv, "overlay_value": oval, "effective_value": eff, "status": st, "status_label": STATUS[st], "source": src,
            "last_modified": (mod.updated_at.isoformat() if mod else (pol or {}).get("updated_at")) or "",
            "last_modified_by": (mod.approved_by if mod else (pol or {}).get("by")) or "", "policy_quote": (pol or {}).get("quote")}


def rows(db: Session, s: System, family: str | None = None, status: str | None = None, q: str | None = None,
         policy_id: uuid.UUID | None = None) -> list[dict]:
    assigned = list(db.scalars(select(ControlAssignment.control_id).where(ControlAssignment.system_id == s.id)))
    ctrls = {c.control_id: c for c in db.scalars(select(Control).where(Control.catalog_version_id == active_catalog_id(db), Control.control_id.in_(assigned)))}
    odps: dict = {}
    for o in db.scalars(select(OdpValue).where(OdpValue.system_id == s.id)):
        odps.setdefault(o.control_id, {})[o.parameter] = o
    pols: dict = {}
    for p in db.scalars(select(Policy).where(Policy.org_id == s.org_id)):
        if str(s.id) not in [str(x) for x in (p.system_ids or [])] or (policy_id and p.id != policy_id):
            continue
        for v in (p.analysis or {}).get("values", []):
            pols.setdefault(v["control_id"], {})[v["parameter"]] = {**v, "title": p.title, "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                                                                    "by": f"{p.title} v{p.version}"}
    out = []
    for cid in sorted(set(assigned) | set(odps) | set(pols)):
        c, so, po = ctrls.get(cid), dict(odps.get(cid, {})), dict(pols.get(cid, {}))
        for prm in (c.parameters or []) if c else []:
            keys = [k for k in (prm["id"], _alt(prm)) if k]
            sysv = next((so.pop(k) for k in keys if k in so), None)
            ov = next((so.pop(f"overlay:{k}") for k in keys if f"overlay:{k}" in so), None)
            pol = next((po.pop(k) for k in keys if k in po), None)
            out.append(_row(cid, prm["id"], _desc(prm), pol, sysv, ov, (pol or {}).get("title")))
        for name in sorted({k.removeprefix("overlay:") for k in so} | set(po)):  # named parameters not mapped to a catalog ODP id
            pol = po.get(name)
            out.append(_row(cid, name, "Named parameter (not mapped to a catalog ODP id)", pol, so.get(name), so.get(f"overlay:{name}"), (pol or {}).get("title")))
    if s.categorization_mode == "cnssi1253":
        out = _with_cnssi(db, out)
    if policy_id:
        out = [r for r in out if r["policy_value"]]
    if family:
        out = [r for r in out if r["control_id"].split("-")[0].lower() == family.lower()]
    if status:
        out = [r for r in out if r["status"] == status]
    if q:
        ql = q.lower()
        out = [r for r in out if ql in f"{r['control_id']} {r['enhancement']} {r['parameter_id']} {r['description']}".lower()]
    return out


CNSSI_COLUMNS = [("cnssi_value", "CNSSI 1253 value"), ("cnssi_ref", "CNSSI 1253 reference"), ("cnssi_status_label", "CNSSI comparison")]
CNSSI_STATUS = {"matches": "Matches CNSSI", "differs": "Differs from CNSSI", "not_set": "Not set – CNSSI value available"}
CONTROL_LEVEL = "(control level)"


def _with_cnssi(db: Session, out: list[dict]) -> list[dict]:
    """NSS systems: CNSSI 1253 Appendix D value beside each mapped ODP; values not tied to one ODP become a control-level row."""
    from app.services import cnssi_params

    m = cnssi_params.mapping(db)
    res, seen = [], set()
    for r in out:
        cid = (r["enhancement"] or r["control_id"]).lower()
        mc = m.get(cid)
        v = (mc or {}).get("odps", {}).get(r["parameter_id"])
        if v:
            st = "not_set" if not r["effective_value"] else "matches" if _norm(r["effective_value"]) == _norm(v["value"]) else "differs"
            r = {**r, "cnssi_value": v["value"], "cnssi_ref": f"{mc['table']}, p. {mc['doc_page']}", "cnssi_source": mc["source"],
                 "cnssi_status": st, "cnssi_status_label": CNSSI_STATUS[st]}
        res.append(r)
        if mc and mc["control_level"] and cid not in seen:
            seen.add(cid)
            for x in mc["control_level"]:
                res.append({**{k: "" for k, _ in COLUMNS}, "control_id": r["control_id"], "enhancement": r["enhancement"], "parameter_id": CONTROL_LEVEL,
                            "description": f"CNSSI 1253 value applies to control – choose parameter ({x['reason']})", "status": "not_set",
                            "status_label": "CNSSI value at control level – choose parameter", "effective_value": None,
                            "cnssi_value": x["value"], "cnssi_ref": f"{mc['table']}, p. {mc['doc_page']}", "cnssi_status": "control_level",
                            "cnssi_status_label": "applies to control – choose parameter", "cnssi_annotation": x["annotation"]})
    return res


def table(rs: list[dict], extra: list[tuple[str, str]] | None = None, tail: list[tuple[str, str]] | None = None) -> tuple[list[str], list[list]]:
    cols = (extra or []) + COLUMNS + (tail or [])
    return [lbl for _, lbl in cols], [[r.get(k) for k, _ in cols] for r in rs]
