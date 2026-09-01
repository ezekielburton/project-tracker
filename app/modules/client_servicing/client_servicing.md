# client_servicing

The CS team's master sheet, digitised: one table over the same projects the
Projects page shows, on its own page. Read-only columns mirror the project
and are edited via an "Open in Projects" link; a set of shared columns will
write back to the project through the existing project services; a set of
CS-only columns live only here. No project overlay — every cell edits in
place (editing itself is a later chunk; this page is read-only for now).

## Structure
```
app/modules/client_servicing/
  models.py                    # ClientServicing, ClientServicingScope
  lib/access.py                 # can_access_client_servicing(user)
  routes/blueprint.py            # client_servicing_bp, url_prefix /client-servicing
  routes/table.py                 # index + table_rows routes, row serializer
  templates/client_servicing/index.html        # page shell
  templates/client_servicing/_table_rows.html   # the table (header+rows); also the
                                                  # live-refresh fragment
  tests/test_client_servicing_models.py
  tests/test_client_servicing_routes.py
  client_servicing.md
```
Front end: `app/static/css/client_servicing.css`, `app/static/js/client_servicing.js`
(module static/ folders aren't split out yet app-wide — see core.md's Known
follow-ups — so these live alongside every other module's, like the rest of
the app currently does).

## Data model
See models.py / the migration for the schema — unchanged from Chunk 1.

## Access
`lib/access.py::can_access_client_servicing(user)`, gated on
`{'admin', 'management', 'cs'}` — one line to widen when CS gets its own
role. Every route in this module calls it and aborts 403 if it fails.

## The table view (Chunk 2)
- `GET /client-servicing/` — the page. `GET /client-servicing/table-rows` —
  the same table fragment, used for the live SSE refresh.
- Row data comes straight from `Project` (eager-loaded: cs_lead,
  project_owner, client_brand, assigned_designers, client_servicing+scope)
  plus a bulk contact lookup and `bulk_project_client_approved_at()` — no
  N+1 queries. Status column reuses `derive_project_status()`
  (core/shared/lib/status_vocabulary.py) so it never drifts from the
  Projects page's own status logic.
- Live refresh reuses the existing `/sse/dashboard` doorbell (the same one
  the Projects list uses) — no new SSE channel needed since every row here
  is still just a `Project`. Wired into `app/static/js/polling.js` next to
  its `_projectTableStream` block; the actual refresh is
  `window.helixRefreshClientServicingTable()` in `client_servicing.js`.
- "Open in Projects" is a `.btn-secondary` link per row to
  `/projects-new/?project=<id>` (the existing deep-link that auto-opens
  that project's overlay).
- Sidebar entry added to `base.html`, Internal Tools, right after Projects.

**Deliberately deferred, not built yet:** column drag-resize/reorder
(`UserTableLayout` + a `project_list_layout.js`-style script) and
interactive click-to-sort. The Projects page's resize/reorder script is
tightly wired to its own DOM ids, not a drop-in-reusable component, so
copying it blind felt like the wrong risk for a chunk with no live
verification available (this sandbox can't reach Ezekiel's local Postgres).
Table is fixed-column, sorted alphabetically by project name for now — a
quick, well-scoped follow-up once this chunk is confirmed working.

## Cell editing (Chunk 3)
CS-only fields only, in place, no overlay/modal anywhere — click a
`.cs-editable` td, it turns into the right input (select for Scope, date/
month/number/text otherwise), saves on blur via
`PATCH /client-servicing/<project_id>` (`routes/edit.py`). That endpoint
whitelists exactly the 8 CS-only fields, type-checks the value, creates the
project's `ClientServicing` row on first edit if it doesn't exist yet, and
returns the recomputed `margin_percent` so the Margin cell updates too on a
cost edit. Writeback fields (job number, CS lead, project owner, SPOC,
installation date, value, due date) now edit too — see Chunk 4 below.
Click handling is delegated on `#client-servicing-table-body` so it
survives the live-refresh swap without rebinding.

## Writeback fields (Chunk 4)
Job No, CS Contact (CS Lead), Project Owner, Client SPOC, Installation
Date, Project Value, Due Date now edit in place too, same as the CS-only
fields — same `.cs-editable` mechanism, same `PATCH
/client-servicing/<project_id>` endpoint. Under the hood they route
through a NEW file, `app/modules/projects/services/mutations.py` (the
Projects module's own public write path — first services/ folder that
module has had): `reassign_cs_lead()` / `set_project_owner()` reproduce
the exact notification + activity-log shape of the existing
reassign-cs-lead / set-project-owner routes; `save_detail_field()` covers
the other five (job_number, contact_id, installation_date, value,
first_output_deadline), each validated, uniqueness-checked where it
matters (job number, SPOC must belong to the project's own client), and
logged to ActivityLog the same way a Details-tab edit is.

Deliberate choice: the existing Projects-overlay routes for these were
left completely untouched (zero risk to a live, working feature) — the
new service functions are net-new and produce the same *effects*
(notifications, activity log, and SSE — which fires automatically for
any Project change via the existing generic hook) without editing any
live route file. Permission is `can_access_client_servicing` (any
CS/management/admin), deliberately broader than the Projects overlay's
own per-project checks — Ezekiel confirmed this table should be editable
by any CS person, not just a project's own assigned lead/owner, since
it's a collaborative sheet.

Cosmetic gap, not a bug: after editing CS Lead or Project Owner, the cell
briefly shows plain text instead of the avatar chip until the next
refresh (SSE ping or reload) — flagged, not hidden.

Tests: `tests/test_client_servicing_writeback.py` — any CS user (not just
that project's own lead) can reassign CS lead; target-role validation;
owner-reassignment notifies; due date saves; job number uniqueness;
SPOC must belong to the project's client; negative value rejected.

## Notifications (Chunk 5 — VERIFIED DONE)
Due Date / Job No / Client SPOC changes now notify, same place the writes
happen — `save_detail_field()` in `app/modules/projects/services/mutations.py`
dispatches to a small `_notify_*` helper per field right after the commit,
only when the value actually changed (existing no-op-on-unchanged guard
covers this for free). Recipients:
- Due Date → the project's assigned designers + secondary CS + Project
  Owner (it's the final design deadline, so designers need it too).
- Job No / Client SPOC → secondary CS + Project Owner.
The actor never notifies themselves; `_dedupe()` collapses someone who's
both secondary CS and the owner into a single notification. Three new
`pref_key`s (`due_date_changed`, `job_number_changed`,
`client_spoc_changed`) added to the Account page's email-notification
toggle list, gated to the roles who'd actually receive each one.
CS Lead / Project Owner reassignment already notified as of Chunk 4 — no
change needed there.
Tests added to `tests/test_client_servicing_writeback.py`: due date
notifies designer+secondary CS+owner but not the actor; an unchanged due
date notifies no one; job number and Client SPOC each notify secondary
CS+owner; a dual secondary-CS/owner gets exactly one notification.

## Inline add + Scope admin (Chunk 6 — VERIFIED DONE, 38/38 tests)
Client SPOC and Scope cells both get a "+ Add new..." option appended
client-side to their select. Picking it swaps the select for a tiny
inline name field + Add/Cancel — same td, no overlay
(`startQuickAdd()` in `client_servicing.js`) — then saves the new
record's id through the normal edit path once created.
- Client SPOC → posts to the client_directory module's existing
  `POST /directory/clients/contacts` (already gated admin/management/cs).
  No new backend route.
- Scope → posts to a NEW `POST /client-servicing/scopes/quick-add`.
  Idempotent (returns the existing scope if the name's taken) and
  reactivates a deactivated scope on re-add, since handing back an
  inactive id here would be a dead end — `edit.py`'s `_parse_scope_id`
  only accepts active scopes.

Admin management of the Scope list is a NEW file,
`app/modules/client_servicing/routes/scopes_admin.py` — list/create
(409 on duplicate)/rename (409 on duplicate)/deactivate, admin-only via
`role_required('admin')`, registered on this module's own
`client_servicing_bp` at `/client-servicing/scopes*`. Deactivate, not
delete — `ClientServicingScope.active` is the flag `_scope_options()`
(table.py) and `_parse_scope_id` (edit.py) already filter on, so a
deactivated scope drops out of future selection without breaking a row
that already has it.

Deliberately kept this logic inside client_servicing rather than in
`admin.py` — admin.py managing a client_servicing-owned model would have
been the exact cross-module reach the modular philosophy says to avoid
(same reasoning as Chunk 4 putting the writeback logic in a new
`projects/services/mutations.py` instead of reaching into
project_overlay). `base.html` and `admin.js` still get touched — a new
"CS Scopes" tab next to Design Types/Directions in the Admin Panel's
Projects section — but that shared UI just calls
`/client-servicing/scopes*`; it's the trigger, not where the logic lives.

Tests: `tests/test_client_servicing_scopes_admin.py` (new) — full CRUD is
admin-only even for a cs-role user who can otherwise use the whole table;
duplicate name rejected on create and rename; deactivate/reactivate;
quick-add works for cs/management/admin and rejects a designer;
quick-add is idempotent; quick-add reactivates a deactivated scope. Plus
one test in `test_client_servicing_routes.py` confirming a deactivated
scope drops out of the scope-picker options while still displaying on a
row that already has it.

## Avatar chip fix (Chunk 7, part 1 — BUILT, not yet verified)
The Chunk 4 cosmetic gap (CS Lead/Project Owner cell showing plain text
right after an edit instead of the avatar chip) is fixed: `edit.py`'s
`update_field()` now returns a `person` object (id/name/avatar_filename,
via `table.py`'s existing `_serialize_person()`) alongside `value` for
`cs_lead_id`/`project_owner_id` saves; `client_servicing.js`'s new
`renderPersonChip()` builds the same `.person-chip` markup the
`person_chip()` Jinja macro renders server-side, so the cell shows the
real chip immediately instead of waiting for the next SSE refresh. Two
tests added to `test_client_servicing_writeback.py`.

## Column resize/reorder + sort — Piece 1: data-driven columns (Chunk 7 — BUILT, not yet verified)
Foundation piece, no visible behaviour change (verified with standalone
Jinja renders against fabricated rows, both empty-state and full-data,
comparing output against every value the old hardcoded markup produced).
- NEW `templates/client_servicing/_columns.html` — one macro per column
  (`cell_client`, `cell_job_number`, ...), each the exact same `<td>`
  markup that used to be inline in `_table_rows.html`. This file only
  answers "how do I render column X" — never "which columns, in what
  order".
- `_table_rows.html` rewritten to loop over a `columns` list (from
  table.py), dispatching to the right macro via a key→macro dict built
  in the template. The pinned "Open in Projects" column stays hardcoded
  first, same as the Projects page's own Expand column — never
  reorderable or resizable.
- `table.py` gains `COLUMNS` (the 22 reorderable columns, in today's
  order — key matches the macro name and, for editable ones, the
  existing `data-field`) and passes it as `columns` through
  `_page_context()`, so both `index()` and `table_rows()` render from it.

This is what makes resize/reorder possible next without a wholesale
rewrite: order and width become data (per-user, later read from
`UserTableLayout` — same model + `table_key` pattern the Projects page
already uses, table_key `client_servicing:table`), not something baked
into the template. Chosen over converting the table to a CSS-grid layout
(what the Projects page does) — that would have let reordering happen
via CSS custom properties alone, but at the cost of rewriting this
module's whole table markup/CSS; sticking with a native `<table>` and
computing column order server-side is more surgical and lower-risk, at
the cost of the server needing to know the user's saved order at render
time (already true here, since every refresh already re-renders the
whole table server-side).

Next pieces (same chunk, delivered separately for review): resize
(drag a `<th>` edge, save width), reorder (drag a `<th>`, save order),
click-to-sort. All three share one new `POST /client-servicing/layout`
route and the `UserTableLayout` model — no schema changes needed, that
table already exists and is used exactly this way by Projects.

## Column resize — Piece 2 (Chunk 7 — BUILT, not yet verified)
- NEW `POST /client-servicing/layout` (`routes/layout.py`) — validates
  `{table_key, layout}` (layout = list of `{key, width}`), upserts one
  `UserTableLayout` row per (user, `TABLE_KEY='client_servicing:table'`).
  Own route rather than reusing the Projects page's generic `/layout`
  endpoint — same reasoning as Chunks 4 & 6: `UserTableLayout` is a
  core/shared model, writing to it belongs in the module that owns the
  table, not routed through another feature module's blueprint.
- `table.py`'s `_page_context()` now also reads the current user's saved
  widths (`_column_widths()`) and passes them as `column_widths`
  (`{key: px}`) alongside `table_key`.
- `_table_rows.html` gained a `<colgroup>` — one `<col>` per column, with
  an inline `width` for any column the user has actually resized (an
  untouched column has no width and keeps auto-sizing to its content, so
  nothing changes for a user who's never dragged anything). The pinned
  "Open in Projects" column has no `<col data-col-key>` and is never
  resizable, same as it's never reorderable.
- `client_servicing.js`: a `mousedown` handler delegated on
  `#client-servicing-table-body` (not the `<table>` itself or individual
  handles — the whole table is replaced wholesale on every live refresh,
  same reasoning as the existing click-to-edit handler) drives the drag,
  clamped to a 60px floor, debounce-saving the full current widths 400ms
  after the drag ends.
- Deliberately kept `table-layout: auto` (content-based sizing) rather
  than switching to `table-layout: fixed` — fixed would need an explicit
  starting width for all 22 columns to avoid every one collapsing to
  its narrowest content, which is a bigger, riskier CSS change than this
  piece needs. With `auto`, a resized column gets a real target width but
  can still grow if its content genuinely doesn't fit — narrowing a
  column below its content's natural width may not always visually
  "stick" the way a spreadsheet's fixed-width columns do. Worth trying
  live before deciding whether `table-layout: fixed` is worth the extra
  risk as a follow-up polish.
- Known edge case, not specially handled: an SSE refresh landing mid-drag
  swaps in a new `<table>`; the drag keeps updating the now-detached old
  one and the save still fires against it. Rare (refreshes are
  infrequent) and low-stakes (worst case, one resize doesn't stick and
  the user just drags again).
- Tests: `tests/test_client_servicing_layout.py` (new) — access gating;
  create vs. update-in-place on a second save; malformed payloads
  rejected; saved widths actually appear in the rendered `<colgroup>`;
  one user's saved widths don't leak into another user's page.

## Sticky horizontal scrollbar (Chunk 7, feedback from the resize try-out)
Ezekiel tried resize live — it works — and flagged that the CS team isn't
technical enough to remember shift+scroll or to hunt for the real
scrollbar at the very bottom of what can be a very long table. Fixed the
same way the Projects page already solves this: a thin scrollbar pinned
to the bottom of the *viewport* (`position: sticky`), not the table,
mirroring `.cs-table-scroll`'s real scroll position bidirectionally.
- `index.html` — new `#cs-sticky-scrollbar` / `#cs-sticky-scrollbar-inner`
  pair, sibling to `.cs-table-scroll` (now `#cs-table-scroll`), outside
  `#client-servicing-table-body` — so unlike the table itself, this
  never gets destroyed by a live refresh.
- CSS — `.cs-sticky-scrollbar` (`position: sticky; bottom: 0;`, its own
  `overflow-x: auto`) — direct port of the Projects page's own
  `.project-table-sticky-scrollbar`, retokened to this module's palette.
- `client_servicing.js` — `syncStickyScrollbar()` keeps the fake bar's
  width matched to the real table's `scrollWidth` and hides it when
  there's nothing to scroll; re-synced after every live refresh (row
  count can change) and after every resize drag (a column's width
  changed, so the table's total width might have too). Bidirectional
  scroll listeners keep the two in lockstep, guarded against feedback
  looping.

## Column reorder — Piece 3 (Chunk 7 — BUILT, not yet verified)
Same native-`<table>` constraint as resize (Piece 2): no CSS-grid trick
available, so reordering means physically moving DOM nodes. Persistence
reuses the exact same `UserTableLayout` row and `/client-servicing/layout`
route as resize — the saved array's element order already *is* the
column order (that was true from Piece 1), so no new storage or route was
needed, only the read side (`_ordered_columns`) and the drag itself.

- `_columns.html` — every one of the 22 `cell_*` macros now stamps
  `data-col-key="<key>"` on its `<td>`, matching the `<th>`/`<col>` that
  already carried it from Piece 1/2. This is what lets the client-side
  drag find and move a given column's cell in every row, not just its
  header.
- `table.py` — `_column_widths()` replaced by three pieces sharing one
  query: `_saved_layout()` (fetches the user's raw saved array once),
  `_ordered_columns(saved)` (reorders `COLUMNS` to match the saved key
  order; a key no longer in `COLUMNS` — e.g. after a future schema
  change — is silently dropped; a `COLUMNS` key missing from the saved
  layout — a brand-new column, or a first visit — is appended at the end
  in its normal default position, so nobody ever loses a column to a
  stale or incomplete save), and `_column_widths(saved)` (now takes the
  already-fetched list instead of querying again). `_page_context()`
  calls `_saved_layout()` once and feeds it to both.
- `client_servicing.js` — new delegated `mousedown` handler on `body`
  (same delegation reasoning as resize: the table is destroyed and
  rebuilt on every live refresh, so listeners live on the stable
  `#client-servicing-table-body` wrapper instead). Explicitly skips
  clicks starting on `.cs-resize-handle` so the two drag types never
  fight each other. A small pixel threshold distinguishes "just clicking
  a header" from "starting a drag." While dragging, `moveColumn()` moves
  the dragged column's `<th>` (thead), `<col>` (colgroup), and every
  row's matching `<td>` (tbody) via `insertBefore`, based on which side
  of the currently-hovered header the cursor is on. On drop, reuses the
  existing (unchanged) `scheduleLayoutSave()` — it already reads order +
  width fresh from the colgroup's live DOM order, so persisting a
  reorder needed zero changes there — and re-syncs the sticky scrollbar.
- CSS — draggable headers get `cursor: grab`; the resize handle sitting
  inside the same `<th>` keeps its own `cursor: col-resize` since a
  child's explicit cursor wins over its parent's directly under the
  pointer, so no conflict. `.cs-th-dragging` dims the header being
  dragged as feedback.
- As with resize: the server render stays the ultimate source of truth.
  These DOM moves are a live preview only — the next full refresh
  re-renders in the saved order via `_ordered_columns()`. Same rare/
  low-stakes edge case as resize if an SSE refresh lands mid-drag.
- Tests: extended `tests/test_client_servicing_layout.py` — a saved
  reordering is reflected in the rendered `<th data-col-key>` order;
  columns missing from a saved (partial) layout are appended afterward
  in their normal default order; a stale/unknown key in a saved layout
  is silently ignored rather than erroring or appearing.

## Sticky Project-name column (Chunk 7, feedback after reorder)
Ezekiel asked for Project to stay pinned on screen while scrolling right,
same as the Projects page's own Name column. Mirrors that exactly —
Projects pins Expand+Name as a pair; here, Open-in-Projects+Project are
the pair:
- `table.py`'s `_ordered_columns()` now forces `project` to index 0 of
  the returned list every time, even if a saved layout has it somewhere
  else (an old save, or a tampered payload) — the sticky CSS assumes
  it's always first, right after the pinned (non-`COLUMNS`) Open column.
- `client_servicing.js`'s reorder-drag excludes `project` entirely — not
  draggable itself, and not a valid drop target for other columns either
  — same treatment `project_list_layout.js` gives its own pinned Name
  column.
- CSS — `th.cs-col-open`/`td.cs-col-open` and `th[data-col-key="project"]`/
  `td[data-col-key="project"]` (element-scoped, not the bare attribute
  selector, so it doesn't also catch the resize-handle `<span>` that
  shares the same `data-col-key`) get `position: sticky`. Open sits at
  `left: 0`; Project's `left` is a CSS custom property
  (`--cs-sticky-project-left`) rather than a hard-coded value, because
  unlike the Projects page's fixed-size icon Expand column, "Open in
  Projects" is a text button with no fixed known width. Header cells for
  both get a higher z-index than body cells so the pinned top-left
  corner always wins the stack when scrolling in both directions.
- `client_servicing.js`'s new `syncStickyProjectOffset()` measures the
  Open column header's actual rendered width and writes it to that CSS
  variable — run at script init, after every live refresh (the whole
  `<table>`, and any inline style on it, gets replaced), and on window
  resize (font/zoom changes).
- Project stays resizable (its own width, not its pinned position) —
  same as Projects page's Name column.
- Tests: extended `test_client_servicing_layout.py` — a saved layout
  that tries to move `project` elsewhere is still rendered with it
  first.

## Status
Chunks 1-6 shipped and verified — 40/40 tests passing (avatar-chip fix
and the data-driven-columns foundation both confirmed on the live page).
Chunk 7: resize (piece 2) BUILT AND CONFIRMED WORKING live by Ezekiel;
sticky-scrollbar fix BUILT, not yet confirmed live; reorder (piece 3)
BUILT, not yet verified; sticky Project column (follow-up feedback)
just built, not yet verified. Next: click-to-sort (piece 4), then a
final full test pass.
