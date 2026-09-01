# SPA Navigation — how page swaps work, and how not to break them

Read this before adding any new page-specific JS file, or any inline `<script>` that reads server data (e.g. `{{ ... | tojson }}`) in a template that a user can navigate to from the sidebar. It explains why the app doesn't do a full page reload when you click a sidebar link, and the traps that catches every new page unless you know about them.

## The short version (follow these 3 rules)

1. **Don't gate your init on `DOMContentLoaded`.** Wrap the file in a plain IIFE and call your init directly at the bottom. Reference: `achievements.js`, `client_directory.js`.
2. **Never declare embedded server data with `const` or `let` at the top level of an inline `<script>` — use `var`.** Any `const X = {{ ... | tojson }};` will throw on the second visit and silently leave stale data in place.
3. **Anything loaded once by `base.html` (like `main.js`) will not re-run on SPA nav.** If you're adding logic that needs to re-run per page, put it in the page's own script tag inside `{% block content %}`, not in `main.js`. See "Known unfixed" below.

## What "SPA nav" actually means here

When you click an internal link in the sidebar, the app **does not do a full page reload**. Instead, `sidebar.js`'s `navigateTo()`:

1. Fetches the target URL in the background with a `X-Nav-Request: 1` header.
2. Takes the returned HTML and swaps it into `<main id="main-content">` — replacing just that block.
3. Runs an `execScripts()` helper that walks the swapped-in HTML, finds every `<script>` tag, and re-executes it (by recreating the tag with `document.createElement('script')`, since a script inserted via `innerHTML` doesn't run on its own).

Two things follow from this and they cause every bug on this page:

- **Only the DOM inside `#main-content` is replaced.** Everything outside it — the sidebar, the header, and *all the JS globals* — stays exactly as it was. The browser never left the original page.
- **Scripts inside the swapped fragment re-run every visit; scripts loaded by `base.html` do not.** `base.html` loads once, on the first real page load, and then never again for the whole session.

That mismatch — DOM replaced, global scope not — is the root of every trap below.

## Trap 1 — page renders on hard reload, blank on sidebar nav

**What breaks:** you build a new page. Loading it directly (typing the URL, or a hard refresh) works fine. Clicking to it from the sidebar shows an empty page or the widgets don't wire up.

**Why:** your init code is inside `document.addEventListener('DOMContentLoaded', function () { ... })`. `DOMContentLoaded` fires **once** per real page load. On an SPA nav there's no new page load, so the event never fires again — your init never runs.

**Fix:** wrap the file in an IIFE and call init directly at the bottom, no event gate. This is safe because page-specific `<script>` tags are placed at the *end* of the content block, so by the time the script runs (either on a hard load, or when `execScripts()` re-runs it after an SPA swap), the DOM it needs is already there.

```js
// ❌ Doesn't work on SPA nav
document.addEventListener('DOMContentLoaded', function () {
  initMyPage();
});

// ✅ Works on both
(function () {
  function initMyPage() { /* ... */ }
  initMyPage();
})();
```

## Trap 2 — second visit shows stale data (silently)

**What breaks:** the page works the first time. Navigate away, come back, and the data on the page is from the *first* visit — old list, old permission flags, whatever the server sent originally. No error visible to the user.

**Why:** an inline `<script>` block declared the server data with `const` or `let` at the top level:

```html
<script>
  const CUSTOMERS = {{ customers | tojson }};
  // ...
</script>
```

`const`/`let` at script top level live in the browser's persistent global lexical scope. `execScripts()` re-runs the same `<script>` tag every navigation, so on visit 2 the browser throws `SyntaxError: Identifier 'CUSTOMERS' has already been declared`. That throw aborts *just that script block* — silently, no console error the user sees — and the value from visit 1 stays in place. The page looks like it's working; it's just wrong.

**Fix:** use `var`. `var` redeclaration is a legal no-op reassignment, which is exactly what we want — each navigation should overwrite the data with that request's fresh values.

```html
<!-- ❌ Throws on second visit -->
<script>
  const CUSTOMERS = {{ customers | tojson }};
  const EDIT_MODE = {{ edit_mode | tojson }};
</script>

<!-- ✅ Reassigns cleanly -->
<script>
  var CUSTOMERS = {{ customers | tojson }};
  var EDIT_MODE = {{ edit_mode | tojson }};
</script>
```

## Known unfixed — Trap 3: logic stuck in `main.js`

`main.js` (and anything else loaded from a `<script>` tag in `base.html` outside `{% block content %}`) is in the **persistent** part of the page. `execScripts()` never touches it. It runs once, on the session's first real page load, and never again.

`main.js` currently holds a lot of the brief form's real logic — autosave, `calculateCompletion`, deliverable pickers, the generic `#sectionBasics` change listener — all inside a single `DOMContentLoaded` handler. That handler runs once on first load. If the user reaches the brief form via SPA nav (including browser Back/Forward, which uses `popstate` and takes the same SPA path), none of that setup runs against the freshly-swapped-in form.

This is **not** a drive-by fix — `main.js` is big, and converting its one-shot handler into something safely re-invocable per navigation (without duplicating listeners, resetting module-level state like `currentDraftId` and `autosaveTimeout`, etc.) needs its own scoped task. Flag this if the brief form needs work again, or if asked to sweep this bug class across the app.

**Rule for new work:** if the logic needs to re-run per page, put it in the page's own script tag inside `{% block content %}`. Don't add to `main.js`.

## Checklist when adding a new page or page-specific JS

Before considering it done, check both:

1. **Init not gated behind `DOMContentLoaded`?** If the page can be reached via a sidebar link (any internal `<a class="sidebar-item--nav">`-style link), the file must be an IIFE that calls init directly, per Trap 1. Copy the pattern from `achievements.js` or `client_directory.js`.
2. **No `const`/`let` at inline-script top level for embedded data?** All `{{ ... | tojson }}` values assigned at top level must use `var`, per Trap 2.

## History

- **9 Jul 2026** — Both traps discovered while wiring the Client Directory page into the sidebar. Fixed same day: `app/templates/projects/create.html`'s six top-level consts (`CUSTOMERS_BY_REGION`, `EDIT_MODE`, `EDIT_PROJECT_ID`, `EXISTING_CUSTOMERS`, `EXISTING_DELIVERABLES`, `EXISTING_STANDARD_DELIVERABLES`) switched to `var`.
- **Trap 3 (`main.js`)** — identified, not fixed. Left as a known limitation until the brief form needs work.
