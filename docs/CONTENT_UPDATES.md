# Controlled content updates (STIG / KEV / catalogs)

1. **Stage**: `python scripts/stage_content_release.py <file>` (or drop a pinned file into `backend/content/` with its SHA-256 in the manifest). Then Admin → Jobs → **Register staged content**, or wait for the scheduled `content.check_updates` job. The new version appears as *available*.
2. **Preview** (Evidence Ledger → Content updates → *Preview diff & impact*). This computes a rule-level diff (added / removed / changed requirement / changed severity) and the impact on assets, findings, controls and POA&Ms. Nothing is changed yet. Synthetic demo V1R1 → V1R2: **6 added / 3 removed / 11 changed / 2 severity**. P-0027 moves CAT II → CAT I.
3. **Apply** (needs `content.apply`, ISSM or platform admin, plus a justification). The new version becomes installed. New observations are evaluated against it. Affected POA&Ms get a re-evaluation flag and a notification. Mappings are re-mapped through mapping history.
4. **History**: the *Application history* table shows a readable summary per update in the form "6 added / 3 removed / 11 changed / 2 severity" followed by "Impact: N assets · N findings · N controls · N POA&Ms · history preserved (0 observations rewritten)". The full diff stays in the `content_updates` row and the audit log.

Guarantees: historical observations, assessments and mappings keep the content version they were made with (`observations_rewritten = 0`). Every file is hash-verified before load. Updates are never applied automatically.

KEV: the pinned CISA catalog (`backend/content/kev/`) is the only KEV source. Refreshing it follows the same stage → preview (count of flags changed) → apply flow.
