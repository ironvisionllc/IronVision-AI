# 4 · Baseline task metrics (CURRENT UI)

- **Run:** `python3 scripts/ux_baseline/tasks.py`, then `python3 scripts/ux_baseline/metrics_table.py`.
- **Setup:** ISSO (demo sandbox) on the SYNTHETIC sandbox (https://aegis-rmf-demo.preview.emergentagent.com), fresh system `UXB6E5` for tasks 1–7 and 12, seeded LTP for tasks 8–11.
- **Counting rules:**
  - Clicks: every click or option choice, including the file chooser and sidebar navigation.
  - Fields: text typed, options chosen or files picked.
  - Page changes: changes of URL path.
  - Scripted time: wall-clock time of the script, including network. It is not human time; use it only to compare before and after.
- **Caveat – "Next action shown":** the walk records yes when any "Next action / Next step" text is on the final screen. Today that is often the generic "Next action: Assign key roles" banner (audit #3), so a yes here overstates the guidance.
- **Package:** the LTP package was already submitted, so the submit button was absent. The package task measures the path to the package page.
- **Screenshots** at the end of each task: `screens/tasks/<task>.png`.

| Task | Clicks | Page changes | Fields | Scripted s | Next action shown | Data entered twice | Completed | eMASS reference (approx.) |
|---|---|---|---|---|---|---|---|---|
| Register a system | 6 | 2 | 3 | 8.6 | yes | info type + PII entered here AND in Categorize | yes | ≈4 wizard pages (System Information, Authorization Information, Roles, Review/Submit) [1] |
| Categorize | 4 | 1 | 3 | 4.1 | yes | yes (see register) | yes | ≈3 screens – Categorization tab, info types, submit (approx.) [2] |
| Select a baseline | 5 | 1 | 1 | 4.7 | yes | no | yes | ≈2 – Controls → baseline auto-assigned from categorization, tailor (approx.) [2] |
| Import implementation info (Implementation Plan) | 6 | 2 | 2 | 7.0 | **no** | no | yes | ≈4 – Controls → Bulk Processing → Implementation Plan import → review (approx.) [1][3] |
| Update a control | 6 | 2 | 2 | 11.7 | **no** | no | yes | ≈3 – Controls → select control → Implementation Plan tab → save (approx.) [2] |
| Attach evidence | 7 | 2 | 3 | 7.1 | **no** | source name before first upload | yes | ≈3 – Artifacts → Add Artifact → associate to control (approx.) [2] |
| Import test results | 4 | 2 | 1 | 5.0 | **no** | no | yes | ≈4 – Controls → Bulk Processing → Test Result import → review (approx.) [1][3] |
| Review a finding | 5 | 3 | 1 | 4.8 | **no** | no | yes | ≈3 – Controls / Assets → non-compliant test result (approx.) [2] |
| Create/update a POA&M (from the finding) | 2 | 1 | 0 | 2.8 | **no** | no | yes | ≈4 – POA&M → Add/Edit item → milestones → save (approx.) [1] |
| Generate an SSP | 3 | 1 | 0 | 3.5 | yes | no | yes | ≈2 – Reports → System Security Plan report (approx.) [2] |
| Prepare an authorization package | 3 | 3 | 0 | 9.5 | yes | no | yes | ≈3 – Package → Submit → Package Approval Chain (PAC) [1] |
| Configure continuous monitoring | 5 | 1 | 3 | 4.6 | yes | no | yes | ≈3 – Controls → SLCM fields per control / bulk (approx.) [2] |
| **Total (12 tasks)** | **56** | **21** | **19** | – | 6/12 | 3 | | |

**eMASS reference sources** (approximate where marked):
- [1] DCSA, *NISP eMASS Industry Operation Guide* v1.1 (registration's 4 steps, POA&M, package submission / PAC) – https://www.dcsa.mil/Portals/91/Documents/CTP/tools/NISP%20eMASS%20Industry%20Operation%20Guide%20Version%201.1.pdf
- [2] DISA eMASS User Guide (in-app Help; not public – counts estimated from [1] and [3], so approximate)
- [3] rmf.org, *eMASS Overview / Essentials* (bulk processing of the Implementation Plan and Test Results) – https://rmf.org/wp-content/uploads/2018/03/eMASS-Overview-Outline.pdf
