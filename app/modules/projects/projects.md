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
  filtering, sorting, row expansion, and saved table views.
- **project_overlay**: the project detail overlay — Details, Deliverables,
  Submissions, Flags, Chat, Notes, and Pre-Production surfaces, project creation
  (create overlay + resumable drafts), status overrides, add/cancel project
  customer, reference-file and submission-file serving, and job-number
  generation. By far the biggest file (~4,700+ lines, 55 routes).
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
`project_overlay.py` is ~4,700 lines. It was moved as-is; splitting it into
smaller files (details / deliverables / submissions / flags / create) is a
worthwhile future refactor, deliberately left for the planned overhaul of this
feature rather than done during the relocation, to avoid changing behaviour on
freshly-overhauled code.

## Not here
The first-login account **wizard** was reassigned to the **profile** module — it
sets the user's own account fields (name, password, birthday), which is profile
territory, not projects.

## Tests
`tests/test_projects_smoke.py` — per-blueprint auth checks, template resolution
for the list and overlay, the two `lib/` helpers importable, and the overlay on
the shared achievements service. Uses the shared fixtures from `core/shared`.
