# client_servicing

The Client Servicing page: the CS team's master sheet, digitised. It's the
same projects the rest of the app already has, seen through a commercial
lens — a second, inline-editable table over existing `Project` rows plus a
1:1 companion row for the CS-only fields. Its own page and sidebar section,
not part of the Projects page; what it shares is the underlying project
records, so a shared field edited here also changes on the Projects page and
dashboard.

## Structure
```
app/modules/client_servicing/
  models.py                 # ClientServicing (1:1 companion), ClientServicingScope, ClientServicingSetting
  lib/
    access.py               # can_access_client_servicing + emulation-aware _effective_user
    summary.py              # Monthly Summary rollup (computed live, nothing stored)
  routes/
    blueprint.py            # the client_servicing blueprint (url_prefix /client-servicing)
    table.py                # table page + live-refresh rows partial, row serialize, shared draft-excluding query
    edit.py                 # PATCH one cell — the single field-update endpoint (CS + finance fields)
    layout.py               # save per-user column widths/order (shared UserTableLayout)
    scopes_admin.py         # CS Scope option-list CRUD + inline quick-add
    calendar.py             # Calendar section (placeholder)
    invoicing.py            # Invoicing section — By Project + Monthly Summary tabs, thresholds endpoint
  templates/client_servicing/
  tests/
```
Routes are split one concern per file. Static: `app/static/js/client_servicing.js`
(table), `app/static/js/client_servicing_invoicing.js` (invoicing edits +
thresholds modal), `app/static/css/client_servicing.css`.

## Architecture
The CS-only and finance fields live on a companion table, never on the shared
`Project`. Everything a CS user edits that also exists on the project (CS lead,
owner, job number, value, deadlines, SPOC) is written to the same project
record — one source of truth, not a copy that drifts. Draft projects are
excluded everywhere in the module via the shared `table.py::_base_projects()`
(`project_status != 'draft'`) — a draft isn't a real project yet.

## Data model
- **`ClientServicing`** — 1:1 with a project (`project_id` unique, `ON DELETE
  CASCADE`).
  - CS fields: `lpo`, `store_location`, `removal_date`, `invoice_month`,
    `cost_to_client` / `inward_cost` (`Numeric(12,2)`), `scope_id`, `priority`.
  - Finance fields: `lpo_date`, `project_value` (`Numeric(12,2)`, the
    sell/quotation value — separate from `Project.value`), `invoice_number`,
    `invoice_date`, `invoice_amount` (`Numeric(12,2)`), `gr_received` /
    `invoice_uploaded` (bool), `validation_status` (`valid` / `pending` /
    `no_lpo` / `overdue`).
  - Derived, never stored: `margin_percent` (`(cost_to_client - inward_cost) /
    cost_to_client × 100`, `None` if either cost missing or zero); `days_pending`
    (days since `invoice_date` if invoiced, else `removal_date`, else `None`).
- **`ClientServicingScope`** — the CS team's own scope option list (`name`,
  `active`), separate from the projects module's `Scope`. Deactivate, don't
  delete: existing rows keep their scope, the option drops from future picks.
- **`ClientServicingSetting`** — single settings row; currently the Days Pending
  colour thresholds (`days_green_max` 30, `days_red_max` 60). `current()` returns
  a transient default when none is saved.

Migrations: `add_client_servicing_tables.py`, `add_client_servicing_invoicing_fields.py`,
`add_client_servicing_settings.py` (run directly, not Alembic).

## Access
`lib/access.py` is the single gate — every route calls
`can_access_client_servicing(_effective_user())`, never an inline role check.
Page-access roles: admin, management, cs, project_owner, finance. Editing the
**finance fields** is further restricted to **admin / cs / finance**
(`_FINANCE_EDIT_ROLES` in `edit.py`) — narrower than page access, so
management/project_owner can view them but not edit. Editing the **day
thresholds** is admin/management only. `_effective_user()` is emulation-aware,
so an admin previewing as someone else is gated, has their layout saved, and
has edits attributed as that person; the admin-only Scope CRUD stays on
`current_user` so real admin tools survive a preview.

## Routes (blueprint prefix `/client-servicing`)
- `GET /` — the table page. `GET /table-rows` — the rows partial for live refresh.
- `PATCH /<project_id>` — update one cell: `{field, value}` (CS + finance fields).
- `POST /layout` — save this user's column widths/order.
- `GET|POST /scopes`, `PATCH /scopes/<id>`, `POST /scopes/quick-add` — scope CRUD + inline add.
- `GET /invoicing` — By Project finance table. `GET /invoicing/summary?year=&month=` — Monthly Summary.
- `POST /invoicing/day-thresholds` — save the Days Pending thresholds (admin/management).
- `GET /calendar` — placeholder.

## The table
Reuses the projects-table patterns: the shared `UserTableLayout` model
(`table_key = 'client_servicing:table'`) for per-user column widths/order,
data-driven columns, client-side click-to-sort (no server round-trip, no saved
sort), column resize/reorder, a sticky Project-name column, and an "Open in
Projects" button per row that deep-links to that project's overlay
(`?project=<id>`). No project overlay here — every cell is edited in place.

## Cell editing (`edit.py`)
One endpoint, `PATCH /<project_id>` with `{field, value}`. It resolves the
effective user, gates access (finance fields additionally gated to
admin/cs/finance), then routes by field:
- **CS + finance fields** — parsed/validated per field and written straight to
  the project's `ClientServicing` row; the response carries the recomputed
  margin. Finance fields are plain columns — no writeback, no notifications.
- **Writeback fields** — routed through `app/modules/projects/services/
  mutations.py` (see below), never a raw column write.
- Anything else is rejected as not editable here.

Edit scope:
- **Read-only mirror** (edit via the Projects page): Client Name, Project Name,
  Project Brief Date, Lead Designer(s), Client Approval, Status.
- **Editable → writes back to the project**: Job No, CS Lead, Project Owner,
  Client SPOC, Installation Date, Project Value, Due Date.
- **CS-only**: Scope, LPO, Store/Location, Removal Date, Invoice Month, Cost to
  Client, Inward Cost; Margin (computed); Priority.
- **Finance** (admin/cs/finance): LPO Date, Project Value, Invoice No./Date/
  Amount, GR, Invoice Uploaded, Validation Status.

## Writeback + notifications
`app/modules/projects/services/mutations.py` is the projects module's public
write path: `reassign_cs_lead`, `set_project_owner`, `save_detail_field` (job
number, SPOC, installation date, value, due date). It does the commit,
activity-log entry and notifications, so a change made here produces the same
history as the same change on the Projects overlay — the overlay delegates to
it too, so there is one implementation. Callers do their own permission checks
first.

## Invoicing (`invoicing.py`, `lib/summary.py`)
Two tabs behind an in-page strip; drafts excluded from both.

- **By Project** (`GET /invoicing`) — a fixed-column finance table over the
  same projects, with the finance columns in an "Invoicing — Master Control"
  band. Finance cells are inline-edited (text/date/number, a GR toggle, a
  validation dropdown) via the shared `PATCH /<project_id>`. Days Pending is a
  badge coloured by the configurable thresholds; no anchor date → a muted dash.
- **Monthly Summary** (`GET /invoicing/summary?year=&month=`) — computed live,
  nothing stored. Four KPI cards for the selected month, a 12-month rollup
  (pipeline / confirmed / invoiced / progress / stuck + FY total), and a
  "due this month" list of that month's uninvoiced projects. Each project is
  bucketed by billing month (invoice date › removal date › due date); Pipeline
  = Σ project value, Confirmed = has LPO, Invoiced = Σ invoice amount, Stuck =
  no LPO or overdue/no-LPO validation. Calendar-year window for now.
- **Day thresholds** — green/amber/red day cut-offs in `ClientServicingSetting`,
  edited by admin/management from a toolbar button + modal. The toolbar's
  search / month & validation filters / Export are present but not yet wired.

## Scope option list
CS-managed. Users add options inline from the Scope dropdown (`/scopes/quick-add`);
admins manage the full list from the "CS Scopes" tab in the Admin Panel
(`scopes_admin.py`), mirroring the Design Types/Directions tabs.

## Demo data
`seed_invoicing_demo.py` (repo root) wipes and reseeds tagged dummy data for
manual testing — demo users (`@invdemo.local`), clients/projects (`Demo — `),
finance rows spread across the year, plus a hidden draft. Marker-scoped, so it
never touches real data; `--wipe` clears only. Not the real importer.

## Sections
Sidebar shell: **Table** and **Invoicing** (both built), **Calendar**
(placeholder). The module's entry in the global app sidebar is currently a
disabled (greyed) `<span class="sidebar-item sidebar-item--unlinked">`; to
enable, swap it back for `<a href="{{ url_for('client_servicing.index') }}"
class="sidebar-item sidebar-item--nav">`.

## Remaining scope
- **Invoicing toolbar** — search, month/validation filters and Export are
  visual only; not wired.
- **Calendar** — real content; scope not yet defined.
- **Data import** — mapping the real master spreadsheet to `Project` +
  `ClientServicing` (matching/creating projects, handling non-matching rows).
  Not built; `seed_invoicing_demo.py` is the pattern to adapt.
