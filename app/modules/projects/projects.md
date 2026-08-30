# projects

The app's largest module: the Projects list page and the project detail overlay. It's one module — the pieces are tightly coupled.

## Structure
```
app/modules/projects/
  routes/
    transfer.py                # move/duplicate a C&CM deliverable
    project_notes.py           # notes + chat panels (JSON)
    project_preproduction.py   # 2D/3D/Technical streams
    project_list.py            # the list page (/projects-new)
    project_overlay/           # the project detail overlay (package)
  lib/
    pptx_convert.py            # .pptx -> .pdf (overlay only)
    submission_cache.py        # submission file caching/zipping (overlay only)
  templates/
    project_list/              # list page + row partials
    project_overlay/           # overlay shell + partials
  tests/
  projects.md
```

### `project_overlay/` package
The overlay was one ~5,400-line file. It's now a package of seven files sharing one blueprint:

- `_common.py` — the `project_overlay_bp` blueprint (every other file imports and decorates onto it, so all `url_for('project_overlay.*')` names and the app-factory import stay unchanged), plus helpers used by two or more files.
- `create.py` — create-draft flow: shell, draft list, finalize, delete.
- `details.py` — Details read/save, project start, status overrides, cancel/uncancel, add customer, NAS link, hold toggle, edit-access requests.
- `flags.py` — Brief Flags (create/reply/resolve/history).
- `deliverables.py` — Deliverables tab, edit (Standard + C&CM), Apply to Multiple, team + people assignment.
- `submissions.py` — Submissions tab: draft cards, file upload/manage, submit for review/to client, client revision, approve, internal-revision flagging.
- `files.py` — Reference Files, job-number generation, submission file serving.

## The five blueprints
- **project_list** (`/projects-new`) — the role-adaptive projects table plus its JSON endpoints (filter, sort, row expansion, saved views). Shows per-user unread dots (project updates vs chat messages, cleared independently) sourced from `ActivityLog`. Relies on the activity-log and notes indexes to stay fast. Deep-links into a project's overlay via `?project=<id>`.
- **project_overlay** — the detail overlay: Details, Deliverables, Submissions, Flags, Chat, Notes, Pre-Production, project creation (create overlay + resumable drafts), status overrides, add/cancel customer, edit-access requests, the per-customer C&CM catalog picker + Apply to Multiple, file serving, job numbers. Now the `project_overlay/` package above.
- **project_preproduction** — the 2D/3D/Technical stream cycle after client approval (assign, mark-done, approve, flag, Skip to Pre-Production, Handed to Production).
- **project_notes** — the notes and chat panels (JSON endpoints).
- **transfer** — move or duplicate a C&CM deliverable to another customer.

## Coupling
`project_overlay` and `project_preproduction` import each other (the overlay's approval path calls into pre-production; pre-production renders overlay sections), so they stay in one module.

## Dependencies
- **core/shared** — db, models, nas, notifications, utils, decorators, status tracking/vocabulary, zip utils, achievements service.
- **lib/** — `pptx_convert` and `submission_cache`, used only by the overlay.
- Nothing outside the module imports it except the app factory.

## Static
The project-card JS/CSS still load from the global `/static`; they move in the shared-static pass.

## Optimization status
- Done: two N+1 fixes (draft-card history rendering; the list page's row expansion), each with a query-count test. The overlay split above.
- Open: list-page live-refresh scaling — targeted single-row SSE updates instead of a full `/table-rows` refetch, plus a cap on full-view rebuilds.

## Not here
The first-login account wizard moved to the profile module.

## Tests
`tests/` — smoke tests (per-blueprint auth, template resolution, lib imports, achievements) plus the two query-count perf tests above.
