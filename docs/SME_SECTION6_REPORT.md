# SME test findings – Section 6 (roles)

Preview: https://aegis-rmf-demo.preview.emergentagent.com. Browser check account: `sme-s2-a41c5d@example.com` / `Sme-S2-2026!x` (sandbox with demo data; personas switched in the header).
Screenshots: `docs/screenshots/sme-section6/`. The Droplet was not touched.

| # | Root cause | Change | Files | Click path |
|---|---|---|---|---|
| 25 Role always visible | Non-sandbox role chips were hidden below the `lg` breakpoint. | Role chips (org roles plus a system-role count) are shown at every width, with a tooltip pointing to Help. Sandbox accounts keep the "Acting as <persona>" selector. The current role label is also used in every denied message. | shell/Header.tsx, context/AuthContext.tsx (`setActingLabel`) | Header (right) |
| 25 Options kept visible but disabled | 39 places used `{can(perm) && …}`, so options **vanished** for other roles. Sidebar items with a permission were filtered out. | A new `Gated` wrapper: the option stays visible, is disabled (native `fieldset disabled`), shows a lock and the tooltip "<Action> requires <roles> – you are acting as <role>". Clicking opens a dialog with the same text and, in sandbox accounts, **"Switch role to …"** buttons (calls `/sandbox/act-as`).<br>Converted 23 direct option guards across Evidence, System detail, Mapping Review/eMASS, Inheritance/Policy Auditor, Workbench (status save, implementation, comments), Systems (register), Categorize and Admin. The rest already had an explanatory else-branch or carry extra state conditions (e.g. "only when the POA&M is open").<br>Gated sidebar items stay listed (locked), with the same dialog. | components/common/RoleGate.tsx (`Gated`, `DeniedDialog`), shell/Sidebar.tsx, AppShell.tsx, converted pages | e.g. act as AO → a control → Status "Save" (locked) → click |
| 25 Backend 403s in plain words | 403s showed "Your role can't do this (needs “implementation.write” …)". | `errorMessage()` turns `missing_permission` 403s into the same sentence (action label from the backend matrix, allowed roles, your current role) and opens the same dialog, so nothing fails silently. | lib/api.ts, RoleGate.tsx | Any refused action |
| 25 Action → role matrix | Not documented in the app. | `GET /reference/role-matrix` is built from the **enforced** RBAC tables (`ROLE_PERMISSIONS`), with plain action labels. The **Help: who can do what** page (Tools) shows a role-by-action grid, a "You" column and the SoD note (AO decides, SCA assesses, Admin holds no decision rights). | api/v1/rmf_steps.py (`role_matrix`), services/rmf_steps.py (`ACTION_LABELS`), pages/HelpPage.tsx, nav | Sidebar → Tools → Help: who can do what |

RBAC itself is unchanged: the backend still enforces every permission, and the UI only explains it.

## Tests
- `backend/tests/test_sme_section6.py`: the matrix equals `ROLE_PERMISSIONS`; AO-only for authorization decisions; a Leadership-persona tailoring call returns a 403 naming `system.write` and the allowed roles.
- Jest: 6 passed (`RoleGate` initialises lazily, so modules that mock `@/lib/api` still work).
- Browser:
  - Acting as AO on a control: 2 locked options with the title "Changing implementation status or writing implementation statements requires System Owner or ISSO – you are acting as AO."
  - Click → dialog with 2 Switch-role buttons → switched to ISSO → 0 locked.
  - The Help row for `implementation.write` shows System Owner ✓ ISSO ✓, others –.
  - As Leadership, the sidebar shows a locked item.
