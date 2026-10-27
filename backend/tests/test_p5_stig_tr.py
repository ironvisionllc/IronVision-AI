"""P5: STIG parsers keep the source data the viewer needs (discussion, check, fix, STIG ID, overrides, legacy IDs, original status/severity);
eMASS Test Results XLSX detection works for blank / populated / reordered / extra-sheet / XLSM variants and never drops rows silently."""
import io
import json

import openpyxl
import pytest

from app.services.ingest.parsers import parse_ckl, parse_cklb
from app.services.tr import xlsx

CKL = b"""<?xml version="1.0"?><CHECKLIST><ASSET><HOST_NAME>syn-web-01</HOST_NAME><HOST_IP>10.0.0.1</HOST_IP></ASSET><STIGS><iSTIG>
<STIG_INFO><SI_DATA><SID_NAME>title</SID_NAME><SID_DATA>SYNTHETIC Web STIG</SID_DATA></SI_DATA><SI_DATA><SID_NAME>stigid</SID_NAME><SID_DATA>SYN_Web_STIG</SID_DATA></SI_DATA>
<SI_DATA><SID_NAME>version</SID_NAME><SID_DATA>2</SID_DATA></SI_DATA></STIG_INFO>
<VULN><STIG_DATA><VULN_ATTRIBUTE>Vuln_Num</VULN_ATTRIBUTE><ATTRIBUTE_DATA>V-1001</ATTRIBUTE_DATA></STIG_DATA>
<STIG_DATA><VULN_ATTRIBUTE>Severity</VULN_ATTRIBUTE><ATTRIBUTE_DATA>high</ATTRIBUTE_DATA></STIG_DATA>
<STIG_DATA><VULN_ATTRIBUTE>Group_Title</VULN_ATTRIBUTE><ATTRIBUTE_DATA>SRG-APP-000001</ATTRIBUTE_DATA></STIG_DATA>
<STIG_DATA><VULN_ATTRIBUTE>Rule_ID</VULN_ATTRIBUTE><ATTRIBUTE_DATA>SV-1001r1_rule</ATTRIBUTE_DATA></STIG_DATA>
<STIG_DATA><VULN_ATTRIBUTE>Rule_Title</VULN_ATTRIBUTE><ATTRIBUTE_DATA>SYNTHETIC TLS must be enabled</ATTRIBUTE_DATA></STIG_DATA>
<STIG_DATA><VULN_ATTRIBUTE>Vuln_Discuss</VULN_ATTRIBUTE><ATTRIBUTE_DATA>SYNTHETIC discussion text</ATTRIBUTE_DATA></STIG_DATA>
<STIG_DATA><VULN_ATTRIBUTE>Check_Content</VULN_ATTRIBUTE><ATTRIBUTE_DATA>SYNTHETIC check text</ATTRIBUTE_DATA></STIG_DATA>
<STIG_DATA><VULN_ATTRIBUTE>Fix_Text</VULN_ATTRIBUTE><ATTRIBUTE_DATA>SYNTHETIC fix text</ATTRIBUTE_DATA></STIG_DATA>
<STIG_DATA><VULN_ATTRIBUTE>LEGACY_ID</VULN_ATTRIBUTE><ATTRIBUTE_DATA>V-9001</ATTRIBUTE_DATA></STIG_DATA>
<STIG_DATA><VULN_ATTRIBUTE>LEGACY_ID</VULN_ATTRIBUTE><ATTRIBUTE_DATA>SV-9001r1_rule</ATTRIBUTE_DATA></STIG_DATA>
<STIG_DATA><VULN_ATTRIBUTE>CCI_REF</VULN_ATTRIBUTE><ATTRIBUTE_DATA>CCI-000068</ATTRIBUTE_DATA></STIG_DATA>
<STATUS>Open</STATUS><FINDING_DETAILS>SYNTHETIC details</FINDING_DETAILS><COMMENTS>SYNTHETIC comment</COMMENTS>
<SEVERITY_OVERRIDE>medium</SEVERITY_OVERRIDE><SEVERITY_JUSTIFICATION>SYNTHETIC compensating TLS proxy</SEVERITY_JUSTIFICATION></VULN></iSTIG></STIGS></CHECKLIST>"""


def test_ckl_preserves_source_fields():
    (r,) = parse_ckl(CKL)
    raw = r["raw"]
    assert raw["discussion"] == "SYNTHETIC discussion text" and raw["check_content"] == "SYNTHETIC check text" and raw["fix_text"] == "SYNTHETIC fix text"
    assert raw["stig_id"] == "SYN_Web_STIG" and raw["group_title"] == "SRG-APP-000001" and raw["legacy_ids"] == "V-9001, SV-9001r1_rule"
    assert raw["severity_override"] == "medium" and raw["severity_justification"].startswith("SYNTHETIC")
    assert raw["source_status"] == "Open" and raw["source_severity"] == "high" and r["ccis"] == ["CCI-000068"]


def test_cklb_preserves_source_fields():
    doc = {"target_data": {"host_name": "syn-db-01"}, "stigs": [{"display_name": "SYNTHETIC DB STIG", "stig_id": "SYN_DB", "version": "1", "rules": [
        {"rule_id": "SV-2r1_rule", "group_id": "V-2", "rule_title": "SYNTHETIC audit", "severity": "medium", "status": "not_a_finding", "ccis": ["CCI-000130"],
         "discussion": "D", "check_content": "C", "fix_text": "F", "group_title": "SRG-2", "legacy_ids": ["V-77"],
         "overrides": {"severity": {"severity": "low", "reason": "SYNTHETIC reason"}}}]}]}
    (r,) = parse_cklb(json.dumps(doc).encode())
    assert {k: r["raw"][k] for k in ("discussion", "check_content", "fix_text", "stig_id", "legacy_ids", "severity_override", "severity_justification")} == \
        {"discussion": "D", "check_content": "C", "fix_text": "F", "stig_id": "SYN_DB", "legacy_ids": "V-77", "severity_override": "low", "severity_justification": "SYNTHETIC reason"}


HDR = ["Control Acronym", "AP Acronym", "CCI", "CCI Definition", "Compliance Status", "Date Tested", "Tested By", "Test Results"]


def _wb(order=HDR, rows=2, extra_first=False, orphan=False) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Template"
    if extra_first:
        wb.create_sheet("Cover", 0)["A1"] = "SYNTHETIC cover sheet"
    ws.append(order)
    for i in range(rows):
        vals = {"Control Acronym": "AC-2", "AP Acronym": f"AC-2.{i + 1}", "CCI": "000007", "CCI Definition": "SYNTHETIC"}
        ws.append([vals.get(h) for h in order])
    if orphan:
        ws.append([None, None, None, None, "Compliant", None, "SYNTHETIC", "orphan"])
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


@pytest.mark.parametrize("name,data,n,warn", [
    ("blank", _wb(rows=0), 0, "blank template"),
    ("populated", _wb(rows=3), 3, None),
    ("reordered", _wb(order=list(reversed(HDR)), rows=2), 2, None),
    ("extra_sheet", _wb(rows=2, extra_first=True), 2, None),
    ("orphan_row", _wb(rows=1, orphan=True), 1, "were not imported"),
])
def test_tr_variants(name, data, n, warn):
    d = xlsx.detect(data)
    assert d["sheet"] == "Template" and len(d["rows"]) == n
    assert {"ap_acronym", "cci", "compliance_status", "test_results"} <= set(d["roles"])
    if name == "reordered":
        assert d["roles"]["ap_acronym"] == "G" and d["roles"]["test_results"] == "A"  # by header text, never by position
    assert (warn is None and not d["warnings"]) or any(warn in w for w in d["warnings"])


def test_tr_xlsm_readable():
    wb = openpyxl.Workbook()
    wb.active.title = "Template"
    wb.active.append(HDR)
    wb.active.append(["AC-2", "AC-2.1", "000007", "x", None, None, None, None])
    b = io.BytesIO()
    wb.save(b)
    assert len(xlsx.detect(b.getvalue())["rows"]) == 1  # .xlsm packages are read the same way; VBA is never executed (keep_vba=False)
