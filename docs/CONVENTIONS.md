# OVP conventions

How we build OVP. Read this before writing a feature, a test or a page. Each rule here came from a real bug.

Related docs: [ARCHITECTURE.md](ARCHITECTURE.md) (module structure) · [CAPABILITIES.md](CAPABILITIES.md) (who can do what) · [DEPLOYMENT.md](DEPLOYMENT.md) · `app/modules/core/shared/theming.md` (read before CSS) · `app/modules/core/shared/spa-navigation.md` (read before page JS).

---

## 1. Before you build

- **Prior art first.** Before writing anything custom, check: has this been solved already (a library, a Flask/SQLAlchemy/Postgres built-in, a standard pattern)? Does it fit our stack? Only go custom if nothing fits, and say why. This applies to *how* we implement, not to the module design itself.
- **Propose before code.** Describe what changes, where and why, in plain words, and get it agreed before writing it.
- **A wireframe is a visual contract, not a data contract.** Check its fields and status names against the models before building; raise every mismatch as a decision first.
- **Wireframes come in both themes**, light and dark, with the palette in CSS variables (the same way the app does it).

## 2. Definition of done

A feature is done when all of these are true, in this order:

1. The code is in and reviewed.
2. **The whole test suite passes** (`python -m pytest`) and the page passes the manual matrix (§10).
3. The docs it touched are updated, including the module's `<module>.md`.
4. A short summary is written: what changed, files touched, tests added, any change from the plan.
5. **The module's wiki articles are updated** — a new article for a new page, edits for anything that changed. Last on purpose: it's the step that gets skipped.

Every page declares a **help key** (`help_button('cs.invoicing')`), registered in `app/modules/wiki/lib/help_keys.py`. The wiki's Coverage panel lists keys with no article, so the gap shows before you tag. A wrong article is worse than a missing one: update it in the same release.

## 3. Modules and seams

- One folder per feature in `app/modules/<name>/`. Shared code lives in `app/modules/core/shared/`.
- Modules never import another module's models, routes or templates. A cross-module **data** read goes through that module's `services/`.
- **Three copies is the bug.** When logic is copied a second time, move it to `core/shared`. By the third copy the copies have already drifted (the popover maths and the fill-height solve both reached three before extraction, and each copy had different bugs).
- **A shared function is not a shared answer.** Two pages calling the same metric still disagree if each loads its own rows. Share the **loader** too, and test that both pages count the same rows.
- **A date window must be about the right date.** Filtering certificates by issue date dropped five-year licences from a 400-day window. Ask what the date means for every row type before windowing.
- **Let the server decide business rules.** If JS filters rows by a rule ("at risk"), the server stamps the result on each row (e.g. `data-chips`) and JS only combines them.

## 4. Gating and emulation

- Use `can('capability')`, `@require(...)` or `@require_api(...)`. **Never a role literal** — a test fails new ones. `ROLE_LABELS` is the only role list; never retype role names in a template.
- **Gate every endpoint, not just the page.** A hidden sidebar link doesn't stop a typed URL. The JSON, fragment and save endpoints behind a gated page need the same check. When you add a gate, sweep the module for routes without one.
- Prefer the broad capability the page already uses (`view_workspace`) over inventing narrow ones per endpoint.
- A global feature that happens to live in a module folder (e.g. the Chat tray under `projects/`) is not module-scoped — don't gate it as if it were.
- Routes and the sidebar read the same access function, so what people see and what they can open never disagree.
- A temporary lock (e.g. `CLIENT_SERVICING_REVIEW_ONLY`) is a config flag on top of the roles, not a change to them.
- **Emulation ("view as"):** reads show the emulated user (`effective_user()`); writes and personal settings belong to the real user. Don't show edit controls whose save would land on someone else. Admin-only tools use `real_user=True` so an emulating admin keeps them, and each one needs a test that an emulating admin is refused.

## 5. SPA navigation (page scripts and links)

The app swaps `#main-content` on navigation and **re-runs the page's scripts on every visit**. `DOMContentLoaded` never fires again. Full detail: `core/shared/spa-navigation.md`.

- Wrap page JS in an IIFE and run it directly; don't wait for `DOMContentLoaded`.
- Server data in an inline script uses `var`, never `const`/`let` (a second visit throws and keeps stale data).
- **Guard anything bound to `window` or `document`** — it survives the swap and stacks on each visit. Listeners on elements inside `#main-content` are fine.
- Don't touch shell elements (`base.html` modals, trays) from a page script; scope selectors to your page.
- Never nest a `<main>` in a page — the fragment is cut at the first `</main>`. Use `<div class="module-main">`.
- A link handler that calls `preventDefault` must first let modified clicks through (`e.button !== 0`, Ctrl/Cmd/Shift/Alt).
- Links must match a real route exactly (trailing slashes matter). Build URLs with `url_for`; in JS reuse the rendered href.
- Module stylesheets load globally from `base.html`. A sheet in `{% block extra_css %}` never loads on a page reached by SPA nav.

## 6. CSS and theming

- **Tokens only.** Never hard-code a colour in a component; both themes are always defined. A module may define its own tokens in its own `:root` and `:root[data-theme="dark"]` blocks. `test_dark_mode_css.py` checks the swept files.
- **An undefined CSS variable fails silently** (`--font-heading` vs the real `--font-headline` went unnoticed in eight files). Use only tokens that exist.
- **A descendant selector is a hidden seam.** Anything a script moves at runtime is styled by a stamped attribute (`[data-popover-owner="…"]`), not through an ancestor id.
- Phone rules go under `@media (max-width: 48em)` in the module's CSS; shared ones in `core/shared/static/css/mobile.css`. Tables opt into phone cards with `.table--cards`.
- `STATIC_VERSION` (the `?v=` cache-buster) is computed automatically from file times at start-up. Restart the local server after CSS/JS edits.

## 7. Layout

**Heights**
- Flexbox does not fill the remaining viewport height here (`.main-content` has no definite height). Use `window.watchFillHeight(selector, cssVar)` from `core/shared/static/js/fill_height.js`, called outside any "already wired" guard.
- Avoid `min-height: calc(100vh - N)` floors. If CSS needs a pre-JS fallback, use a viewport fraction (`72vh`), not a magic offset.

**Cards and scrolling (the card-scroll rule)**
- Cards and list panels have a max height and **scroll inside**; the page fits one screen. Add `overscroll-behavior: contain` so scroll doesn't chain to the page.
- Exceptions: dense dashboard pages on a laptop may grow and let the page scroll (`min-height` from the fill solve, `height: auto`); **on phones nothing scrolls inside a card** — max-heights are lifted and the page scrolls.

**Scroll boxes**
- A sticky header and horizontal scroll can't share one element: give the box a real height and `overflow-y: auto` so the header sticks inside it.
- Capping a scroll box's height makes its native scrollbar always visible — don't add a custom one on top.
- `margin-left: auto` only pushes inside a flex row.

**Tables**
- Column width is set on the `<col>`, not the cell. Let long columns wrap.
- A header that both drags and clicks: track it in mousedown/mouseup and suppress the click after a real drag.
- Row actions go in a "⋯" menu, not a column of buttons.
- A saved per-user column layout freezes column order; changing the default order needs a migration that resets saved orders (keep widths).

**Popovers**
- `backdrop-filter`, `filter` and `transform` break `position: fixed` for descendants. Any floating UI uses `PopoverPosition` (`core/shared/static/js/popover_position.js`), which parks it on `<body>` while open.
- A popover on `<body>` is outside the page's delegated listeners: wire its items directly, and bind document/window close listeners once per session.

**Measure, don't theorise.** When a layout bug only happens for someone else, get a number off their screen (one console snippet) before changing code. A test harness must copy the real shell (`<main class="main-content">`, real footer) or it will confirm whatever you already believe.

## 8. Declared contracts

Some couplings break silently — e.g. JS binding to a template's ids and classes. At a seam like that:

- **Declare** the dependency as data in the consumer (`var TEMPLATE_CONTRACT = {...}` / `FRAGMENT_CONTRACT`), with a comment that a test reads it.
- Write one test that **parses the declaration** (never restates it) and checks the producer still satisfies it. The failure message says what to do.
- The same idea runs the route contract (`refactor/route_baseline.txt`) and the role-literal baseline. After adding or removing a route: `python -m app.modules.core.shared.tests.regen_route_baseline`, and check the diff shows only your routes.

## 9. Comments and docs

- Docstrings: what it does plus any non-obvious gotcha, **1–3 lines**. Explain *why*, not history. No dates, names, chunk numbers or "moved from X".
- Inline comments explain a non-obvious line, briefly. Never leave a comment claiming something that isn't true.
- A module's `<module>.md` is a short reference of how it works now — never a build log.

## 10. Testing

**Commands and helpers**
- Run `python -m pytest` (bare `pytest` can't import `app`). Run the whole suite before a push — some guards live in other modules.
- `login_as(client, app, user, password)` logs in through the real `/login`. `count_queries()` counts SQL statements: assert the count **doesn't grow with rows**, never an exact number.

**Traps**
- Fixtures use `db_session.flush()`, never `.commit()`.
- Put logged-out checks first in a test file (one run after `login_as` returned 404).
- A `Project(...)` without `project_status=` is a draft and shows in no active list.
- `projects.created_by_id` is NOT NULL in the database even though the model says nullable — set it in fixtures.
- Watch for fixture names that are substrings of each other.

**Test database**
`db.create_all()` adds missing tables but never missing columns. After any migration that adds or changes a column, run `python sync_test_db.py --confirm` (dry run without the flag). It also clears the local preview cache, which is keyed by ids that restart after a rebuild.

**Manual matrix — test the states you don't use yourself**
- Sidebar **collapsed and pinned** (the overlay's offset depends on it).
- Narrow, wide, phone width (below 48em), and once at 125% display scaling.
- Light and dark theme.
- Both ends of every scrollable list.
- A role that isn't admin (admin's wildcard hides gating mistakes).
- Arrive by SPA navigation **and** full page load, and visit two or three times in a row.

## 11. Design for non-technical users

Most OVP users aren't technical. Prefer obvious controls — visible buttons, chips, a "⋯" that is always visible — over hover-only actions or shortcut keys.
