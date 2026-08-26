# dashboard

The role-based dashboard: the landing page after login, showing each role a
tailored set of cards (next actions, decisions, clashes, what-changed, at-risk /
overdue, stat tiles) over their own scoped view of the projects.

## Structure
```
app/modules/dashboard/
  routes/dashboard.py    # the dashboard blueprint (see naming note) + its API endpoints
  lib/dashboard_logic.py # pure helpers: RAG, clashes, next-action owner, guidance, approvals
  templates/
    dashboard.html, dashboard_cs.html, dashboard_designer.html, dashboard_leadership.html
    dashboard/           # macros, modals, toggle boxes, view-switcher, and the cards/
  tests/
  dashboard.md
```

## Naming note (important)
The blueprint is registered as **`projects`**, not `dashboard`
(`Blueprint('projects', __name__, url_prefix='/dashboard')`) — a historical name.
Every `url_for()` for this blueprint uses it, e.g. `url_for('projects.index')`
(the root redirect and the sidebar's dashboard link). The name was **kept** on
migration so those references and the route contract stay identical. Do not
rename it without updating every `projects.*` reference.

## Routes
`GET /dashboard` (`projects.index`) renders the role-appropriate dashboard, plus
JSON/SSE endpoints (`/dashboard/api/*`) that feed the cards' live bodies. 16
routes in total.

## Layout (how the page is built)
My Day/My Week and Overdue/At Risk are permanent collapsible toggle boxes above a
tab strip; every other card is a tab whose body renders in one shared area below
(the `dash_card()` tab+body mechanic in `_dashboard_macros.html`). `CARD_ORDER`
sets the per-role tab order; `_STAT_TILES` (active / pending / avg-time) are
always last.

## lib/ — dashboard_logic
Pure functions with no app imports: `get_project_rag`, `compute_clashes`,
`nearest_deadline`, `get_next_action_owner`, `guidance_for_viewer`,
`needs_client_approval`, and the status→next-action map. Single-consumer
(dashboard only), so it lives in the module's own `lib/`.

## Dependencies
- **core/shared**: `db`, models, `get_actor` (lib/utils), `derive_project_status`
  (lib/status_vocabulary). All imported directly from core/shared.
- **time_tracking (documented cross-module seam)**: the Average Time card borrows
  `build_time_tracking_rows` and `compute_project_hours` from
  `app.modules.time_tracking.logic`. This is a deliberate, documented dependency;
  the decision to promote that shared hour-math to core/shared was left for the
  planned time_tracking overhaul, so the seam stays as-is for now.
- **No inbound feature seams** — only the app factory imports this module.

## Static
`css/dashboard.css`, `js/dashboard.js` — served from the global `/static` loader;
move in the shared-static pass.

## Tests
`tests/test_dashboard_smoke.py` — the dashboard requires authentication, its role
templates and cards resolve, and the logic helpers import.
