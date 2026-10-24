"""CNSSI 1253 Appendix D parameter values (PV) mapped to Rev 5 ODPs. Notation per Appendix D pp. D-2–D-3: a paragraph label
('a.', 'c.1.') and/or '1st PV'/'2nd PV' locate the value; no annotation = the control has only one value to define.
A value is tied to an ODP only when that is unambiguous; otherwise it is kept at control level ('applies to control – choose parameter')."""
import re
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Control
from app.services import cnssi1253
from app.services.content.loader import active_catalog_id

REF = re.compile(r"^((?:[a-z]\.(?:\d+\.?)*(?:,\s*|:\s*|\s+|(?=\d+(?:st|nd|rd|th) PV)))+)")
ORD = re.compile(r"^(\d+)(?:st|nd|rd|th) PV:\s*")
LABEL = re.compile(r"^(\s*)(?:([a-z])|(\d+)|\(([a-z0-9]+)\))\.?\s")
TOKEN = re.compile(r"\[(Assignment|Selection)[^:\]]*:|\[|\]")


def entries(text: str) -> list[dict]:
    out: list[dict] = []
    for line in (text or "").splitlines():
        t = line.strip()
        if not t:
            continue
        m = REF.match(t + " ")
        paras = [p.rstrip(".") for p in re.findall(r"[a-z]\.(?:\d+\.?)*", m.group(1))] if m else []
        rest = t[m.end():].strip() if m else t
        o = ORD.match(rest)
        if not paras and not o and out:
            out[-1]["value"] += " " + t  # wrapped line
            continue
        if o and not paras and out and out[-1]["ordinal"] and out[-1]["paras"]:
            paras = list(out[-1]["paras"])  # '2nd PV' continuing the previous paragraph's '1st PV'
        out.append({"paras": paras, "ordinal": int(o.group(1)) if o else None, "value": rest[o.end():] if o else rest, "raw": t})
    for e in out:
        e["value"] = " ".join(e["value"].split())
    return out


def placeholders(statement: str) -> list[dict]:
    """[Assignment: …] / [Selection: …] in reading order with paragraph path ('h.1') and nesting depth."""
    paths: list[tuple[int, str]] = []
    out, stack, pos = [], [], 0
    for line in (statement or "").splitlines(keepends=True):
        m = LABEL.match(line)
        if m and (m.group(2) or m.group(3) or m.group(4)):
            lvl = len(m.group(1).expandtabs(4)) // 4
            while paths and paths[-1][0] >= lvl:
                paths.pop()
            paths.append((lvl, m.group(2) or m.group(3) or m.group(4)))
        for t in TOKEN.finditer(line):
            if t.group(1):
                ph = {"kind": t.group(1), "path": ".".join(x for _, x in paths), "depth": sum(1 for x in stack if x) + 1, "start": pos + t.end(), "nested": False}
                for x in stack:
                    if x:
                        x["nested"] = True
                out.append(ph)
                stack.append(ph)
            elif t.group(0) == "[":
                stack.append(None)
            elif stack:
                x = stack.pop()
                if x:
                    x["label"] = statement[x["start"]:pos + t.start()].strip()
        pos += len(line)
    return out


def _norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _flat(s: str | None) -> str:
    """Normalised placeholder text with nested placeholders / OSCAL inserts removed."""
    s = re.sub(r"\{\{[^}]*\}\}", "", s or "")
    while re.search(r"\[[^\[\]]*\]", s):
        s = re.sub(r"\[[^\[\]]*\]", "", s)
    return _norm(s)


def _map_control(row: dict, c: Control) -> dict:
    ref = {"table": row["table"], "doc_page": row["doc_page"], "pdf_page": row["pdf_page"],
           "source": f"CNSSI 1253 (2022) {row['table']} p. {row['doc_page']}"}
    allp = c.parameters or []
    agg = {x["id"]: [pr["value"] for pr in x.get("props") or [] if pr.get("name") == "aggregates"] for x in allp}
    inner = {v for vs in agg.values() for v in vs}
    params = [x for x in allp if x["id"] not in inner]  # statement-level parameters, in reading order
    phs = placeholders(c.statement or "")
    res: dict = {"odps": {}, "control_level": [], "raw": row["parameter_value"], **ref}
    es = entries(row["parameter_value"])
    rendered = lambda p: _flat(re.sub(r"^\[(Assignment|Selection)[^:]*:\s*|\]$", "", p.get("rendered") or ""))  # noqa: E731
    num = lambda p: [int(x) for x in re.findall(r"\d+", p["id"].split("_", 1)[-1])]  # noqa: E731
    order, used = [], set()  # placeholder → statement parameter by rendered text (ties: parameter numbering = reading order)
    for ph in phs:
        cand = sorted((p for p in params if p["id"] not in used and rendered(p) and rendered(p) == _flat(ph.get("label"))), key=num)
        if not cand:
            order = None
            break
        order.append(cand[0])
        used.add(cand[0]["id"])
    order_ok = order is not None and len(order) == len(params)
    params = order if order_ok else params
    for e in es:
        why = None
        if not order_ok:
            why = f"catalog statement has {len(phs)} placeholders for {len(params)} ODPs (order not verifiable)"
        hits = []
        for para in (e["paras"] or [None]):
            if why:
                break
            scope = [i for i, ph in enumerate(phs) if para is None or ph["path"] == para or ph["path"].startswith(para + ".")]
            exact = [i for i in scope if phs[i]["path"] == para]
            if para and not e["ordinal"] and len(exact) == 1 and phs[exact[0]]["depth"] == 1:
                scope = exact  # the value annotates the paragraph's own parameter
            if not scope:
                why = f"paragraph {para}. has no parameter in the Rev 5 statement"
            elif e["ordinal"]:
                if any(phs[i]["depth"] > 1 or phs[i]["nested"] for i in scope):
                    why = f"'{e['ordinal']}{'st' if e['ordinal'] == 1 else 'nd' if e['ordinal'] == 2 else 'rd' if e['ordinal'] == 3 else 'th'} PV' counted within nested parameters"
                elif e["ordinal"] > len(scope):
                    why = f"only {len(scope)} parameter(s) in {'paragraph ' + para + '.' if para else 'the control'}"
                else:
                    hits.append(scope[e["ordinal"] - 1])
            else:
                outer = [i for i in scope if phs[i]["depth"] == 1 or (para and not any(phs[j]["start"] < phs[i]["start"] and phs[j]["nested"] for j in scope))]
                if len(outer) == 1:
                    hits.append(outer[0])
                else:
                    why = f"{len(outer)} parameters in {'paragraph ' + para + '.' if para else 'the control'} and the value has no '1st/2nd PV' position"
        if why or not hits:
            res["control_level"].append({"value": e["value"], "annotation": e["raw"], "reason": why or "not located"})
            continue
        for i in hits:
            pid = params[i]["id"]
            if agg.get(pid):
                res["control_level"].append({"value": e["value"], "annotation": e["raw"],
                                             "reason": f"placeholder covers several ODPs ({', '.join(agg[pid])})"})
                continue
            if pid in res["odps"]:
                res["control_level"].append({"value": e["value"], "annotation": e["raw"], "reason": f"second value for {pid}"})
                continue
            res["odps"][pid] = {"value": e["value"], "annotation": e["raw"], "paragraph": phs[i]["path"] or None, "label": params[i].get("label")}
    return res


@lru_cache(maxsize=4)
def _all(catalog_id) -> dict:
    from app.db import SessionLocal

    with SessionLocal() as db:
        rows = {r["control_id"]: r for r in cnssi1253.rows() if r["parameter_value"] and not r["withdrawn"]}
        ctrls = {c.control_id: c for c in db.scalars(select(Control).where(Control.catalog_version_id == catalog_id, Control.control_id.in_(list(rows))))}
        return {cid: _map_control(r, ctrls[cid]) for cid, r in rows.items() if cid in ctrls}


def mapping(db: Session) -> dict:
    return _all(active_catalog_id(db))


def for_control(db: Session, cid: str) -> dict | None:
    return mapping(db).get(cid)


class Conflict(Exception):
    def __init__(self, items: list[dict]):
        super().__init__("conflict")
        self.items = items


def _odp_label(c: Control | None, pid: str) -> str:
    return next((p.get("label") or pid for p in (c.parameters if c else []) or [] if p["id"] == pid), pid)


def adopt(db: Session, s, items: list[tuple[str, str]], confirm: bool, actor) -> dict:
    """Set system ODP values to the CNSSI 1253 value (source = table/page); policy / overlay / other system values need confirmation."""
    from datetime import date

    from app.models import OdpValue
    from app.services import audit, param_compare

    if s.categorization_mode != "cnssi1253":
        raise ValueError("CNSSI 1253 parameter values apply only to NSS systems on the CNSSI 1253 framework")
    m = mapping(db)
    todo = []
    for cid, pid in items:
        v = (m.get(cid) or {}).get("odps", {}).get(pid)
        if not v:
            raise ValueError(f"No CNSSI 1253 value is mapped to {pid} of {cid.upper()}")
        todo.append((cid, pid, v, m[cid]["source"]))
    cmp = {(r["enhancement"] or r["control_id"]).lower() + "|" + r["parameter_id"]: r for r in param_compare.rows(db, s)}
    conflicts = []
    for cid, pid, v, src in todo:
        r = cmp.get(f"{cid}|{pid}") or {}
        for kind, val, who in (("Policy", r.get("policy_value"), r.get("source") if (r.get("source") or "").startswith("Policy") else "policy"),
                               ("Overlay", r.get("overlay_value"), "overlay"), ("System value", r.get("system_value"), "system ODP")):
            if val and param_compare._norm(val) != param_compare._norm(v["value"]) and not (kind == "System value" and str(r.get("source", "")).startswith("System ODP: CNSSI")):
                conflicts.append({"control_id": cid, "parameter_id": pid, "kind": kind, "current": val, "cnssi": v["value"],
                                  "message": f"{kind} ({who}) for {cid.upper()} {pid} sets '{val}'; CNSSI says '{v['value']}' – replace?"})
    if conflicts and not confirm:
        raise Conflict(conflicts)
    changes = []
    for cid, pid, v, src in todo:
        o = db.scalar(select(OdpValue).where(OdpValue.system_id == s.id, OdpValue.control_id == cid, OdpValue.parameter == pid))
        before = {"value": o.value, "source": o.source, "approved_by": o.approved_by, "approved_at": o.approved_at.isoformat() if o.approved_at else None} if o else None
        if o is None:
            o = OdpValue(system_id=s.id, control_id=cid, parameter=pid, value=v["value"][:255], source=src)
            db.add(o)
        o.value, o.source, o.approved_by, o.approved_at = v["value"][:255], src, actor.email, date.today()
        changes.append({"control_id": cid, "parameter": pid, "before": before, "after": {"value": o.value, "source": src}})
    ev = audit.record(db, action="system.parameter_cnssi_adopted", actor_user_id=actor.id, actor_email=actor.email, entity_type="system",
                      entity_id=str(s.id), after={"changes": changes, "confirmed_conflicts": conflicts})
    db.flush()
    return {"adopted": len(changes), "changes": changes, "undo_id": str(ev.id), "confirmed_conflicts": conflicts}


def undo(db: Session, s, event_id, actor) -> dict:
    from datetime import date

    from app.models import AuditEvent, OdpValue
    from app.services import audit

    ev = db.get(AuditEvent, event_id)
    if ev is None or ev.entity_id != str(s.id) or ev.action != "system.parameter_cnssi_adopted":
        raise ValueError("Adoption not found for this system")
    done = db.scalars(select(AuditEvent).where(AuditEvent.entity_id == str(s.id), AuditEvent.action == "system.parameter_cnssi_undone"))
    if any((d.after or {}).get("event_id") == str(ev.id) for d in done):
        raise ValueError("This adoption was already undone")
    for ch in (ev.after or {}).get("changes", []):
        o = db.scalar(select(OdpValue).where(OdpValue.system_id == s.id, OdpValue.control_id == ch["control_id"], OdpValue.parameter == ch["parameter"]))
        b = ch["before"]
        if b is None:
            if o:
                db.delete(o)
        else:
            o = o or OdpValue(system_id=s.id, control_id=ch["control_id"], parameter=ch["parameter"], value=b["value"], source=b["source"])
            o.value, o.source, o.approved_by = b["value"], b["source"], b["approved_by"]
            o.approved_at = date.fromisoformat(b["approved_at"]) if b["approved_at"] else None
            db.add(o)
    audit.record(db, action="system.parameter_cnssi_undone", actor_user_id=actor.id, actor_email=actor.email, entity_type="system",
                 entity_id=str(s.id), after={"event_id": str(ev.id), "restored": (ev.after or {}).get("changes", [])})
    return {"restored": len((ev.after or {}).get("changes", []))}


def control_view(db: Session, s, cid: str) -> dict | None:
    """Workbench: each ODP of the control with the current system value and the CNSSI value (NSS systems only)."""
    from app.services import param_compare

    if s.categorization_mode != "cnssi1253":
        return None
    m = for_control(db, cid)
    rs = [r for r in param_compare.rows(db, s, q=cid) if (r["enhancement"] or r["control_id"]).lower() == cid and r["parameter_id"] != "(control level)"]
    return {"source": m["source"] if m else None, "pdf_page": m["pdf_page"] if m else None, "raw": m["raw"] if m else None,
            "control_level": m["control_level"] if m else [], "odps": [{k: r.get(k) for k in ("parameter_id", "description", "policy_value", "system_value",
                                                                                         "overlay_value", "effective_value", "source", "cnssi_value", "cnssi_ref",
                                                                                         "cnssi_status", "cnssi_status_label")} for r in rs]}
