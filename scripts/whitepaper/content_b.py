from blocks import H1, H2, IMG, NOTE, OL, P, PB, TABLE, UL

S = "/app/docs/screenshots/"

PART_B = [
    PB,
    H1("6", "AI components"),
    P("All AI calls go through one service (backend/app/services/ai/service.py). Every prompt is versioned (id@version) and declares a "
      "strict output schema (Pydantic). Each call is logged to the ai_interactions table: provider, model, prompt id and version, input "
      "SHA-256, token usage, latency, validation status and correlation id. Output that fails schema validation gets exactly one repair "
      "retry. A reply cut off at the output-token limit (finish_reason 'length') is detected and retried as a smaller batch. If it still "
      "fails, the deterministic result stands."),
    H2("6.1 Inventory of AI features"),
    TABLE(["Feature (prompt)", "Inputs", "Output", "Grounding / validation", "Fallback"], [
        ["Policy audit (policy.audit@1.0.0)", "Policy text, mapped control, ODP / observed values", "Proposed findings (gaps, value mismatches)",
         "Schema; findings stay proposed until a human confirms", "Deterministic parser findings"],
        ["Policy coverage refine (policy.coverage_refine@1.0.0)", "Assessment objectives / CCIs of one control (batches of 8), deterministic result, policy text",
         "met / partial / missing + exact quote + rationale per requirement", "Quote must be an exact contiguous substring of the policy; "
         "otherwise the AI result is discarded and noted; disagreement lowers confidence and needs review", "Per-batch deterministic coverage"],
        ["Mapping suggestion (mapping.suggest@1.0.0)", "Finding title, source, rule/plugin, CVEs, CCIs", "Up to 3 controls with rationale and confidence",
         "Control IDs validated against the catalog; proposal only", "Manual mapping"],
        ["Implementation statement draft (control.implementation_statement@1.0.0)", "Control, system context, evidence, policies, open POA&Ms",
         "Sectioned draft with citations", "Citations validated against real records; draft versioning; review request required", "Manual writing"],
        ["TR evidence analysis (tr.evidence_analysis@1.1.0)", "TR row (CCI / AP), linked evidence, STIG/ACAS results, policy coverage, POA&Ms",
         "Per-source verdict, reason, quote and suggested Test Results text", "References must exist; quotes verified; fields compliance_status / "
         "tested_by / date_tested are rejected by the schema", "Deterministic analysis label"],
        ["Inventory correlation ranking (inventory.correlation_rank@1.0.0)", "Scan host facts and candidate assets",
         "Ranked candidates with confidence and identifiers", "Fabricated candidates and unsupported identifiers dropped; creates no asset or finding",
         "Deterministic correlation engine"],
        ["Discrepancy explanation (inventory.discrepancy_explain@1.0.0)", "An inventory discrepancy and its records", "Plain-language explanation and ranking",
         "References validated; suggestion only", "Rule text"],
        ["Connection test (ai.health_check@1.0.0)", "A random nonce", "Status, echoed nonce, one-sentence summary", "Nonce must match", "—"],
    ], [20, 22, 20, 24, 14]),
    NOTE("never", "Set or approve a Compliance Status, assessment result, authorization decision or risk acceptance; fill in 'Tested by' "
                  "or 'Date tested'; close a POA&M; approve its own suggestion; make a privacy determination; create assets or findings; "
                  "change inventory records; or bypass the human approval gate, which is locked on."),
    H2("6.2 Provider architecture"),
    P("The provider is chosen with environment values only: AI_PROVIDER, AI_MODEL, an optional per-use-case AI_MODEL_DRAFTING / _POLICY / "
      "_MAPPING / _SUMMARY, AI_TIMEOUT_SECONDS and AI_MAX_OUTPUT_TOKENS (default 8000). Switching providers takes an env change and a "
      "restart of the backend and worker. A platform admin can override the model in the Admin page; this is audited."),
    TABLE(["AI_PROVIDER", "Transport", "Notes"], [
        ["openrouter (recommended)", "OpenAI Chat Completions over HTTPS, base https://openrouter.ai/api/v1", "One key (OPENAI_COMPAT_API_KEY); any model slug passed verbatim; "
         "structured output negotiated json_schema → json_object → prompt; 429/502/503 retried honouring Retry-After; clear 401/402/404 messages"],
        ["anthropic", "Anthropic Messages API", "ANTHROPIC_API_KEY; direct adapter (not exercised against the live API in development)"],
        ["openai_compatible", "Any OpenAI-compatible endpoint (vLLM, Ollama, LM Studio, gateways)", "Keeps data inside your boundary when self-hosted"],
        ["emergent", "Emergent universal key", "Development preview only; refused in staging and production"],
        ["none / empty", "—", "All features run in deterministic mode"],
    ], [22, 33, 45]),
    H2("6.3 Status, health and usage"),
    UL("**GET /api/v1/ai/status** (every signed-in role): provider / model, configured yes/no, analysis mode ('AI-assisted (provider / "
       "model)' or 'Deterministic analysis (no AI)'), endpoint, whether a key is configured (never the key), last successful call, "
       "24-hour call and token usage. Only admins see the last error.",
       "**POST /api/v1/ai/health** (platform admin, 'Test AI connection'): one tiny call returning provider, model and latency. Success "
       "and failure are both audited.",
       "**GET /api/v1/health**: platform health including the AI component.",
       "The API key is sent only as a bearer header. It is never logged, returned or shown."),
    NOTE("info", "With OpenRouter, prompts go to OpenRouter and on to the provider of the selected model. Choose models and routing settings "
                 "(data retention, no training) that fit your data policy, or use a self-hosted openai_compatible endpoint for data that "
                 "must stay inside your boundary. Development and staging use synthetic data only."),
    PB,
    H1("7", "Reference content"),
    P("Reference content is pinned, versioned and SHA-256-verified at load. Updates are previewed (diff and impact) and applied only by a "
      "role with content.apply. History is never rewritten: observations and assessments keep the content version they were made against."),
    TABLE(["Content", "Version / source", "Loaded"], [
        ["NIST SP 800-53 Rev. 5 controls", "OSCAL catalog (5.1.x)", "1,196 controls: 324 base, 872 enhancements, 182 withdrawn"],
        ["NIST SP 800-53A assessment objectives", "OSCAL", "3,715 objectives"],
        ["NIST SP 800-53B baselines", "OSCAL profiles", "Low 149 · Moderate 287 · High 370 · Privacy 96"],
        ["DISA CCI list", "Pinned DISA CCI XML", "5,137 CCIs; 3,838 CCI → Rev. 5 mappings, all resolved"],
        ["NIST SP 800-60 Vol. 2 Rev. 1", "Appendices C and D", "168 information types (C: 76, D: 92) with provisional C/I/A"],
        ["CNSSI 1253 Appendix D", "29 July 2022, corrected copy 6 Oct 2022 (161 pp.)", "1,189 rows (Tables D-1 … D-20), 182 withdrawn, page-cited"],
        ["CNSSI 1253 parameter values", "Appendix D 'Parameter Value' column", "162 controls with values; 204 mapped to single ODPs; 27 kept at control level"],
        ["CNSSI 1253 overlays", "Official attachments (e.g. Classified, Privacy, Space)", "13 overlay records; restricted overlays shown as unavailable"],
        ["CISA KEV", "Pinned snapshot", "Re-evaluated daily against findings"],
        ["STIG content", "Versioned releases (demo data synthetic)", "Diff and impact preview before apply"],
        ["OSCAL schemas", "OSCAL 1.2.2", "SSP, POA&M, Assessment Plan, Assessment Results"],
    ], [28, 32, 40]),
    H2("7.1 CNSSI 1253 baseline numbers (selected = 'X' or '+')"),
    TABLE(["Impact level", "Confidentiality", "Integrity", "Availability"], [
        ["Low", "273", "310", "147"], ["Moderate", "319", "380", "202"], ["High", "397", "474", "283"]], [25, 25, 25, 25]),
    P("The privacy control baseline has 93 rows. Example unions: L-L-L = 394 (357 security plus privacy), M-M-M = 492, M-H-L = 559, "
      "H-H-H = 607. Thirty rows were checked by hand against rendered PDF pages and are pinned in the test suite. Compared with "
      "SP 800-53B: all 149 Low controls are selected at L-L-L; 286 of 287 Moderate at M-M-M (IA-12(5) is '--'); 369 of 370 High at H-H-H."),
    NOTE("sme", "Union interpretation: the NSS baseline is computed as (C column at the C level) ∪ (I at the I level) ∪ (A at the A level) "
                "∪ the privacy control baseline, with no high-water mark. CNSSI 1253 §3.2.1 does not use the word 'union'. Seven Rev. 5 "
                "controls that are not in the 2022 tables (IA-13 and its enhancements, SA-15(13), SA-24, SI-2(7)) are not selected and "
                "are listed for SME review."),
    NOTE("sme", "Privacy Overlay / ACCT layering: whether ACCT layers under Low/Moderate/High exactly as the variant switcher assumes "
                "(CNSSI 1253F Att. 6 Table 2). ACCT covers 23 of the 27 privacy controls left to the overlay; SA-4, SC-7(24), SI-12(2) "
                "and SI-19 are shown as 'not covered – SME review'."),
    NOTE("sme", "Privacy Threshold Analysis defaults: the shipped questionnaire is a generic example and must be validated by the "
                "agency's privacy office."),
    PB,
    H1("8", "Evidence and data integrity"),
    UL("**Content addressing.** Every uploaded file is stored under its SHA-256. File names are never used as storage paths. "
       "Duplicate uploads are detected by hash.",
       "**Provenance.** Each evidence item records its source (upload, connector, generated export), uploader, ingest run, linked "
       "controls and scan status ('not_scanned' when no ClamAV scanner is configured).",
       "**Integrity verification.** A worker job re-reads each object, recomputes SHA-256 and records an integrity check. The Evidence "
       "Ledger shows the current integrity status and the last verification time.",
       "**Freshness.** Freshness policies define a window per evidence type. Controls are rolled up as current, partially stale or expired "
       "per asset ('N of M assets'). Stale evidence feeds Continuous Monitoring.",
       "**Versioning.** Replacing evidence creates a new version with a reason. The previous version is kept, and dependent controls and "
       "TR rows are flagged for re-review. Removal requires a reason and is audited.",
       "**Retention and legal hold.** Retention rules per resource type purge only after their window; items under legal hold are never "
       "purged. Every purge supports a dry run and is audited. The audit log itself is never purged.",
       "**Generated artifacts.** OSCAL exports and workbook exports are stored as hashed evidence with their validation reports."),
    IMG(S + "rmf-accuracy/09_evidence_version_history.png", "Evidence version history", 85),
    PB,
    H1("9", "eMASS workbooks"),
    H2("9.1 Test Result (TR) workbook"),
    UL("**Import:** the real eMASS Test Result template. Header roles are detected (control acronym, AP acronym, CCI, CCI definition, "
       "implementation guidance, assessment procedures, Compliance Status, Date Tested, Tested By, Test Results). AP/CCI rows are matched "
       "to the system's controls, with manual resolution, and the mapping is saved as a reusable template definition.",
       "**Generation:** rows are proposed from SCA assessments, STIG/ACAS results, policy coverage, evidence freshness and POA&Ms, with "
       "missing, conflict and stale flags.",
       "**Approval:** only the SCA approves. Each approval records the actual tester and test date (not the approver or today's date). "
       "Rows approved under an older rule were marked 'needs confirmation'.",
       "**Two export modes, detected automatically.** Pre-populated mode (rows came from eMASS) writes only columns M–P (Compliance "
       "Status, Date Tested, Tested By, Test Results) of SCA-approved rows. Blank-template mode also writes the identifiers A/F/G/H, "
       "but only on rows added from the system, because eMASS needs them to identify each added row.",
       "**Validation report:** every cell outside the permitted ranges is compared (value, formula, style) and every other package part "
       "byte-for-byte. The report lists the mode, the permitted ranges with a reason for each, and the changed cells."),
    IMG(S + "tr/6-export-history.png", "Test Results export history with validation status", 88),
    H2("9.2 Hardware/Software (HW/SW) list"),
    UL("Import of the eMASS HW/SW .xlsm. Headers are detected and vocabularies come from the template's '(U) Lists' tables. Existing "
       "records are never overwritten without proposal → accept → approve.",
       "**Macros are never executed.** The workbook is processed as an OOXML package. On export, vbaProject.bin and the three signature "
       "parts stay byte-identical to the template, and only permitted cells are written.",
       "Every export comes with a validation report."),
    NOTE("human", "Open both exported workbooks in Microsoft Excel (macros disabled) and confirm there is no repair prompt and that the dropdowns "
                  "still work. Import the TR export (Assessment → Test Result Import) and the HW/SW export into eMASS, and spot-check rows. "
                  "eMASS import compatibility has not been verified in the development environment."),
    PB,
    H1("10", "Technical architecture"),
    IMG("__DIAGRAM__", "Reference architecture", 100),
    TABLE(["Layer", "Technology", "Responsibility"], [
        ["Frontend", "React + TypeScript, Tailwind design tokens, shadcn/ui", "Page per RMF module; permission-aware UI; no secrets in the bundle"],
        ["API", "FastAPI (Python 3.11), Pydantic, SQLAlchemy 2", "REST under /api/v1; OpenAPI at /api/openapi.json; RBAC dependencies on every mutating route"],
        ["Worker", "Separate Python process", "jobs table queue (SELECT … FOR UPDATE SKIP LOCKED), DB-stored schedules with locking and stale-job recovery, heartbeat"],
        ["Database", "PostgreSQL 16, Alembic", "29 migration files (0001 … 0028); additive, reversible; org_id on every record; append-only audit trigger"],
        ["Object storage", "Storage abstraction: local FS or any S3 API", "SeaweedFS (Compose profile), AWS S3, DigitalOcean Spaces, Garage; selected via env"],
        ["Identity", "dev_password (dev/demo), OIDC (Keycloak profile), mTLS header stub", "Authorization Code + PKCE, server-side sessions"],
        ["Optional", "ClamAV, HashiCorp Vault, Prometheus / Grafana", "Compose profiles"],
    ], [16, 36, 48]),
    H2("10.1 API design"),
    UL("JSON over HTTPS, bearer-token authentication, base path /api/v1. Interactive docs at /api/docs.",
       "Error semantics: 401 unauthenticated or expired session · 403 RBAC denial (audited) · 404 not found or other tenant · 409 state "
       "conflict · 413/415/422 upload or validation · 429 rate limited with Retry-After.",
       "Long-running work (ingest, policy analysis, TR generation and analysis, inventory checks) returns 202 with a job id.",
       "Appendix A summarises the endpoint groups from the live OpenAPI specification."),
    H2("10.2 Multi-tenancy"),
    P("Every record carries org_id. Queries are scoped to the caller's organization and to their system role assignments. Objects "
      "addressed by id (workbooks, rows, evidence, discrepancies) resolve their owning system, and requests across tenants return 404. "
      "Automated tests check that a user of tenant B gets 403/404 or empty results for tenant A's systems, POA&Ms, findings, search, "
      "audit, TR and inventory objects. Each sandbox is its own tenant and is purged after a configurable inactivity period."),
    PB,
    H1("11", "Security and compliance posture"),
    TABLE(["Area", "Implementation"], [
        ["Authentication", "AUTH_PROVIDERS: dev_password (simulated, dev only, disabled in production compose), oidc (Code + PKCE S256, state + nonce, "
                           "JWKS signature, iss/aud/exp checks), mtls_header (trusted-proxy stub for CAC/PIV front-ends)"],
        ["Sessions", "Server-side sessions; idle 30 min, absolute 12 h; rotating hashed refresh tokens; logout revokes; lockout 5 failures / 15 min"],
        ["Authorization", "RBAC scoped to org/system; every mutating route declares a permission dependency (enforced by test); denials audited"],
        ["Separation of duties", "Self-approval blocked; SCA independence; AO-only decisions; Platform Admin has no decision rights; real-user SoD in production"],
        ["Audit", "Hash-chained, append-only audit_events (DB trigger); chain verification; CSV/JSON export; never purged"],
        ["Web hardening", "Strict CSP, nosniff, X-Frame-Options DENY, no-referrer, HSTS; exact-origin CORS allowlist ('*' refused); per-IP rate limits"],
        ["Uploads", "Extension allowlist per kind, magic bytes, size limit, defusedxml, zip-bomb/path-traversal checks, optional ClamAV"],
        ["Secrets", "Env files are parsed as data (never sourced) and validated by check_env; Fernet secret store or Vault KV v2; keys never logged or returned"],
        ["Production safety", "check_env refuses insecure production settings (e.g. AI_PROVIDER=emergent, wildcard CORS, demo login without explicit opt-in)"],
        ["Supply chain", "pip-audit clean on production requirements; Bandit high/medium 0; remaining yarn-audit highs are build-time only (react-scripts)"],
    ], [22, 78]),
    NOTE("human", "OIDC has been tested against a mocked IdP and a dev Keycloak realm. Vault was tested with a mocked client only and ClamAV "
                  "was not run against a live clamd. FIPS 140-3 operation needs a FIPS-validated OpenSSL provider and host FIPS mode, which "
                  "have not been set up or validated."),
    PB,
    H1("12", "Deployment and portability"),
    UL("**Docker Compose** is the reference deployment: edge proxy, frontend, backend, worker, PostgreSQL, object storage, optional "
       "Keycloak, ClamAV, Vault and monitoring profiles.",
       "**DigitalOcean reference** (docs/DIGITALOCEAN_DEPLOYMENT.md): measured sizing, Ubuntu 24.04 set-up, block-storage volumes, TLS "
       "with automatic certificates, a one-command deploy script with fail-fast preflight checks, environment templates, lifecycle "
       "procedures, and migration paths to Managed PostgreSQL and other storage profiles with no code change.",
       "**Demo deploy with recovery deferred** (deploy.sh --demo-without-recovery): read-only preflight, rollback snapshot of the env and "
       "image tags, demo settings, backup verification, migration, demo smoke test. Any failure restores the previous env and images.",
       "**Data recovery tooling** (recover.sh): read-only rehearsal on isolated replicas, a plan with a hash that must match at apply "
       "time, read-only evidence integrity checks, cutover and rollback.",
       "**Portability register** (docs/PORTABILITY.md): the only preview-platform dependencies are the Emergent AI adapter (refused "
       "outside preview) and pod bootstrap scripts, neither of which is used by Docker deployments."),
    NOTE("human", "The recovery toolkit was built and verified on isolated replicas in the build environment only. It has **not** been run on "
                  "the customer Droplet. Docker builds and 'compose up --wait' health checks were validated statically (YAML and shellcheck) "
                  "in development; the first real run is on the target host."),
    PB,
    H1("13", "Use cases and walkthroughs"),
    H2("13.1 New system to ATO (FIPS 199)"),
    OL("ISSO registers the system and its assets; the ISSM assigns key roles (Prepare).",
       "ISSO selects SP 800-60 information types; FIPS 199 computes the high-water mark; the AO approves (Categorize).",
       "ISSO applies the SP 800-53B Moderate baseline, tailors with justification and sets ODPs (Select).",
       "ISSO writes implementation statements (optionally AI-drafted and reviewed), uploads STIG/ACAS results and policies (Implement).",
       "SCA assesses controls, approves TR rows with tester and date, and exports the TR workbook (Assess).",
       "ISSM endorses the package; the AO grants ATO with an expiry; POA&Ms track residual risk (Authorize).",
       "Monitoring flags KEV, CAT I, overdue POA&Ms and stale evidence (Monitor)."),
    H2("13.2 National Security System (CNSSI 1253)"),
    OL("Categorize answers 'Is this an NSS?' = Yes, which preselects CNSSI 1253; C/I/A are kept separate (e.g. M-H-L).",
       "Select loads the Appendix D trigraph union with page citations; a re-categorization produces an 'N added / M removed' proposal that applies only on Accept.",
       "Official overlays are offered with applicability; the Classified overlay requires an explicit 'classified = Yes'.",
       "The parameter comparison shows catalog, CNSSI and system values. Adopting a CNSSI value is audited, can be undone and warns about conflicts.",
       "When PII is present (Yes or Unknown), the Privacy Overlay prompt shows the 27 privacy controls left to the overlay."),
    H2("13.3 Continuous monitoring"),
    P("Scheduled jobs re-evaluate KEV, freshness and deadlines. The Monitor step and the Portfolio surface what needs attention. New scans "
      "deduplicate into canonical findings; remediation marks POA&Ms closure-eligible for a human to close."),
    H2("13.4 eMASS round trip"),
    P("Export the TR template from eMASS, import it, let IronVision AI propose results, have the SCA approve, export, review the "
      "validation report, and import into eMASS. The same applies to the HW/SW list. Final eMASS acceptance requires human verification."),
    H2("13.5 Policy gap analysis"),
    P("Upload an organization's policies. The Policy Auditor maps sections and pages to controls, evaluates each assessment objective and "
      "CCI, and optionally refines the results with AI using verified quotes. Gaps become proposed findings that a human confirms or "
      "dismisses; the CCI view shows coverage."),
    H2("13.6 Inventory reconciliation"),
    P("Import the HW/SW list and scans. The correlation engine links hosts deterministically, sends ambiguous matches (shared IPs, "
      "conflicts) to review with optional AI ranking, and lists discrepancies (missing from inventory, no scan, conflicting identifiers, "
      "duplicates, stale scans). Each change needs accept and then approval by a different real user."),
    H2("13.7 Demo and sales sandbox"),
    P("'Explore demo' opens a shared synthetic workspace that resets nightly. 'Create account' provisions an empty private sandbox with "
      "personas, so one person can walk through ISSO → SCA → AO hand-offs, labelled 'Sandbox: same person'."),
    PB,
    H1("14", "Limitations, known gaps and roadmap"),
    TABLE(["Area", "Status today", "Roadmap"], [
        ["Live evidence connectors", "MOCKED (MockAdapter, labelled)", "Real scanner, cloud and ticketing connectors"],
        ["eMASS REST sync", "MOCKED default adapter; REST adapters are stubs", "Authorized read/write against eMASS"],
        ["eMASS / Excel acceptance of exported workbooks", "REQUIRES HUMAN VERIFICATION", "Confirm in Excel and eMASS"],
        ["Droplet deployment and data recovery", "Built and rehearsed on replicas; not run on the customer Droplet", "Operator-run cutover"],
        ["CNSSI union, PTA defaults, ACCT layering", "SME REVIEW REQUIRED", "Agency SME sign-off"],
        ["Agency-specific information types, SP 800-60 descriptions", "Not implemented", "Load descriptions; agency type editor"],
        ["Agency overlay control changes", "Metadata only", "Apply agency overlay deltas"],
        ["EPSS, email notifications, OSCAL component definitions", "Not implemented / disabled", "Backlog"],
        ["Software ↔ asset assignment UI, asset merge", "Future", "Inventory phase 2"],
        ["Multi-replica rate limiting / OIDC state", "Per-process in memory", "Shared store (Redis or proxy)"],
        ["Frontend build tooling", "Create React App (build-time audit findings)", "Migrate to Vite"],
        ["FIPS 140-3, CAC/PIV, FedRAMP, ATO of the tool itself", "Not claimed", "Customer-specific"],
    ], [32, 36, 32]),
    PB,
    H1("15", "Glossary"),
    TABLE(["Term", "Meaning"], [
        ["ACAS", "Assured Compliance Assessment Solution (Tenable-based DoD vulnerability scanning)"],
        ["ACCT", "Accountability control set of the CNSS Privacy Overlay (CNSSI 1253F Att. 6)"],
        ["AO / AODR", "Authorizing Official / AO Designated Representative"],
        ["AP", "Assessment Procedure (eMASS)"],
        ["ATO / IATT / DATO", "Authority to Operate / Interim Authority to Test / Denial of Authority to Operate"],
        ["CAT I/II/III", "STIG severity categories"],
        ["CCI", "Control Correlation Identifier (DISA)"],
        ["CKL / CKLB", "STIG Viewer checklist formats"],
        ["CNSSI 1253", "Committee on National Security Systems Instruction 1253: categorization and control selection for NSS"],
        ["CRM", "Customer Responsibility Matrix"],
        ["eMASS", "Enterprise Mission Assurance Support Service"],
        ["FIPS 199 / 200", "Federal standards for security categorization / minimum security requirements"],
        ["HW/SW", "Hardware/Software list"],
        ["IL2–IL6", "DoD Cloud Computing SRG information impact levels"],
        ["ISSM / ISSO", "Information System Security Manager / Officer"],
        ["KEV", "CISA Known Exploited Vulnerabilities catalog"],
        ["NSS", "National Security System (44 U.S.C. §3552(b)(6))"],
        ["ODP", "Organization-Defined Parameter"],
        ["OIDC / PKCE", "OpenID Connect / Proof Key for Code Exchange"],
        ["OSCAL", "Open Security Controls Assessment Language (NIST)"],
        ["PII / PIA / PTA", "Personally Identifiable Information / Privacy Impact Assessment / Privacy Threshold Analysis"],
        ["POA&M", "Plan of Action and Milestones"],
        ["RBAC / SoD", "Role-Based Access Control / Separation of Duties"],
        ["RMF", "Risk Management Framework (NIST SP 800-37 Rev. 2)"],
        ["SCA", "Security Control Assessor"],
        ["SCAP / XCCDF", "Security Content Automation Protocol / Extensible Configuration Checklist Description Format"],
        ["SSP", "System Security Plan"],
        ["STIG", "Security Technical Implementation Guide (DISA)"],
        ["TR", "Test Result (eMASS workbook)"],
    ], [22, 78]),
]
