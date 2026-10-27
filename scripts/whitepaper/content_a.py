from blocks import H1, H2, IMG, NOTE, P, PB, SCREEN, TABLE, UL

S = "/app/docs/screenshots/"

PART_A = [
    H1("1", "Executive summary"),
    P("IronVision AI (formerly AegisRMF) is a web application for the NIST Risk Management Framework (RMF). It covers all seven steps "
      "of NIST SP 800-37 Rev. 2 for a portfolio of systems, from preparation and categorization through continuous monitoring. "
      "It brings together the records that are usually spread across spreadsheets, SharePoint folders, scanner exports and eMASS: "
      "systems, roles, categorization, baselines and overlays, control implementations, evidence, findings, POA&Ms, assessments, "
      "authorization decisions and the audit trail."),
    P("The product rests on four commitments:"),
    UL("**Human-approved AI.** AI drafts, ranks and explains. It never decides. Every AI output is schema-validated, quotes and references "
       "are checked against the source, and a human must approve before anything changes a compliance record. With no AI provider "
       "configured, every feature still works with deterministic analysis.",
       "**Evidence integrity.** Every artifact is stored content-addressed by SHA-256, with provenance, freshness, version history and a "
       "hash-chained, append-only audit trail.",
       "**eMASS-faithful workbooks.** Test Result and Hardware/Software workbooks are imported and written back into the user's own "
       "eMASS templates. Only permitted cells change, macros are never executed, and every export comes with a validation report.",
       "**Portability.** Standard components only (React/TypeScript, FastAPI, PostgreSQL, S3-compatible storage, OIDC), deployable with "
       "Docker Compose. AI providers and storage back-ends are chosen through environment values, with no code change."),
    P("This paper describes what the software does today. It is derived from the code base, database migrations, API specification and "
      "project reports. Capabilities that are simulated are labelled **MOCKED**. Results that could not be verified in the development "
      "environment are labelled **REQUIRES HUMAN VERIFICATION**. Interpretations of authoritative documents that need a subject-matter "
      "expert are labelled **SME REVIEW REQUIRED**."),
    NOTE("info", "IronVision AI is not FedRAMP-authorized, holds no ATO and has not been assessed for IL4–IL6 or CUI. The demonstration "
                 "environment contains synthetic data only. Nothing in this document claims FIPS 140-3 validation or CAC/PIV conformance."),
    H2("1.1 Problem statement"),
    P("Getting and keeping an Authority to Operate (ATO) is labour-intensive. The RMF itself is sound; the burden comes from the tooling "
      "around it:"),
    UL("**ISSOs** keep control narratives, evidence folders and STIG/ACAS results consistent by hand. They re-type the same facts into "
       "the SSP, the Test Result workbook, the POA&M and the hardware/software list.",
       "**Security Control Assessors (SCAs)** must judge evidence that is stale, unattributed or impossible to trace back to a specific "
       "file, scan or policy paragraph.",
       "**Authorizing Officials (AOs)** sign risk decisions based on packages whose provenance is hard to check, with little visibility "
       "into what changed since the last review.",
       "**ISSMs and leadership** lack a live, cross-system view of authorization expirations, overdue POA&Ms, CAT I findings and "
       "stale evidence.",
       "**National Security Systems** add CNSSI 1253 categorization (separate C/I/A impact levels), NSS baselines, overlays and parameter "
       "values. Teams usually apply these from PDF tables by hand."),
    P("Generic GRC tools either ignore these DoD/IC specifics or bolt on unverifiable AI. IronVision AI models the RMF tasks directly, keeps "
      "every artifact traceable, and uses AI only where its output can be checked."),
    PB,
    H1("2", "Core value and differentiators"),
    TABLE(["Differentiator", "What it means in practice", "Where it is enforced"], [
        ["Human-approved AI", "AI produces drafts, suggestions, rankings and explanations. Approval gates are locked on and cannot be disabled.",
         "AIService (schema + quote validation), review engine, Admin AI settings ('human approval: always on (locked)')"],
        ["Grounded output", "Policy quotes must be exact substrings of the uploaded text. Evidence references must point to real records. "
                            "Fabricated items are dropped and counted.", "policy_profile.verify_quote, TR analysis and inventory validators"],
        ["Deterministic fallback", "With no AI provider, or when AI output fails validation, the deterministic result stands and is labelled.",
         "Every AI call site; the AI status panel shows 'Deterministic analysis (no AI)'"],
        ["Evidence integrity", "SHA-256 content addressing, integrity re-verification, version history, freshness windows, retention with legal hold.",
         "Storage service, evidence_versions, retention job, Evidence Ledger"],
        ["Tamper-evident audit", "Every state change writes a hash-chained audit_events row. A database trigger makes the table append-only.",
         "audit service, migration 0001 trigger, chain verification in the Audit Log"],
        ["Separation of duties", "No self-approval, SCA independence, AO-only decisions, Platform Admin without decision rights.",
         "rbac.py assertion, sod.py, review engine"],
        ["eMASS-faithful workbooks", "Import and write back the user's own TR and HW/SW templates. Only permitted ranges change; the VBA project and "
                                     "signature parts stay byte-identical.", "services/tr, services/inventory/hwsw, validation reports"],
        ["CNSSI 1253 depth", "Per-objective C/I/A, Appendix D baselines with page citations, official overlays, parameter value adoption "
                             "with undo and conflict detection.", "cnssi1253.py, cnssi_params.py, overlays.py"],
        ["Portability", "Docker Compose, PostgreSQL, any S3 API, OIDC, pluggable AI. The env file is parsed as data and validated by check_env.",
         "deploy/, scripts/check_env.py, docs/PORTABILITY.md"],
    ], [22, 48, 30]),
    PB,
    H1("3", "Personas, roles and separation of duties"),
    P("Authorization is role-based and scoped to an organization or to a single system. Roles come only from IronVision AI's own RBAC, "
      "never from identity-provider claims. The permission matrix is defined in code (backend/app/security/rbac.py) and shown read-only "
      "on the Admin page and in 'Help: who can do what'."),
    TABLE(["Role", "Typical person", "Key permissions (abridged)"], [
        ["System Owner", "Mission/system owner", "system.write, evidence.submit, poam.manage, system.register, ingest.upload, implementation.write"],
        ["ISSO", "Information System Security Officer", "System Owner rights plus finding.map, source.manage, evidence.verify, audit.read, emass.queue"],
        ["ISSM", "Information System Security Manager", "portfolio.read, system.roles.manage, content.apply, finding.map, emass.queue, admin.health.read"],
        ["SCA", "Security Control Assessor", "assessment.perform (the only role that sets assessment status / TR compliance status), evidence.verify"],
        ["AO", "Authorizing Official", "authorization.decide, risk.accept, portfolio.read"],
        ["DevSecOps", "Engineer / pipeline owner", "evidence.submit, ingest.upload, source.manage"],
        ["Leadership Viewer", "Executive", "portfolio.read (read-only)"],
        ["Privacy Official", "Senior agency privacy official", "privacy.review (approve or return PTAs and privacy determinations)"],
        ["Platform Admin", "Tool administrator", "Users, content loading, AI test, jobs, eMASS connector settings. **No** AO, SCA or risk-acceptance rights (asserted at start-up)."],
    ], [18, 27, 55]),
    H2("3.1 Separation of duties"),
    UL("A requester can never approve their own request (reviews engine).",
       "Only the SCA sets an assessment result. The SCA must be independent of the implementer.",
       "Only the AO issues ATO, ATO with conditions, IATT or DATO decisions and accepts risk. The ISSO cannot accept risk.",
       "Test Results: a row edited or prepared by one person must be approved by a different real user (shared helper services/sod.py). "
       "The same applies to inventory changes (accept → approve).",
       "Every denial is audited as authz.denied. Every mutating API route declares a permission dependency, and an automated test "
       "fails if any route lacks one."),
    H2("3.2 Real organizations vs. sandboxes"),
    P("Self-service sandboxes (Explore Demo or self sign-up) can enable **persona mode**. One person can then act as ISSO, SCA, AO and the "
      "other roles through the 'Acting as' switcher in the header. Actions run as synthetic persona identities, so the role rules stay "
      "enforced. Every audit event also records the real operator."),
    UL("In a **real organization**, approval must come from a different real user. Switching persona does not count, and the UI shows "
       "the action as locked with the reason.",
       "In a **sandbox**, a different persona of the same real user may approve. The event is labelled **'Sandbox: same person'** in "
       "the audit log, on the row and in export history.",
       "Persona approvals are labelled 'simulated signature – not CAC/PIV · sandbox persona'.",
       "Persona mode is refused (403) on non-sandbox tenants. Client-supplied flags such as is_sandbox or X-Sandbox are ignored."),
    NOTE("info", "One human holding all personas is **not** acceptable separation of duties for production. Production tenants keep strict "
                 "real-identity separation of duties."),
    IMG(S + "signup-demo/04-role-switcher-open.png", "Sandbox persona switcher ('Acting as') in the header", 88),
    PB,
    H1("4", "RMF lifecycle coverage (NIST SP 800-37 Rev. 2)"),
    P("The RMF overview ('Getting started') and the per-system stepper compute a status for each of the seven steps from live data. A "
      "status is never typed in by hand. Each step reports one of **not started**, **needs attention** or **complete**, with the criteria "
      "behind it, a progress counter and the single next action with a deep link."),
    TABLE(["Step", "What IronVision AI does", "'Complete' when"], [
        ["1 Prepare", "Key roles (AO, ISSM, ISSO, System Owner, SCA, Privacy Official …) assigned per system, with role history; system boundary and description.",
         "All required key roles are filled"],
        ["2 Categorize", "Information types from the NIST SP 800-60 Vol. 2 Rev. 1 catalog (168 types); FIPS 199 high-water mark or CNSSI 1253 per-objective C/I/A; "
                         "NSS determination (Yes/No/Unsure); PTA; AO approval with revision history and re-approval on change.",
         "Categorization approved and no required field missing"],
        ["3 Select", "SP 800-53B baseline (FIPS) or CNSSI 1253 Appendix D trigraph union (NSS); overlays; tailoring in/out with justification; "
                     "organization-defined parameters (ODPs); CNSSI parameter adoption; Privacy Overlay prompt.",
         "Baseline applied, no unresolved reconciliation or tailoring issues"],
        ["4 Implement", "Control Workbench: implementation status, statements (with optional AI draft), inheritance, evidence, policy mappings, CCIs.",
         "Every assigned control has an implementation status"],
        ["5 Assess", "SCA assessments per control, eMASS Test Results workbook, STIG/ACAS findings, Mapping Review.",
         "Every assigned control is assessed"],
        ["6 Authorize", "Authorization package, ISSM endorsement, AO decision (ATO / ATO w/ conditions / IATT / DATO), POA&Ms, risk acceptance, eMASS sync.",
         "A current authorization decision exists"],
        ["7 Monitor", "Rule-based monitoring: CISA KEV, CAT I, overdue POA&Ms, stale evidence; scheduled jobs; evidence freshness; Evidence Ledger.",
         "Monitoring configured and nothing needs attention"],
    ], [13, 62, 25]),
    IMG(S + "sme-final/07-rmf-overview-final.png", "RMF overview with live step statuses and the next action", 92),
    PB,
    H1("5", "Screen-by-screen guide"),
    P("Each entry describes one page in the application: its purpose, who uses it, the key actions, what it produces and the guardrails "
      "that apply. Routes are given for orientation. Navigation follows the RMF steps (Start, 1 Prepare … 7 Monitor, Tools)."),
    H2("5.1 Access"),
    SCREEN("Login, demo and sign-up (/login)",
           "Sign in with the configured provider (local password in development and demo, OIDC/Keycloak in deployed environments), open the "
           "shared synthetic demo, or create a private sandbox.",
           "Everyone", "Sign in; 'Explore demo' (one-click, rate-limited, audited); 'Create account' (when sign-up is enabled); open the public whitepaper.",
           "A server-side session (idle timeout 30 min, absolute 12 h, rotating refresh tokens).",
           "Lockout after 5 failures for 15 minutes. Sign-up bot checks (trap field and minimum time-to-submit), 12+ character passwords. "
           "Sign-up is off in production. New sandboxes start empty."),
    IMG(S + "login-light.png", "Login page", 80),
    H2("5.2 Start"),
    SCREEN("Getting started – RMF overview (/rmf-workflow)",
           "Live seven-step overview for the active system, with criteria and the next action.", "All roles",
           "Follow the next-action link; open any step.", "Step statuses, progress counters.", "Statuses are computed, never edited."),
    SCREEN("Systems (/systems, /systems/new, /systems/:id)",
           "Register systems, maintain boundary, description, operating environment, DoD Cloud SRG impact level, assets and system-scoped "
           "role assignments.", "ISSO, ISSM, System Owner",
           "Register (role keys validated server-side); edit; assign and revoke roles (audited); archive and restore (audited).",
           "System record, role history.",
           "Impact-level rules: IL picker only for cloud deployment models; IL6 only for NSS + classified = Yes (422 otherwise). "
           "Archived systems are hidden but restorable."),
    SCREEN("Portfolio / Leadership (/portfolio)",
           "Cross-system posture: ATO expirations, open POA&Ms, CAT I, KEV exposure, evidence freshness, trends, 'waiting on you'.",
           "ISSM, AO, Leadership Viewer", "Drill into a system or POA&M.", "Portfolio cards, operational priority scores with a breakdown that sums.",
           "Requires portfolio.read."),
    IMG(S + "leadership-light.png", "Portfolio / Leadership dashboard", 90),
    H2("5.3 Step 1 – Prepare"),
    SCREEN("Key roles (/rmf/prepare)",
           "Assign the RMF key roles for the system and record the people who hold them.", "ISSM, ISSO",
           "Assign or replace a role holder; view history.", "Role assignments used by the review engine.",
           "Role changes need system.roles.manage and are audited."),
    H2("5.4 Step 2 – Categorize"),
    SCREEN("Categorization (/rmf/categorize)",
           "Select information types and compute the security category. Record the NSS determination, framework (FIPS 199 or CNSSI 1253), "
           "PII presence and Privacy Threshold Analysis.", "ISSO (prepares), AO (approves), Privacy Official (PTA)",
           "Pick SP 800-60 information types with provisional impacts and adjust them with justification; answer 'Is this a National "
           "Security System?' (Yes/No/Unsure); fill in the PTA questionnaire; submit for approval.",
           "FIPS 199: per-objective high-water mark and overall category. CNSSI 1253: separate C/I/A trigraph (e.g. M-H-L) and no overall "
           "value. A versioned categorization revision.",
           "Approval needs authorization.decide. A change to an approved categorization creates a pending re-approval and the approved "
           "values stay in force. PTA outcomes are recommendations only; a single 'No' never concludes 'no PIA required'. Only a Privacy "
           "Official approves a PTA."),
    NOTE("sme", "The default PTA questions are a generic example set ('validate against your agency's privacy requirements'). Agencies must "
                "replace or confirm them."),
    IMG(S + "rmf-accuracy/02_categorize_framework_nss.png", "Categorize: NSS determination and framework selection", 90),
    IMG(S + "rmf-accuracy/04_pta_questionnaire.png", "Privacy Threshold Analysis questionnaire (example question set)", 90),
    H2("5.5 Step 3 – Select"),
    SCREEN("Baseline, overlays and tailoring (/rmf/select)",
           "Apply and reconcile the control baseline, overlays, tailoring decisions and organization-defined parameters.",
           "ISSO, ISSM", "Apply the SP 800-53B baseline or the CNSSI 1253 trigraph baseline; accept or decline a baseline proposal after "
           "re-categorization; apply overlays (official CNSSI overlays for NSS, agency overlays as metadata); tailor controls in or out "
           "with justification; compare and adopt CNSSI parameter values; respond to the Privacy Overlay prompt.",
           "Control assignments with selection provenance (for example 'Selected by CNSSI 1253 Table D-3 (C=M), p. D-22 (PDF p. 43)'), "
           "tailoring record, ODP values with source.",
           "Proposals apply only on Accept. Tailored-out controls stay out, and controls that already have statements, evidence or "
           "assessment work are kept as tailored in, never dropped. Overlays: CNSSI overlays only on NSS; the Classified overlay "
           "requires an explicit 'classified = Yes'; restricted overlays show 'Unavailable – pending validation'. Parameter adoption "
           "returns 409 with the conflicts before it overwrites a differing value, and can be undone."),
    IMG(S + "sme-overlays/1-select-overlay-groups.png", "Select: official CNSSI 1253 overlay groups with applicability", 90),
    IMG(S + "rmf-accuracy/05_parameter_comparison.png", "Select: parameter comparison (catalog vs. CNSSI 1253 vs. system values)", 90),
    SCREEN("Control catalog (/catalog)",
           "Browse the pinned NIST SP 800-53 Rev. 5 catalog with assessment objectives, baselines and content versions.", "All roles",
           "Search; filter by family or baseline; open control detail.", "None (read-only).", "Content is SHA-256 verified at load."),
    H2("5.6 Step 4 – Implement"),
    SCREEN("Implementation progress (/rmf/implement)", "Progress of implementation statuses and statements across the system's controls.",
           "ISSO, System Owner", "Filter by status or family; open the workbench.", "Counts consistent with the stepper.", "Read-only summary."),
    SCREEN("Control Workbench (/controls, /systems/:id/controls/:controlId)",
           "The ISSO's main workspace: one control at a time with status, implementation statement, parameters, inheritance, evidence, "
           "mapped policies, CCIs, findings and assessment.", "ISSO, System Owner, SCA (assessment section)",
           "Save implementation status; write or AI-draft a statement (grounded in evidence, policies and POA&Ms); submit it for review; "
           "attach evidence; view policy mappings and coverage.",
           "Versioned implementation statements, review requests, eMASS Implementation Plan and Risk Assessment fields.",
           "AI drafts are labelled, carry validated citations and need human approval. Only the SCA sets the assessment status."),
    SCREEN("eMASS Implementation Plan and Risk Assessment (Control Workbench panels)",
           "eMASS field names and values (Implementation Status, Security Control Designation, Estimated Completion Date, Responsible Entities, "
           "SLCM Criticality/Frequency/Method/Reporting/Tracking/Comments, N/A Justification, Common Control Provider; Severity, Relevance of Threat, "
           "Likelihood, Impact, Residual Risk Level and risk text). Required fields follow the eMASS API business rules for each status.",
           "ISSO, System Owner (edit); other roles read-only",
           "Pick values from dropdowns (with Other… for free-text fields); Suggest values (AI or deterministic rules) and accept per field or all; "
           "bulk-set plan fields on selected controls; filter by eMASS status or missing required fields; Import from eMASS: upload an eMASS "
           "Control Information export (compatibility pending verification against a real eMASS export), review current vs imported values "
           "per field, accept or reject, then apply (audited with the file name and SHA-256).",
           "eMASS-formatted Implementation Plan xlsx (compatibility pending human verification), validation report, OSCAL SSP props/remarks, "
           "MOCKED eMASS sync payload with eMASS API field names.",
           "One implementation status (eMASS status is derived from it). Inherited controls are read-only and their Risk Assessment cannot be edited. "
           "Suggestions are never saved automatically; accepted values are audited as AI- or rule-assisted. AI never sets compliance or test results."),
    IMG(S + "controls-workbench-cm6-light.png", "Control Workbench (CM-6)", 92),
    SCREEN("Inheritance (/inheritance)",
           "Common and hybrid control inheritance from providers (data centres, cloud platforms, enclaves).", "ISSO, ISSM",
           "Add or edit providers with package, authorization type and expiry; import a customer responsibility matrix (CRM); bulk "
           "inheritance; owner attestations.", "Inherited, shared and system-owned responsibility per control.",
           "Expired or expiring provider authorizations are flagged with the number of dependent controls."),
    SCREEN("HW/SW Inventory (/inventory)",
           "The eMASS hardware/software list together with scan-observed hosts.", "ISSO, ISSM",
           "Import the HW/SW .xlsm; review correlations between scan hosts and assets; resolve consistency issues; export to the same template.",
           "Inventory records, discrepancy decisions, validated export.", "See section 6 (AI) and section 9 (workbooks)."),
    IMG(S + "inventory/01_inventory_overview.png", "HW/SW Inventory overview", 90),
    SCREEN("CCI view (/ccis)", "DISA CCIs of the system's controls with their policy coverage.", "ISSO, SCA",
           "Filter by control, family or coverage status; open the source policy passage.", "Coverage per CCI.",
           "Coverage comes from policy text only; 'covered elsewhere' links never turn MISSING into MET."),
    SCREEN("Policy Auditor (/policy-auditor, /policy-auditor/:id)",
           "Upload policies and procedures (PDF/DOCX/TXT). They are parsed into sections and pages, mapped to controls and evaluated "
           "against assessment objectives and CCIs.", "ISSO, ISSM",
           "Upload; reanalyze; review proposed mappings; confirm, dismiss (with justification) or link findings; export CSV.",
           "Policy-to-control mappings with confidence and source (section/page), per-requirement coverage (met / partial / missing) with quotes.",
           "Findings stay proposed until a human confirms them. AI may raise a requirement only with an exact quote."),
    IMG(S + "rmf-accuracy/10_policy_mappings_confidence.png", "Policy mappings with confidence and source attribution", 90),
    SCREEN("Evidence Sources (/evidence-sources, /ingest-runs/:id)",
           "Upload STIG checklists (.ckl/.cklb), ACAS/Nessus (.nessus/CSV), SCAP/XCCDF and other evidence, and manage connectors.",
           "ISSO, DevSecOps", "Upload; follow an ingest run (processing → analysed / failed with reason); retry failed runs.",
           "Evidence records, canonical deduplicated findings, CCI→800-53 mappings, asset correlation.",
           "Upload allowlists, magic-byte checks, size limits, safe XML parsing and archive checks."),
    NOTE("mocked", "Live connectors (scanner, cloud configuration and ticketing APIs) are **MOCKED** in this release. The MockAdapter contacts no "
                   "external system, and its records are labelled 'MOCKED source · <collector>'. File import is the real ingestion path."),
    IMG(S + "sme-final/04-stig-run-detail.png", "STIG ingest run detail", 90),
    H2("5.7 Step 5 – Assess"),
    SCREEN("Assessment progress (/rmf/assess)", "Assessment coverage across the system's controls.", "SCA, ISSM",
           "Filter; open controls to assess.", "Counts consistent with the stepper.", "Read-only summary."),
    SCREEN("Reviews (/reviews, /reviews/:id)",
           "Every review request type (implementation statements, dispositions, closures, risk acceptances, extensions, categorization, "
           "authorization package) runs under versioned decision rules.", "Requesters and the roles named in each decision rule",
           "Endorse, approve, return or deny, with comments.", "Decisions and their effects (applied only on approval).",
           "Self-approval blocked; decision rules versioned and audited."),
    SCREEN("Templates → Test Results (/test-results)",
           "Import the eMASS Test Result template (blank or pre-populated), generate rows from assessments, scans, policy coverage and "
           "evidence, run AI evidence analysis, have the SCA approve rows, and export.", "ISSO (prepares), SCA (approves)",
           "Import; resolve header and AP/CCI matching; review auto-suggested rows; run evidence analysis; 'Use this text'; SCA approval "
           "(single or bulk) with actual tester and test date; export with a validation report.",
           "Exported workbook, validation report, export history.",
           "Only the SCA sets or approves Compliance Status. Approval requires 'Tested by' and a 'Date tested' not in the future. AI never "
           "sets Compliance Status, Tested By or Date Tested."),
    IMG(S + "tr/07_ai_evidence_analysis.png", "Test Results: AI evidence analysis on a row (suggestion only)", 90),
    SCREEN("Mapping Review (/mapping-review)",
           "One queue for status suggestions, policy proposals, unmapped findings and asset correlations, with a side-by-side view of "
           "the source passage and the control requirement.", "ISSO, ISSM",
           "Accept or reject proposals; map unmapped rules (with optional AI suggestion); disposition with justification.",
           "Human-approved mappings.", "AI suggestions are proposals; dispositions create reviews."),
    IMG(S + "rmf-accuracy/11_side_by_side_review.png", "Mapping Review: side-by-side source passage and control requirement", 90),
    H2("5.8 Step 6 – Authorize"),
    SCREEN("Authorization package (/rmf/authorize, /systems/:id/authorization)",
           "Assemble the package, request ISSM endorsement and AO decision.", "ISSO, ISSM, AO",
           "Submit; endorse; decide ATO / ATO with conditions / IATT / DATO with expiry and conditions.",
           "Authorization decision record; authorization type and expiry drive the Portfolio view.",
           "Only the AO decides; denials are audited."),
    IMG(S + "rmf-accuracy/07_authorize_authorization_type.png", "Authorize: authorization type and decision", 88),
    SCREEN("POA&M (/poams, /poams/:id)",
           "Plan of Action and Milestones with weaknesses, milestones, risk, linked findings and history.", "ISSO, ISSM, AO (risk acceptance)",
           "Create from findings (match/link rules); add milestones; request closure, risk acceptance or extension.",
           "POA&M records; OSCAL POA&M export.",
           "Remediation detection marks items closure-eligible but never closes them automatically. Status cannot change while a "
           "closure or risk review is pending. Later due dates need an extension request."),
    IMG(S + "poam-light.png", "POA&M list", 90),
    SCREEN("eMASS Sync (/emass)",
           "Connector setup, approval-gated outbound queue, compare/import, retry with back-off, conflict resolution and failure simulation.",
           "ISSO, ISSM (queue), Platform Admin (connector)", "Queue changes; approve; resolve conflicts ('keep local' needs a fresh ISSM approval).",
           "Sync history.", "Truthful setup panel showing which capabilities are real."),
    NOTE("mocked", "The default eMASS adapter is **MOCKED** ('MOCK eMASS – synthetic demo connector, no real eMASS contacted'). The authorized "
                   "read/write REST adapters are stubs that require credentials and have **not** been run against eMASS."),
    H2("5.9 Step 7 – Monitor"),
    SCREEN("Continuous monitoring (/rmf/monitor)",
           "Rule-based monitoring status: CISA KEV matches, CAT I findings, overdue POA&Ms, stale evidence, scheduled job health.",
           "ISSO, ISSM", "Open the items that need attention.", "Monitoring status feeding step 7.",
           "KEV is versioned content (pinned CISA snapshot) re-evaluated daily; EPSS is not loaded (labelled)."),
    SCREEN("Evidence Ledger (/evidence-ledger)",
           "Tamper-evident list of all evidence with SHA-256, provenance, freshness, integrity status and versions.", "ISSO, SCA, ISSM",
           "Verify integrity; view, replace (new version) or remove (with reason) evidence; see dependents flagged for re-review.",
           "Integrity checks, version history.", "Removal and replacement keep history and flag dependent controls."),
    IMG(S + "evidence-ledger-light.png", "Evidence Ledger", 90),
    H2("5.10 Tools and administration"),
    SCREEN("Traceability matrix (/traceability)", "Control → implementation → evidence → finding → POA&M → assessment chain.",
           "SCA, ISSM, AO", "Filter; follow links.", "Traceability view.", "Read-only."),
    SCREEN("Help: who can do what (/help)", "Plain-language permission matrix and role descriptions.", "All", "Read.", "—", "—"),
    SCREEN("Audit Log (/audit-log)", "The hash-chained audit trail with filters, pagination, chain verification and CSV/JSON export.",
           "ISSO, ISSM, SCA, AO, Privacy Official, Platform Admin (audit.read)", "Filter by action, outcome, actor; verify chain; export.",
           "Exports.", "Append-only; the retention job refuses to purge audit events."),
    SCREEN("Admin (/admin)",
           "Platform health (database, storage, worker heartbeat, AI), AI status and 'Test AI connection', RBAC enforcement demo, worker "
           "jobs and schedules, users and roles, security status, AI administration (model override, use cases), decision rules, "
           "content updates, demo tools.", "Platform Admin (most panels), all roles (health and AI status)",
           "Run health checks; test the AI connection; enqueue content loads; invite users (dev); edit decision rules; edit the banner.",
           "Health, audit entries.", "Panels are permission-gated with an explicit 'Your roles do not grant …' message. No secrets are shown."),
    SCREEN("Docs Center (/docs-center)", "In-app handover documentation (deployment, security, operations).", "Admins, operators",
           "Read.", "—", "—"),
    SCREEN("Notifications (/settings/notifications) and global search", "Per-user notification preferences; RBAC-filtered search across "
           "systems, controls, findings and POA&Ms.", "All", "Set preferences; search.", "—", "The email adapter is disabled by default."),
    SCREEN("Sandbox controls (header)", "Sandbox badge, 'Acting as' persona switcher, demo reset (demo tools).", "Sandbox users",
           "Switch persona; reset the demo workspace.", "—", "Only on sandbox tenants; persona actions are labelled."),
]
