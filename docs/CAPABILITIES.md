# Capabilities — the map and how to use it

Everything lives in `app/modules/core/shared/lib/capabilities.py`. The map is the source of truth — this doc restates it; if they disagree, the file wins.

> **Changing with the Dashboard update (2.7, section S0):** roles become **Department + Role + Seniority + Reports to**. Capabilities = department set + seniority set; admin a separate switch; `can()` unchanged for callers. Update this doc when it lands.

## Helpers

- `can(capability, user=<unset>)` — **Omit** `user` for the effective user (emulation-aware, needs a request context). **Pass** a user — including `None`, or anything without a role — and the answer is about that user, False when there is no role. Admin's `'*'` grants everything.
- `@require(capability, real_user=False)` — HTML routes. 401 logged out, 403 without it.
- `@require_api(capability, real_user=False)` — JSON routes. Returns `{'success': False, 'error': 'Forbidden'}, 403` for both cases.
- **`real_user=True`** checks the logged-in user instead of the emulated one — for admin-only tooling an admin should keep while previewing as someone else: the admin panel, wiki editing, badge tools, user management, the client directory. Every such route needs a test that an *emulating* admin is refused.
- `effective_user()` — the emulated user when an admin is viewing as someone else, otherwise the logged-in user. `_get_actor()` / `get_actor()` are local names for it. DI keeps a parameterised variant `_effective_role_user(user)` on purpose.
- Jinja globals `can(cap)` and `role_labels`, registered in `app/__init__.py`.
- `ROLE_LABELS` (key → display label, in picker order) is **the one role list** — pickers, the admin panel, and any template that lists roles (the wiki section modal since 2.5.3) read it. Never retype role names in a template.

## The map

| Role | Capabilities |
|---|---|
| `admin` | `*` |
| `management` | view_workspace, view_cs, view_finance, edit_invoicing_thresholds, close_projects, view_all_projects, manage_projects, create_projects, start_projects, review_submissions, transfer_projects, edit_client_directory, raise_flags, manage_flags, log_site_visits, manage_reference_data, complete_preproduction, manage_project_files, switch_dashboard_scope, view_team_snapshot, view_di_performance, view_all_di, view_hse, write_friction_log, view_time_reports |
| `cs` | view_workspace, view_cs, view_finance, edit_finance, close_projects, view_all_projects, create_projects, review_submissions, transfer_projects, edit_client_directory, raise_flags, manage_reference_data, manage_project_files |
| `finance` | view_workspace, view_cs, view_finance, edit_finance |
| `project_owner` | view_workspace, view_cs, view_finance, view_all_projects, create_projects, log_site_visits, claim_ownership |
| `designer` | view_workspace, manage_drafts, claim_work, raise_flags, complete_preproduction, start_projects |
| `team_lead` | same as designer |
| `digital_innovation` | view_workspace, view_all_di |
| `hse` | view_hse, manage_hse — **no `view_workspace`**: the officer sees the HSE module, File Storage and the Wiki, nothing else (`test_hse_sidebar.py` pins it) |
| `hr` | `_READ_ONLY_STAFF` **plus view_hse** — reads HSE (injuries and lost time are HR's concern too), which also puts HR in the HSE report-email recipients |
| `production` / `logistics` | `_READ_ONLY_STAFF`: view_workspace, view_cs, view_finance, view_all_projects, edit_client_directory |

- **`view_workspace`** is the broad "can use the main app" capability held by every role but `hse`. It is the gate to reach for on a data endpoint behind an already-gated page (CONVENTIONS.md → *Gate the endpoints*), rather than inventing a narrower one.
- **`view_finance`** is held by every role with `view_cs` (project owners since v2.6), so everyone who can open Client Servicing sees its figures. Editing them is `edit_finance` (admin, CS, Finance). The gate stays in code for any future CS role without it.
- **`view_hse` doubles as the HSE email recipient list** (`hse/lib/share.py::recipients`). Anyone who should receive the reports must be able to open the link in them, so the two are one capability on purpose.
- `designer` and `team_lead` hold identical capabilities. What separates them is the team a deliverable belongs to — a per-record rule, never a role rule.
- Admin-only capabilities are listed in `ADMIN_ONLY`: admin_panel, manage_users, manage_wiki, manage_blog, manage_feedback, manage_achievements, manage_scopes, manage_di_templates, override_status, edit_di_board, toggle_project_hold. Granting one to a role means editing two places on purpose.
- **Coming with 2.7 (the Dashboard update):** `raise_escalation` (design lead, CS, PO, designers), `decide_escalation` (management), `nudge` (every role with a dashboard), `view_adoption` (management + the champion grant), and whatever the six dashboard gates settle on in S2 (reuse existing capabilities where they fit).

### `start_projects` — who moves a project off Briefed
Held by **designer, team_lead, management, admin** only. CS deliberately does not — the people who do the work decide when it starts. A pure capability with no relationship half: any designer can start any project. If that needs tightening, `_is_assigned_designer` in `details.py` is the helper to combine it with (mind the branch-selector trap).

## Adding a role
1. One key in `ROLE_CAPABILITIES` with its capability set.
2. One entry in `ROLE_LABELS`.
Both pickers and the account-edit form render from the map. Decide whether the role holds `view_workspace`; check `dashboard/lib/project_loader.py::scope_query` — a role holding `view_all_projects` sees the full active list, one without it gets an empty dashboard by design.

## Four kinds of check — keep them apart
1. **Gate** — can you reach this at all? `can()` / `@require`.
2. **Scope** — which records does your role see? A capability in the map, applied as a query filter, not a door.
3. **Relationship** — "management **or** the project's owner **or** its CS lead". The map answers only the role-wide half; ownership stays in code: `can('manage_projects', actor) or actor.id == project.project_owner_id`.
4. **Grant** — a per-person exception a role can't express: a join table owned by the feature (the OVP champion → `is_champion(user)`; per-person DI board visibility, after October). Never in the map. The pattern is *gate OR grant*: `can('write_friction_log', user) or is_champion(user)`.

Two more that look like gates and are not: checks about **another** user's role (validation), and the **branch selector** below.

## State gates — not a role question at all
What the record's own state allows, regardless of who is asking. Admin's wildcard does not open these. Reference: `submissions_blocked_reason(project)` in `project_overlay/_common.py` — a `briefed` project takes no submission work until Start Project; every Submissions write route returns **409**, not 403. The gate has one definition and the UI reads it too (`submissions_open`); the grandfather clause is self-sealing (only a project that already carries a submission is exempt, and creating one is what's blocked).

## The branch-selector trap
Admin holds every capability through `'*'`. Where a role literal selects a branch that admin is *deliberately outside of*, converting it hands admin that branch. About 40 literals stay literal for this reason, each commented: `self_claim_only` (deliverables), `_is_assigned_designer` (details), `default_focus`, `layout_role` (dashboard template choice), the notification-preference toggles in `account.html`. **Definition of done is not "zero role literals"** — it is no role literal without a comment saying why it is not a gate, and the baseline test enforces it.

## Where the CS review lock lives
`can_access_client_servicing()` in `client_servicing/lib/access.py` = `can('view_cs', user)` plus the `CLIENT_SERVICING_REVIEW_ONLY` narrowing (off from the 2.6 activation). CS routes gate through `@require_cs`; `can()` stays a pure map lookup.

## The contract test
`core/shared/tests/test_capabilities_contract.py` fails if any module imports the retired `role_required` or hand-rolls `admin_required`; declares a local `_ROLES` set (two allowlisted by name); or introduces a **new `.role` literal not in the baseline** `core/shared/tests/role_literal_baseline.txt`. Generator and test share one definition in `core/shared/tests/role_literals.py`. After an intentional change to a role literal (adding or removing one): `python generate_role_literal_baseline.py`, commit the baseline with the change. `test_capabilities.py` also pins `set(ROLE_LABELS) == set(ROLE_CAPABILITIES)`, and that HR matches Production and Logistics apart from `view_hse`.

## Loose ends
- `_tab_strip.html`'s label list is narrower than `view_all_projects`: a project owner gets the all-projects query but the "Team Projects" label. Pre-existing; left alone.
