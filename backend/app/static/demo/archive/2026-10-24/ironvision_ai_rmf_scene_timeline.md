# IronVision AI – RMF product demo · scene timeline

Video: 1920×1080, 30 fps, H.264, no audio, duration 300.02 s. Times below are measured from the recording (event log of the recorder).

## Scene 1 · Intro & Login

- **Start / end:** 0:00.0 – 0:20.0
- **Screens:** Intro card (synthetic-data notice) → login page → Explore demo → RMF overview
- **Actions:** Intro card fades out; cursor points at brand and the 'Synthetic data · shared demo workspace' caption; clicks Explore demo; points at the SYNTHETIC banner and the 'Acting as' persona switcher.
- **Production notes:** Intro card is an authored HTML branding card (not a UI mockup). Sign-in itself is cut (load time removed).

| Time | On-screen event |
|---|---|
| 0:00.0 | `open intro.html` |
| 0:05.9 | `open /login` |
| 0:15.0 | `click [data-testid="demo-login-btn"]` |
| 0:15.7 | `open /rmf-workflow` |

**Narration**

- 0:00.0–0:06.0: This is IronVision AI: human-approved AI for the NIST Risk Management Framework.
- 0:06.5–0:13.0: Everything here runs in a shared demonstration workspace with synthetic data, one click from sign-in.
- 0:13.5–0:20.0: Personas let one presenter act as ISSO, assessor and AO, and every action stays labelled.

## Scene 2 · RMF Command Center

- **Start / end:** 0:20.0 – 0:45.0
- **Screens:** Getting started · RMF overview; Portfolio / Leadership (as ISSM persona)
- **Actions:** Cursor walks the 7 step cards and the stepper, Ongoing activities and Next action; persona switch to ISSM; Portfolio cards (authorized, KEV), Waiting on your decision, operational priority score.
- **Production notes:** Persona switches are cut; the header shows the active persona at all times.

| Time | On-screen event |
|---|---|
| 0:33.0 | `persona issm` |
| 0:34.2 | `click [data-testid="nav-portfolio"]` |

**Narration**

- 0:20.0–0:31.0: The RMF overview is the command center: all seven NIST 800-37 steps, computed from live records, with the criteria behind every status.
- 0:31.0–0:36.0: Ongoing work and the single next action are always one click away.
- 0:36.0–0:45.0: As the ISSM, the portfolio shows authorizations, CAT I and KEV exposure, overdue POA&Ms, and what is waiting on you.

## Scene 3 · Prepare / Categorize / Select

- **Start / end:** 0:45.0 – 1:35.0
- **Screens:** Register system form; Step 1 Prepare – key roles (LTP); Step 2 Categorize (LTP, FIPS 199); Step 2 Categorize (TEG, CNSSI 1253 M-H-L); Step 3 Select (TEG)
- **Actions:** Types an example system name (form not submitted); points at key-role pickers and the NSS question; Prepare shows the missing SCA; FIPS 199 selection and summary; system switch to the synthetic NSS 'Tactical Edge Gateway'; CNSSI 1253 + NSS = Yes, Privacy Overlay prompt, scrolls the C/I/A and approval sections; Select counts (CNSSI baseline for M-H-L) and parameter comparison.
- **Production notes:** TEG was created for the demo (synthetic) and its categorization approved by the AO persona beforehand (audited). The registration form is not submitted.

| Time | On-screen event |
|---|---|
| 0:45.0 | `persona isso` |
| 0:45.1 | `open /systems/new` |
| 0:45.9 | `click [data-testid="reg-name"]` |
| 0:56.1 | `click [data-testid="nav-rmf-prepare"]` |
| 1:02.9 | `click [data-testid="nav-rmf-categorize"]` |
| 1:25.5 | `click [data-testid="nav-rmf-select"]` |

**Narration**

- 0:45.0–0:56.0: Prepare and Categorize start at registration: name the system, assign the RMF key roles, and answer whether it is a National Security System.
- 0:56.0–1:02.0: Step one tracks every required role. Here, the assessor is still missing.
- 1:02.0–1:08.0: Federal systems use FIPS 199: information types roll up to a high-water mark.
- 1:08.0–1:16.0: For a national security system, CNSSI 1253 keeps confidentiality, integrity and availability separate, and prompts for the Privacy Overlay.
- 1:16.0–1:25.0: Integrity was raised to High with a recorded rationale, and the change waited for the AO's approval before it took effect.
- 1:25.5–1:35.0: Select then applies the CNSSI 1253 baseline: five hundred fifty-nine controls, each traced to its source table, plus overlays, tailoring and parameters.

## Scene 4 · Implement & AI

- **Start / end:** 1:35.0 – 2:20.0
- **Screens:** Control Workbench – AC-2 (LTP); Mapping review side-by-side
- **Actions:** Control header, scrolls to supporting evidence and mapped policies; clicks 'Generate draft' (live OpenRouter call; the ~12 s wait is cut); points at the AI-draft label, citations and 'Request review'; opens Policy mappings → side-by-side review; points at requirement, policy passage, Accept.
- **Production notes:** The AI draft is generated live and not saved; nothing is accepted in Mapping review.

| Time | On-screen event |
|---|---|
| 1:36.0 | `open /systems/53ce70f2-6c09-4c0e-a7e5-03770d64e81a/controls/ac-2` |
| 1:48.2 | `click [data-testid="ai-generate-btn"]` |
| 1:58.2 | `open /mapping-review` |
| 1:59.3 | `click [data-testid="queue-tab-policy_map"]` |
| 2:01.8 | `click [data-testid^="queue-sbs-"]` |

**Narration**

- 1:35.5–1:47.5: Implementation happens in the Control Workbench. For AC-2, the ISSO sees status, supporting evidence with hashes and freshness, open findings and mapped policies in one place.
- 1:48.0–1:58.0: AI can draft the statement, grounded in that evidence with validated citations. It is labelled as AI and never auto-approved.
- 1:58.5–2:20.0: Mapping Review puts the control requirement next to the exact policy passage. Automated matching and AI only propose; a person accepts, rejects or overrides with a justification. Nothing changes a compliance record until a human decides.

## Scene 5 · Assess

- **Start / end:** 2:20.0 – 3:05.0
- **Screens:** Evidence Sources; ingest run ltp_db-server-01.ckl (STIG); ingest run ltp_weekly_scan.nessus (ACAS); Step 5 Assess; eMASS Test Results; SCA approval dialog
- **Actions:** Upload kinds and MOCK/DEMO connector note; STIG and ACAS findings with control mappings; assessment progress; TR export mode and AI evidence analysis on row 41 (pre-generated); persona SCA opens Approve → Date tested / Tested by fields; dialog cancelled.
- **Production notes:** The TR workbook is the blank eMASS template imported into the demo workspace; AI analysis of rows 41/42 was generated before recording (live provider). No row is approved.

| Time | On-screen event |
|---|---|
| 2:20.0 | `open /evidence-sources` |
| 2:26.0 | `open /ingest-runs/72751da6-7493-4013-99b7-5b765a9b5d28` |
| 2:31.6 | `open /ingest-runs/0f6b0076-70b4-488f-8848-767071afd121` |
| 2:36.2 | `click [data-testid="nav-rmf-assess"]` |
| 2:39.0 | `open /test-results` |
| 2:43.2 | `click [data-testid="tr-open-analysis-41"]` |
| 2:49.1 | `persona sca` |
| 2:49.2 | `open /test-results` |
| 2:50.4 | `click [data-testid="tr-approve-41"]` |

**Narration**

- 2:20.0–2:26.0: Evidence arrives as STIG, SCAP, ACAS or Nessus files. Live connectors here are mocked.
- 2:26.0–2:36.0: Each ingest run is hashed, deduplicated and mapped through CCIs to NIST 800-53 controls, including this Log4j finding from an ACAS scan.
- 2:36.5–2:49.0: Test Results imports the eMASS Test Result template and is designed to preserve it. Rows are proposed from assessments, scans and evidence; AI explains each row.
- 2:49.5–3:05.0: Only the Security Control Assessor approves a result, and must record who actually tested and when. AI never sets compliance status, tester or test date.

## Scene 6 · Authorize

- **Start / end:** 3:05.0 – 3:45.0
- **Screens:** Authorization package (ISSO view); POA&M list; Authorization package (AO view)
- **Actions:** SSP summary, POA&Ms, OSCAL exports, 'Authorization decision (AO only)'; POA&M cards and KEV/CAT I row, MOCK eMASS note; persona AO: decision form, selects ATO with conditions, types a rationale, points at Record (not clicked).
- **Production notes:** Package was submitted (ISSO persona) and endorsed (ISSM persona) before recording so the AO form is reachable. No decision is recorded.

| Time | On-screen event |
|---|---|
| 3:05.0 | `persona isso` |
| 3:05.1 | `open /systems/53ce70f2-6c09-4c0e-a7e5-03770d64e81a/authorization` |
| 3:15.9 | `click [data-testid="nav-poam"]` |
| 3:24.2 | `persona ao` |
| 3:24.2 | `open /systems/53ce70f2-6c09-4c0e-a7e5-03770d64e81a/authorization` |
| 3:29.6 | `click [data-testid="authz-rationale"]` |

**Narration**

- 3:05.0–3:16.0: The authorization package brings together the SSP, assessment results, POA&Ms and risk acceptances, with OSCAL exports. The ISSO can submit it, but the decision is AO-only.
- 3:16.0–3:24.0: POA&Ms rank risk, flag KEV and CAT I items, and show sync status with a mocked eMASS connector.
- 3:24.0–3:45.0: After ISSM endorsement, the Authorizing Official records the decision: ATO, ATO with conditions, IATT or denial, with rationale and expiration. Separation of duties is enforced; no one approves their own work, and in a real organization that means a different person.

## Scene 7 · Continuous Monitoring

- **Start / end:** 3:45.0 – 4:25.0
- **Screens:** Step 7 Monitor; Evidence Ledger; Traceability matrix; Audit log (filtered 'review')
- **Actions:** Monitor stat cards; Evidence Ledger with Verify integrity and the hashed ledger table; traceability row AC-17(2); audit log filtered to review actions.
- **Production notes:** Audit log is filtered so no client-IP detail is on screen.

| Time | On-screen event |
|---|---|
| 3:45.0 | `persona isso` |
| 3:45.1 | `open /rmf/monitor` |
| 3:53.1 | `click [data-testid="mon-go-ledger"]` |
| 4:00.1 | `open /traceability` |
| 4:05.7 | `open /audit-log (filtered: review)` |

**Narration**

- 3:45.0–3:53.0: Continuous monitoring watches evidence freshness, CAT I findings, CISA KEV and overdue POA&Ms.
- 3:53.0–4:00.0: The Evidence Ledger keeps every artifact with its SHA-256 hash, provenance and versions.
- 4:00.0–4:05.5: Traceability links each control to evidence, findings, POA&Ms and assessment.
- 4:06.0–4:25.0: And every action, including each review and approval, lands in a hash-chained, append-only audit log you can verify and export.

## Scene 8 · Closing

- **Start / end:** 4:25.0 – 5:00.0
- **Screens:** RMF overview; closing card
- **Actions:** Returns to the RMF overview; branded closing card fades in and holds.
- **Production notes:** Closing card is an authored HTML branding card with the existing logo and brand colours.

| Time | On-screen event |
|---|---|
| 4:25.0 | `open /rmf-workflow` |
| 4:33.0 | `open closing.html` |

**Narration**

- 4:25.0–4:33.0: From preparation to continuous monitoring, the whole lifecycle stays in one place.
- 4:33.5–4:46.0: IronVision AI: human-approved AI for the NIST Risk Management Framework. AI does the heavy lifting; people keep the authority.
- 4:46.5–4:56.0: Get audit-ready, and stay audit-ready. Request your demo today.
