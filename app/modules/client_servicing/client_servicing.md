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
    access.py               # can_access_client_servicing, can_view_finance, emulation-aware _effective_user
    status.py               # effective_cs_status (manual overlay + derived) + design-stream chips
    calendar.py             # install risk + month/agenda data service
    summary.py              # Monthly Summary rollup (computed live, nothing stored)
    dashboard.py            # Dashboard aggregations (six panels) + module feed items
  services/
    dashboard_feed.py       # feed_for(user) — the module's feed for the global Dashboard
  routes/
    blueprint.py            # the client_servicing blueprint (url_prefix /client-servicing)
    dashboard.py            # Dashboard page — the module landing (GET /)
    table.py                # table page (GET /table) + live-refresh rows partial, shared draft-excluding query
    edit.py                 # PATCH one cell — the single field-update endpoint (CS + finance fields)
    layout.py               # save per-user column widths/order (shared UserTableLayout)
    scopes_admin.py         # CS Scope option-list CRUD + inline quick-add
    calendar.py             # Installation Calendar — Month + Agenda
    invoicing.py            # Invoicing section — By Project + Monthly Summary tabs, thresholds endpoint
  templates/client_servicing/
  tests/
```
Routes are one concern per file. Static (in the module):
`static/js/client_servicing.js` (table inline-edit, sort, search + filter),
`static/js/client_servicing_dashboard.js` (dashboard SSE refresh),
`static/js/client_servicing_calendar.js`, `static/js/client_servicing_invoicing.js`,
`static/css/client_servicing.css` (table, calendar, dashboard, toolbar).

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
thresholds** is admin/management only. Viewing **finance on the Dashboard**
(money KPIs, Invoicing Health, feed finance items) is gated by
`can_view_finance` — admin / management / cs / finance; project_owner can open
CS but doesn't see finance there. `_effective_user()` is emulation-aware,
so an admin previewing as someone else is gated, has their layout saved, and
has edits attributed as that person; the admin-only Scope CRUD stays on
`current_user` so real admin tools survive a preview.

## Routes (blueprint prefix `/client-servicing`)
- `GET /` — **Dashboard** (the module landing). `GET /dashboard-panels` — panels fragment for the dashboard's SSE refresh.
- `GET /table` — the table page. `GET /table-rows` — the rows partial for the table's live refresh.
- `PATCH /<project_id>` — update one cell: `{field, value}` (CS + finance fields).
- `POST /layout` — save this user's column widths/order.
- `GET|POST /scopes`, `PATCH /scopes/<id>`, `POST /scopes/quick-add` — scope CRUD + inline add.
- `GET /invoicing` — By Project finance table. `GET /invoicing/summary?year=&month=` — Monthly Summary.
- `POST /invoicing/day-thresholds` — save the Days Pending thresholds (admin/management).
- `GET /calendar` — Installation Calendar (Month + Agenda).

## Dashboard (`routes/dashboard.py`, `lib/dashboard.py`)
The module landing (`GET /`) and first rail entry — the daily-standup "where
does everything stand" view. Read-only, no new models: one eager-loaded
`_base_projects()` fetch, composed from the existing helpers so numbers can't
drift from the Table / Calendar / Invoicing pages.

Six panels:
- **KPI band** — Active · Installs (month) · Next 7 days · At Risk · Pipeline · Stuck.
- **Urgent Actions** — at-risk/attention installs + finance items (LPO / overdue / unbilled) + data gaps; each row deep-links (Calendar / Invoicing / Open in Projects). Scrolls internally.
- **Status Spread** — active count per lifecycle family (segmented bar + legend).
- **Upcoming Installs** — next installs, risk dot + relative day. Scrolls internally.
- **Invoicing Health** — month pipeline / confirmed / invoiced + progress + stuck count/amount.
- **CS Lead Workload** — active + at-risk count per lead.

- **Finance gating** — the Pipeline/Stuck KPIs, Invoicing Health, and finance rows in Urgent Actions show only to `can_view_finance` roles.
- **Module feed** — `services/dashboard_feed.py::feed_for(user)` exposes the cross-cutting subset (upcoming installs + finance items) for the future global Dashboard — same computation as the panels, one source. Empty for no-access users; finance items hidden from non-finance.
- **Layout** — role tokens, light + dark; the two list panels scroll internally, the page scrolls to the bottom row.
- **Live refresh** — panels live in `_dashboard_panels.html`, re-rendered by `GET /dashboard-panels`. `polling.js` opens `/sse/dashboard` on the `.cs-dash` marker and calls `window.helixRefreshCSDashboard()` (`client_servicing_dashboard.js`), which swaps `#cs-dash-panels`. Same doorbell as the table/calendar.

## Table height

`.cs-table-scroll` is sized so its bottom edge meets the footer, which is what
keeps its horizontal scrollbar on screen. Flexbox cannot do it — `.main-content`
is a flex item with no definite height, so a flex child grows to its content
and the page scrolls instead.

`syncTableScrollHeight()` is now a two-line call into
`core/shared/js/fill_height.js`; the maths moved there when Digital Innovation
and HSE turned out to need the same solve. Its call sites are unchanged, and
`--cs-table-scroll-height` still drives the CSS. If that file ever fails to
load, the CSS `calc()` fallback takes over.

## The table
Reuses the projects-table patterns: the shared `UserTableLayout` model
(`table_key = 'client_servicing:table'`) for per-user column widths/order,
data-driven columns, client-side click-to-sort (no server round-trip, no saved
sort), column resize/reorder, a sticky Project-name column, and an "Open in
Projects" button per row that deep-links to that project's overlay
(`?project=<id>`). No project overlay here — every cell is edited in place.

**Search + filter** (client-side, in `client_servicing.js`) — a toolbar above
the table: a search box (client / project / job no) and a Filter panel of chips
(Client, CS Contact, Project Owner, Status, Scope, Priority). Options and
faceted counts are built from the loaded rows, so they always match what's in
the table. Filtering hides rows and re-runs the sort, and re-applies after each
live refresh — no server round-trip. CSS is module-local (`cs-toolbar` /
`cs-filter-*` / `cs-chip`).

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
Sidebar shell, in order: **Dashboard** (landing) · **Table** · **Invoicing** ·
**Calendar** — all built. Opening CS lands on the Dashboard. The global
app-sidebar entry is a live link pointing at `client_servicing.index`.

Internal nav between the four sections is SPA soft-nav:
core/shared's `module_rail.js` routes `.module-rail-item` clicks through the
app's `window.navigateTo`. The global `sidebar.js` only intercepts its own
`.sidebar-item--nav`, so the shared rail SPA-ifies itself for every module that
uses it. The listener is document-delegated and
guarded (`_csNavDispatcherWired`), so it survives SPA swaps without stacking.

## Remaining scope
- **Invoicing toolbar** — search, month/validation filters and Export are
  visual only; not wired.
- **Data import** — mapping the real master spreadsheet to `Project` +
  `ClientServicing` (matching/creating projects, handling non-matching rows).
  Not built; `seed_invoicing_demo.py` is the pattern to adapt.
