# 8 · Compatibility risks and how each is preserved

| Risk | Where | Preservation |
|---|---|---|
| Deep links / bookmarks / emailed links | every route in `App.tsx` (e.g. `/systems/:id/controls/:cid`, `/findings/:id`, `/poams/:id`, `/emass-import/:id`, notification links) | Keep every current path as a route alias that redirects (with params and query) to the new location. Add a test that walks the route inventory in `AUDIT.md` and asserts no 404. Notification and email templates keep working through the aliases. |
| Test IDs | frontend tests, `scripts/*_shots.py`, testing-agent playbooks, `scripts/ux_baseline/*` | Keep existing `data-testid`s on the moved components; add new ones only. Run a CI grep that every testid used by tests still exists. Re-run the baseline scripts unchanged. |
| Role matrix / SoD | `require_permission`, `/help` role matrix, SCA independence, AO-only decision | No backend change. UI hides only actions the matrix already denies. Re-run the role-matrix tests and pass-C checks (AO-only categorization approval, ISSM strategy approval). |
| Tenant isolation | `test_tenant_isolation_sweep.py` (4), `test_tenant_isolation_full.py` (1) | No new endpoints in R1–R5. Dashboard/My Work reuse existing tenant-scoped endpoints. If an aggregate endpoint is added, it must be added to the sweep in the same release. |
| Audit and provenance | audit events, import provenance | UI-only changes. No write path changes. |
| Guided-mode preference | user settings | Per-user preference in the existing settings store. Tenant-scoped. |
| Screenshot docs | `docs/screenshots/*` | Regenerate after each release. |
