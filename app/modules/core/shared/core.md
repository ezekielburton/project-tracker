# core/shared

The single home for all cross-module shared code. Anything used by two or more
feature modules lives here — and only here. Feature modules depend on
`core/shared`; they never reach into one another.

## Structure

```
app/modules/core/shared/
  extensions.py    # db, login_manager, mail — the extension singletons
  blueprint.py     # the `core` blueprint (shared templates; shared static later)
  models/          # all SQLAlchemy models, split by domain (package re-exports all)
  lib/             # stateless helpers
  services/        # stateful / IO / side-effecting shared services
  routes/          # app-shell + live-update routes
  templates/       # shared base layout, macros, shared partials
  static/          # shared assets (DEFERRED — see Known follow-ups)
  testing.py       # shared pytest fixtures
  tests/           # core/shared's own tests
  core.md          # this file
```

### extensions.py
Creates the `db` (SQLAlchemy), `login_manager` (Flask-Login), and `mail`
(Flask-Mail) singletons. They are bound to the application in the app factory.
Every module imports these same instances so the whole app shares one database
registry, one login manager, and one mail sender.

### models/
The ~65 SQLAlchemy models, grouped by domain across 14 files: `users`,
`clients`, `projects`, `deliverables`, `status_logs`, `submissions`, `flags`,
`notes`, `notifications`, `activity`, `blog`, `feedback`, `wiki`,
`achievements`. The package `__init__` re-exports every model, so the whole
schema is available from one import surface. Relationships resolve across files
through SQLAlchemy's registry (string class names), so a model's file placement
is purely organizational.

### lib/ (stateless helpers)
- `decorators` — `role_required`
- `utils` — `file_type_label`, `strip_html`, `get_actor`, `log_activity`
- `zip_utils` — build and serve one-shot zip downloads
- `status_vocabulary` — pure `derive_*` functions turning raw status values
  into the (label, css_modifier) pairs templates render as status pills

### services/ (stateful / IO)
- `notifications` — the notification service: `create_notification` plus the
  `notify_*` helpers and outbound email
- `status_tracking` — the status-change funnel (`record_*_status`) that writes
  the `*StatusLog` history, plus bulk read helpers
- `nas` — the Synology file-storage client (upload/download/folders + Drive
  deep links)
- `live_events` — SQLAlchemy commit hooks that detect changes and fan out
- `sse_relay` — the Postgres LISTEN/NOTIFY relay backing Server-Sent Events
- `achievements` — the achievement checker (`check_achievements`): advances
  and awards achievements in response to events fired from across the app

### routes/
- `shell` — the `main` blueprint: root redirect to the dashboard, sidebar
  click analytics
- `sse` — the `sse` blueprint: SSE stream endpoints (doorbells that tell the
  browser to re-fetch)
- `api` — the `api` blueprint: JSON polling endpoints for live updates

### templates/
`base.html` (the site layout every page extends), `base_fragment.html`,
`_macros.html`, `_shared_macros.html`, and shared `partials/`. Placed on
Jinja's search path by the `core` blueprint, so any module can
`{% extends 'base.html' %}` and import the shared macros.

## How feature modules use core/shared
- Models: `from app.models import X` (currently resolved through a compatibility
  shim into `core/shared/models`).
- Extensions: `from app import db` (shim into `core/shared/extensions`).
- Shared helpers/services: imported from their old `app.<name>` paths during the
  migration (each is a shim re-exporting from `core/shared`); the final form
  imports directly from `core/shared`.

## Conventions established here (the template every module follows)
- **Shim pattern** — when shared code moves into `core/shared`, a one-line
  re-export shim stays at the old path so existing imports keep resolving. Shims
  are removed once every feature module has migrated.
- **Per-blueprint static** — each module owns and serves its own static assets
  through its blueprint; `core` serves the shared assets.
- **Time-proof comments** — comments describe what the code does, never when it
  changed (no dates, milestone codes, or migration filenames).
- **Module shape** — every feature module is `routes/ models/ templates/
  static/` plus a `<module>.md` and a `tests/` folder.

## Testing
The shared pytest harness lives here:
- `testing.py` — fixtures: `app` (built on the dedicated `project_tracker_test`
  database), `client` (test HTTP client), `db_session` (per-test transaction
  rolled back at teardown, for data isolation). The root `conftest.py`
  re-exports these so every module's tests inherit them.
- `TestingConfig` (in `config.py`) points at the test database and disables
  outbound mail; the suite refuses to run if the test DB URL ever equals the
  real one.
- `tests/test_routes_contract.py` — asserts the live `url_map` matches
  `refactor/route_baseline.txt`. This is the refactor's automated safety net:
  any change that drops, renames, or unexpectedly adds a route fails instantly.
  When routes change intentionally, regenerate the baseline.
- `tests/test_boot.py` — the app factory builds, the ORM configures across the
  split model package, and the shared templates resolve.

Run the suite from the repo root with `python -m pytest`.

## Known follow-ups
- **Static assets stay consolidated in `app/static/` (decided).** The physical
  relocation into per-module `static/` folders was deliberately NOT done: the
  asset graph is entangled (the base layout loads every feature's CSS globally,
  fonts are shared across CSS via `url(../fonts/)`, some paths are hardcoded in
  JS, and a `STATIC_VERSION` cache-buster stamps every URL), and the app is live.
  Instead, each module's assets move into its own `static/` folder *during that
  module's overhaul*, one at a time. The full ownership map and the per-module
  move recipe are in `Documentation/Static_Asset_Ownership.md`.
  (`main_backup.css` is a dead file that can be deleted.)
- **Repoint intra-core imports** — files inside `core/shared` still import some
  siblings through the old `app.<name>` shims; repoint them to direct
  `core/shared` paths.
- **Remove shims** — once every feature module imports from `core/shared`
  directly, delete the compatibility shims.
