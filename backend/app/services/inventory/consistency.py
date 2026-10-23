"""Deterministic inventory consistency checks → discrepancies. Every change is a proposal: accept → pending approval → approve → applied (audited).
Nothing here overwrites inventory data on its own."""
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Asset, AssetCorrelation, Evidence, EvidenceSource, Finding, FreshnessPolicy, InventoryDiscrepancy, SoftwareItem
from app.services.inventory import correlate as cr

CHECK_KINDS = {"missing_from_inventory", "ambiguous_correlation", "no_scan", "conflict", "software_version", "duplicate", "likely_duplicate",
               "shared_ip", "stale_scan", "template_rule"}
KIND_LABEL = {"missing_from_inventory": "In scan, missing from inventory", "ambiguous_correlation": "Ambiguous scan → asset match",
              "no_scan": "No scan / checklist", "conflict": "Conflicting identifier", "software_version": "Software version conflict",
              "duplicate": "Duplicate", "likely_duplicate": "Likely duplicate", "shared_ip": "Shared IP", "stale_scan": "Stale scan",
              "template_rule": "eMASS template rule", "import_conflict": "Import differs from inventory"}
DEFAULT_WINDOW = 30


def now():
    return datetime.now(timezone.utc)


def _iso(d):
    return d.isoformat() if d else None


def src_label(src: str | None) -> str:
    s = src or ""
    if "mock" in s:
        return "MOCKED source"
    if s.startswith("ingest:"):
        return "Scan/checklist file import"
    return {"hwsw_import": "eMASS HW/SW import", "manual": "Manually entered", "inventory:created_from_scan": "Created from scan (approved)"}.get(s, s or "unknown")


def is_inventory(a: Asset) -> bool:
    return not a.is_unmatched and a.correlated_asset_id is None


def rec_asset(a: Asset) -> dict:
    return {"type": "asset", "id": str(a.id), "label": a.name, "source": a.inventory_source, "source_label": src_label(a.inventory_source),
            "timestamp": _iso(a.last_observed_at or a.created_at), "identifiers": {k: v for k, v in (("hostname", a.hostname), ("ip", a.ip_address),
                                                                                                    ("fqdn", a.fqdn), ("mac", a.mac_address), ("serial", a.serial_number), ("os", a.os)) if v}}


def rec_evidence(db: Session, ev: Evidence) -> dict:
    mocked = ev.source == "mock_adapter" or (ev.source_id and (s := db.get(EvidenceSource, ev.source_id)) is not None and s.adapter == "mock")
    return {"type": "evidence", "id": str(ev.id), "label": ev.file_name, "source": ev.source, "source_label": "MOCKED source" if mocked else "Scan/checklist file import",
            "timestamp": _iso(ev.collected_at)}


def window_days(db: Session, system_id) -> int:
    w = db.scalars(select(FreshnessPolicy.window_days).where(FreshnessPolicy.evidence_type.in_(("stig_checklist", "vulnerability_scan")))).all()
    return min(w) if w else DEFAULT_WINDOW


def _cpe(v: str):
    p = v.replace("cpe:2.3:", "cpe:/").split(":")
    return (p[2], p[3], p[4]) if len(p) >= 5 and p[1].strip("/") in ("a", "o") and p[4] not in ("", "*", "-") else None


def _pn(v: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (v or "").lower()).strip("_")


def detect(db: Session, system_id) -> list[dict]:
    assets = list(db.scalars(select(Asset).where(Asset.system_id == system_id)))
    by_id = {a.id: a for a in assets}
    inv = [a for a in assets if is_inventory(a)]
    linked: dict = {}
    for a in assets:
        if a.correlated_asset_id:
            linked.setdefault(a.correlated_asset_id, []).append(a)
    hist = cr._hist(db, system_id)
    fst = {aid: (n, last) for aid, n, last in db.execute(select(Finding.asset_id, func.count(), func.max(Finding.last_seen_at))
                                                          .where(Finding.system_id == system_id).group_by(Finding.asset_id))}
    corrs = list(db.scalars(select(AssetCorrelation).where(AssetCorrelation.system_id == system_id)))
    ev_ids: dict = {}
    for c in corrs:
        for aid in (c.observed_asset_id, c.chosen_asset_id):
            if aid:
                ev_ids.setdefault(aid, set()).update(c.evidence_ids or [])
    evs = {str(e.id): e for e in db.scalars(select(Evidence).where(Evidence.id.in_([uuid.UUID(i) for s in ev_ids.values() for i in s])))} if ev_ids else {}

    def ev_recs(*aids):
        ids = set().union(*(ev_ids.get(x, set()) for x in aids))
        return [rec_evidence(db, evs[i]) for i in sorted(ids) if i in evs][:5]

    out = []

    def add(kind, key, title, records, recommendation, proposed=None, details=None):
        out.append({"kind": kind, "key": key, "title": title, "records": records, "recommendation": recommendation, "proposed_change": proposed,
                    "details": details or {}})

    pending = {c.observed_asset_id: c for c in corrs if c.status == "needs_review"}
    for a in assets:
        if not (a.is_unmatched and a.correlated_asset_id is None):
            continue
        n, last = fst.get(a.id, (0, None))
        if a.id in pending:
            c = pending[a.id]
            add("ambiguous_correlation", f"amb:{a.id}", f"Scanned host “{a.name}” could match more than one inventory asset",
                [rec_asset(a), *[rec_asset(by_id[uuid.UUID(x["asset_id"])]) for x in c.candidates if uuid.UUID(x["asset_id"]) in by_id], *ev_recs(a.id)],
                "Confirm the right asset under Asset correlation (Mapping Review), or reject to keep the scanned host separate.",
                details={"correlation_id": str(c.id), "reason": c.reason, "findings": n})
        else:
            add("missing_from_inventory", f"missing:{a.id}", f"“{a.name}” appears in STIG/ACAS data but is not in the inventory",
                [rec_asset(a), *ev_recs(a.id)], "Create an inventory asset from the scan data (needs approval), or ignore with a reason.",
                {"type": "create_asset", "observed_asset_id": str(a.id)}, {"findings": n, "last_seen": _iso(last)})
    win = window_days(db, system_id)
    for a in inv:
        group = [a, *linked.get(a.id, [])]
        n = sum(fst.get(x.id, (0, None))[0] for x in group)
        last = max((fst[x.id][1] for x in group if x.id in fst and fst[x.id][1]), default=None)
        if n == 0:
            add("no_scan", f"noscan:{a.id}", f"Inventory asset “{a.name}” has no STIG checklist or ACAS scan", [rec_asset(a)],
                "Upload a STIG checklist or ACAS scan that covers this asset, or ignore with a reason (e.g. not scannable).")
        elif last and last < now() - timedelta(days=win):
            add("stale_scan", f"stale:{a.id}", f"Latest scan/checklist for “{a.name}” is {(now() - last).days} days old (freshness window {win} days)",
                [rec_asset(a), *ev_recs(*(x.id for x in group))], "Re-scan the asset or upload a current checklist.", details={"last_seen": _iso(last), "window_days": win})
        seen: dict = {}
        for x in group:
            for h in hist.get(x.id, []):
                if h.source.startswith("ingest:"):
                    seen.setdefault(h.kind, set()).add(h.value)
            if x is not a:
                for k, v in (("hostname", cr.n_host(x.hostname)), ("fqdn", cr.n_fqdn(x.fqdn)), ("mac", cr.n_mac(x.mac_address)), ("os", x.os)):
                    if v:
                        seen.setdefault(k, set()).add(v)
        evr = ev_recs(*(x.id for x in group))
        for field, kind, cur, norm, label in (("hostname", "hostname", cr.n_host(a.hostname or a.name), cr.n_host, "Hostname"),
                                              ("fqdn", "fqdn", cr.n_fqdn(a.fqdn), cr.n_fqdn, "FQDN"), ("mac_address", "mac", cr.n_mac(a.mac_address), cr.n_mac, "MAC"),
                                              ("os", "os", (a.os or "").strip() or None, lambda v: (v or "").strip(), "OS")):
            for v in sorted(seen.get(kind, ())):
                if cur and norm(v) and (norm(v).lower() != cur.lower()):
                    add("conflict", f"conflict:{a.id}:{field}:{v}", f"{label} differs for “{a.name}”: inventory “{getattr(a, field) or cur}”, scan “{v}”",
                        [rec_asset(a), *evr], f"Update the inventory {label} to the scanned value (needs approval), or ignore if the scan is wrong.",
                        {"type": "set_field", "asset_id": str(a.id), "field": field, "from": getattr(a, field), "to": v})
                elif not cur and kind in ("fqdn", "mac", "os"):
                    add("conflict", f"conflict:{a.id}:{field}:{v}", f"{label} “{v}” reported by a scan is missing in the inventory for “{a.name}”",
                        [rec_asset(a), *evr], f"Add the scanned {label} to the inventory (needs approval).",
                        {"type": "set_field", "asset_id": str(a.id), "field": field, "from": None, "to": v})
        ips = {x for x in map(cr.n_ip, [a.ip_address, *(a.ip_addresses or [])]) if x}
        for v in sorted(seen.get("ip", set()) - ips):
            add("conflict", f"conflict:{a.id}:ip:{v}", f"A scan reports IP {v} for “{a.name}”; the inventory has {', '.join(sorted(ips)) or 'no IP'}",
                [rec_asset(a), *evr], "Add the IP to the asset's inventory record (needs approval), or ignore if it belongs to another machine.",
                {"type": "add_ip", "asset_id": str(a.id), "value": v})
        if a.inventory and bool(a.inventory.get("manufacturer")) != bool(a.inventory.get("model")):
            add("template_rule", f"rule6:{a.id}", f"“{a.name}”: eMASS requires both Manufacturer and Model Number when either is given", [rec_asset(a)],
                "Complete both fields on the asset before exporting the HW/SW list.")
    cpes = [(h, _cpe(h.value)) for hs in hist.values() for h in hs if h.kind == "cpe" and h.source.startswith("ingest:")]
    for sw in db.scalars(select(SoftwareItem).where(SoftwareItem.system_id == system_id)):
        pn = _pn(sw.name)
        for h, c in cpes:
            if c and sw.version and len(pn) >= 3 and (c[1] in pn or pn in c[1]) and c[2] != sw.version:
                a = by_id.get(h.asset_id)
                add("software_version", f"swv:{sw.id}:{c[2]}", f"{sw.vendor} {sw.name}: inventory version {sw.version}, scan reports {c[2]} on “{a.name if a else '?'}”",
                    [{"type": "software", "id": str(sw.id), "label": f"{sw.vendor} {sw.name} {sw.version}", "source": sw.source, "source_label": src_label(sw.source),
                      "timestamp": _iso(sw.created_at)}, *([rec_asset(a)] if a else []), *(ev_recs(h.asset_id))],
                    "Update the software version in the inventory (needs approval), or ignore if both versions are installed.",
                    {"type": "set_software", "software_id": str(sw.id), "field": "version", "from": sw.version, "to": c[2]}, {"cpe": h.value})
    exact = set()
    for kind, get in (("hostname", lambda a: cr.n_host(a.hostname or a.name)), ("fqdn", lambda a: cr.n_fqdn(a.fqdn)), ("mac", lambda a: cr.n_mac(a.mac_address)),
                      ("serial", lambda a: cr.n_serial(a.serial_number))):
        groups: dict = {}
        for a in inv:
            if (v := get(a)):
                groups.setdefault(v, []).append(a)
        for v, g in groups.items():
            if len(g) > 1:
                exact.add(frozenset(x.id for x in g))
                add("duplicate", f"dup:{kind}:{v}", f"{len(g)} inventory assets share {kind} “{v}”", [rec_asset(x) for x in g],
                    "Remove or merge the duplicate inventory entry (edit the asset), or ignore if intentional.")
    ipg: dict = {}
    for a in inv:
        for v in {x for x in map(cr.n_ip, [a.ip_address, *(a.ip_addresses or [])]) if x}:
            ipg.setdefault(v, []).append(a)
    for v, g in ipg.items():
        if len(g) > 1:
            add("shared_ip", f"sharedip:{v}", f"{len(g)} inventory assets share IP {v}", [rec_asset(x) for x in g],
                "Shared IPs (NAT, load balancer, re-used DHCP lease) make scan correlation ambiguous – confirm scans per asset in Mapping Review.")
    loose: dict = {}
    for a in inv:
        if (h := cr.n_host(a.hostname or a.name)):
            loose.setdefault(re.sub(r"[^a-z0-9]", "", h), []).append(a)
    for v, g in loose.items():
        if len(g) > 1 and frozenset(x.id for x in g) not in exact:
            add("likely_duplicate", f"likedup:{v}", f"Likely duplicates: {', '.join(x.name for x in g)} (names differ only by punctuation)",
                [rec_asset(x) for x in g], "Check whether these are the same machine; merge or ignore with a reason.")
    return out


def run(db: Session, system_id) -> dict:
    found = {d["key"]: d for d in detect(db, system_id)}
    existing = {d.key: d for d in db.scalars(select(InventoryDiscrepancy).where(InventoryDiscrepancy.system_id == system_id))}
    ts = now()
    for k, d in found.items():
        e = existing.get(k)
        if e is None:
            db.add(InventoryDiscrepancy(system_id=system_id, status="open", last_detected_at=ts, **d))
        else:
            e.records, e.details, e.title, e.recommendation, e.last_detected_at = d["records"], d["details"], d["title"], d["recommendation"], ts
            if e.status == "open":
                e.proposed_change = d["proposed_change"]
            if e.status == "resolved":
                e.status = "open"
    for k, e in existing.items():
        if k not in found and e.kind in CHECK_KINDS and e.status in ("open", "pending_approval"):
            e.status, e.reason = "resolved", "No longer detected by the consistency checks"
    db.flush()
    rows = db.execute(select(InventoryDiscrepancy.status, func.count()).where(InventoryDiscrepancy.system_id == system_id).group_by(InventoryDiscrepancy.status)).all()
    return {"detected": len(found), **{s: n for s, n in rows}}


def apply(db: Session, d: InventoryDiscrepancy, actor_email: str) -> dict:
    pc = d.proposed_change or {}
    t = pc.get("type")
    if t == "create_asset":
        p = db.get(Asset, uuid.UUID(pc["observed_asset_id"]))
        if p is None or p.correlated_asset_id:
            raise ValueError("The scanned host is already linked to an inventory asset")
        a = Asset(system_id=p.system_id, name=p.hostname or p.name, hostname=p.hostname, ip_address=p.ip_address, ip_addresses=p.ip_addresses, fqdn=p.fqdn,
                  mac_address=p.mac_address, os=p.os, asset_type=p.asset_type, inventory_source="inventory:created_from_scan", review_status="confirmed",
                  source="inventory", provenance={"created_from_observed_asset": str(p.id), "discrepancy_id": str(d.id), "approved_by": actor_email})
        db.add(a)
        db.flush()
        cr.link(db, p, a)
        for c in db.scalars(select(AssetCorrelation).where(AssetCorrelation.observed_asset_id == p.id)):
            c.chosen_asset_id = a.id
        return {"before": None, "after": {"asset_id": str(a.id), "name": a.name, "linked_observed_asset": str(p.id)}}
    if t == "set_software":
        sw = db.get(SoftwareItem, uuid.UUID(pc["software_id"]))
        if sw is None or sw.version != pc["from"]:
            raise ValueError("The software item changed after this proposal – re-run the checks")
        sw.version = pc["to"]
        return {"before": {"version": pc["from"]}, "after": {"version": sw.version}}
    a = db.get(Asset, uuid.UUID(pc["asset_id"])) if pc.get("asset_id") else None
    if a is None:
        raise ValueError("Nothing to apply for this discrepancy – edit the inventory or ignore it with a reason")
    if t == "add_ip":
        before = {"ip_address": a.ip_address, "ip_addresses": a.ip_addresses}
        a.ip_addresses = sorted(set((a.ip_addresses or ([a.ip_address] if a.ip_address else [])) + [pc["value"]]))
        a.ip_address = a.ip_address or pc["value"]
        return {"before": before, "after": {"ip_address": a.ip_address, "ip_addresses": a.ip_addresses}}
    field = pc["field"]
    if field.startswith("inventory."):
        k = field.split(".", 1)[1]
        cur = (a.inventory or {}).get(k)
    else:
        cur = getattr(a, field)
    if (cur or None) != (pc.get("from") or None):
        raise ValueError("The asset changed after this proposal – re-run the checks")
    if field.startswith("inventory."):
        a.inventory = {**(a.inventory or {}), k: pc["to"]}
    else:
        setattr(a, field, pc["to"])
    return {"before": {field: cur}, "after": {field: pc["to"]}}

