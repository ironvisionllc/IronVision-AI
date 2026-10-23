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


SUPPORTED = ("Supported scan formats: DISA STIG checklist .ckl (XML) and .cklb (JSON, STIG Viewer 3); SCAP/XCCDF results .xml (DISA STIG XCCDF "
             "results, SCAP Compliance Checker output, SCAP ARF); Nessus/ACAS .nessus (XML) and CSV export; SARIF (.sarif/.json). "
             "Policy documents (.docx/.pdf) are uploaded in Policy Auditor.")


def _root_tag(data: bytes) -> str | None:
    import re
    s = data[:200_000].decode("utf-8", "ignore")
    s = re.sub(r"<\?.*?\?>|<!--.*?-->", "", s, flags=re.S)
    m = re.search(r"<(?:[A-Za-z_][\w.-]*:)?([A-Za-z_][\w.-]*)", s)
    return m.group(1) if m else None


def detect_format(file_name: str, data: bytes) -> str:
    """By CONTENT (the extension is only a hint). Every rejection says exactly why and lists the supported formats."""
    body = data.lstrip(b"\xef\xbb\xbf \t\r\n")
    if body[:5] == b"%PDF-" or (body[:4] == b"PK\x03\x04" and b"word/" in data[:300_000]):
        raise ParseError(f"{file_name}: this is a policy document ({'PDF' if body[:5] == b'%PDF-' else 'DOCX'}), not a scan result. {SUPPORTED}")
    if body[:1] == b"<":
        root = _root_tag(body)
        if root == "NessusClientData_v2":
            return "nessus_xml"
        if root == "CHECKLIST":
            return "ckl"
        if root in ("Benchmark", "TestResult", "asset-report-collection", "data-stream-collection"):
            if b"TestResult" in data:   # anywhere: SCC/DISA results put TestResult after all Rule definitions (often > 2 MB)
                return "xccdf"
            raise ParseError(f"{file_name}: XCCDF {root} without results – no <TestResult> element. This is STIG/SCAP content, not a scan result: "
                             f"run SCAP Compliance Checker (or OpenSCAP) against it and upload the XCCDF results file. {SUPPORTED}")
        raise ParseError(f"{file_name}: XML but not a supported scan format – root element is <{root}>. {SUPPORTED}")
    if body[:1] in (b"{", b"["):
        try:
            doc = json.loads(data.decode("utf-8-sig"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ParseError(f"{file_name}: malformed JSON ({exc}). {SUPPORTED}") from exc
        if isinstance(doc, dict) and "stigs" in doc:
            return "cklb"
        if isinstance(doc, dict) and "runs" in doc:
            return "sarif"
        keys = sorted(doc)[:8] if isinstance(doc, dict) else "a list"
        raise ParseError(f"{file_name}: JSON but neither CKLB (no 'stigs') nor SARIF (no 'runs'); top level: {keys}. {SUPPORTED}")
    first = data.decode("utf-8-sig", "ignore").splitlines()[0] if data else ""
    cols = [c.strip().strip('"') for c in first.split(",")]
    if "Plugin ID" in cols or ("Plugin" in cols and ({"Host", "IP Address", "DNS Name"} & set(cols))):
        return "nessus_csv"
    if "," in first:
        raise ParseError(f"{file_name}: CSV but not a Nessus/ACAS export – no 'Plugin ID' column (columns: {', '.join(cols[:8])}). {SUPPORTED}")
    raise ParseError(f"{file_name}: unrecognized content (starts with {body[:16]!r}). {SUPPORTED}")


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
        r = {**r, "Plugin ID": r.get("Plugin ID") or r.get("Plugin"), "Host": r.get("Host") or r.get("IP Address") or r.get("DNS Name"),
             "Risk": r.get("Risk") or r.get("Severity"), "Name": r.get("Name") or r.get("Plugin Name")}
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


XCCDF_RESULT = {"pass": "pass", "fail": "open", "notapplicable": "not_applicable", "fixed": "pass"}
CCI_SYSTEMS = ("http://cyber.mil/cci", "http://iase.disa.mil/cci")


def _ln(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_xccdf(data: bytes) -> list[dict]:
    """XCCDF 1.1/1.2 results (standalone or inside a SCAP ARF report). rule-result idref → Rule (title, severity, CCI idents)."""
    root = _safe_xml(data)
    rules, groups = {}, {}
    bench = ver = None
    for el in root.iter():
        n = _ln(el.tag)
        if n == "Benchmark" and bench is None:
            bench = el.get("id")
            ver = next((c.text for c in el if _ln(c.tag) == "version"), None)
        elif n == "Group":
            for r in el:
                if _ln(r.tag) == "Rule":
                    groups[r.get("id")] = el.get("id")
        elif n == "Rule":
            rules[el.get("id")] = {"title": next((c.text for c in el if _ln(c.tag) == "title"), None), "severity": el.get("severity"),
                                   "ccis": [c.text for c in el if _ln(c.tag) == "ident" and c.get("system") in CCI_SYSTEMS]}
    out = []
    for tr in (e for e in root.iter() if _ln(e.tag) == "TestResult"):
        host = next((c.text for c in tr if _ln(c.tag) == "target"), None)
        ip = next((c.text for c in tr if _ln(c.tag) == "target-address"), None)
        bench = bench or (next((c.get("href") for c in tr if _ln(c.tag) == "benchmark"), None))
        for rr in (c for c in tr if _ln(c.tag) == "rule-result"):
            rid = rr.get("idref")
            res = next((c.text for c in rr if _ln(c.tag) == "result"), "") or ""
            meta = rules.get(rid, {})
            ccis = meta.get("ccis") or [c.text for c in rr if _ln(c.tag) == "ident" and c.get("system") in CCI_SYSTEMS]
            rec = _stig_record(host, ip, bench, ver, {"rule_id": rid, "vuln_id": groups.get(rid) or rid, "title": meta.get("title") or rid,
                                                      "severity": rr.get("severity") or meta.get("severity"), "status": "", "ccis": ccis,
                                                      "finding_details": f"XCCDF result: {res}"})
            rec["status"] = XCCDF_RESULT.get(res.strip().lower(), "not_reviewed")
            out.append(rec)
    if not out:
        raise ParseError("No XCCDF TestResult/rule-result elements found")
    return out


SARIF_LEVEL = {"error": "high", "warning": "medium", "note": "low", "none": "info"}


def parse_sarif(data: bytes) -> list[dict]:
    """SARIF 2.1.0 (pipeline SAST / container scanners). CWE taken from rule tags/properties; mapping via a versioned org rule."""
    import re

    try:
        doc = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ParseError(f"Malformed JSON: {exc}") from exc
    out = []
    for run in doc.get("runs", []):
        drv = (run.get("tool") or {}).get("driver") or {}
        host = (run.get("properties") or {}).get("host") or (run.get("properties") or {}).get("image") or drv.get("name") or "pipeline"
        rmeta = {}
        for r in drv.get("rules", []):
            tags = " ".join((r.get("properties") or {}).get("tags", []) + [str((r.get("properties") or {}).get("cwe", ""))])
            rmeta[r.get("id")] = {"title": (r.get("shortDescription") or {}).get("text") or r.get("name"),
                                  "cwes": sorted({f"CWE-{m}" for m in re.findall(r"cwe[-/:]?(\d+)", tags, re.IGNORECASE)})}
        for res in run.get("results", []):
            rid = res.get("ruleId") or (res.get("rule") or {}).get("id")
            meta = rmeta.get(rid, {"title": rid, "cwes": []})
            loc = ((res.get("locations") or [{}])[0].get("physicalLocation") or {}).get("artifactLocation", {}).get("uri")
            sev = SARIF_LEVEL.get(res.get("level", "warning"), "medium")
            status = "pass" if res.get("kind") == "pass" else "open"
            out.append({"source_type": "sarif", "host": host, "ip": None, "plugin_id": None, "rule_id": rid, "vuln_id": rid, "benchmark": drv.get("name"),
                        "benchmark_version": drv.get("version"), "title": meta["title"] or (res.get("message") or {}).get("text", rid),
                        "severity": sev, "cat": None, "status": status, "ccis": [], "cves": [c for c in re.findall(r"CVE-\d{4}-\d+", json.dumps(res))],
                        "port": None, "protocol": None, "component": loc,
                        "raw": {"cwes": meta["cwes"], "message": ((res.get("message") or {}).get("text") or "")[:1000], "tool": drv.get("name")}})
    return out


PARSERS = {"ckl": parse_ckl, "cklb": parse_cklb, "nessus_xml": parse_nessus_xml, "nessus_csv": parse_nessus_csv, "xccdf": parse_xccdf,
           "sarif": parse_sarif}
SOURCE_TYPE = {"ckl": "stig_checklist", "cklb": "stig_checklist", "xccdf": "stig_checklist", "sarif": "sarif"}
