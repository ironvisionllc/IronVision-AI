"""Parsers for ACAS/Nessus (.nessus XML, CSV) and DISA STIG checklists (.ckl XML, .cklb JSON) → normalized records."""
import csv
import io
import json
from xml.etree import ElementTree as ET

import defusedxml.ElementTree as SafeET
from defusedxml import DefusedXmlException

MAX_BYTES = 50 * 1024 * 1024
STIG_STATUS = {"open": "open", "notafinding": "pass", "not_a_finding": "pass", "not_applicable": "not_applicable",
               "not_reviewed": "not_reviewed"}
CAT = {"high": "CAT I", "medium": "CAT II", "low": "CAT III"}
NESSUS_SEV = {"0": "info", "1": "low", "2": "medium", "3": "high", "4": "critical"}


class ParseError(ValueError):
    pass


def detect_format(file_name: str, data: bytes) -> str:
    name = file_name.lower()
    head = data[:4000].decode("utf-8", "ignore")
    if name.endswith(".nessus") or "<NessusClientData_v2" in head:
        return "nessus_xml"
    if name.endswith(".ckl") or "<CHECKLIST" in head:
        return "ckl"
    if name.endswith(".cklb"):
        return "cklb"
    if name.endswith(".csv") and "Plugin ID" in head:
        return "nessus_csv"
    raise ParseError("Unsupported file: expected .nessus, Nessus CSV export, .ckl or .cklb")


def _safe_xml(data: bytes) -> ET.Element:
    if b"<!DOCTYPE" in data[:2000] or b"<!ENTITY" in data[:5000]:
        raise ParseError("DTD/entity declarations are not allowed")
    try:
        return SafeET.fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except DefusedXmlException as exc:
        raise ParseError(f"Unsafe XML rejected: {exc}") from exc
    except ET.ParseError as exc:
        raise ParseError(f"Malformed XML: {exc}") from exc


def _stig_record(host, ip, bench, bench_ver, rule: dict) -> dict:
    sev = (rule.get("severity") or "").lower()
    status = STIG_STATUS.get((rule.get("status") or "").lower().replace(" ", "_"), "not_reviewed")
    return {"source_type": "stig_checklist", "host": host, "ip": ip, "benchmark": bench, "benchmark_version": bench_ver,
            "rule_id": rule.get("rule_id"), "vuln_id": rule.get("vuln_id"), "title": rule.get("title") or rule.get("rule_id"),
            "severity": sev, "cat": CAT.get(sev), "status": status, "ccis": rule.get("ccis", []), "cves": [],
            "plugin_id": None, "port": None, "protocol": None, "component": None,
            "raw": {k: rule.get(k) for k in ("finding_details", "comments", "rule_version")}}


def parse_ckl(data: bytes) -> list[dict]:
    root = _safe_xml(data)
    host = root.findtext("ASSET/HOST_NAME") or root.findtext("ASSET/HOST_FQDN")
    ip = root.findtext("ASSET/HOST_IP")
    out = []
    for istig in root.iterfind("STIGS/iSTIG"):
        info = {s.findtext("SID_NAME"): s.findtext("SID_DATA") for s in istig.iterfind("STIG_INFO/SI_DATA")}
        for vuln in istig.iterfind("VULN"):
            attrs: dict = {}
            ccis = []
            for sd in vuln.iterfind("STIG_DATA"):
                k, v = sd.findtext("VULN_ATTRIBUTE"), sd.findtext("ATTRIBUTE_DATA")
                if k == "CCI_REF":
                    ccis.append(v)
                else:
                    attrs[k] = v
            out.append(_stig_record(host, ip, info.get("title") or info.get("stigid"), info.get("version"), {
                "rule_id": attrs.get("Rule_ID"), "vuln_id": attrs.get("Vuln_Num"), "title": attrs.get("Rule_Title"),
                "severity": attrs.get("Severity"), "status": vuln.findtext("STATUS"), "ccis": ccis,
                "finding_details": vuln.findtext("FINDING_DETAILS"), "comments": vuln.findtext("COMMENTS"),
                "rule_version": attrs.get("Rule_Ver")}))
    return out


def parse_cklb(data: bytes) -> list[dict]:
    try:
        doc = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ParseError(f"Malformed JSON: {exc}") from exc
    t = doc.get("target_data", {})
    out = []
    for stig in doc.get("stigs", []):
        for r in stig.get("rules", []):
            out.append(_stig_record(t.get("host_name") or t.get("fqdn"), t.get("ip_address"),
                                    stig.get("display_name") or stig.get("stig_name"), stig.get("version"), {
                                        "rule_id": r.get("rule_id"), "vuln_id": r.get("group_id"), "title": r.get("rule_title"),
                                        "severity": r.get("severity"), "status": r.get("status"), "ccis": r.get("ccis", []),
                                        "finding_details": r.get("finding_details"), "comments": r.get("comments"),
                                        "rule_version": r.get("rule_version")}))
    return out


def _acas(host, ip, plugin_id, title, sev, cves, port, proto, component, raw) -> dict:
    return {"source_type": "acas", "host": host, "ip": ip, "plugin_id": plugin_id, "rule_id": f"plugin-{plugin_id}",
            "vuln_id": None, "benchmark": None, "benchmark_version": None, "title": title, "severity": sev, "cat": None,
            "status": "open", "ccis": [], "cves": sorted(set(cves)), "port": port, "protocol": proto,
            "component": component, "raw": raw}


def parse_nessus_xml(data: bytes) -> list[dict]:
    root = _safe_xml(data)
    out = []
    for rh in root.iterfind("Report/ReportHost"):
        tags = {t.get("name"): t.text for t in rh.iterfind("HostProperties/tag")}
        host = tags.get("hostname") or tags.get("host-fqdn") or rh.get("name")
        ip = tags.get("host-ip") or rh.get("name")
        for it in rh.iterfind("ReportItem"):
            sev = NESSUS_SEV.get(it.get("severity", "0"), "info")
            if sev == "info":
                continue
            out.append(_acas(host, ip, it.get("pluginID"), it.get("pluginName"), sev, [c.text for c in it.iterfind("cve")],
                             it.get("port"), it.get("protocol"), it.get("svc_name"),
                             {"risk_factor": it.findtext("risk_factor"), "plugin_output": (it.findtext("plugin_output") or "")[:2000]}))
    return out


def parse_nessus_csv(data: bytes) -> list[dict]:
    rows = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    merged: dict[tuple, dict] = {}
    for r in rows:
        risk = (r.get("Risk") or "None").lower()
        if risk in ("none", ""):
            continue
        key = (r.get("Host"), r.get("Plugin ID"), r.get("Port"), r.get("Protocol"))
        rec = merged.get(key) or _acas(r.get("Host"), r.get("Host"), r.get("Plugin ID"), r.get("Name"), risk, [],
                                       r.get("Port"), r.get("Protocol"), None, {"synopsis": r.get("Synopsis")})
        if r.get("CVE"):
            rec["cves"] = sorted(set(rec["cves"] + [r["CVE"]]))
        merged[key] = rec
    return list(merged.values())


PARSERS = {"ckl": parse_ckl, "cklb": parse_cklb, "nessus_xml": parse_nessus_xml, "nessus_csv": parse_nessus_csv}
