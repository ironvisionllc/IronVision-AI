"""Customer responsibility matrix (CRM) import: CSV/XLSX, column mapping, preview with row-level errors, apply with audit; bulk inheritance."""
import csv
import io
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CommonControlProvider, ControlAssignment, ProviderControl, User
from app.services import audit

FIELDS = {"control_id": "Control ID", "responsibility": "Responsibility (inherited / shared / system)",
          "provider_responsibility": "Provider responsibility text", "customer_responsibility": "Customer (system) responsibility text"}
REQUIRED = ("control_id", "responsibility")
SYNONYMS = {"control_id": ("control", "control id", "control_id", "id", "control identifier", "nist control"),
            "responsibility": ("responsibility", "type", "inheritance", "implementation", "responsible party", "status"),
            "provider_responsibility": ("provider responsibility", "provider_responsibility", "csp responsibility", "provider"),
            "customer_responsibility": ("customer responsibility", "customer_responsibility", "system responsibility", "customer", "tenant responsibility")}
RESP_WORDS = {"inherited": "inherited", "fully inherited": "inherited", "provider": "inherited", "csp": "inherited",
              "shared": "shared", "hybrid": "shared", "system": "system", "customer": "system", "system-specific": "system", "system specific": "system"}
SAMPLE = ("# SAMPLE – synthetic customer responsibility matrix template. Replace with your provider's official CRM.\n"
          "control_id,responsibility,provider_responsibility,customer_responsibility\n"
          "pe-3,inherited,SAMPLE: Provider controls physical access to the data center.,\n"
          "ac-2,shared,SAMPLE: Provider manages platform administrator accounts.,SAMPLE: System team manages application user accounts.\n"
          "sc-28,shared,SAMPLE: Provider encrypts storage volumes at rest.,SAMPLE: System team enables encryption for its databases.\n"
          "au-6,system,,SAMPLE: System team reviews its own audit logs weekly.\n")


def _xlsx_rows(data: bytes) -> list[list[str]]:
    """First worksheet of an .xlsx (Office Open XML) read with the standard library – no extra dependency."""
    import re
    import zipfile
    from xml.etree import ElementTree as ET

    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        names = z.namelist()
        shared = []
        if "xl/sharedStrings.xml" in names:
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t")))
        sheet = sorted(n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n))[0]
        root = ET.fromstring(z.read(sheet))
    except (zipfile.BadZipFile, IndexError, KeyError, ET.ParseError) as exc:
        raise ValueError("Could not read the Excel file – save it as .xlsx or CSV and try again.") from exc
    out = []
    for row in root.iter(f"{{{ns['m']}}}row"):
        cells: dict[int, str] = {}
        for c in row.findall("m:c", ns):
            letters = re.match(r"[A-Z]+", c.get("r", "A"))
            col = 0
            for ch in letters.group(0) if letters else "A":
                col = col * 26 + ord(ch) - 64
            t, v = c.get("t"), c.find("m:v", ns)
            if t == "s" and v is not None:
                val = shared[int(v.text)]
            elif t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter(f"{{{ns['m']}}}t"))
            else:
                val = v.text if v is not None and v.text else ""
            cells[col - 1] = val.strip()
        if cells:
            out.append([cells.get(i, "") for i in range(max(cells) + 1)])
    return out


def read_table(name: str, data: bytes) -> tuple[list[str], list[list[str]]]:
    if name.lower().endswith((".xlsx", ".xlsm")) or data[:2] == b"PK":
        rows = _xlsx_rows(data)
    else:
        text = data.decode("utf-8-sig", errors="replace")
        rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(text)) if r and not r[0].lstrip().startswith("#")]
    rows = [r for r in rows if any(r)]
    if len(rows) < 2:
        raise ValueError("The file has no data rows – expected a header row and at least one control row.")
    return rows[0], rows[1:]


def suggest(headers: list[str]) -> dict:
    out = {}
    low = [h.lower().strip() for h in headers]
    for f, words in SYNONYMS.items():
        idx = next((i for i, h in enumerate(low) if h in words), None)
        if idx is None:
            idx = next((i for i, h in enumerate(low) if any(w in h for w in words)), None)
        if idx is not None and headers[idx] not in out.values():
            out[f] = headers[idx]
    return out


def _norm_id(v: str) -> str:
    return v.strip().lower().replace(" ", "").replace("(", ".").replace(")", "")


def preview(db: Session, provider: CommonControlProvider, system_id, name: str, data: bytes, mapping: dict | None) -> dict:
    headers, rows = read_table(name, data)
    mapping = mapping or suggest(headers)
    missing = [FIELDS[f] for f in REQUIRED if not mapping.get(f) or mapping[f] not in headers]
    out = {"headers": headers, "mapping": mapping, "suggested": suggest(headers), "fields": FIELDS, "missing_columns": missing, "rows": [], "summary": {}}
    if missing:
        return out
    col = {f: headers.index(h) for f, h in mapping.items() if h in headers}
    assigned = {a.control_id: a for a in db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == system_id))} if system_id else {}
    existing = {pc.control_id: pc for pc in db.scalars(select(ProviderControl).where(ProviderControl.provider_id == provider.id))}
    seen = set()
    for n, r in enumerate(rows, start=2):
        get = lambda f: (r[col[f]] if f in col and col[f] < len(r) else "").strip()  # noqa: E731
        cid, raw = _norm_id(get("control_id")), get("responsibility").lower()
        resp = RESP_WORDS.get(raw)
        errs = []
        if not cid:
            errs.append("control ID is empty")
        elif cid in seen:
            errs.append("control appears twice in the file")
        if not resp:
            errs.append(f"responsibility “{raw or '(blank)'}” is not inherited, shared or system")
        if resp == "shared" and not (get("provider_responsibility") and get("customer_responsibility")):
            errs.append("shared controls need both provider and customer responsibility text")
        seen.add(cid)
        a = assigned.get(cid)
        change = "error" if errs else ("not in this system" if system_id and a is None else
                                       ("unchanged" if a is not None and a.responsibility == resp and a.provider_id == provider.id else
                                        (f"{a.responsibility} → {resp}" if a is not None else ("update matrix" if cid in existing else "new in matrix"))))
        out["rows"].append({"row": n, "control_id": cid, "responsibility": resp or raw, "provider_responsibility": get("provider_responsibility"),
                            "customer_responsibility": get("customer_responsibility"), "errors": errs, "change": change})
    s = out["summary"]
    for r in out["rows"]:
        k = "errors" if r["errors"] else ("unchanged" if r["change"] == "unchanged" else ("not_in_system" if r["change"] == "not in this system" else "changes"))
        s[k] = s.get(k, 0) + 1
    return out


def apply(db: Session, provider: CommonControlProvider, system_id, name: str, data: bytes, mapping: dict | None, actor: User) -> dict:
    pv = preview(db, provider, system_id, name, data, mapping)
    if pv["missing_columns"]:
        raise ValueError(f"Map these columns first: {', '.join(pv['missing_columns'])}")
    good = [r for r in pv["rows"] if not r["errors"]]
    if not good:
        raise ValueError("No valid rows to apply – fix the row errors shown in the preview.")
    label = f"CRM import: {name}"
    for r in good:
        pc = db.scalar(select(ProviderControl).where(ProviderControl.provider_id == provider.id, ProviderControl.control_id == r["control_id"]))
        if pc is None:
            pc = ProviderControl(provider_id=provider.id, control_id=r["control_id"], responsibility=r["responsibility"])
            db.add(pc)
        pc.responsibility, pc.provider_responsibility, pc.system_responsibility = r["responsibility"], r["provider_responsibility"], r["customer_responsibility"]
        pc.matrix_source = label
    changed = []
    if system_id:
        assigned = {a.control_id: a for a in db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == system_id))}
        for r in good:
            a = assigned.get(r["control_id"])
            if a is None:
                continue
            a.responsibility = r["responsibility"]
            a.provider_id = provider.id if r["responsibility"] != "system" else None
            a.provider_responsibility_text, a.system_responsibility_text = r["provider_responsibility"] or None, r["customer_responsibility"] or None
            if r["responsibility"] == "inherited":
                a.implementation_status = "inherited"
            changed.append(r["control_id"])
        db.flush()
        from app.services.evaluation import evaluate_system

        evaluate_system(db, system_id)
    result = {"matrix_rows": len(good), "skipped_errors": len(pv["rows"]) - len(good), "controls_updated": len(changed)}
    audit.record(db, action="provider.crm_applied", actor_user_id=actor.id, actor_email=actor.email, entity_type="provider", entity_id=str(provider.id),
                 details={**result, "file": name, "system_id": str(system_id) if system_id else None, "mapping": pv["mapping"], "controls": changed[:200]})
    return result


def bulk_set(db: Session, system_id, control_ids: list[str], responsibility: str, provider_id, provider_text: str | None, system_text: str | None,
             actor: User) -> dict:
    ids = {_norm_id(c) for c in control_ids if c.strip()}
    rows = list(db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == system_id, ControlAssignment.control_id.in_(ids))))
    for a in rows:
        a.responsibility, a.provider_id = responsibility, provider_id if responsibility != "system" else None
        if provider_text is not None:
            a.provider_responsibility_text = provider_text or None
        if system_text is not None:
            a.system_responsibility_text = system_text or None
        if responsibility == "inherited":
            a.implementation_status = "inherited"
        elif a.implementation_status == "inherited":
            a.implementation_status = "planned"
    db.flush()
    from app.services.evaluation import evaluate_system

    evaluate_system(db, system_id)
    done = sorted(a.control_id for a in rows)
    audit.record(db, action="inheritance.bulk_updated", actor_user_id=actor.id, actor_email=actor.email, entity_type="system", entity_id=str(system_id),
                 after={"responsibility": responsibility, "provider_id": str(provider_id) if provider_id else None, "controls": done})
    return {"updated": done, "not_assigned": sorted(ids - set(done))}


def expiry_status(p: CommonControlProvider, today: date | None = None) -> dict:
    today = today or date.today()
    if not p.package_expiration:
        return {"status": "unknown", "message": "No authorization expiration date recorded – add it so inherited controls can be trusted."}
    days = (p.package_expiration - today).days
    if days < 0:
        return {"status": "expired", "days": days, "message": f"Provider authorization EXPIRED {-days} day(s) ago – inherited controls are no longer covered."}
    if days <= 90:
        return {"status": "expiring", "days": days, "message": f"Provider authorization expires in {days} day(s) – confirm renewal with the provider."}
    return {"status": "current", "days": days, "message": f"Authorized until {p.package_expiration.isoformat()}."}


def provider_or_404(db: Session, provider_id: uuid.UUID, org_id):
    p = db.get(CommonControlProvider, provider_id)
    return p if p is not None and p.org_id == org_id else None
