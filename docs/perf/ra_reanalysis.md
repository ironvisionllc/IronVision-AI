# RA policy re-analysis (2026-10-28)

Policy `c7978e91` (RA Policy, ra_policy_dod_aws_raven_demo.docx). Old = stored result (analyzer `deterministic`, stamped coverage-4); new = current auditor with AI, tenant cache bypassed. Verdict per control = worst requirement; counts are met/partial/missing requirements.

| Control | Old verdict (met/partial/missing) | Old reason for a missing requirement | New verdict (met/partial/missing) | Quoted policy sentence (new) |
|---|---|---|---|---|
| RA-1 | partial (31/7/0) |  | partial (31/7/0) | Purpose |
| RA-2 | missing (1/6/1) | Not found: no sentence in the policy addresses the requirement “the system and the informa | met (8/0/0) | The categorization, with supporting rationale and any applicable overlays (for example Privacy or Classified I |
| RA-2.1 | missing (0/0/2) | Not found: no sentence in the policy addresses the requirement “Conduct a impact-level cat | partial (0/2/0) | Within the system, components shall be prioritized by impact so that protection and remediation effort goes fi |
| RA-3 | missing (9/9/5) | Not found: no sentence in the policy addresses the requirement “Conduct a risk assessment, | partial (20/3/0) | Each assessment shall identify threats and vulnerabilities, and determine the likelihood and magnitude of harm |
| RA-3.1 | missing (2/2/2) | Not found: no sentence in the policy addresses the requirement “Defines the systems, syste | partial (5/1/0) | The SCRM lead shall assess supply chain risk for the system's cloud services, commercial and open-source softw |
| RA-3.2 | partial (0/2/0) |  | met (2/0/0) | Risk assessments shall draw on all-source threat information available through the CSSP and DoD cyber threat r |
| RA-3.3 | missing (0/0/3) | Not found: no sentence in the policy addresses the requirement “Determine the current cybe | partial (0/3/0) | The ISSO shall monitor the threat environment continuously, using CSSP reporting, vulnerability alerts, and AW |
| RA-5 | missing (10/5/9) | Not found: no sentence in the policy addresses the requirement “Employ vulnerability monit | partial (12/12/0) | The ISSO shall monitor and scan the system and hosted applications on the schedule below, and again whenever a |
| RA-5.2 | partial (2/1/0) |  | met (3/0/0) | Signatures and plugins shall be updated before each scan and whenever new vulnerabilities are announced. |
| RA-5.3 | missing (0/1/1) | Not found: no sentence in the policy addresses the requirement “Define the breadth and dep | partial (1/1/0) | Scan coverage shall be 100 percent of assets in the system inventory. |
| RA-5.4 | missing (0/2/3) | Not found: no sentence in the policy addresses the requirement “Defines the corrective act | partial (2/3/0) | At least quarterly, the ISSO shall determine what information about the system is discoverable from outside th |
| RA-5.5 | missing (3/0/1) | Not found: no sentence in the policy addresses the requirement “privileged access authoriz | partial (0/4/0) | Risk decisions for The Raven shall be made by the Authorizing Official on the basis of current, documented ris |
| RA-5.6 | missing (0/1/2) | Not found: no sentence in the policy addresses the requirement “Compare the results of mul | partial (1/2/0) | Results of successive scans shall be compared by automated means to identify trends, recurring findings, and r |
| RA-5.8 | missing (0/3/1) | Not found: no sentence in the policy addresses the requirement “Defines the system in whic | partial (3/1/0) | When a high or critical vulnerability is found, the ISSO shall review AWS CloudTrail, VPC Flow Logs, and host  |
| RA-5.10 | partial (0/2/0) |  | met (2/0/0) | Findings from all scanning tools shall be aggregated in AWS Security Hub or the Component SIEM and correlated  |
| RA-5.11 | missing (0/0/2) | Not found: no sentence in the policy addresses the requirement “Establish a public reporti | partial (0/2/0) | The system shall accept reports of vulnerabilities from the public through the DoD Vulnerability Disclosure Pr |
| RA-7 | partial (1/7/0) |  | met (8/0/0) | Every finding from a security or privacy assessment, continuous monitoring, or an audit shall receive a docume |
| RA-9 | met (4/0/0) |  | met (4/0/0) | The ISO shall perform a criticality analysis of system components, functions, and services, consistent with Do |
| RA-10 | partial (3/4/0) |  | met (7/0/0) | The ISSM, with the CSSP, shall establish and maintain a threat hunting capability to search for indicators of  |
