# Digital Innovation

The department's own workspace: Trello-style **boards** of **features** moving through
an 8-stage pipeline, a per-project **cost ledger**, and a **Performance** rollup. A
permanent OVP board is seeded and un-deletable; other boards can be created, closed,
archived and reopened.

## Structure
Vertical slice. All tables are `Di`-prefixed and self-contained; the only outward
reference is `DiProject.linked_project_id` → the shared `Project` (read-only). The
one inbound seam is `services/intake.py::add_feedback_item()`, which other modules
call to file an item onto the OVP board's Incoming tray — DI never imports another
module's models.

```
digital_innovation/
  models.py            all Di* tables + DI_STAGES / labels / colours / tracks
  lib/                 the "brains" (pure logic, no HTTP)
    access.py          who can view/edit — the single access choke point
    board_data.py      board + sidebar + Incoming-tray assembly
    feature_detail.py  the feature-detail modal's context
    step_engine.py     stage/step state machine
    template_admin.py  department step-template CRUD
    costs.py           cost-ledger rules + summary
    excel_export.py    cost + performance .xlsx exports
    periods.py         week/month/quarter math + the rollover overlap query
    snapshots.py       Performance rollup + month/quarter freeze
  services/intake.py   the inbound seam (files items onto the OVP board)
  routes/              thin HTTP layers over lib/ (one blueprint, blueprint.py)
  templates/           board / performance / templates / archive + fragments
```
CSS: `app/static/css/digital_innovation.css`. JS: `digital_innovation_*.js` (board,
archive, performance, templates).

## Data model
- **DiProject** — one board. `lifecycle` ∈ active / closed / archived. `is_permanent`
  marks the seeded OVP board (the backend refuses to close/archive/delete it).
  `track` ∈ internal / external decides whether `management_review` reads as
  "Management Review" or "Client Review". `linked_project_id` → shared Project.
- **DiFeature** — one card. `status` is a stage in `DI_STAGES` or `'closed'`.
- **DiFeatureStep** — a checklist item for one stage, copied from a DiStepTemplate
  when the feature first enters that stage. Steps from past stages are kept.
- **DiStepTemplate** — department-wide default steps per stage. Editing a template
  never rewrites steps already copied onto features.
- **DiCostEntry** — a dated ledger line. `dev_time` entries set a feature and price
  `amount` from `DiSetting.dev_hourly_rate` at save time; the other types are
  project-level. Deletable, never editable.
- **DiSetting** — single-row department settings (hourly rate, currency).
- **DiPeriodSnapshot** — a frozen month/quarter rollup (`snapshot_data` JSON).
- **DiIntakeItem** — one Incoming-tray item; also used as a dismissal marker for a
  FeatureRequest.

`DI_STAGES` (8, in order): researching, planning, coding, testing, optimizing,
management_review, revision, implementation. Stage colours reuse the app's
`.status-pill--<name>` classes for free dark-mode tinting (see theming.md).

## Access (lib/access.py)
The single choke point — routes/templates gate through these, never inline role
checks, and all are **emulation-aware** (an admin emulating another user is held to
that user's role):
- `can_view_di_performance` — Performance / Cost / the feature-detail cost note
  (admin, management).
- `can_view_di_project` / `visible_di_projects` — every board but the permanent OVP
  one is restricted to admin/management/future `digital_innovation`; everyone else
  sees only OVP.
- `can_edit_di_board` — any data change (create, tick/add/delete a step, move, close).
  Viewing stays open; only writes are gated. Admin-only for now.
- `can_edit_di_templates` — the Edit Templates screen (admin).

## The brains
- **step_engine.py** — the stage/step state machine. A feature's current-stage steps
  are freely editable; a feature moves to any stage forward or backward with no
  completion gate; revisiting a stage resumes its existing steps, a first visit seeds
  from the template. Closing is separate, gated on the last stage being complete.
- **costs.py** — ledger rules + `cost_summary` (per-type totals, grand total,
  projected profit when a client charge is set).
- **periods.py / snapshots.py** — a project belongs to a period if its active lifespan
  overlaps it. Weeks compute live; a month/quarter freezes automatically on first view
  once it has fully ended, locking its numbers.

## Routes
One blueprint (`/digital-innovation`). Full page loads render the board / performance /
templates / archive screens; mutating routes return the same fragment a fresh GET
would, so the modal or screen always shows true current state. Fragment routes
(`*_fragment`, `board/columns`, `intake/cards`) re-render a partial on the DI-wide
live SSE ping so other users' changes appear without a manual reload.

## Incoming tray
Only the permanent OVP board has one. It merges two sources oldest-first: native
`DiIntakeItem` rows (`status='pending'`) and live `FeatureRequest` rows
(`status='requested'`, read straight off the shared table). Promoting creates a real
feature; a promoted FeatureRequest is set to `in_progress` (which removes it from the
tray and notifies the submitter). Dismissing a FeatureRequest only hides it here,
recorded as a marker DiIntakeItem — the request itself is untouched.

## SPA + SSE notes
- The board wrapper is a `<div>`, **not** a `<main>`: base.html's `#main-content` is the
  page's one `<main>`, and `spa_strip_response` extracts up to the first `</main>`, so a
  nested `<main>` would drop everything below it on an SPA nav.
- Live refresh rides the DI-wide SSE ping, which fires only for DI's own watched
  models — a brand-new FeatureRequest submission appears on the next full load, not live.

## Remaining scope
A management dashboard rolling DI hours/profit up into a linked system project
(`DiProject.linked_project_id` exists for this); wiring FeatureRequest submissions into
the live SSE ping; the department's own `digital_innovation` role (the access sets are
already separate so it slots in without touching the others).
