# OVP architecture

OVP (codename Helix, repo `project-tracker`) is a Flask app built as **vertical slices**: one folder per feature. It has been structured this way since v2.4.3.

Stack: Flask 3.1 · SQLAlchemy 2.0 · PostgreSQL · Jinja2 server-rendered pages · Flask-Login · vanilla JS · custom CSS · gevent + SSE for live updates · Python 3.14. Navigation is a light SPA: the sidebar swaps `<main>` instead of reloading the page.

## Structure
```
app/modules/
  core/shared/   # extensions, blueprint, models/, lib/ (capabilities, org, users, utils, paths…),
                 # services/ (notifications, nas, live_events, sse_relay, achievements…),
                 # routes/ (shell, sse, api), templates/ (base, partials, _shared_macros),
                 # static/ (css, js, fonts), testing.py, tests/
  auth/ profile/ notifications/ wiki/ blog/ feedback/ file_templates/ client_directory/
  achievements/ time_tracking/ projects/ dashboard/ admin/
  client_servicing/ digital_innovation/ hse/ roadmap/ hr/
```
Each module has `routes/` and, as needed, `lib/` (rules and helpers), `services/` (what other modules may call), `templates/`, `static/`, `tests/`, and a short `<module>.md` saying how it works now.

## Rules
- **Modules import only from `core/shared`** (plus their own files). No module reaches into another's models, routes or templates.
- **Anything used by two or more modules moves to `core/shared`** — on the second copy, not the third. Examples: `module_rail.js`, `fill_height.js`, `popover_position.js`, the tray dock.
- **Cross-module data reads go through `modules/<name>/services/`.** Examples: `client_servicing/services/dashboard_feed.py::feed_for`, `digital_innovation/services/intake.py`, `hse/services/feed.py`.
- **Business rules live in `lib/` and `services/`, never in routes or templates.** This keeps a future JSON API (for the OVP app) a thin second set of routes over the same services.
- Blueprint name quirks are kept on purpose: the dashboard blueprint is named `projects` (url `/dashboard`); the projects module has `project_list` (`/projects-new`), `project_overlay`, `project_preproduction`, `project_notes`, `transfer`.
- One temporary seam remains: the dashboard imports `build_time_tracking_rows` and `compute_project_hours` from `time_tracking.logic`. It moves to shared with the designer work calendar.

## The org model
Access comes from where a person sits: **department + seniority** on the shared user record, with admin as a separate switch (`core/shared/lib/capabilities.py`, `lib/org.py`; detail in CAPABILITIES.md). **Reports to** drives approvals through the HR module's `services/approvers.py::approvers_for(user)`. Admins edit the fields in Admin → Accounts until the HR pages arrive.

## The module feed (dashboards)
A module with enough to summarise has its own dashboard as the first entry of its rail. The global Dashboard is the app-wide, role-based home: it rolls up and links into module dashboards, never contains them.

Each module exposes `modules/<name>/services/dashboard_feed.py::feed_for(user) -> list[FeedItem]` with one shape — `{ source, kind, title, detail, link, urgency, date }` (`urgency` is `info`, `warning` or `urgent`). The module computes these once in its own `lib/dashboard.py`; `feed_for` exposes the cross-cutting subset, so there is one source and no drift.

## Static assets
- Module CSS/JS live in `app/modules/<module>/static/{css,js}`; shared assets and fonts in `core/shared/static/`.
- Each module has a small `<module>_assets` blueprint (`static_url_path=/<module>/static`); templates use `url_for('<bp>.static', …)` with `?v={{ config.STATIC_VERSION }}`.
- `STATIC_VERSION` is computed at start-up from the newest file time under `app/`, so it changes on every deploy without a manual bump.
- Stylesheets are loaded globally from `base.html` because SPA navigation only swaps `<main>`. Per-page loading is planned after October (it needs `sidebar.js` to sync `<head>`).
- Runtime data (avatars, banners, deliverable images, wiki uploads) stays in `app/static/`.

## Versioning
`MAJOR.MINOR.PATCH`, numbers in ship order. PATCH = fixes, polish, small additions; MINOR = a new page, capability or module; MAJOR = a new era (3.0 is the OVP app). Each shipped item gets an annotated tag `v<version>`; the footer shows the running tag (`APP_VERSION`, from `git describe --tags`).

## Checks that guard the structure
`python -m pytest` runs, among others:
- the **route contract** against `refactor/route_baseline.txt` (regenerate after an intentional route change);
- the **role-literal baseline** (no new hard-coded role, department or seniority checks);
- **boot and per-module smoke tests**;
- **dark-mode CSS** (no hard-coded colours outside token blocks).

## Still open
- Remove the leftover shims: `app/achievements.py` (update its one test), `app/routes/api.py` and `app/routes/sse.py` (point the factory at `core/shared/routes`, then delete).
- Grow characterisation tests feature by feature ("test what you touch") rather than as one job.
