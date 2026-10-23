"""Identifier normalisation and deterministic asset correlation. Reliable: MAC, serial, FQDN, hostname (without a conflicting IP).
IP-only, shared-IP, conflicting or multiple candidates → needs_review (Mapping Review). Findings and source IDs are never changed."""
import hashlib
import ipaddress
import json
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Asset, AssetCorrelation, AssetIdentifier

KINDS = ("mac", "serial", "fqdn", "hostname", "ip")
STRONG = {"mac", "serial", "fqdn", "hostname"}


def now():
    return datetime.now(timezone.utc)


def n_ip(v):
    try:
        return str(ipaddress.ip_address((v or "").strip()))
    except ValueError:
        return None


def n_host(v):
    v = (v or "").strip().lower()
    return v.split(".")[0] if v and not n_ip(v) else None


def n_fqdn(v):
    v = (v or "").strip().lower().rstrip(".")
    return v if "." in v and not n_ip(v) else None


def n_mac(v):
    h = re.sub(r"[^0-9a-f]", "", (v or "").lower())
    return ":".join(h[i:i + 2] for i in range(0, 12, 2)) if len(h) == 12 else None


def n_serial(v):
    v = (v or "").strip().upper()
    return v if v and v not in ("VIRTUAL", "N/A", "NA") else None


def observed(f: dict) -> dict[str, set]:
    return {"hostname": {x for x in (n_host(f.get("host")), n_host(f.get("fqdn"))) if x}, "fqdn": {x for x in (n_fqdn(f.get("fqdn")), n_fqdn(f.get("host"))) if x},
            "ip": {x for x in map(n_ip, f.get("ips") or []) if x}, "mac": {x for x in map(n_mac, f.get("macs") or []) if x},
            "serial": {x for x in [n_serial(f.get("serial"))] if x}}


def facts_key(obs: dict) -> str:
    return hashlib.sha256(json.dumps({k: sorted(v) for k, v in obs.items()}, sort_keys=True).encode()).hexdigest()


def asset_idents(a: Asset, hist: list[AssetIdentifier]) -> dict[str, set]:
    ids = {"hostname": {x for x in (n_host(a.hostname), n_host(a.name) if not a.hostname else None, n_host(a.fqdn)) if x},
           "fqdn": {x for x in [n_fqdn(a.fqdn)] if x}, "ip": {x for x in map(n_ip, [a.ip_address, *(a.ip_addresses or [])]) if x},
           "mac": {x for x in [n_mac(a.mac_address)] if x}, "serial": {x for x in [n_serial(a.serial_number)] if x}}
    for h in hist:
        if h.kind in ids:
            ids[h.kind].add(h.value)
    return ids


def _hist(db: Session, system_id) -> dict:
    out: dict = {}
    for h in db.scalars(select(AssetIdentifier).where(AssetIdentifier.system_id == system_id)):
        out.setdefault(h.asset_id, []).append(h)
    return out


def evaluate(db: Session, system_id, facts: dict, exclude: set | None = None) -> dict:
    obs = observed(facts)
    hist = _hist(db, system_id)
    cands = []
    for a in db.scalars(select(Asset).where(Asset.system_id == system_id, Asset.correlated_asset_id.is_(None))):
        if exclude and a.id in exclude:
            continue
        ids = asset_idents(a, hist.get(a.id, []))
        matched = [k for k in KINDS if obs[k] & ids[k]]
        if not matched:
            continue
        conflicts = [k for k in ("mac", "serial", "fqdn", "hostname") if obs[k] and ids[k] and not obs[k] & ids[k]]
        if "ip" not in matched and obs["ip"] and ids["ip"]:
            conflicts.append("ip")
        cands.append({"asset_id": str(a.id), "name": a.name, "matched": matched, "conflicts": conflicts, "scan_observed": a.is_unmatched,
                      "identifiers": {k: sorted(v) for k, v in ids.items() if v}})
    reliable = [c for c in cands if not c["conflicts"] and set(c["matched"]) & STRONG]
    if not cands:
        return {"status": "new", "candidates": [], "reason": "No inventory asset shares a hostname, FQDN, MAC, serial or IP"}
    if len(reliable) == 1 and len(cands) == 1:
        c = reliable[0]
        return {"status": "matched", "asset_id": c["asset_id"], "method": "deterministic:" + "+".join(c["matched"]), "candidates": cands,
                "reason": f"Matched on {', '.join(c['matched'])}"}
    shared = [i for i in obs["ip"] if sum(1 for c in cands if "ip" in c["matched"]) > 1]
    if shared:
        reason = f"Shared IP {', '.join(shared)} matches {len(cands)} assets"
    elif len(reliable) > 1:
        reason = f"{len(reliable)} assets match reliable identifiers (possible duplicates)"
    elif any(c["conflicts"] for c in cands):
        reason = "; ".join(f"{c['name']}: matches {', '.join(c['matched'])} but conflicts on {', '.join(c['conflicts'])}" for c in cands if c["conflicts"])
    else:
        reason = "Only the IP address matches – an IP alone is not a reliable identifier"
    return {"status": "needs_review", "candidates": cands, "reason": reason}


def record_identifiers(db: Session, a: Asset, facts: dict, source: str, ref: str | None = None) -> None:
    obs = observed(facts)
    extra = {"os": {facts["os"]} if facts.get("os") else set(), "cpe": set(facts.get("cpe") or []), "benchmark": set(facts.get("benchmarks") or [])}
    ts = now()
    for kind, vals in {**obs, **extra}.items():
        for v in vals:
            h = db.scalar(select(AssetIdentifier).where(AssetIdentifier.asset_id == a.id, AssetIdentifier.kind == kind, AssetIdentifier.value == v[:500],
                                                        AssetIdentifier.source == source))
            if h is None:
                db.add(AssetIdentifier(system_id=a.system_id, asset_id=a.id, kind=kind, value=v[:500], source=source, source_ref=ref, first_seen_at=ts, last_seen_at=ts))
            else:
                h.last_seen_at = ts
    db.flush()


def match_for_ingest(db: Session, system_id, facts: dict, fmt: str, evidence_id=None) -> Asset:
    obs = observed(facts)
    key = facts_key(obs)
    corr = db.scalar(select(AssetCorrelation).where(AssetCorrelation.system_id == system_id, AssetCorrelation.key == key))
    asset = None
    if corr is not None:
        aid = corr.observed_asset_id or corr.chosen_asset_id
        asset = db.get(Asset, aid) if aid else None
    if asset is None:
        d = evaluate(db, system_id, facts)
        if d["status"] == "matched":
            asset = db.get(Asset, __import__("uuid").UUID(d["asset_id"]))
        else:
            host = next(iter(sorted(obs["hostname"])), None)
            ip = next(iter(sorted(obs["ip"])), None)
            asset = Asset(system_id=system_id, name=host or ip or "unknown", hostname=host, ip_address=ip, fqdn=next(iter(sorted(obs["fqdn"])), None),
                          mac_address=next(iter(sorted(obs["mac"])), None), ip_addresses=sorted(obs["ip"]) or None, os=facts.get("os"),
                          asset_type=facts.get("target_type") or "unknown", inventory_source=f"ingest:{fmt}", is_unmatched=True, review_status="needs_review",
                          source="ingest", provenance={"reason": d["reason"]})
            db.add(asset)
            db.flush()
        if corr is None:
            corr = AssetCorrelation(system_id=system_id, key=key, facts=facts, candidates=d["candidates"], status=d["status"], method=d.get("method"),
                                    reason=d["reason"], observed_asset_id=None if d["status"] == "matched" else asset.id,
                                    chosen_asset_id=asset.id if d["status"] == "matched" else None, source_format=fmt, evidence_ids=[])
            db.add(corr)
    corr.last_seen_at = now()
    if evidence_id and str(evidence_id) not in (corr.evidence_ids or []):
        corr.evidence_ids = [*(corr.evidence_ids or []), str(evidence_id)]
    record_identifiers(db, asset, facts, f"ingest:{fmt}", str(evidence_id) if evidence_id else None)
    asset.last_observed_at = now()
    return asset


def link(db: Session, observed_asset: Asset, target: Asset) -> None:
    """Link a scan-observed asset to an inventory asset. Findings keep their asset_id and IDs; the link is what changes."""
    observed_asset.correlated_asset_id, observed_asset.is_unmatched, observed_asset.review_status = target.id, False, "confirmed"


def effective_id(a: Asset):
    return a.correlated_asset_id or a.id
