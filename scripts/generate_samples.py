"""Generate deterministic SYNTHETIC sample files into /app/samples (fake hosts: RFC 5737 IPs, .demo domains)."""
import csv
import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "samples")
BENCH = ("Demo Linux Server STIG (SYNTHETIC)", "1", "Release: 1 Benchmark Date: 01 Jan 2026 (SYNTHETIC)")
RULES = [
    ("V-900140", "SV-900140r1_rule", "high", "The operating system must enable FIPS 140-validated cryptography (FIPS mode).", ["CCI-002450", "CCI-000366", "CCI-000068"]),
    ("V-900101", "SV-900101r1_rule", "medium", "The SSH daemon must not permit direct root logins.", ["CCI-000366", "CCI-000770"]),
    ("V-900118", "SV-900118r1_rule", "medium", "Audit log files must have mode 0600 or less permissive.", ["CCI-000162", "CCI-000163", "CCI-000164"]),
    ("V-900200", "SV-900200r1_rule", "medium", "The system must display the Standard Mandatory Notice and Consent Banner.", ["CCI-000048"]),
    ("V-900210", "SV-900210r1_rule", "low", "The system must limit the number of concurrent sessions.", ["CCI-000054"]),
    ("V-900220", "SV-900220r1_rule", "medium", "Audit records must contain event type information.", ["CCI-000130"]),
    ("V-900999", "SV-900999r1_rule", "low", "Legacy policy documentation check (CCI has no Rev 5 reference – expected UNMAPPED).", ["CCI-000001"]),
]
LTP_HOSTS = [("db-server-01", "192.0.2.11"), ("app-server-02", "192.0.2.12"), ("web-server-03", "192.0.2.13"),
             ("api-gateway-04", "192.0.2.14"), ("mq-broker-05", "192.0.2.15"), ("cache-node-06", "192.0.2.16"),
             ("batch-worker-07", "192.0.2.17"), ("report-server-08", "192.0.2.18"), ("dc-ldap-09", "192.0.2.21"),
             ("file-server-10", "192.0.2.22"), ("print-server-11", "192.0.2.23"), ("backup-server-12", "192.0.2.24"),
             ("jump-host-13", "192.0.2.25"), ("ntp-server-14", "192.0.2.26")]
OPEN = {"db-server-01": {"V-900140", "V-900118", "V-900999"}, "app-server-02": {"V-900101", "V-900118"}, "mpp-app-01": {"V-900140"}}


def status(host, vid, cklb=False):
    if vid in OPEN.get(host, set()):
        return "open" if cklb else "Open"
    return "not_a_finding" if cklb else "NotAFinding"


def ckl(host, ip):
    vulns = []
    for vid, rid, sev, title, ccis in RULES:
        attrs = [("Vuln_Num", vid), ("Severity", sev), ("Rule_ID", rid), ("Rule_Ver", vid.replace("V-", "DEMO-")), ("Rule_Title", title)]
        sd = "".join(f"<STIG_DATA><VULN_ATTRIBUTE>{k}</VULN_ATTRIBUTE><ATTRIBUTE_DATA>{escape(v)}</ATTRIBUTE_DATA></STIG_DATA>" for k, v in attrs)
        sd += "".join(f"<STIG_DATA><VULN_ATTRIBUTE>CCI_REF</VULN_ATTRIBUTE><ATTRIBUTE_DATA>{c}</ATTRIBUTE_DATA></STIG_DATA>" for c in ccis)
        vulns.append(f"<VULN>{sd}<STATUS>{status(host, vid)}</STATUS><FINDING_DETAILS>Synthetic result</FINDING_DETAILS><COMMENTS/></VULN>")
    info = "".join(f"<SI_DATA><SID_NAME>{k}</SID_NAME><SID_DATA>{escape(v)}</SID_DATA></SI_DATA>" for k, v in
                   (("title", BENCH[0]), ("version", BENCH[1]), ("releaseinfo", BENCH[2]), ("stigid", "Demo_Linux_STIG")))
    return (f'<?xml version="1.0" encoding="UTF-8"?><!--SYNTHETIC DEMONSTRATION DATA--><CHECKLIST><ASSET><ROLE>Member Server</ROLE>'
            f"<HOST_NAME>{host}</HOST_NAME><HOST_IP>{ip}</HOST_IP><HOST_FQDN>{host}.logistics.demo</HOST_FQDN></ASSET>"
            f"<STIGS><iSTIG><STIG_INFO>{info}</STIG_INFO>{''.join(vulns)}</iSTIG></STIGS></CHECKLIST>")


def cklb(host, ip):
    rules = [{"group_id": vid, "rule_id": rid, "rule_version": vid.replace("V-", "DEMO-"), "rule_title": title, "severity": sev,
              "status": status(host, vid, True), "ccis": ccis, "finding_details": "Synthetic result", "comments": ""}
             for vid, rid, sev, title, ccis in RULES]
    return json.dumps({"title": "SYNTHETIC DEMONSTRATION DATA", "target_data": {"host_name": host, "ip_address": ip, "fqdn": f"{host}.logistics.demo"},
                       "stigs": [{"stig_name": "Demo_Linux_STIG", "display_name": BENCH[0], "version": BENCH[1], "release_info": BENCH[2], "rules": rules}]}, indent=1)


def item(port, proto, svc, sev, pid, name, cves=()):
    c = "".join(f"<cve>{x}</cve>" for x in cves)
    return (f'<ReportItem port="{port}" svc_name="{svc}" protocol="{proto}" severity="{sev}" pluginID="{pid}" pluginName="{escape(name)}">'
            f"<risk_factor>{['None','Low','Medium','High','Critical'][int(sev)]}</risk_factor>{c}<plugin_output>Synthetic</plugin_output></ReportItem>")


def host(name, ip, items):
    return (f'<ReportHost name="{ip}"><HostProperties><tag name="host-ip">{ip}</tag><tag name="hostname">{name}</tag>'
            f'<tag name="operating-system">Demo Linux 9</tag></HostProperties>{"".join(items)}</ReportHost>')


def nessus():
    hosts = [
        host("app-server-02", "192.0.2.12", [item(8443, "tcp", "www", "4", "156014", "Apache Log4j RCE (Log4Shell)", ["CVE-2021-44228"]),
                                             item(22, "tcp", "ssh", "2", "187315", "SSH Terrapin Prefix Truncation Weakness", ["CVE-2023-48795"]),
                                             item(0, "tcp", "general", "0", "19506", "Nessus Scan Information")]),
        host("db-server-01", "192.0.2.11", [item(5432, "tcp", "postgresql", "2", "51192", "SSL Certificate Cannot Be Trusted")]),
        host("legacy-scanner-host", "198.51.100.77", [item(443, "tcp", "www", "2", "57582", "SSL Self-Signed Certificate")]),
    ]
    return f'<?xml version="1.0"?><!--SYNTHETIC DEMONSTRATION DATA--><NessusClientData_v2><Report name="LTP weekly scan (SYNTHETIC)">{"".join(hosts)}</Report></NessusClientData_v2>'


def main():
    (OUT / "stig").mkdir(parents=True, exist_ok=True)
    (OUT / "acas").mkdir(parents=True, exist_ok=True)
    for h, ip in LTP_HOSTS:
        if h == "app-server-02":
            (OUT / "stig" / f"ltp_{h}.cklb").write_text(cklb(h, ip))
        else:
            (OUT / "stig" / f"ltp_{h}.ckl").write_text(ckl(h, ip))
    (OUT / "stig" / "mpp_mpp-app-01.ckl").write_text(ckl("mpp-app-01", "203.0.113.10"))
    (OUT / "acas" / "ltp_weekly_scan.nessus").write_text(nessus())
    with open(OUT / "acas" / "fmdh_scan_export.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Plugin ID", "CVE", "CVSS v3.0 Base Score", "Risk", "Host", "Protocol", "Port", "Name", "Synopsis"])
        w.writerow(["187315", "CVE-2023-48795", "5.9", "Medium", "198.51.100.21", "tcp", "22", "SSH Terrapin Prefix Truncation Weakness", "SYNTHETIC"])
        w.writerow(["19506", "", "", "None", "198.51.100.21", "tcp", "0", "Nessus Scan Information", "SYNTHETIC"])
    (OUT / "README.md").write_text("# SYNTHETIC sample files\nGenerated by scripts/generate_samples.py. Hosts/IPs are fake (RFC 5737, .demo).\n"
                                   "STIG rules V-9001xx belong to a SYNTHETIC benchmark; their CCI references are real CCI IDs resolved via the pinned DISA CCI list.\n")


if __name__ == "__main__":
    main()
