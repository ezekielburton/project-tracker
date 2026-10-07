# Capabilities — the map and how to use it

Access lives in `app/modules/core/shared/lib/capabilities.py`; the org model it reads (departments, seniority, the branch checks) lives in `lib/org.py`. The files are the source of truth — this doc restates them; if they disagree, the files win.

## The org model

Every person has four fields on the shared user record, plus an admin switch:
- **Department** — Client Servicing, Project Owners, Design, Production, Logistics, Finance, HR, Digital Innovation, HSE, or none (the GM). Keys in `org.DEPARTMENTS`.
- **Role** — the job title (`User.job_role` → `JobRole`), picked or typed per person. Cosmetic: it never decides access.
- **Seniority** — None → Manager → Head of Department → Management (`org.SENIORITY_LEVELS`).
- **Reports to** — a person. Drives approvals (`hr/services/approvers.py`).
- **Admin** — `User.is_admin`, a separate switch that grants everything.

Admins edit all of these in Admin → Accounts until the HR pages arrive.

## Helpers

- `can(capability, user=<unset>)` — **Omit** `user` for the effective user (emulation-aware, needs a request context). **Pass** a user — including `None`, or anything without org fields — and the answer is about that user, False when they hold nothing. Admin holds everything.
- `capabilities_for(user)` — the full set: `{'*'}` for admin, otherwise department set ∪ seniority set.
- `@require(capability, real_user=False)` — HTML routes. 401 logged out, 403 without it.
- `@require_api(capability, real_user=False)` — JSON routes. Returns `{'success': False, 'error': 'Forbidden'}, 403` for both cases.
- **`real_user=True`** checks the logged-in user instead of the emulated one — for admin-only tooling an admin should keep while previewing as someone else: the admin panel, wiki editing, badge tools, user management, the client directory. Every such route needs a test that an emulating admin keeps it and a non-admin is refused.
- `effective_user()` — the emulated user when an admin is viewing as someone else, otherwise the logged-in user. `_get_actor()` / `get_actor()` are local names for it. DI keeps a parameterised variant `_effective_role_user(user)` on purpose.
- **Emulation exception — the Friction Log.** Posting and deleting there act as the emulated person, as in the chat tray. No capability gates posting (everyone signed in may); deleting is the author's own post, or any post with `manage_feedback`.
- Jinja globals `can(cap)`, `org` (the branch checks, e.g. `org.is_designer(current_user)`), `role_labels` and `role_label`.

## The map

**Departments** (`DEPARTMENT_CAPABILITIES`):

| Department | Capabilities |
|---|---|
| `client_servicing` | view_workspace, view_cs, view_finance, edit_finance, close_projects, view_all_projects, create_projects, review_submissions, edit_client_directory, raise_flags, manage_reference_data, manage_project_files |
| `project_owner` | everything Client Servicing holds **plus** log_site_visits, claim_ownership — owners stand in for CS when CS is stretched |
| `design` | view_workspace, manage_drafts, claim_work, raise_flags, complete_preproduction, start_projects |
| `finance` | view_workspace, view_cs, view_finance, edit_finance |
| `digital_innovation` | view_workspace, view_all_di |
| `hse` | view_hse, manage_hse — **no `view_workspace`**: the officer sees the HSE module, File Storage and the Wiki, nothing else (`test_hse_sidebar.py` pins it) |
| `hr` | `_READ_ONLY_STAFF` **plus view_hse** — reads HSE (injuries and lost time are HR's concern too), which also puts HR in the HSE report-email recipients |
| `production` / `logistics` | `_READ_ONLY_STAFF` minus view_cs: view_workspace, view_finance, view_all_projects, edit_client_directory |

**Seniority** (`SENIORITY_CAPABILITIES`) adds to the department's set:

| Seniority | Adds |
|---|---|
| none, manager | nothing yet |
| head | view_department_overview |
| management | view_workspace, view_cs, view_finance, edit_invoicing_thresholds, close_projects, view_all_projects, manage_projects, create_projects, start_projects, review_submissions, edit_client_directory, raise_flags, manage_flags, log_site_visits, manage_reference_data, complete_preproduction, manage_project_files, switch_dashboard_scope, view_team_snapshot, view_department_overview, view_management_dashboard, view_di_performance, view_all_di, view_hse, view_time_reports |

- A Management person inside a department holds both sets (e.g. Design + Management also has drafts and claim work).
- **`view_workspace`** is the broad "can use the main app" capability held by every department but HSE. It is the gate to reach for on a data endpoint behind an already-gated page (CONVENTIONS.md → *Gate the endpoints*), rather than inventing a narrower one.
- **`view_finance`** is held by every department with `view_cs`, so everyone who can open Client Servicing sees its figures. Editing them is `edit_finance`. The gate stays in code for any future CS department without it.
- **`view_hse` doubles as the HSE email recipient list** (`hse/lib/share.py::recipients`). Anyone who should receive the reports must be able to open the link in them, so the two are one capability on purpose.
- Designers and design leads hold the same capabilities. What separates them is seniority and the team a deliverable belongs to — a per-record rule, never a capability.
- Admin-only capabilities are listed in `ADMIN_ONLY`: admin_panel, manage_users, manage_wiki, manage_blog, manage_feedback, manage_achievements, manage_scopes, manage_di_templates, override_status, edit_di_board, toggle_project_hold. Granting one to a department or seniority means editing two places on purpose.
- **Dashboard gates:** `view_department_overview` (Head of Department and Management) opens the department pages (Design workload, Needs attention); which one is picked by department on the rail. `view_management_dashboard` (Management) opens the Management rail's own pages. Admin system pages reuse `admin_panel` with `real_user=True`.
- **Coming with 2.7:** `raise_escalation`, `decide_escalation`, `nudge`, `view_adoption`.

### `start_projects` — who moves a project off Briefed
Held by **Design, Management and admin** only. CS deliberately does not — the people who do the work decide when it starts. A pure capability with no relationship half: any designer can start any project. If that needs tightening, `_is_assigned_designer` in `details.py` is the helper to combine it with (mind the branch-selector trap).

## Adding a department
1. One key in `org.DEPARTMENTS` (label, picker order).
2. One key in `DEPARTMENT_CAPABILITIES` with its set. Decide whether it holds `view_workspace`.
3. Its sidebar row in `lib/sidebar.py::HIDDEN_LINKS` if it doesn't need every link.
The account forms and the Accounts list render from these. Check `dashboard/lib/project_loader.py::scope_query` — a department holding `view_all_projects` sees the full active list, one without it gets an empty dashboard by design.

## The role-key bridge
`User.role` is no longer stored. It is worked out from department + seniority + admin (`org.legacy_role_for`), in Python and in SQL, and setting it fills those fields from a key (`org.LEGACY_ROLES`). It keeps code not yet on the org model working — user pickers and lists that filter by role, the wiki's "relevant to" roles, profile titles, the dashboard layout choice — and every test fixture written with `role=`. Those move to the org model as each area is rebuilt; nothing new should read `User.role`. The old column survives as `users.legacy_role`, unread, until November.

## Four kinds of check — keep them apart
1. **Gate** — can you reach this at all? `can()` / `@require`.
2. **Scope** — which records do you see? A capability, applied as a query filter, not a door.
3. **Relationship** — "management **or** the project's owner **or** its CS lead". The map answers only the department/seniority half; ownership stays in code: `can('manage_projects', actor) or actor.id == project.project_owner_id`.
4. **Grant** — a per-person exception the map can't express: a join table owned by the feature (per-person DI board visibility, after October). Never in the map. The pattern is *gate OR grant*.

Two more that look like gates and are not: checks about **another** person (validation, e.g. "the new CS lead must be in CS"), and the **branch selector** below.

## State gates — not an access question at all
What the record's own state allows, regardless of who is asking. Admin's wildcard does not open these. Reference: `submissions_blocked_reason(project)` in `project_overlay/_common.py` — a `briefed` project takes no submission work until Start Project; every Submissions write route returns **409**, not 403. The gate has one definition and the UI reads it too (`submissions_open`); the grandfather clause is self-sealing (only a project that already carries a submission is exempt, and creating one is what's blocked).

## The branch-selector trap
Admin holds every capability. Where a check selects a branch that admin is *deliberately outside of* — the designer's self-claim path, the designer's default focus, the notification toggles a person can receive — `can()` would hand admin that branch. Those checks go through `lib/org.py` instead: `is_designer`, `is_design_lead`, `is_plain_designer`, `is_cs`, `is_project_owner`, `is_department_head`, `is_leadership`, `is_admin`. Admin and Management always take the company-wide branch, never a department's, so `is_designer()` is False for a Management person in Design. Each call site carries a short comment saying why it is not `can()`.

## Where the CS review lock lives
`can_access_client_servicing()` in `client_servicing/lib/access.py` = `can('view_cs', user)` plus the `CLIENT_SERVICING_REVIEW_ONLY` narrowing (off by default). CS routes gate through `@require_cs`; `can()` stays a pure map lookup.

## The contract test
`core/shared/tests/test_capabilities_contract.py` fails if any module imports the retired `role_required` or hand-rolls `admin_required`; declares a local `_ROLES` set (three allowlisted by name, including `LEGACY_ROLES`); or introduces a **new `.role`, `.department` or `.seniority` comparison not in the baseline** `core/shared/tests/role_literal_baseline.txt`. The baseline holds the bridge's SQL expression in `models/users.py`. Branch checks belong in `lib/org.py`, which reads the fields through `getattr`. Generator and test share one definition in `core/shared/tests/role_literals.py`; after an intentional change run `python generate_role_literal_baseline.py` and commit the baseline with it.

Other guards: `test_org_capabilities.py` writes out every role key's access in full and checks `can()` for every capability (the only allowed change is Project Owners gaining CS); `test_org_model.py` checks the bridge and that each branch check matches the old role keys; `test_capabilities.py` pins that HR matches Production and Logistics apart from `view_hse` and `view_cs`.

## Loose ends
- `_tab_strip.html`'s label list is narrower than `view_all_projects`: a project owner gets the all-projects query but the "Team Projects" label. Pre-existing; left alone.
