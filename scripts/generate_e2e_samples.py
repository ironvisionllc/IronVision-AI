"""Generate Phase 2 E2E sample files (SYNTHETIC; RFC 5737 IPs, .demo hosts) from the Phase 1 samples.

samples/e2e/e2e-web-01.ckl               fresh STIG checklist for host e2e-web-01 (open findings incl. CAT I V-900140, CM-6)
samples/e2e/e2e-web-01_remediated.ckl    rescan: every Open rule now NotAFinding
samples/e2e/e2e_scan.nessus              fresh ACAS scan: e2e-web-01 with Log4Shell (KEV) + Terrapin
samples/e2e/e2e_scan_remediated.nessus   rescan: Log4Shell plugin no longer present on that host
"""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "samples"
OUT = ROOT / "e2e"
HOST, IP = "e2e-web-01", "192.0.2.150"


def ckl() -> None:
    src = (ROOT / "stig" / "ltp_db-server-01.ckl").read_text()
    src = src.replace("db-server-01", HOST).replace("192.0.2.11", IP)
    (OUT / f"{HOST}.ckl").write_text(src)
    (OUT / f"{HOST}_remediated.ckl").write_text(re.sub(r"<STATUS>Open</STATUS>", "<STATUS>NotAFinding</STATUS>", src))


def nessus() -> None:
    tree = ET.parse(ROOT / "acas" / "ltp_weekly_scan.nessus")
    report = tree.getroot().find("Report")
    hosts = report.findall("ReportHost")
    keep = next(h for h in hosts if any(i.get("pluginID") == "156014" for i in h.findall("ReportItem")))
    for h in hosts:
        if h is not keep:
            report.remove(h)
    keep.set("name", IP)
    for tag in keep.find("HostProperties"):
        if tag.get("name") == "host-ip":
            tag.text = IP
        elif tag.get("name") in ("host-fqdn", "netbios-name", "hostname"):
            tag.text = f"{HOST}.ltp.demo" if tag.get("name") == "host-fqdn" else HOST
    tree.write(OUT / "e2e_scan.nessus", encoding="utf-8", xml_declaration=True)
    for item in keep.findall("ReportItem"):
        if item.get("pluginID") == "156014":
            keep.remove(item)
    tree.write(OUT / "e2e_scan_remediated.nessus", encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    ckl()
    nessus()
    print("wrote", sorted(p.name for p in OUT.iterdir()))
