# time_tracking

The management/admin time-tracking page: a full-page table of business hours
per project and per deliverable, broken down by status. Hours are derived from
status-log history, not a live timer.

> **Overhaul note:** this feature is slated for an overhaul with a different way
> of tracking. It was moved as a fully self-contained module for exactly that
> reason — everything time-tracking (page, hour math, row-building) lives in
> this one folder. The one boundary to respect is the **dashboard contract**
> below; whatever the new tracking method looks like, the dashboard's Average
> Time card calls those functions. When the overhaul lands, promote to
> `core/shared` whatever genuinely turns out to be shared.

## Structure
```
app/modules/time_tracking/
  routes/time_tracking.py    # the `time_tracking` blueprint (one page)
  logic.py                   # all hour math + row-building (pure functions)
  templates/time_tracking/   # index.html
  tests/test_time_tracking_smoke.py
  time_tracking.md
```

## Routes (the `time_tracking` blueprint)
- `GET /time-tracking` — the full-page breakdown. Admin/management only, via a
  manual `get_actor()` check (emulation-aware, unlike the shared `role_required`
  decorator, because this is a read-only view).

## logic.py — the hour math
Pure functions, no Flask/DB writes. They recompute from `*StatusLog` history on
every read, so the numbers can't drift from a missed write. The rules:
- Business hours only: Mon-Fri, 10AM-6PM Dubai time.
- Weekend hours are discarded unless a status change happened that weekend.
- Per-status breakdown, plus an "overall" that excludes the statuses in
  `EXCLUDED_FROM_OVERALL` (`in_queue`, `submitted_to_client`,
  `internal_revision`, `on_hold`).

## Dashboard contract (the one external dependency)
The dashboard's **Average Time** card reuses this module's logic — it does NOT
keep its own copy. It imports, from `app.modules.time_tracking.logic`:
- `build_time_tracking_rows()` — for the card's expandable full table
- `compute_project_hours(project)` — for the "average project time" number

This is a temporary cross-module import (the dashboard reaching into this
module) and is expected to be revisited when the dashboard module migrates. A
smoke test asserts these three symbols exist, so a rename during the overhaul
will fail loudly rather than silently break the dashboard. The dashboard's card
template also reuses this page's `.tt-*` CSS classes, and `time_tracking.css` is
loaded globally — noted for the shared-static pass.

## Models
None of its own. `build_time_tracking_rows` reads `Project` from
`core/shared/models`; the compute functions operate on passed project/deliverable
objects via their `status_logs` backref.

## Static
`css/time_tracking.css`, `js/time_tracking.js` — served from the global
`/static` loader; move in the shared-static pass.

## Dependencies
- **core/shared**: `Project` (models), `get_actor` (lib/utils).
- **No inbound feature seams** except the documented dashboard contract above.

## Exports
The `time_tracking` blueprint (registered in the app factory) and the logic
functions in the dashboard contract. The sidebar has no direct link; the page is
reached at `/time-tracking` and surfaced through the dashboard card.

## Tests
`tests/test_time_tracking_smoke.py` — the page requires authentication, its
template resolves, and the dashboard-contract functions are present.
