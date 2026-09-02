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
  models.py                 # ClientServicing (1:1 companion) + ClientServicingScope
  lib/access.py             # can_access_client_servicing + emulation-aware _effective_user
  routes/
    blueprint.py            # the client_servicing blueprint (url_prefix /client-servicing)
    table.py                # table page + live-refresh rows partial, row serialize, column layout read
    edit.py                 # PATCH one cell — the single field-update endpoint
    layout.py               # save per-user column widths/order (shared UserTableLayout)
    scopes_admin.py         # CS Scope option-list CRUD + inline quick-add
    calendar.py             # Calendar section (placeholder)
    invoicing.py            # Invoicing section (placeholder)
  templates/client_servicing/
  tests/
```
Routes are split one concern per file. Static: `app/static/js/client_servicing.js`,
`app/static/css/client_servicing.css` (served from the global loader).

## Architecture
The CS-only fields live on a companion table, never on the shared `Project`.
Everything a CS user edits that also exists on the project (CS lead, owner,
job number, value, deadlines, SPOC) is written to the same project record —
so there is one source of truth, not a copy that drifts.

## Data model
- **`ClientServicing`** — 1:1 with a project (`project_id` unique, `ON DELETE
  CASCADE`). Fields: `lpo`, `store_location`, `removal_date`, `invoice_month`,
  `cost_to_client` / `inward_cost` (`Numeric(12,2)`), `scope_id`, `priority`.
  `margin_percent` is a derived property — `(cost_to_client - inward_cost) /
  cost_to_client × 100`, `None` when either figure is missing or cost is zero.
  Never stored.
- **`ClientServicingScope`** — the CS team's own scope option list (`name`,
  `active`), separate from the projects module's `Scope`. Deactivating, not
  deleting, keeps existing rows valid while dropping the option from future
  selection.
Migration: `migrations/add_client_servicing_tables.py`.

## Access
`lib/access.py` is the single gate — every route calls
`can_access_client_servicing(_effective_user())`, never an inline role check.
Roles: admin, management, cs, project_owner (`finance` is listed commented-out,
pending that role existing on the User model). `_effective_user()` is
emulation-aware, so an admin previewing as someone else is gated, has their
layout saved, and has edits attributed as that person. The admin-only Scope
CRUD stays on `current_user` so real admin tools survive a preview.

## Routes (blueprint prefix `/client-servicing`)
- `GET /` — the table page. `GET /table-rows` — the rows partial for live refresh.
- `PATCH /<project_id>` — update one cell: `{field, value}`.
- `POST /layout` — save this user's column widths/order.
- `GET|POST /scopes`, `PATCH /scopes/<id>`, `POST /scopes/quick-add` — scope CRUD + inline add.
- `GET /calendar`, `GET /invoicing` — the two other sections (placeholders).

## The table
Reuses the projects-table patterns: the shared `UserTableLayout` model
(`table_key = 'client_servicing:table'`) for per-user column widths/order,
data-driven columns, click-to-sort (client-side only — a live re-order of the
rows on screen, no server round-trip or saved sort), column resize/reorder,
a sticky Project-name column, and an "Open in Projects" button per row that
deep-links to that project's overlay (`?project=<id>`). No project overlay
here — every cell is edited in place.

## Cell editing (`edit.py`)
One endpoint, `PATCH /<project_id>` with `{field, value}`. It resolves the
effective user, gates access, then routes by field:
- **CS-only fields** (`lpo`, `store_location`, `removal_date`, `invoice_month`,
  `cost_to_client`, `inward_cost`, `scope_id`, `priority`) — parsed/validated
  per field and written to the project's `ClientServicing` row; the response
  carries the recomputed margin.
- **Writeback fields** — routed through `app/modules/projects/services/
  mutations.py` (see below), never a raw column write.
- Anything else is rejected as not editable here.

Edit scope:
- **Read-only mirror** (edit via the Projects page): Client Name, Project Name,
  Project Brief Date, Lead Designer(s), Client Approval, Status.
- **Editable → writes back to the project**: Job No, CS Lead, Project Owner,
  Client SPOC, Installation Date, Project Value, Due Date (the project's
  `first_output_deadline`).
- **CS-only**: Scope (its own list), LPO, Store/Location, Removal Date, Invoice
  Month, Cost to Client, Inward Cost; Margin (computed, read-only); Priority
  (free text, not linked to the project's urgency).

## Writeback + notifications
`app/modules/projects/services/mutations.py` is the projects module's public
write path: `reassign_cs_lead`, `set_project_owner`, and `save_detail_field`
(job number, SPOC, installation date, value, due date). It does the commit,
activity-log entry and notifications, so a change made here produces the same
history and notifications as the same change made in the Projects overlay —
the overlay's own routes delegate to it too, so there is a single
implementation. Callers do their own permission checks first. Due-date,
job-number and SPOC changes notify designers / secondary CS / owner as
appropriate; CS-lead and owner changes notify through the same path the
overlay uses.

## Scope option list
CS-managed. Users add options inline from the Scope dropdown (`/scopes/quick-add`);
admins manage the full list from the "CS Scopes" tab in the Admin Panel
(`scopes_admin.py`), mirroring the Design Types/Directions tabs.

## Sections
The sidebar shell has three: **Table** (built), **Calendar** and **Invoicing**
(real, clickable placeholder pages, content not yet built).

## Remaining scope
- **Invoicing** — real content. The finance fields deliberately kept off the
  table land here: LPO/PO Number, LPO Date, Invoice #/Date/Amount, Collected
  Amount, Collection Date, Days Pending, GR, Invoice Uploaded, Validation Status.
- **Calendar** — real content; scope not yet defined.
- **Data seeding** from the master spreadsheet — import not built; needs the
  real sheet (matching rows to existing projects, handling rows that don't match).
- **`finance` role** — add to the User model, then uncomment it in `access.py`
  (plus a migration).
