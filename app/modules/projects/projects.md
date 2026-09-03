# projects

The largest module in the app: everything behind the Projects page and the
project detail overlay. Migrated in four stages (transfer → notes → list →
overlay+preproduction) because of its size (~7,300 lines across five
blueprints), but it is one module — the pieces are tightly coupled and belong
together.

## Structure
```
app/modules/projects/
  routes/
    transfer.py                # `transfer` — move/duplicate a C&CM deliverable
    project_notes.py           # `project_notes` — notes + chat panels (JSON)
    project_preproduction.py   # `project_preproduction` — 2D/3D/Technical streams
    project_list.py            # `project_list` (/projects-new) — the list page
    project_overlay.py         # `project_overlay` — the project detail overlay
  lib/
    pptx_convert.py            # .pptx -> .pdf conversion (overlay-only)
    submission_cache.py        # submission file caching/zipping (overlay-only)
  templates/
    project_list/              # the list page + its row partials
    project_overlay/           # the overlay shell + ~25 partials
  tests/
  projects.md
```

## The five blueprints
- **project_list** (`/projects-new`): the role-adaptive projects table — one page
  that renders differently per viewing role — plus the JSON endpoints for its
  filtering, sorting, row expansion, and saved table views. Its people filters (CS Lead, Designer, Project Owner) list active users first and sink deactivated ones to the bottom, keeping them selectable for historical projects (see `core.md` on deactivation). Also computes the
  per-user unread indicators shown on each row (separate dots for new project
  updates vs. new chat messages, cleared independently — see
  ProjectActivitySeen and `mark_project_activity_seen()` in
  `core/shared/lib/utils.py`), sourced from the same `ActivityLog` every
  other project-change entry point already writes to. That lookup runs on
  every page load, filter/sort, and live-refresh (including the one that
  fires when an overlay closes), so it needs `ix_activity_logs_entity_type_
  entity_id` and an index on `project_notes.project_id` to stay fast —
  `activity_logs` is an app-wide audit log with no index of its own on
  those columns otherwise, and once it grew large enough that mattered, the
  whole page hung 30s+ on those actions (see
  `migrations/add_activity_log_and_notes_indexes.py`). The page also
  supports deep-linking straight into one project's overlay via a
  `?project=<id>` query param (read by `autoOpenFromUrl()` in
  `project_list.js`, the same param `openProjectOverlay()` pushes onto the
  URL when a project is opened) — every inbound link to a specific project
  (dashboard cards, notifications, etc.) is expected to use this instead
  of the old `/projects/<id>` detail page; `dashboard.js`'s client-rendered
  rows also link through the overlay (see dashboard.md). The whole toolbar
  (tabs, filters, sort/group, search, show-cancelled, saved views)
  soft-navigates instead of reloading the page: a `/projects-new/page-state`
  JSON endpoint re-renders the tab strip, filter panel, sort panel, and
  table, and `project_list.js`'s `softNavigate()`/`applyPageState()` swap
  those into the stable containers so existing listeners survive.
- **project_overlay**: the project detail overlay — Details, Deliverables,
  Submissions, Flags, Chat, Notes, and Pre-Production surfaces, project creation
  (create overlay + resumable drafts), status overrides, add/cancel project
  customer, self-service editing-access requests (an assigned designer asking
  for, and a CS Lead/Secondary CS granting, full deliverable-management rights
  on one open project — see ProjectEditAccessRequest), a per-customer
  deliverable catalog picker for C&CM (replacing free-text entry with a pick
  from that customer's DeliverableType catalog, or add a new one to it
  permanently) plus an Apply to Multiple flow to duplicate one customer's
  deliverable set onto others on the same project, reference-file and
  submission-file serving, and job-number generation. By far the biggest file
  (~5,400 lines, 60 routes).
- **project_preproduction**: the 2D/3D/Technical stream cycle after client
  approval — assign, mark-done, approve, flag, Skip to Pre-Production, and the
  Handed to Production cascade.
- **project_notes**: the notes and chat panels (JSON endpoints; renders two of
  the overlay's partials).
- **transfer**: move or duplicate a C&CM deliverable to a different customer.

## Internal coupling
`project_overlay` and `project_preproduction` import each other (the overlay's
approval path calls into pre-production, and pre-production renders overlay
sections). That circular relationship is why they are one module and were moved
together.

## Dependencies
- **core/shared**: everything shared — db, models, nas, notifications, utils,
  decorators, status_tracking, status_vocabulary, zip_utils, and the
  achievements checker service. All imported directly from core/shared;
  migrating this module closed the last remaining `app.achievements` shim
  consumer.
- **lib/**: `pptx_convert` and `submission_cache` are used only by the overlay,
  so they live in the module's own `lib/`, not core/shared.
- **No inbound feature seams**: nothing outside the projects files imports them
  except the app factory.

## Static
The project-card JS set (15 JS + 3 CSS: project_list, project_overlay,
project_overlay_create/edit, deliverables/details/flags/chat/notes/submissions
cards, transfer, etc.) is still served from the global `/static` loader; it moves
in the shared-static pass.

## Known follow-up (deferred to the per-module overhaul)
`project_overlay.py` is ~5,400 lines. It was moved as-is; splitting it into
smaller files (details / deliverables / submissions / flags / create) is a
worthwhile future refactor, deliberately left for the planned overhaul of this
feature rather than done during the relocation, to avoid changing behaviour on
freshly-overhauled code.

## Reference-file preview
Reference files preview inline in the overlay. Allowed/previewable types cover
PDF, common images, plus audio (mp3/wav/m4a/aac/ogg) and video (mp4/webm).
`preview_project_file` caches audio/video to `uploads/preview-cache/<file_id>.<ext>`
on first fetch, so `send_file` serves real HTTP range requests for seeking
instead of re-downloading the whole file from NAS on every request; `preview.js`
points `<video>`/`<audio src>` straight at the route so the browser drives its
own range requests. The NAS stays the source of truth — the cache is disposable.
`preview_cache_cleanup.py` (repo root) empties the cache; installing its daily
systemd timer / cron job on the server is a manual step.

## Details edit mode
The Details tab's Edit button (project_overlay_edit.js) swaps every
`[data-field]` row from its `.overlay-edit-view` to its `.overlay-edit-input`
and Saves a whitelisted field set to `overlay_details_save` (concurrent-edit
guarded via `edit_snapshot_at`, diffed into ActivityLog). **Teams Required**
(`design_teams_requested`) is editable here: a checkbox group
(shared partial `_details_teams_required.html`, in both brief templates). It
rides the same edit flow via two generic, reusable hooks in the edit JS — a
`data-edit-type="checkbox-group"` input collected as a comma-joined value,
and a `data-confirm-uncheck` gate that confirms before Save when a
checked-on-load box is unticked. Dropping a team also deletes that team's
Design Lead (its ProjectDesigner row) server-side and logs `lead_removed`;
per-deliverable team tags are untouched. Note: adding a team does not
scaffold its NAS folder (folders are created at project creation only).

## Performance
The list page and row-expand are eager-loaded (no N+1 on the main table);
see the query-count regression tests below. The **Deliverables sub-tab**
had the same trap and is fixed the same way: its read query
eager-loads each row's assignment tags + their designers and the
deliverable type's team list — Standard in `overlay_deliverables`, C&CM in
`_build_ccm_deliverable_sections` (`routes/project_overlay/_common.py`), so
the query count no longer grows with the number of deliverables. This was
the cause of the slow/hanging Deliverables tab on large C&CM projects.

Still open: on a live update the projects list rebuilds its whole serialized
view (the deferred "targeted single-row refresh + render cap" work) — a
separate, larger job, not this fix.

## Not here
The first-login account **wizard** was reassigned to the **profile** module — it
sets the user's own account fields (name, password, birthday), which is profile
territory, not projects.

## Tests
`tests/test_projects_smoke.py` — per-blueprint auth checks, template resolution
for the list and overlay, the two `lib/` helpers importable, and the overlay on
the shared achievements service. Uses the shared fixtures from `core/shared`.
`tests/test_overlay_deliverables_perf.py` — Deliverables-tab query count
doesn't scale with deliverable count (Standard + C&CM) + rows still render.
`tests/test_project_list_expand_perf.py`, `tests/test_overlay_history_perf.py`
— the earlier eager-loading regression guards.
