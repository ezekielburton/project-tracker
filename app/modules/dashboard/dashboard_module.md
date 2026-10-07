# Dashboard module

**What it is.** The page people land on after logging in. It shows each person what needs them: their work, what is late, and what is waiting on someone else.

**Who it is for.** Everyone with dashboard access (`view_workspace`). The HSE officer has no dashboard and starts on HSE instead (`core/shared/lib/home.py`).

## How the rails work
Each person gets a side menu (the rail). Which rail comes from the org model only: `lib/rails.py::rail_for(user)` reads department, seniority and the admin switch through the `org.py` checks, never `User.role`. While an admin views as someone, the rail is that person's, except on the admin pages, which keep the admin's own rail.

| Rail | Who | Pages (landing first) |
|---|---|---|
| Admin | the admin switch | Overview · System · Database · Performance · Usage · Errors · Uptime · Jobs |
| Management | Management seniority | Overview · Escalations · Needs attention · Design workload · Delivery · Teams · Clients · Adoption |
| Head of Design | Design · Head of Department | Design workload · Overview · Assignments · Team · Calendar |
| Design lead | Design · Manager | Overview · Assignments · Team · Calendar |
| Designer | Design · None | Overview · My projects · Site visits · Calendar |
| Head of CS | Client Servicing · Head of Department | Needs attention · Overview · Approvals · My clients · Calendar |
| Client Servicing | Client Servicing · None or Manager | Overview · Approvals · My clients · Calendar |
| Project Owner | Project Owners | Overview · Approvals · My projects · Site visits · Calendar |
| Basic | everyone else | Overview |

Every rail ends with **My hub · Soon** (no route; HR builds it).

- **Landing.** `/dashboard` redirects to the first page of the rail and keeps the query string, so old `/dashboard?…` links still work.
- **Routes.** One route per page, in `routes/pages.py` (Overview stays in `routes/dashboard.py`). Every page has two checks: its capability (`@require`) and being on the person's rail (`@on_rail`, which admin passes). A typed URL opens only what the rail shows.
- **Gates.** `view_workspace` for the personal pages · `view_department_overview` for Design workload and Needs attention · `view_management_dashboard` for the Management pages · `admin_panel` with `real_user=True` for the system pages, so an admin keeps them while viewing as someone.
- **Badges.** `lib/rail_counts.py::rail_counts(user)` runs once per request. A page gets a badge by adding its counter to `COUNTERS`; counters read the loader, never their own project query. Zero shows no badge.
- **New briefs.** Active projects with no deliverables yet, company-wide, newest first: `project_loader.load_new_briefs()`, one query. Shown on the landing page only.
- **Calendar.** One page for every rail that has it. `lib/calendar.py` holds `EVENT_KINDS` and `calendar_events_for(user, start, end)`, which the event sections fill. The grid comes from `core/shared/lib/month_grid.py`. A new event kind needs a `.dash-cal-kind--<key>` rule in `dashboard.css` (a test checks).
- **Page frame.** A page extends `templates/dashboard/_shell.html`, fills `dash_main`, and renders with `**page_context('<key>')` from `lib/shell.py`.

**Adding a page:** a `Page` in `rails.PAGES` → its key in `rails.RAILS` → a route with `@require` and `@on_rail` → render with `page_context`. A badge is one entry in `COUNTERS`.

**Until each section lands:** Overview is today's role view inside the shell. The basic rail's Overview is New briefs only. Every other page shows *Coming soon*.

## The admin pages
Eight pages on the Admin rail show OVP's own health. They only read: the system module (`app/modules/system/system.md`) records everything with timers and request hooks. Every page and endpoint is real admin only (`admin_panel`, `real_user=True`), so an admin keeps them while viewing as someone.

- **One file per page** in `lib/admin_pages/`: overview, system, database, performance, usage, errors, uptime, jobs. Each lists its cards in `PARTS` (name → builder). The card pages also give `LAYOUT`: a row of tiles, then rows of one, two or three cards, laid out by `templates/dashboard/admin/cards.html`. Overview and System have their own templates. `common.py` holds the shared pieces: links, relative times, the live badge, tiles.
- **Cards load on their own** from `/dashboard/api/admin/<page>/<part>` into `templates/dashboard/admin/parts/<page>_<part>.html`. A card whose data is missing shows "No data", never an error.
- **Live.** Open pages listen on `/sse/system` and reload the cards when a snapshot, heartbeat or job run lands (`static/js/admin_system.js`). The badge in each page head reads *Live · <day>* while the snapshot is under 3 minutes old, then *Updated N min ago*, or *No data yet*.
- **Charts** are SVG built on the server by `lib/admin_charts.py` (bars, lines, scales, hover labels). No chart library.
- **Two writes only:** Run now (`POST /dashboard/api/admin/jobs/<job>/run`, confirmed with a second click) and Add incident (`POST /dashboard/api/admin/incidents`). Both are logged.
- **Layout.** The pages size to their own width (container queries on `.dash-admin`), so they fit with the sidebar pinned or collapsed. Cards that scroll use the shared scroll hold (`core/shared/static/js/scroll_hold.js`): they take the mouse wheel only when their content overflows.

**Adding an admin card:** a builder in that page's `PARTS`, a `parts/<page>_<part>.html` template, its place in `LAYOUT`, and a test in `tests/test_admin_pages.py`.

## How it gets its data
When a dashboard page loads, it asks for the person's projects **once**, together with everything the cards need: deliverables, customers, designers, flags, status history. Every card then reads from that one list.

**Rules for anyone adding to the dashboard:**
- New cards, badges and panels take their projects from `lib/project_loader.py`. They never ask the database for projects themselves.
- Which projects a role can see is decided in one place: `scope_query()` in that file.
- The list is for showing things. A page that changes a project must not rely on it afterwards.
- One number, one source. A count shown in two places must come from the same list.

**Checks:** `tests/test_dashboard_perf.py` fails if a page's database requests grow as projects are added. `refactor/dashboard_snapshot.py` saves every card's output so a change can be compared before and after.

## Files
```
app/modules/dashboard/
  routes/dashboard.py     Overview (today's role views) and the card data endpoints
  routes/pages.py         the landing redirect, Calendar, and every other rail page
  lib/rails.py            the pages, the rails, rail_for(user)
  lib/shell.py            rail items, the on-rail check, page_context, New briefs rows
  lib/rail_counts.py      the badge counts
  lib/calendar.py         event kinds and the calendar_events_for seam
  lib/project_loader.py   the one project fetch per page load, and New briefs
  lib/dashboard_logic.py  small rules: deadline colour, clashes, whose turn it is
  lib/admin_pages/        the admin pages: one file per page, plus common.py
  lib/admin_charts.py     the admin pages' SVG charts
  templates/dashboard/    _shell, _new_briefs, placeholder, overview_basic, calendar, the cards
  templates/dashboard/admin/  the admin pages: cards.html, overview, system, _macros, parts/
  templates/              today's role views (inside the shell)
  static/                 the module's CSS and JS
  tests/
```

## Things to know
- **Internal name.** The module is registered as `projects`, not `dashboard`. Links use `projects.<page>`. Do not rename it.
- **Borrowed piece.** The average-project-time figure comes from the time tracking module.
- **Help keys.** `dashboard.overview` (the role views and the basic Overview), `dashboard.calendar`, `dashboard.admin` (every admin page but Jobs) and `dashboard.jobs`. Each new page declares its own.

## Build progress
The plan is `dashboard_master_plan.md` in the OVP project docs.

| Section | What | Status |
|---|---|---|
| S0 | Org model | Done |
| S1 | One project fetch per page | Done |
| S2 | Shared shell, rails, badges, New briefs, calendar page | Done |
| S7/S8 | Admin dashboard | Done |
| S1b | Teams from deliverables, the overdue rule | Next |
| S3 | Escalations | — |
| S4 | Nudges | — |
| S15 | Whose turn, department pages' data | — |
| S5/S6 | Site visits, calendar events | — |
| S9 | Management dashboard | — |
| S10/S11 | Design dashboards | — |
| S12 | Client Servicing dashboard | — |
| S13 | Project Owner dashboard | — |
| S14 | Adoption page | — |

This file replaces `dashboard.md`, which is removed in the last section.
