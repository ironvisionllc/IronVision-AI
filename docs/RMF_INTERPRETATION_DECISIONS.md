# RMF interpretation decisions (RMF Accuracy and Usability Improvements release)

Each interpretive UAT item was checked against the authoritative source before implementation. Tester suggestions were not adopted blindly.
Where a point could not be verified from a source we hold, it is marked **SME review required** here and in the UI.

| # | Topic | Source (section / page) | Decision | Residual SME questions |
|---|---|---|---|---|
| 2a | NSS determination | 44 U.S.C. §3552(b)(6) (NSS definition); NIST SP 800-59 (Guideline for Identifying an Information System as a National Security System) | Categorize asks "Is this a National Security System?" with **Yes / No / Unsure**, with help text citing both. Yes preselects CNSSI 1253, No preselects FIPS 199, and Unsure is recorded without choosing for the user. A No + CNSSI mismatch is warned about, not blocked. | Should the app require the SP 800-59 checklist itself to be attached as evidence? |
| 2b | FIPS 199 calculation | FIPS 199 §3 (security categories, high-water mark per objective); FIPS 200 §3 (baseline from the highest impact); SP 800-53B §2.2 | Per objective, the high-water mark across the selected information types; the overall category is the highest objective, which selects the SP 800-53B Low/Moderate/High baseline. This is unchanged and now revisioned and approved. | — |
| 2c | CNSSI 1253 categorization | CNSSI No. 1253 (security categorization of NSS: per-objective C/I/A values, no high-water-mark overall category; information types per SP 800-60) | For CNSSI 1253, C, I and A are kept **separate** (e.g. M-H-L) and no single overall value is computed. Information types still come from the SP 800-60 catalog, and CNSSI is not presented as an information-type catalog. | Resolved for control selection by the CNSSI 1253 Appendix D tables (see the next section). Still SME: the 7 Rev 5 catalog controls that are not in the 2022 tables. |
| 2d | SP 800-60 catalog content | NIST SP 800-60 Vol. 2 Rev. 1 (Aug 2008), Appendices C (Management & Support) and D (Mission-based) | The catalog is the extract already in `sp800_60_info_types.json`: **168 types** (C: 76, D: 92) with provisional C/I/A. **Gaps (reported, not invented):** (1) type descriptions are not in the extract, so the picker shows names, the line of business and provisional impacts only; (2) agency-specific information types are **not implemented** in this release. SP 800-60 Rev. 2 is an initial working draft only (csrc.nist.gov/pubs/sp/800/60/r2/iwd); Vol. 2 Rev. 1 remains the final publication used. | Load the type descriptions from the source PDF? Which roles may define agency types? |
| 2e | Approval | SP 800-37 Rev. 2, Task C-1 (categorization), C-3 (review and approval by the AO or AO's designated representative) | Approval needs the `authorization.decide` permission (Authorizing Official role). A change to an approved categorization creates a **pending re-approval** revision, and the approved values stay in force until it is re-approved. Full revision history is kept. | Should an AODR also be able to approve? (Not added: no AODR permission exists in RBAC, and RBAC was not changed.) |
| 4 | Privacy Threshold Analysis | NIST SP 800-53 Rev. 5 RA-8 (Privacy Impact Assessments) and PT family; OMB M-03-22 (PIA guidance) | The questionnaire is configurable and versioned per agency. The default set is labelled "Example set – validate against your agency's privacy requirements". Answers are Yes / No / Not sure with follow-up questions shown conditionally. The outcome is always a **recommendation**; a single "No" never concludes "no PIA required". Only a **Privacy Official** (new additive `privacy_official` role and persona with `privacy.review`) can approve or return a PTA. | The user's example question wording was not supplied in this repository; the default questions are generic PTA questions and must be validated by the agency's privacy office. |
| 6 | Overlays | CNSSI 1253 App. E Att. 5 Classified System Overlay §3 p. 3 (applicability: "by intent and design store, process, or transmit classified information"); CNSSI 1253F Att. 6 Privacy Overlays; Att. 2 Space | CNSSI overlays are offered only to systems on the CNSSI 1253 (NSS) framework. The Classified overlay additionally requires an explicit **Yes** to the classified-information question and is never applied from a classification level alone (Unknown/No → blocked with the reason). Restricted overlays (Intelligence, CDS) show "Unavailable – pending validation". Each overlay shows its issuing authority, source document, framework, status, effective date and applicability. Admins can record approved agency overlays (metadata). Existing selections are preserved and flagged "Applicability review needed". | Applying agency overlay control changes is not implemented (the record is metadata only). |
| 7 | Privacy overlay / ACCT | CNSSI 1253F Att. 6 (31 Oct 2024): Table 1 "Accountability (ACCT) Control Set", **p. 11**; Question 2 (determines whether the ACCT overlay is required), **p. 12**; §3.2 PII definition, p. 10 | The source **does** define "ACCT", so the term is kept and cited, and offered only for NSS. For non-NSS (FIPS 199) systems the CNSS Privacy Overlay is shown as not applicable, with the reason that privacy controls come from the **SP 800-53B privacy baseline** selected through the PTA / PII determination. Privacy determinations need a Privacy Official's approval (reviewer, status, date and rationale shown). No AI privacy determination exists; the UI states AI is suggestion-only. | Whether ACCT layers under Low/Moderate/High exactly as our variant switcher assumes (Att. 6 Table 2) – **SME review required**. |
| 9 | DoD Cloud SRG impact levels | DoD Cloud Computing SRG (CC SRG v1r2, Jan 2025, DISA), §3 Information Impact Levels: IL2/IL4/IL5 unclassified, **IL6 = classified information up to SECRET** | The IL picker appears only for cloud deployment models (IaaS/PaaS/SaaS/hybrid). IL6 is enabled only for CNSSI 1253 (NSS) + classified = Yes; otherwise it is disabled with the reason. On-premises systems have no IL picker, with the explanation "SRG impact levels apply to cloud service offerings". Saving an IL on a non-cloud environment, or IL6 without the conditions, is rejected (422). Existing values are kept and flagged "Review applicability". | Whether IL6 should also require a DoD mission owner flag (not modelled). |

Sources consulted on the web: DISA Cloud Computing SRG (dl.dod.cyber.mil/wp-content/uploads/cloud/); NIST SP 800-60 Rev. 2 IWD status (csrc.nist.gov/pubs/sp/800/60/r2/iwd); NIST SP 800-53B (doi.org/10.6028/NIST.SP.800-53B).

## CNSSI 1253 Appendix D NSS baselines (loaded)

**Source:** CNSSI No. 1253, *Categorization and Control Selection for National Security Systems*, 29 July 2022, corrected copy 6 Oct 2022 (`reference/cnssi1253/CNSSI_1253_Final_CORRECTED_COPY_6Oct22.pdf`, 161 pages, SHA-256 `d876741dfb78c54cf21e1f8f966475bddb9df0d3fc8e935e5350862c246d1180`). It references NIST SP 800-53 Rev 5. The old Rev 4 instruction (`CNSSI_No1253.pdf`, 27 March 2014) is not used and stays gitignored.

**Markings:** there is no banner, portion or distribution marking on any page. "FOUO" appears only in the acronym list (p. C-1, PDF p. 20) and in the Appendix E note that overlays marked UNCLASSIFIED//FOUO are on the restricted CNSS website (PDF p. 161). The PDF is therefore committed. "Distribution" hits are control titles (Trusted / Protected Distribution).

**Data:** `backend/app/services/content/cnssi1253_baselines.json` is built by `scripts/parse_cnssi1253.py` (pdfplumber; the table's vertical rules are the column boundaries and its horizontal rules are the rows) and checked by `scripts/cnssi1253_report.py`.
- 1,189 rows (Tables D-1 to D-20), each with pdf_page and doc_page; 182 of them withdrawn.
- Every ID is normalised to the Rev 5 catalog (`AC-2(12)` → `ac-2.12`): 0 IDs are missing from the catalog and 0 withdrawn statuses disagree.
- Also captured: the legend (pp. D-1–D-2), the selection rule, the PM/PT family notes, the privacy implementation consideration digits, justifications, 162 NSS parameter values, and the Assurance / Resiliency / ATT&CK flags.

**Legend (pp. D-1–D-2, PDF pp. 22–23):**
- "X" = NIST SP 800-53B baseline applicability for NSS.
- "+" = a control added for NSS.
- "--" = selected for a NIST baseline but not for an NSS baseline (privacy ones are addressed in the Privacy Overlay).
- Blank = not selected.
- Privacy Control Baseline column: X or + = "required for all NSS".

**Selection rule:** §3.2.1 Task S-1, p. 10 (PDF p. 14) says to select the NSS security control baseline from Tables D-1 to D-20 "corresponding to the security categorization of the system (i.e., the impact levels determined for each security objective)" and to include the NSS privacy control baseline, "a default for all NSS". The trigraph comes from §3.1.2 (p. 10).
- Implemented as: (C column at the C level) ∪ (I at the I level) ∪ (A at the A level) ∪ the privacy control baseline. A control counts as selected only for an X or a +, never for "--", a blank or a withdrawn row. No overall high-water mark is used.
- *Interpretation note:* the document does not use the word "union". Union is the reading of "corresponding to … the impact levels determined for each security objective", combined with the D-1 definition that the columns associate a control with an objective and a level.
- For NSS systems the SP 800-53B privacy baseline is not added; NIST-only privacy controls ("--") come through the Privacy Overlay, as §2.5.1 and the legend say.

**Counts (selected = X or +):**

| Level | C | I | A |
|---|---|---|---|
| L | 273 | 310 | 147 |
| M | 319 | 380 | 202 |
| H | 397 | 474 | 283 |

- Privacy control baseline: 93 rows.
- Unions: L-L-L = 394 (357 security + privacy), M-H-L = 559 (525 security), M-M-M = 492, H-H-H = 607.
- The document states no totals to compare against.

**Hand verification:** 30 rows were checked against rendered PDF pages 26, 79, 101, 114, 123, 129, 147 and 149. They include enhancements, withdrawn rows, "--", PM privacy-only rows, rows that differ between C, I and A, and NSS "+" additions. They are pinned in `backend/tests/test_cnssi1253.py::HAND`.

**Comparison with NIST SP 800-53B (information only, nothing changed):**
- Low: all 149 NIST Low controls are selected at L-L-L, and every "X" at Low equals NIST Low.
- Moderate: 286 of 287 are selected at M-M-M. The only NIST Moderate control not selected is IA-12(5), which the document explicitly marks "--". SA-15 and SC-7(8) are in NIST Moderate but marked "+" (not "X") at M; they are still selected.
- High: 369 of 370 are selected at H-H-H. IA-12(5) is "--"; SI-4(22) is "+" at H.
- Privacy: 69 of the 96 NIST privacy controls are in the NSS privacy baseline. The other 27 (AC-3(14), MP-6, PL-8, PM-21, PT-2 to PT-8 and others) are "--". 24 NSS-only privacy-baseline controls are added (for example AC-8, AU-9, AU-12, PM-1).

**Ambiguous rows:** none in the marks. Every C/I/A and privacy cell parsed to X, +, -- or blank with no parse problems, and the X marks reproduce SP 800-53B as shown above. Open items:

| Item | Handling |
|---|---|
| ia-13, ia-13.1, ia-13.2, ia-13.3, sa-15.13, sa-24, si-2.7: in our Rev 5 (5.1.x) catalog but not in the July 2022 tables | Not selected. The Select step shows **SME review required** with this list. |
| 13 title wording differences (e.g. AC-6(8) "Least Privilege Levels…" vs the catalog "Privilege Levels…", IA-8(2)) | Information only; IDs match. Catalog titles are shown. |
| NSS parameter values (162 rows) | Captured with their page; not auto-written into system ODP values. |
| The union rule (above) | Applied as described; confirm with an SME if your organisation reads §3.2.1 differently. |

**In the app:**
- The NSS baseline is the trigraph selection. Overlays and tailoring apply on top.
- Each control shows "Selected by CNSSI 1253 Table D-x (C=M, …), p. D-n (PDF p. n)".
- A changed trigraph (after re-approval) or an existing NSS system shows a proposal: "CNSSI 1253 baseline loaded – N added / M removed – review". It is applied only on Accept.
- On Accept, tailored-out controls stay out, and baseline controls with statement, evidence or assessment work are kept as tailored in, never dropped.
- The PTA defaults and ACCT layering SME items are unchanged.

## CNSSI 1253 parameter values (Appendix D "Parameter Value" column)

The notation is defined in Appendix D, pp. D-2–D-3: a paragraph label ("a.", "c.1.") and/or "1st PV" / "2nd PV" locates a value, and no annotation means the control has only one value to define. `backend/app/services/cnssi_params.py` ties a value to a Rev 5 ODP only when that is unambiguous:
- Each catalog placeholder is matched to its ODP by its exact rendered text, in reading order. If any placeholder can't be matched, the whole control stays at control level.
- The paragraph is resolved from the statement's labels (a., 1., (a)).
- "Nth PV" is counted only where the paragraph has no nested placeholders.
- A placeholder that aggregates several ODPs (e.g. the policy and procedures "personnel or roles") is never split.

Result: 162 controls carry a value. 204 values are mapped to single ODPs, and 27 stay at control level ("applies to control – choose parameter"). Those 27 are listed below; none was guessed.

| Control | Source | Document text | Why not mapped |
|---|---|---|---|
| AC-16 | Table D-1 p. D-13 | “f. 2nd PV: 90 days” | placeholder covers several ODPs (ac-16_odp.10, ac-16_odp.11) |
| AT-1 | Table D-2 p. D-19 | “a. all personnel” | placeholder covers several ODPs (at-01_odp.01, at-01_odp.02) |
| AT-2 | Table D-2 p. D-19 | “a.1. at least annually” | placeholder covers several ODPs (at-02_odp.01, at-02_odp.02) |
| AU-1 | Table D-3 p. D-22 | “a. all personnel” | placeholder covers several ODPs (au-01_odp.01, au-01_odp.02) |
| CM-14 | Table D-5 p. D-43 | “any software and firmware” | placeholder covers several ODPs (cm-14_odp.01, cm-14_odp.02) |
| CM-3.4 | Table D-5 p. D-35 | “1st PV: at a minimum, the” | placeholder covers several ODPs (cm-03.04_odp.01, cm-03.04_odp.02) |
| CM-5.5 | Table D-5 p. D-37 | “5.b. at least annually” | placeholder covers several ODPs (cm-05.05_odp.01, cm-05.05_odp.02) |
| CM-7 | Table D-5 p. D-39 | “b. all functions, ports,” | placeholder covers several ODPs (cm-07_odp.02, cm-07_odp.03, cm-07_odp.04, cm-07_odp.05, cm-07_odp.06) |
| CM-7.1 | Table D-5 p. D-39 | “b. all functions, ports,” | placeholder covers several ODPs (cm-07.01_odp.02, cm-07.01_odp.03, cm-07.01_odp.04, cm-07.01_odp.05, cm-07.01_odp.06) |
| CP-1 | Table D-6 p. D-44 | “a. at a minimum, key” | placeholder covers several ODPs (cp-01_odp.01, cp-01_odp.02) |
| CP-10 | Table D-6 p. D-50 | “a time period as defined in” | placeholder covers several ODPs (cp-10_odp.01, cp-10_odp.02) |
| CP-2 | Table D-6 p. D-44 | “b. key personnel or roles and” | placeholder covers several ODPs (cp-02_odp.03, cp-02_odp.04) |
| CP-2 | Table D-6 p. D-44 | “f. key personnel and” | placeholder covers several ODPs (cp-02_odp.06, cp-02_odp.07) |
| CP-4 | Table D-6 p. D-46 | “a. 2nd PV: tests as defined” | placeholder covers several ODPs (cp-04_odp.02, cp-04_odp.03) |
| CP-9.1 | Table D-6 p. D-49 | “at least monthly or as” | placeholder covers several ODPs (cp-09.01_odp.01, cp-09.01_odp.02) |
| IR-8 | Table D-8 p. D-64 | “d. all personnel with a role” | placeholder covers several ODPs (ir-08_odp.06, ir-08_odp.05, ir-08_odp.07) |
| MA-4.1 | Table D-9 p. D-67 | “a. as defined in the” | placeholder covers several ODPs (ma-04.01_odp.01, ma-04.01_odp.02) |
| MP-2 | Table D-10 p. D-69 | “1st PV: all types of digital” | placeholder covers several ODPs (mp-02_odp.01, mp-02_odp.03) |
| MP-6.2 | Table D-10 p. D-70 | “at least annually” | placeholder covers several ODPs (mp-06.02_odp.01, mp-06.02_odp.02) |
| PM-17 | Table D-13 p. D-81 | “b. at least annually” | placeholder covers several ODPs (pm-17_odp.01, pm-17_odp.02) |
| PM-25 | Table D-13 p. D-82 | “d. at least annually” | placeholder covers several ODPs (pm-25_odp.01, pm-25_odp.02, pm-25_odp.03, pm-25_odp.04) |
| RA-5 | Table D-16 p. D-90 | “a. at least every 30 days” | placeholder covers several ODPs (ra-05_odp.01, ra-05_odp.02) |
| SI-3 | Table D-19 p. D-125 | “c.2 1st PV: block and” | '1st PV' counted within nested parameters |
| SI-3 | Table D-19 p. D-125 | “c.2 2nd PV: system” | '2nd PV' counted within nested parameters |
| SI-4.4 | Table D-19 p. D-126 | “b. 1st PV: continuously” | placeholder covers several ODPs (si-04.04_odp.01, si-04.04_odp.03) |
| SI-5 | Table D-19 p. D-128 | “a. minimally the US-CERT” | catalog statement has 5 placeholders for 5 ODPs (order not verifiable) |
| SR-1 | Table D-20 p. D-137 | “a. at a minimum, key” | placeholder covers several ODPs (sr-01_odp.01, sr-01_odp.02) |

Adopting a value sets the system ODP with source "CNSSI 1253 (2022) Table D-x p. D-n", the adopter and the date. It is audited (`system.parameter_cnssi_adopted`) and can be undone (`system.parameter_cnssi_undone` restores the previous value). Before replacing a differing policy value, overlay value or other system value it returns 409 and lists the conflicts, and the user must confirm.

## Privacy Overlay prompt (NSS + PII)

- **Gap:** the 27 controls are computed as (NIST SP 800-53B privacy baseline) ∩ (rows marked "--" in the Appendix D Privacy Control Baseline column). The legend (p. D-1) says these "are addressed in the Privacy Overlay".
- **Coverage:** taken only from the loaded CNSSI 1253F Attachment 6 overlay data (controls_add plus a detail entry that is not "remove", with its page).
  - Low, Moderate and High each cover 27 of 27.
  - ACCT covers 23 of 27. It does not cover SA-4, SC-7(24), SI-12(2) or SI-19.
  - When ACCT is applied, those four show "not covered by the applied Privacy Overlay (acct) – SME review".
- **Display:** the prompt appears in Categorize, in the Select overlays panel and as the stepper's next action (once Prepare and Categorize are complete). It shows for PII = Yes or Unknown only, never for FIPS systems, and the overlay is never applied automatically.

## eMASS Implementation Plan and Risk Assessment fields (Implement step / Control Workbench)

**Source verified before coding:** MITRE `emass_client` OpenAPI spec, `docs/eMASSRestOpenApi.yaml` (rendered at https://mitre.github.io/emass_client/docs/redoc/), operation `PUT /api/systems/{systemId}/controls`, schemas `ControlsRequiredFields`, `ControlsConditionalFields` and `ControlsOptionalFields`. Fetched October 2026.

| Field (eMASS API name) | Values / limit, taken from the spec |
|---|---|
| implementationStatus | Planned, Implemented, Inherited, Not Applicable, Manually Inherited |
| controlDesignation | Common, System-Specific, Hybrid |
| commonControlProvider | DoD, Component, Enclave |
| slcmFrequency | Constantly, Daily, Weekly, Monthly, Quarterly, Semi-Annually, Annually, Every Two Years, Every Three Years, Undetermined |
| slcmMethod | Automated, Semi-Automated, Manual, Undetermined |
| severity, relevanceOfThreat, likelihood, impact, residualRiskLevel | Very Low, Low, Moderate, High, Very High |
| responsibleEntities, slcmCriticality, slcmReporting, slcmTracking, naJustification, recommendations, mitigations | free text, max 2,000 characters |
| slcmComments | free text, max 4,000 characters |
| implementationNarrative | max 2,000 characters |
| estimatedCompletionDate | Unix time (integer) in the API; a date picker in the UI; an ISO date in OSCAL and the xlsx |

**Implementation Narrative — one shared rule:** `implementationNarrative` is in eMASS `ControlsRequiredFields`, so it is required on every controls PUT. It counts as missing for every status except Inherited, where the narrative comes from the providing system. `emass_fields.missing_all()` applies this rule, and the panel's missing list, the Workbench "missing required eMASS fields" filter and the xlsx Validation sheet / validation report all use it. The narrative is edited in the implementation statement, so saving the Implementation Plan does not block on it.

**Conditional-required rules** (from the "Business Rules" table in the spec):
- **Planned or Implemented:** all six SLCM fields. The user specification also requires Security Control Designation, Estimated Completion Date and Responsible Entities here. eMASS lists those three as body-required on every PUT.
- **Not Applicable:** naJustification.
- **Manually Inherited:** commonControlProvider and all six SLCM fields.

The server enforces these rules with HTTP 422. The UI shows or hides fields to match.

**Inherited controls:**
- The spec says: "Risk Assessment information cannot be updated if a Security Control is Inherited". The risk endpoint returns 422 for Inherited controls.
- Implementation Plan fields for Inherited controls are read-only. The panel shows the inheritance record (provider, package and the responsibility split).
- **Decision:** a control can only be marked "Inherited" when an inheritance record exists (provider_id, or responsibility = inherited). Otherwise the user is directed to "Manually Inherited", which names the Common Control Provider.

**Vulnerability Summary:** the user specification lists this as a Risk Assessment field, but it is **not** an eMASS API field. We store it and export it in the xlsx (marked "no API field – eMASS UI only"). It is excluded from the mocked API payload.

**One status, not two:**
- `control_assignments.implementation_status` remains the single source of truth. The eMASS Implementation Status is derived from it:

  | eMASS status | Internal status |
  |---|---|
  | Planned | planned / partially_implemented / not_implemented |
  | Implemented | implemented |
  | Not Applicable | not_applicable |
  | Inherited | inherited (no manual flag) |
  | Manually Inherited | inherited (with `emass_control_fields.manually_inherited`) |

- Saving the plan with a different status updates the internal status. That write is audited as `implementation.status_changed` (via = emass_implementation_plan) and re-evaluates the system.
- Choosing Planned keeps a more specific internal value (for example, partially_implemented).

**Residual risk suggestion:** shown only, never set automatically. It uses a 5×5 Likelihood × Impact lookup in the style of NIST SP 800-30 Rev. 1, Appendix I, Table I-2.

**Editing, saving and audit:**
- Editing needs `implementation.write` (ISSO and System Owner, the existing system-edit roles). Every other role sees the panels read-only, with the reason.
- The plan PUT carries the full set of fields for the chosen status.
- Every save writes `emass.plan_updated` or `emass.risk_updated`, with before/after values for the changed fields only.
- Accepted suggestions are recorded with `suggestion_source` (ai or rules), `suggested_fields_accepted` and the AI `interaction_id`. AI-assisted values without a logged interaction id are rejected with 422.

**Suggestions:**
- The prompt is `control.emass_fields_suggest@1.0.0`. It is grounded in the system's categorization, inheritance, evidence, open findings, POA&Ms, policies and role holders.
- Output is schema-validated with `extra=forbid`, so it has no compliance or test-result keys. Server-side enum, limit and date checks then drop invalid values and list them as rejected.
- If the reply is truncated, the request is split into plan and risk batches.
- On any AI failure, or when AI is disabled, the deterministic rules in `services/emass_fields.rule_suggestions` are used instead.
- Nothing is saved until the user accepts values and presses Save.

**Bulk set:**
- Sets Implementation Plan fields only, never the status.
- Needs `confirm=true`. It writes one audit event per control plus a summary event.
- Skips Inherited and Not Applicable controls.
- Does not enforce completeness, because partial bulk fills are the purpose. The "Missing required eMASS fields" filter and the validation report show what is still missing.

**Exports:**
- **xlsx:** "eMASS-formatted, compatibility pending human verification". There is no official eMASS Control Import/Export template in the repo. Column names follow the eMASS field labels, and a Field mapping sheet gives the API names. A Validation sheet is included.
- **OSCAL SSP:** each `implemented-requirement` gets `props` with ns `https://ironvisionai.com/ns/oscal/emass` (enums and dates) and markdown `remarks` (free text). The SSP still validates against the pinned OSCAL schema.
- **Mocked eMASS sync:** the queued control change (`entity_type=control`) uses eMASS API field names and stays labelled MOCKED.

**SME review required:** check the xlsx column order against a current eMASS Control Information export before any upload.
