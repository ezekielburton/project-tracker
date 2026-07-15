// app/static/js/dashboard.js
//
// Role-based dashboard. Tab strip + single interactive content area (see
// the big comment on .dash-content-tabs/.dash-content-area in
// dashboard.css, redesigned 15 Jul 2026), filter chips, the Flag to
// Management modal, and SSE live-updates — each added in its own section
// of this file rather than replacing what came before.
//
// This page is reachable via the SPA sidebar nav (sidebar.js swaps
// #main-content's innerHTML and re-executes any <script> tags found in it —
// see execScripts() there). That means this whole IIFE can run more than
// once per browser session if the user navigates away and back without a
// full reload. State-restoring code (initCards) is SAFE to rerun — it just
// syncs inline max-height to whatever the server rendered as .expanded on
// this particular load. Event listeners are NOT safe to rerun: attaching
// document.addEventListener() again on a second run would stack a duplicate
// handler on top of the first (same class of bug CLAUDE.md's achievements
// system hit with _helixBound). window._dashboardListenersBound guards
// against that — listeners attach exactly once per page session, ever.

(function () {
    'use strict';

    // ── Management view-switcher: scope-aware fetch helper ──────────────
    // Added 11 Jul 2026 alongside the ?scope= tab bar in dashboard.html
    // (see the big comment on _resolve_dashboard_scope() in
    // app/routes/dashboard.py). HELIX_DASH_SCOPE is a page-level var set
    // by that template — null/undefined for every role except management,
    // in which case this is a no-op and every URL below is untouched.
    // Every dashboard.js fetch that re-queries card data (filter clicks,
    // SSE live-refresh) needs to carry the SAME scope the page loaded
    // with, or a management user previewing a CS lead's tab would see
    // that tab's cards silently repopulate with the unfiltered "All
    // Projects" data the moment they click a filter pill or an SSE event
    // fires.
    function withDashScope(url) {
        if (typeof HELIX_DASH_SCOPE === 'undefined' || !HELIX_DASH_SCOPE) return url;
        var sep = url.indexOf('?') === -1 ? '?' : '&';
        return url + sep + 'scope=' + encodeURIComponent(HELIX_DASH_SCOPE);
    }

    // Client-side mirror of decisions.html's `effective_role in ('admin',
    // 'management')` gate — see renderDecisionRow() below, which needs to
    // decide whether to include the Resolve button when it rebuilds a row
    // after a live refresh (SSR only runs once, on page load). Reads
    // HELIX_EFFECTIVE_ROLE, a page-level var set by dashboard.html
    // alongside HELIX_DASH_SCOPE.
    function isManagementOrAdmin() {
        return typeof HELIX_EFFECTIVE_ROLE !== 'undefined' &&
            (HELIX_EFFECTIVE_ROLE === 'admin' || HELIX_EFFECTIVE_ROLE === 'management');
    }

    // ── Smooth expand/collapse via JS-measured max-height ────────────────
    // Added 12 Jul 2026 (second pass, replacing a CSS-only grid-template-
    // rows attempt from earlier the same day) — see the big comment on
    // .dash-card-body-content in dashboard.css for the full history: a
    // fixed max-height (9999px) animated at a constant rate across the
    // whole range so the visible portion barely moved, and the grid-rows
    // trick that replaced it didn't reliably collapse to zero height in
    // every browser, leaving body content visible and unboxed even when
    // "closed". Measuring the real height with JS and animating max-height
    // to that exact pixel value avoids both problems.
    //
    // bodyEl is always a .dash-card-body-content element (see
    // dashboard.css) — every card, Summary included as of the 15 Jul 2026
    // tab-strip redesign, shares this one body wrapper class now, so
    // there's nothing else these two helpers need to branch on.
    function expandBody(bodyEl) {
        if (!bodyEl) return;
        // Add .expanded FIRST — for tile bodies this turns on
        // .dash-card-body-visual's padding/shadow (see dashboard.css),
        // and scrollHeight needs to measure that fully-styled state, not
        // a smaller pre-expansion one.
        bodyEl.classList.add('expanded');
        bodyEl.style.maxHeight = bodyEl.scrollHeight + 'px';
    }

    // Re-measures an already-expanded tile body's max-height after its
    // content changes WITHOUT a full open/close cycle — e.g. an AJAX fetch
    // swapping in a longer or shorter list. expandBody() only captures
    // scrollHeight once, at the moment a tile opens; it has no way to know
    // the content inside changed afterward, so if a later fetch renders
    // something taller than that original snapshot, the extra content is
    // silently clipped by the same overflow: hidden that makes the
    // open/close animation work in the first place. Real bug (13 Jul 2026,
    // per Ezekiel, after the request-sequencing fix above didn't fully
    // resolve it: "It still doesn't always load the full list on Other's
    // Actions") — the data was always there, it was just visually clipped
    // whenever the fetched list was taller than whatever content originally
    // set the max-height (My Actions on first tile-open, or an even
    // shorter still-collapsed measurement). No-op if the body isn't
    // currently expanded — nothing visible to fix in that case.
    function remeasureExpandedBody(bodyEl) {
        if (bodyEl && bodyEl.classList.contains('expanded')) {
            bodyEl.style.maxHeight = bodyEl.scrollHeight + 'px';
        }
    }

    function collapseBody(bodyEl) {
        if (!bodyEl) return;
        // Give max-height a concrete starting pixel value before dropping
        // it to 0 — without this, a body that was server-rendered
        // .expanded and never had JS set an inline height yet (see
        // initCards() below) would have nothing to transition FROM and
        // would just snap shut instead of animating.
        bodyEl.style.maxHeight = bodyEl.scrollHeight + 'px';
        // Setting max-height to its own current value and then straight to
        // 0 in the same synchronous block would collapse into one style
        // recalc with nothing to interpolate between — the browser needs
        // to actually PAINT the "open" value at least once before the next
        // change can animate. requestAnimationFrame guarantees that.
        requestAnimationFrame(function () {
            bodyEl.style.maxHeight = '0px';
        });
        // Only strip .expanded once the height transition has actually
        // finished — removing it immediately would make a tile body lose
        // its card padding/shadow WHILE still visibly shrinking, which
        // looks broken rather than smooth.
        bodyEl.addEventListener('transitionend', function handler(e) {
            if (e.propertyName !== 'max-height') return;
            bodyEl.classList.remove('expanded');
            bodyEl.removeEventListener('transitionend', handler);
        });
    }

    // ── initCards() ───────────────────────────────────────────────────
    //
    // Simplified 15 Jul 2026 redesign — every card (Summary included) is
    // now a tab+body pair with NO localStorage persistence at all; AT MOST
    // one tab is active on any given page load, decided purely by the
    // server (initial_expanded_card — see index() in dashboard.py). As of
    // 16 Jul 2026, per Ezekiel ("have it hidden until a user selects a
    // tab"), there's no default fallback anymore — initial_expanded_card
    // is None unless a ?view= deep link maps to a real card, so on a
    // normal page load NO tab is active and this loop simply finds
    // nothing to sync, leaving .dash-content-area collapsed to zero
    // height until the user clicks a tab. This function otherwise still
    // does the same one-time sync of inline max-height to whatever
    // .expanded the server DID render (deep-link case), so that tab's
    // body appears instantly at its full height on first paint instead of
    // growing into place (the visible height comes from an inline style
    // JS sets, not a CSS rule keyed off the class — without this sync it
    // would render visually collapsed despite having .expanded on it).
    // Also covers the two toggle boxes below (Overdue/At Risk, My Day/My
    // Week), which ARE still open by default and share this same class.
    function initCards() {
        document.querySelectorAll('.dash-card-body-content.expanded').forEach(function (body) {
            body.style.maxHeight = body.scrollHeight + 'px';
        });
    }

    // ── Due card: filter pills ────────────────────────────────────────
    //
    // The Due card's list is server-rendered on first page load (see
    // due.html / due_default in dashboard.py). Clicking a filter pill
    // (Overdue / Due Today / Due This Week) re-fetches from
    // GET /dashboard/api/due?filter=<value> and replaces the list
    // client-side — no page reload, matches the spec.
    //
    // renderDueRow() below is a HAND-WRITTEN JS MIRROR of the
    // dash_due_row(item) Jinja macro in _dashboard_macros.html. Jinja
    // macros only run server-side, so there's no way to literally share
    // the template between the initial SSR render and this client-side
    // re-render — if you change what a due row looks like, you must
    // change BOTH this function and that macro, or the two will drift
    // apart visually. This comment is duplicated in both places on purpose.

    // Minimal HTML-escaping for text we're inserting via innerHTML — project
    // names, guidance text, etc. come from the database and could contain
    // characters like & or < that would otherwise break the markup or
    // (worse) get interpreted as HTML. Using the browser's own escaping
    // (set textContent, read back innerHTML) rather than a hand-rolled
    // regex replace, so it's exactly as correct as the browser's own DOM.
    function escapeHtml(str) {
        var div = document.createElement('div');
        div.textContent = (str === null || str === undefined) ? '' : String(str);
        return div.innerHTML;
    }

    // Builds one ".dash-mini-stat" span — dot + bold number + label — the
    // RAG-only collapsed-card header format added 12 Jul 2026 (see the big
    // comment on .dash-mini-stat in dashboard.css). color is 'red' |
    // 'yellow' | 'green'; every live-refreshed card summary below builds
    // its pills through this one helper so they can't drift from each
    // other's markup shape. Pass value === null to omit the number entirely
    // (used for the Clashing Projects card's zero-clash "No Clashes" state,
    // which has nothing to count).
    function miniStat(color, value, label) {
        var valueHtml = value === null
            ? ''
            : '<span class="dash-mini-stat-value">' + value + '</span>';
        return '<span class="dash-mini-stat dash-mini-stat--' + color + '">' +
            '<span class="dash-mini-stat-dot"></span>' +
            valueHtml +
            '<span class="dash-mini-stat-label">' + escapeHtml(label) + '</span>' +
            '</span>';
    }

    // Small shared helper for the two toggle boxes (Overdue/At Risk and My
    // Day/My Week — added 15 Jul 2026, later still, see toggle_overdue_
    // at_risk.html/toggle_my_day_week.html) — each box has TWO view-switch
    // buttons, each carrying its own .dash-mini-stat badge (no shared
    // box-level badge the way tab-strip cards have one). Finds the button
    // matching (boxKey, view) and swaps its badge's outerHTML via
    // miniStat(), same "replace the whole mini-stat span" approach every
    // other live-refresh block on this page uses. Label is always '' — the
    // button's own text already says what the number means (see the SSR
    // template, which never renders a label span at all for these).
    // No-op (same as every other `if (el)` guard in this file) if the
    // button isn't found — harmless on a page where a role's card_order
    // doesn't happen to include one of these (shouldn't happen today, both
    // boxes render for every role, but matches the defensive convention
    // used everywhere else here).
    function toggleBoxBadge(boxKey, view, color, value) {
        var btn = document.querySelector(
            '[data-toggle-box="' + boxKey + '"] .dash-toggle-box-btn[data-view="' + view + '"]'
        );
        if (!btn) return;
        var badge = btn.querySelector('.dash-mini-stat');
        if (badge) badge.outerHTML = miniStat(color, value, '');
    }

    // Mirrors dash_person_chip() in _dashboard_macros.html — avatar+name
    // chip, or a .dash-risk-tag when `person` is falsy and a label was
    // given. missingClass defaults to the plain rose .dash-risk-tag (CS
    // Missing); renderDueRow() below passes the --red modifier for
    // designer-missing tags specifically (13 Jul 2026, per Ezekiel: "make
    // the designer missing tags red" — see .dash-risk-tag--red in
    // dashboard.css). NOTE: avatar src is hardcoded to /static/avatars/,
    // same "JS has no url_for" reasoning as the /projects/ link below.
    function personChip(person, missingLabel, missingClass) {
        if (person) {
            var avatarInner = person.avatar_filename
                ? '<img src="/static/avatars/' + encodeURIComponent(person.avatar_filename) + '" alt="">'
                : '<span class="dash-person-avatar-initials">' + escapeHtml(person.name.charAt(0).toUpperCase()) + '</span>';
            return '<span class="dash-person-chip">' +
                '<span class="dash-person-avatar">' + avatarInner + '</span>' +
                '<span class="dash-person-name">' + escapeHtml(person.name) + '</span>' +
                '</span>';
        }
        if (missingLabel) {
            return '<span class="' + (missingClass || 'dash-risk-tag') + '">' + escapeHtml(missingLabel) + '</span>';
        }
        return '';
    }

    // Mirrors dash_row_people() in _dashboard_macros.html (extracted 13 Jul
    // 2026 alongside that macro) — CS lead chip first, then one chip per
    // assigned designer or a red missing-team tag. Only renderDueRow()
    // below calls this today (At Risk/Clashing Projects got the same chips
    // added the same day, but those two cards' row lists have no JS mirror
    // — see their card partials' docstrings), kept as its own function
    // anyway so a future JS mirror for either card can reuse it.
    function personPeopleRow(csLead, designers) {
        var people = personChip(csLead, 'CS Missing');
        (designers || []).forEach(function (teamEntry) {
            if (teamEntry.users && teamEntry.users.length) {
                teamEntry.users.forEach(function (u) { people += personChip(u); });
            } else {
                people += personChip(null, teamEntry.missing_label, 'dash-risk-tag dash-risk-tag--red');
            }
        });
        return '<span class="dash-row-people">' + people + '</span>';
    }

    // Builds the exact same markup dash_due_row() produces server-side —
    // see the comment above this section for why these two must be kept in
    // sync. REDESIGNED 13 Jul 2026 alongside the macro: guidance/owner
    // pills are gone, replaced by a person-chip row (CS lead + per-team
    // designers or missing-team tags, from item.cs_lead/item.designers —
    // see _due_row_people() in dashboard.py) under the title, and a
    // right-hand "Next Action" block (item.guidance, sized up) instead of
    // the old inline .dash-action-tag pill. item.owner is still present on
    // the payload but no longer rendered here.
    //
    // Title INVERTED same day, per Ezekiel: "Invert the text so that
    // deliverable is first and bold, project is second and grey" — was
    // project (bold, main) — deliverable/customer (grey, detail); now
    // deliverable/customer (bold, main) — project (grey, detail). A plain
    // project-level row (item.type === 'project') has nothing to invert.
    function renderDueRow(item) {
        var title;
        if (item.type === 'deliverable') {
            title = escapeHtml(item.deliverable_name) + ' <span class="dash-row-title-detail">— ' + escapeHtml(item.project_name) + '</span>';
        } else if (item.type === 'customer' && item.customer_name) {
            title = escapeHtml(item.customer_name) + ' <span class="dash-row-title-detail">— ' + escapeHtml(item.project_name) + '</span>';
        } else {
            title = escapeHtml(item.project_name);
        }

        var people = personPeopleRow(item.cs_lead, item.designers);

        // NOTE: this URL is hardcoded to match project_detail.detail's
        // route (/projects/<id>) rather than built with Flask's url_for —
        // JS has no access to url_for, it only exists at Jinja render
        // time. If that route's URL pattern ever changes, this must be
        // updated to match by hand.
        //
        // .dash-row-date (was a coloured .rag-badge rag-<colour> pill) and
        // .dash-row-next-action-tag (was plain .dash-row-next-action-text)
        // both changed 13 Jul 2026, same-day follow-up — see the matching
        // comment on dash_due_row() in _dashboard_macros.html and the CSS
        // comments on .dash-row-date/.dash-row-next-action-tag.
        //
        // "No deadline" fallback added same day when Next Actions started
        // reusing this function — Due's own rows never have a null
        // deadline (only overdue items reach this card), but Next Actions
        // rows can (e.g. a project still 'in_queue' with no deliverable
        // deadlines set yet). Harmless no-op for Due since item.deadline
        // is always truthy there.
        return '<a class="dash-row" href="/projects/' + item.project_id + '?from=dashboard">' +
            '<span class="dash-row-date">' + escapeHtml(item.deadline || 'No deadline') + '</span>' +
            '<span class="dash-row-main">' +
            '<span class="dash-row-title">' + title + '</span>' +
            people +
            '</span>' +
            '<span class="dash-row-next-action">' +
            '<span class="dash-row-next-action-label">Next Action</span>' +
            '<span class="dash-row-next-action-tag">' + escapeHtml(item.guidance) + '</span>' +
            '</span>' +
            '</a>';
    }

    function fetchAndRenderDue(filterValue) {
        var container = document.getElementById('dash-due-list');
        if (!container) return;

        fetch(withDashScope('/dashboard/api/due?filter=' + encodeURIComponent(filterValue)))
            .then(function (r) { return r.json(); })
            .then(function (items) {
                if (!items.length) {
                    // Only ever called with 'overdue' now (see the SSE
                    // refresh call site below) — fixed copy instead of the
                    // old generic "Nothing matches this filter." text.
                    container.innerHTML = '<p class="dash-empty-state">Nothing overdue this week.</p>';
                } else {
                    container.innerHTML = items.map(renderDueRow).join('');
                }
                // Same fix as fetchAndRenderNextActions() (13 Jul 2026) —
                // see remeasureExpandedBody()'s big comment: an SSE-
                // triggered refresh could grow this list past whatever
                // height was captured when the box was last opened, and
                // without this the extra rows would be silently clipped by
                // the collapse mechanic's overflow: hidden.
                //
                // Went through TWO ownership changes since: while Overdue
                // briefly lived in the always-visible pinned section (15
                // Jul 2026, mode='static' — see git history), this was a
                // permanent no-op (no .dash-card-body-content ancestor
                // existed for that markup at all). Now that Overdue lives
                // in the Overdue/At Risk toggle box (15 Jul 2026, later
                // still — see toggle_overdue_at_risk.html), the ancestor
                // exists again — the toggle box's own collapse mechanic
                // reuses .dash-card-body-content — so this call is live and
                // meaningful once more, no code change needed to make that
                // true, just the ancestor coming back into existence.
                remeasureExpandedBody(container.closest('.dash-card-body-content'));
            })
            .catch(function () {
                // Network blip — leave whatever list was already showing
                // rather than blanking it out. Matches polling.js's
                // "silently skip on failure" convention elsewhere in this app.
            });
    }

    // ── Decisions Needed card + Flag to Management modal ────────────────
    //
    // JS mirror of the dubai_time Jinja filter (app/__init__.py). Needed
    // here (not just server-side) because refreshDecisionsCard() below
    // re-renders rows from raw JSON after a flag is submitted, and the
    // /dashboard/api/decisions endpoint returns raised_at as a plain ISO
    // string — the dubai_time filter only runs at Jinja render time, so
    // the client-side re-render has to do its own UTC -> Dubai (UTC+4,
    // fixed offset, matches CLAUDE.md's DB Facts on why this app uses a
    // fixed offset instead of ZoneInfo) conversion by hand.
    function formatDubaiTime(isoString) {
        if (!isoString) return '_';
        // Python's naive datetime.isoformat() has no trailing 'Z' or
        // offset — appending 'Z' here forces the browser to parse it as
        // UTC instead of local time, matching how the Python filter
        // treats string input (dt.replace(tzinfo=timezone.utc)).
        var utcMs = new Date(isoString + 'Z').getTime();
        var dubai = new Date(utcMs + 4 * 60 * 60 * 1000);
        var months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        var pad = function (n) { return String(n).padStart(2, '0'); };
        return pad(dubai.getUTCDate()) + ' ' + months[dubai.getUTCMonth()] + ' ' + dubai.getUTCFullYear() +
            ', ' + pad(dubai.getUTCHours()) + ':' + pad(dubai.getUTCMinutes());
    }

    // Hand-written JS mirror of the row markup in decisions.html — same
    // duplication tradeoff documented on renderDueRow() above (Jinja
    // macros only run server-side, so there's no way to share the literal
    // template between SSR and this client-side re-render). Keep both in
    // sync if you change what a decision row looks like. Reworked 10 Jul
    // 2026 alongside decisions.html: raised-by and days-waiting are now
    // tags (.dash-owner-tag / .dash-action-tag) instead of stacked plain
    // text; the raised-at timestamp stays plain on the right as a stamp.
    // Resolve button (added 13 Jul 2026, admin/management only — mirrors
    // decisions.html's .dash-decision-row wrapper and its `effective_role
    // in ('admin', 'management')` gate). See isManagementOrAdmin() near
    // withDashScope() above, which reads HELIX_EFFECTIVE_ROLE — a
    // page-level var dashboard.html sets for exactly this purpose.
    function renderDecisionRow(item) {
        var tags = '';
        if (item.raised_by) tags += '<span class="dash-owner-tag">' + escapeHtml(item.raised_by.name) + '</span>';
        if (item.days_waiting !== null && item.days_waiting !== undefined) {
            tags += '<span class="dash-action-tag">' + item.days_waiting + ' day' + (item.days_waiting !== 1 ? 's' : '') + ' waiting</span>';
        }

        // Same hardcoded-URL caveat as renderDueRow() above — no url_for()
        // available client-side.
        var row = '<a class="dash-row" href="/projects/' + item.project_id + '?from=dashboard">' +
            '<span class="dash-row-main">' +
            '<span class="dash-row-title">' + escapeHtml(item.project_name) + '</span>' +
            '<span class="dash-row-sub">' + escapeHtml(item.note) + '</span>' +
            '<span class="dash-row-tags">' + tags + '</span>' +
            '</span>' +
            '<span style="text-align:right; flex-shrink:0; font-size:0.8rem; color:var(--grey-dark);">' +
            escapeHtml(formatDubaiTime(item.raised_at)) + '</span>' +
            '</a>';

        var resolveBtn = isManagementOrAdmin()
            ? '<button type="button" class="dash-resolve-btn" data-action="resolve-decision" data-project-id="' + item.project_id + '">✓ Resolve</button>'
            : '';

        return '<div class="dash-decision-row">' + row + resolveBtn + '</div>';
    }

    // Resolves a flagged decision: confirm, POST, then re-fetch the queue
    // via refreshDecisionsCard() (same pattern submitFlagManagement() uses
    // after raising a flag — see above) rather than manually removing just
    // this one row from the DOM, so the collapsed mini-stat count and the
    // expanded list can never drift out of sync with each other.
    function resolveDecision(projectId, btn) {
        if (!confirm('Mark this decision as resolved?')) return;
        if (btn) btn.disabled = true;
        fetch('/projects/' + projectId + '/resolve-decision', { method: 'POST' })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    showToast('Decision resolved', 'success');
                    refreshDecisionsCard();
                } else {
                    showToast(data.error || 'Could not resolve this decision', 'error');
                    if (btn) btn.disabled = false;
                }
            })
            .catch(function () {
                showToast('Something went wrong', 'error');
                if (btn) btn.disabled = false;
            });
    }

    // Re-fetches the whole queue after a successful flag submission and
    // rebuilds BOTH the collapsed count (always) and the expanded row list
    // (only if the card happens to be open right now — dash-decisions-list
    // won't exist in the DOM otherwise, hence the null check). A newly
    // flagged project is essentially always a different project than the
    // ones already showing, so a full replace is simpler and always
    // correct — same reasoning fetchAndRenderDue() uses for the Due card.
    function refreshDecisionsCard() {
        fetch(withDashScope('/dashboard/api/decisions'))
            .then(function (r) { return r.json(); })
            .then(function (items) {
                var tab = document.querySelector('.dash-content-tab[data-card="decisions"]');
                var summaryEl = tab ? tab.querySelector('.dash-content-tab-badge') : null;
                if (summaryEl) {
                    // Matches decisions.html's decisions_summary block
                    // (reworked 12 Jul 2026 — RAG mini-stat, red/green by
                    // count, instead of a rag-badge pill). Keep in sync.
                    summaryEl.innerHTML = miniStat(items.length > 0 ? 'red' : 'green', items.length, 'Flagged');
                }

                var list = document.getElementById('dash-decisions-list');
                if (!list) return; // card isn't expanded right now — nothing else to update
                list.innerHTML = items.length
                    ? items.map(renderDecisionRow).join('')
                    : '<p class="dash-empty-state">No decisions currently needed.</p>';
                // Same fix as fetchAndRenderNextActions()/fetchAndRenderDue()
                // (13 Jul 2026) — see remeasureExpandedBody()'s big comment.
                remeasureExpandedBody(list.closest('.dash-card-body-content'));
            })
            .catch(function () {
                // Network blip — same "leave it stale" convention as
                // fetchAndRenderDue() above.
            });
    }

    // Tracks which project the Flag to Management modal already knows
    // about, if any — set by openFlagManagementModal(projectId, ...) when
    // called WITH arguments. Only relevant for a future per-project
    // trigger (e.g. a "Flag to Management" button on the project detail
    // page) — see the big comment on the modal markup in dashboard.html
    // for why the modal needs to support both "project already known" and
    // "user must pick one" modes. THIS chunk only wires up the second
    // mode (the Decisions Needed card's shortcut, which calls this
    // function with no arguments), so _flagManagementProjectId stays null
    // for every real code path right now — it exists so the modal doesn't
    // need rework when that future trigger is added.
    var _flagManagementProjectId = null;

    function openFlagManagementModal(projectId, projectName) {
        var overlay = document.getElementById('flag-management-modal');
        var selectEl = document.getElementById('flag-management-project-select');
        var readonlyEl = document.getElementById('flag-management-project-readonly');
        var noteEl = document.getElementById('flag-management-note');
        var errorEl = document.getElementById('flag-management-error');
        if (!overlay) return;

        // Reset on every open — otherwise cancelling and reopening would
        // show the previous attempt's leftover note text or error message.
        noteEl.value = '';
        errorEl.classList.add('hidden');
        errorEl.textContent = '';

        if (projectId) {
            _flagManagementProjectId = projectId;
            readonlyEl.textContent = projectName || '';
            readonlyEl.classList.remove('hidden');
            selectEl.classList.add('hidden');
        } else {
            _flagManagementProjectId = null;
            selectEl.value = '';
            selectEl.classList.remove('hidden');
            readonlyEl.classList.add('hidden');
        }

        overlay.classList.remove('hidden');

        // See CLAUDE.md's "Polling — pause during modals" pattern. This is
        // a harmless no-op on THIS page right now — polling.js doesn't
        // recognise the new dashboard yet (Task #17, the SSE integration
        // chunk, extends it to), so there's no active stream here for
        // pause() to tear down. Calling it anyway costs nothing and means
        // this modal is already correct/spec-compliant the moment that
        // chunk lands, instead of needing to remember to add it later.
        if (window.helixPolling) window.helixPolling.pause();
    }

    function closeFlagManagementModal() {
        var overlay = document.getElementById('flag-management-modal');
        if (overlay) overlay.classList.add('hidden');
        if (window.helixPolling) window.helixPolling.resume();
    }

    function submitFlagManagement() {
        var selectEl = document.getElementById('flag-management-project-select');
        var noteEl = document.getElementById('flag-management-note');
        var errorEl = document.getElementById('flag-management-error');

        var projectId = _flagManagementProjectId || selectEl.value;
        var note = noteEl.value.trim();

        if (!projectId) {
            errorEl.textContent = 'Please select a project.';
            errorEl.classList.remove('hidden');
            return;
        }
        if (!note) {
            errorEl.textContent = 'Please describe what decision or information is needed.';
            errorEl.classList.remove('hidden');
            return;
        }

        fetch('/projects/' + projectId + '/flag-management', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ decision_note: note })
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.success) {
                    errorEl.textContent = data.error || 'Something went wrong.';
                    errorEl.classList.remove('hidden');
                    return;
                }
                // This modal is a direct submit-then-close flow, not a
                // "confirm this pending action" one — there's no separate
                // stored callback to save before closing here, so
                // CLAUDE.md's "save the callback before calling close"
                // pitfall doesn't apply. Still closing BEFORE toasting so
                // the modal is visibly gone the moment the toast appears,
                // rather than the two happening in a jarring simultaneous
                // flash.
                closeFlagManagementModal();
                showToast('Management has been notified', 'success');
                refreshDecisionsCard();
            })
            .catch(function () {
                errorEl.textContent = 'Something went wrong. Please try again.';
                errorEl.classList.remove('hidden');
            });
    }

    // ── Next Actions card: My Actions / Others' Actions toggle ──────────
    //
    // Two-way toggle (not a multi-select filter set like the Due card's
    // three pills) — exactly one of "My Actions" / "Others' Actions" is
    // ever active. The 'mine' list is server-rendered on page load (see
    // next_actions_default in dashboard.py); clicking "Others' Actions"
    // fetches GET /dashboard/api/next-actions?filter=others and replaces
    // the list, same pattern as fetchAndRenderDue() above. Clicking back
    // to "My Actions" re-fetches too, rather than caching the original
    // SSR content — simpler, and the extra request is cheap.
    //
    // Row layout matched to Overdue (13 Jul 2026, per Ezekiel: "make the
    // layout of the rows match Overdue layout") — this card no longer has
    // its own bespoke row markup or render function. next_actions.html now
    // calls dash_due_row(item) directly and this JS mirror calls
    // renderDueRow(item) directly (see that macro/function's own big
    // comments for the row shape: date+divider, CS lead/designer person
    // chips, right-hand pine "Next Action" tag). The old owner tag
    // ("Assigned to: X", previously shown only on the Others' Actions tab)
    // and the separate flat missing_designer_tags chips are both gone —
    // CS lead/designer person chips now cover both: who's relevant to the
    // project, and which teams are unstaffed (red fallback chips), same
    // "one missing-designer indicator per row" rule the At Risk card's
    // duplicate-tag fix established. item.owner/item.owner_role are still
    // computed server-side (_is_owner() needs them to split mine/others)
    // but, like Due's own rows, are no longer rendered — renderNextActionRow()
    // and ownerNames() are gone; if you're looking for them, check git
    // history around 13 Jul 2026.

    // Guards against a real race condition (fixed 13 Jul 2026, per
    // Ezekiel: "clicking other's actions sometimes doesn't load the full
    // details"). fetchAndRenderNextActions() had no way to know if a
    // response it was about to render was still the one the user actually
    // wanted. Two ways this went wrong: (1) rapid tab clicking — "Others'"
    // then quickly back to "Mine" — where the network reorders the two
    // responses and the slower "Others'" response lands last, silently
    // showing the wrong (or, from the user's perspective, incomplete/
    // stale-looking) list under the now-active "Mine" tab; (2) an
    // SSE-triggered background refresh (see refreshDashboardFromSSE()
    // below) landing mid-flight against a manual tab click. This is the
    // one card left where it can actually happen — fetchAndRenderDue()
    // has the identical gap in its own code, but Due's filter is pinned
    // to a single fixed value now (see its fourth follow-up in
    // CLAUDE.md), so there's no second filter value left for a race to
    // manifest against there. nextActionsRequestSeq is bumped on every
    // call; a response is only rendered if it's still the most recent
    // request issued when it comes back.
    var nextActionsRequestSeq = 0;

    function fetchAndRenderNextActions(filterType) {
        var container = document.getElementById('dash-next-actions-list');
        if (!container) return;

        var requestSeq = ++nextActionsRequestSeq;

        fetch(withDashScope('/dashboard/api/next-actions?filter=' + encodeURIComponent(filterType)))
            .then(function (r) { return r.json(); })
            .then(function (items) {
                if (requestSeq !== nextActionsRequestSeq) return; // superseded by a newer request — discard

                if (!items.length) {
                    container.innerHTML = '<p class="dash-empty-state">' +
                        (filterType === 'mine' ? 'Nothing needs your action right now.' : 'Nothing is currently waiting on anyone else.') +
                        '</p>';
                } else {
                    container.innerHTML = items.map(renderDueRow).join('');
                }
                // See remeasureExpandedBody()'s big comment above — without
                // this, a longer "Others'" list than whatever content last
                // set the tile's max-height gets silently clipped.
                remeasureExpandedBody(container.closest('.dash-card-body-content'));
            })
            .catch(function () {
                // Same "leave it stale on a network blip" convention as
                // fetchAndRenderDue() above.
            });
    }

    // ── Clashing Projects card: By Deliverable / By Project toggle ──────
    //
    // Both panels are already fully server-rendered (see clashes.html) —
    // clash lists are always small, so unlike the Due/Next Actions/
    // Decisions cards there's no separate fetch here, just show/hide
    // between two pre-built blocks. This is its own small, independent
    // function (not shared with anything else on the page) since it
    // targets a specific pair of elements ([data-clashes-panel]) scoped to
    // this one card.
    function switchClashesTab(filterValue) {
        document.querySelectorAll('[data-action="clashes-tab"]').forEach(function (btn) {
            btn.classList.toggle('active', btn.dataset.filter === filterValue);
        });
        document.querySelectorAll('[data-clashes-panel]').forEach(function (panel) {
            panel.classList.toggle('hidden', panel.dataset.clashesPanel !== filterValue);
        });
    }

    // ── Toggle boxes: Overdue/At Risk (left) + My Day/My Week (right) ───
    // (added 15 Jul 2026, later still — see toggle_overdue_at_risk.html/
    // toggle_my_day_week.html for the full markup/mechanic writeup)
    //
    // switchToggleBoxView() — same "both panels already fully
    // server-rendered, just show/hide" idea as switchClashesTab() directly
    // above, generalized to work for EITHER box via a boxKey param (Clashes
    // only ever needed one instance of this pattern; these two boxes need
    // two INDEPENDENT instances, so a shared parameterized function beats
    // copy-pasting switchClashesTab() twice). Queries are scoped with
    // `[data-toggle-box="boxKey"]` so switching the view inside one box
    // never touches the other box's buttons/panels.
    function switchToggleBoxView(boxKey, view) {
        var box = document.querySelector('[data-toggle-box="' + boxKey + '"]');
        if (!box) return;
        box.querySelectorAll('.dash-toggle-box-btn').forEach(function (btn) {
            btn.classList.toggle('active', btn.dataset.view === view);
        });
        box.querySelectorAll('[data-toggle-view-panel]').forEach(function (panel) {
            panel.classList.toggle('hidden', panel.dataset.toggleViewPanel !== view);
        });
        // Real bug, fixed 16 Jul 2026: swapping panels changes the body's
        // real content height (e.g. "Today" empty-state vs. a taller
        // "This Week" list with several rows), but the outer
        // .dash-card-body-content's max-height is an inline pixel value
        // captured ONCE by expandBody() when the box was opened — same
        // "stale measurement" root cause as remeasureExpandedBody()'s big
        // comment near the top of this file (AJAX-swapped Due/Next
        // Actions lists, the tt-deliverables <details> listener). Without
        // this, switching to a taller panel gets clipped by the shorter
        // panel's old max-height, and because overflow:hidden clips
        // mid-row rather than hiding it cleanly, the cut-off row visually
        // overlaps the row above it. No-ops if the box is currently
        // collapsed (nothing visible to fix — toggleBoxCollapse's own
        // expandBody() call captures a fresh height next time it opens).
        remeasureExpandedBody(box.querySelector('[data-toggle-box-body="' + boxKey + '"]'));
    }

    // toggleBoxCollapse() — independent per-box collapse/expand, NOT the
    // page-wide single-open accordion the tab-strip's toggle-card handler
    // uses (further down) — both toggle boxes can be open or closed at the
    // same time, unrelated to each other and unrelated to whichever tab is
    // active. Reuses the exact same expandBody()/collapseBody() JS-measured
    // max-height mechanic every tab-strip card body already uses (see the
    // big comment on those two functions near the top of this file) — the
    // only genuinely new piece here is flipping the collapse button's own
    // .expanded class so its chevron rotates (see .dash-toggle-box-chevron
    // in dashboard.css).
    function toggleBoxCollapse(boxKey, btn) {
        var body = document.querySelector('[data-toggle-box-body="' + boxKey + '"]');
        if (!body) return;
        var nowExpanded = !body.classList.contains('expanded');
        if (nowExpanded) {
            expandBody(body);
        } else {
            collapseBody(body);
        }
        btn.classList.toggle('expanded', nowExpanded);
    }

    // ── SSE integration: refresh hook called by polling.js ───────────────
    //
    // polling.js (UI Chunk 9) opens an EventSource on /sse/dashboard for
    // this page and calls window.helixDashboardRefresh() every time it
    // fires — it deliberately knows nothing about this dashboard's cards
    // beyond that one global function name, matching sse.py's own
    // "deliberately dumb doorbell" design (see CLAUDE.md's Live Updates
    // section): something changed somewhere, go fetch and figure out what.
    //
    // SCOPE OF WHAT ACTUALLY REFRESHES LIVE HERE — deliberately partial:
    // every card's COLLAPSED summary count refreshes (cheap: one fetch to
    // /dashboard/api/summary, then just swap text). Of the EXPANDED bodies,
    // only Due / Decisions / Next Actions refresh live, because those three
    // already had working fetch-and-replace functions from earlier chunks
    // (fetchAndRenderDue, refreshDecisionsCard, fetchAndRenderNextActions)
    // — reusing them here cost nothing extra. What Changed's list, Clashing
    // Projects' by-deliverable/by-project lists, and the deep-dive zone's
    // Projects/Deliverables tables were all built as one-time server-
    // rendered content with NO client-side re-render function (a deliberate
    // call in each of those chunks, since nothing needed one at the time) —
    // building four more hand-written row-renderers just for this chunk
    // would roughly double its size. Practical effect: if you leave one of
    // those four expanded and something relevant changes elsewhere, it can
    // go stale until your next full page load. A reasonable follow-up if
    // that turns out to matter day-to-day: either write those renderers, or
    // simply call location.reload() here whenever one of those four happens
    // to be expanded at the moment a refresh fires.
    function refreshDashboardFromSSE() {
        fetch(withDashScope('/dashboard/api/summary'))
            .then(function (r) { return r.json(); })
            .then(function (summary) {
                // Due tab's mini-stat — rebuilt wholesale from scratch
                // rather than patched number-by-number; cheap, and
                // guarantees this always matches due.html's exact original
                // markup (see the due_summary Jinja block there). Selector
                // targets .dash-content-tab (the 15 Jul 2026 tab-strip
                // redesign — see the big comment on .dash-content-tabs in
                // dashboard.css); every tab-card's badge lives at
                // .dash-content-tab-badge now, NOT .dash-tile-summary
                // (that class still exists, but only for the 4 static stat
                // tiles above the tab strip — see the stat_* block further
                // down, which is deliberately unchanged).
                //
                // FIXED 12 Jul 2026 (fifth follow-up): this used to rebuild
                // THREE mini-stats (Overdue/Today/This Week) — a bug left
                // over from the fourth follow-up, which narrowed due.html
                // itself down to ONE stat but never updated this JS mirror
                // to match. Net effect: the page loaded correctly with one
                // stat, then the very next SSE refresh silently overwrote
                // it with the old three-stat markup — exactly the "SSR and
                // JS mirror must stay in sync" trap this file's other
                // render functions call out explicitly. Single stat now,
                // label matches due.html's ("This Week", not "Overdue" —
                // the card's own title already says Overdue). Colour is
                // count-based since the eleventh follow-up (green at
                // zero, red at 1+) — keep in sync with due.html.
                //
                // Selector moved TWICE now: .dash-content-tab[...] (tab
                // strip) -> .dash-pinned-card[...] (always-visible pinned
                // card, 15 Jul 2026) -> the current
                // [data-toggle-box="overdue_at_risk"] .dash-toggle-box-btn
                // form (15 Jul 2026, later still), when Overdue/At Risk
                // were rebuilt as one toggle box with two view-switch
                // buttons instead of two separate always-visible cards —
                // see the big comment on .dash-toggle-row in dashboard.css.
                // Each button carries its OWN badge now (no shared box-level
                // badge), so this replaces just the .dash-mini-stat span
                // living inside the "Overdue" button specifically —
                // toggleBoxBadge() (below) is a tiny shared helper for this
                // exact "find the mini-stat inside a toggle button and swap
                // it" pattern, used by both this block and the "At Risk"
                // block right after it. Label stays '' — the button's own
                // text already says "Overdue"/"At Risk", so a label here
                // would repeat it, same reasoning stat_active/stat_pending's
                // badges above use.
                toggleBoxBadge('overdue_at_risk', 'overdue', summary.overdue === 0 ? 'green' : 'red', summary.overdue);

                // Matches next_actions.html's next_actions_summary block
                // (reworked 12 Jul 2026 — RAG mini-stats, red=mine,
                // instead of owner-tag/action-tag pills). "Waiting on
                // Others" changed the same day (tenth follow-up) from
                // flat yellow to green-at-zero/orange-otherwise — keep
                // this in sync with next_actions_summary in
                // next_actions.html.
                var nextActionsSummaryEl = document.querySelector('.dash-content-tab[data-card="next_actions"] .dash-content-tab-badge');
                if (nextActionsSummaryEl) {
                    nextActionsSummaryEl.innerHTML =
                        miniStat('red', summary.my_actions, 'Needed From Me') +
                        miniStat(summary.others_actions === 0 ? 'green' : 'orange', summary.others_actions, 'Waiting on Others');
                }

                // Matches what_changed.html's what_changed_summary block
                // (reworked 12 Jul 2026 — single green mini-stat instead of
                // an ashen action-tag pill; still flat-coloured regardless
                // of count — informational, not urgent). Keep in sync.
                var whatChangedSummaryEl = document.querySelector('.dash-content-tab[data-card="what_changed"] .dash-content-tab-badge');
                if (whatChangedSummaryEl) {
                    whatChangedSummaryEl.innerHTML =
                        miniStat('green', summary.what_changed, 'Update' + (summary.what_changed !== 1 ? 's' : ''));
                }

                // Matches clashes.html's clashes_summary block (reworked 12
                // Jul 2026 — RAG mini-stats, detected=red/potential=yellow,
                // instead of severity-tag pills; needs the clashes_detected/
                // clashes_potential fields _compute_summary() returns
                // alongside the plain clashes total). Keep in sync.
                var clashesTabEl = document.querySelector('.dash-content-tab[data-card="clashes"]');
                if (clashesTabEl) {
                    var clashesSummaryEl = clashesTabEl.querySelector('.dash-content-tab-badge');
                    if (clashesSummaryEl) {
                        if (summary.clashes > 0) {
                            var clashPills = '';
                            if (summary.clashes_detected > 0) {
                                clashPills += miniStat('red', summary.clashes_detected, 'Detected');
                            }
                            if (summary.clashes_potential > 0) {
                                clashPills += miniStat('yellow', summary.clashes_potential, 'Potential');
                            }
                            clashesSummaryEl.innerHTML = clashPills;
                        } else {
                            clashesSummaryEl.innerHTML = miniStat('green', null, 'No Clashes');
                        }
                    }
                    // NOTE: this toggles the muted VISUAL state live, but the
                    // tab's data-action="toggle-card" attribute (set
                    // server-side by the dash_card() macro, see
                    // _dashboard_macros.html — only rendered when NOT muted)
                    // is NOT re-added here — a card that goes from 0 to 1+
                    // clashes without a full page reload will look active but
                    // stay unclickable until the next reload. Small, known
                    // gap; not worth a bigger DOM-attribute dance for
                    // something that self-corrects on the user's next visit.
                    clashesTabEl.classList.toggle('dash-content-tab--muted', summary.clashes === 0);
                }

                // Matches at_risk.html's at_risk_summary block (added 12
                // Jul 2026) — single mini-stat, red if >0 else green. The
                // row list itself isn't re-fetched here, same as Clashes
                // above — see at_risk.html's docstring for why that's
                // acceptable staleness for this card.
                //
                // Same toggleBoxBadge() move as Overdue directly above —
                // see that block's comment for the full history.
                toggleBoxBadge('overdue_at_risk', 'at_risk', summary.at_risk_count > 0 ? 'red' : 'green', summary.at_risk_count);

                // My Day/My Week toggle box (added 15 Jul 2026, later
                // still, replacing summary.html's old Today/This Week
                // .dash-two-col split — see toggle_my_day_week.html).
                // NEW live-refresh, not a move: the old Summary card had
                // NO SSE refresh at all (it was "always open, not
                // collapsible" with no JS mirror function), so its
                // due_today/due_week mini-stats just sat static until the
                // next full page load. Now that Today/This Week are a
                // toggle box's own view-switch button badges — visually
                // equivalent to every other live-refreshed badge on this
                // page — they get the same treatment for consistency.
                toggleBoxBadge('my_day_week', 'today', summary.due_today > 0 ? 'red' : 'green', summary.due_today);
                toggleBoxBadge('my_day_week', 'week', summary.due_week > 0 ? 'red' : 'green', summary.due_week);
            })
            .catch(function () {
                // Same "leave it stale on a network blip" convention as
                // every other fetch in this file.
            });

        // Stat cards (added 12 Jul 2026, own small fetch rather than being
        // folded into the /api/summary handler above — matches
        // _compute_project_stats() in dashboard.py exactly). Rebuilt via
        // miniStat() same as every other tab's badge above.
        //
        // Moved from .dash-tile/.dash-tile-summary to
        // .dash-content-tab/.dash-content-tab-badge (15 Jul 2026, same day
        // as the rest of the tab-strip redesign's badge selectors) when
        // these four stopped being static non-interactive tiles and became
        // ordinary tab+body cards, last in card_order — see the big
        // comment on CARD_ORDER in dashboard.py. .dash-tile now has NO
        // consumers left on this page at all.
        //
        // Label is '' for stat_active/stat_pending since the tab's own
        // title already says what the number means, same as the Jinja
        // templates render an empty label span rather than omitting it, so
        // the two markups stay byte-for-byte matched. stat_avg_time is the
        // one exception — its label is 'HRS', matching stat_avg_time.html
        // exactly, since a bare number there would be ambiguous.
        // (stat_total REMOVED 15 Jul 2026, later still — see the comment
        // further down where its block used to be.) Note this only ever
        // rebuilds the BADGE — the row-list bodies (Active/Pending's
        // project lists, Avg Time's full table) are server-rendered only,
        // same "acceptable staleness until next full page load" convention
        // At Risk/Clashing Projects already use for their own row lists.
        fetch(withDashScope('/dashboard/api/project-stats'))
            .then(function (r) { return r.json(); })
            .then(function (stats) {
                var statActiveEl = document.querySelector('.dash-content-tab[data-card="stat_active"] .dash-content-tab-badge');
                if (statActiveEl) statActiveEl.innerHTML = miniStat('green', stats.your_active, '');

                var statPendingEl = document.querySelector('.dash-content-tab[data-card="stat_pending"] .dash-content-tab-badge');
                if (statPendingEl) statPendingEl.innerHTML = miniStat('blue', stats.pending_approval, '');

                // stat_total REMOVED 15 Jul 2026, later still, per Ezekiel:
                // "Remove total active projects also" — this block used to
                // rebuild its badge from stats.total_active. That field is
                // still present in the /api/project-stats response (see
                // _compute_project_stats()'s docstring in dashboard.py for
                // why it was left in rather than torn out), just nothing
                // reads it here anymore.

                var statAvgTimeEl = document.querySelector('.dash-content-tab[data-card="stat_avg_time"] .dash-content-tab-badge');
                if (statAvgTimeEl) statAvgTimeEl.innerHTML = miniStat('oak', stats.average_time, 'HRS');
            })
            .catch(function () {
                // Same "leave it stale on a network blip" convention as
                // every other fetch in this file.
            });

        // Due card's LIST: UNCONDITIONAL, still — Overdue isn't part of
        // the tab strip's single-open system (it moved out entirely 15 Jul
        // 2026, first into an always-visible pinned card, then later the
        // same day into the Overdue/At Risk toggle box — see
        // toggle_overdue_at_risk.html), so there's no "is this tab even
        // open" question to gate on here even though the BOX itself can
        // now be collapsed by the user — refreshing the data underneath a
        // collapsed box is harmless and keeps it correct the moment it's
        // reopened. No filter pills to read either (removed 12 Jul 2026,
        // fourth follow-up — the card only ever shows one thing: overdue
        // this week), so this always refetches with 'overdue', full stop.
        fetchAndRenderDue('overdue');

        // Decisions: refreshDecisionsCard() already updates both the
        // collapsed count and the expanded list (only if expanded) in one
        // call — cheap enough to just always run it, no expanded-check needed.
        refreshDecisionsCard();

        // Next Actions' LIST: same "only if expanded" idea as Due above,
        // using whichever tab (My/Others) is currently active.
        var nextActionsBodyEl = document.querySelector('.dash-card-body-content[data-card="next_actions"]');
        if (nextActionsBodyEl && nextActionsBodyEl.classList.contains('expanded')) {
            var activeNextActionsBtn = nextActionsBodyEl.querySelector('[data-action="next-actions-tab"].active');
            if (activeNextActionsBtn) fetchAndRenderNextActions(activeNextActionsBtn.dataset.filter);
        }
    }

    // ── Runs every time this script executes (initial load or SPA renav) ──

    // Reassigned unconditionally on every execution (not just once, unlike
    // the listener-binding block further below) — if the user navigates
    // away and back via the SPA sidebar, this whole script re-runs and
    // refreshDashboardFromSSE() above is a brand new function closure each
    // time; window.helixDashboardRefresh must point at the CURRENT one, not
    // a stale reference to a closure from a previous page visit.
    window.helixDashboardRefresh = refreshDashboardFromSSE;

    initCards();

    // ── Runs exactly once per page session — see file header ─────────────

    if (!window._dashboardListenersBound) {
        window._dashboardListenersBound = true;

        document.addEventListener('click', function (e) {
            // These four are checked FIRST, ahead of toggle-card below, on
            // purpose: the "Flag a Project" button lives inside decisions.html's
            // expanded body, which is itself inside .dash-card-body-content
            // in .dash-content-area — NOT inside the .dash-content-tab
            // button that carries data-action="toggle-card" — so there's
            // no actual bubbling conflict here today. They're still
            // ordered first defensively, so that if a future chunk ever
            // moves one of these triggers somewhere that IS nested inside
            // a tab, matching happens here before it would reach (and
            // wrongly fire) the toggle-card branch below.
            if (e.target.closest('[data-action="open-flag-management-modal"]')) {
                openFlagManagementModal();
                return;
            }
            if (e.target.closest('[data-action="close-flag-management-modal"]')) {
                closeFlagManagementModal();
                return;
            }
            var flagOverlay = e.target.closest('[data-action="close-flag-management-overlay"]');
            if (flagOverlay && e.target === flagOverlay) {
                closeFlagManagementModal();
                return;
            }
            if (e.target.closest('[data-action="submit-flag-management"]')) {
                submitFlagManagement();
                return;
            }
            var resolveBtn = e.target.closest('[data-action="resolve-decision"]');
            if (resolveBtn) {
                // Same defensive-ordering reasoning as the flag-management
                // triggers above: this button lives inside a .dash-row
                // sibling, not the row itself, so there's no bubbling
                // conflict today — but it's still checked ahead of
                // toggle-card in case that ever changes.
                resolveDecision(resolveBtn.getAttribute('data-project-id'), resolveBtn);
                return;
            }

            // CS/Designer picker toggle (added 15 Jul 2026, per Ezekiel:
            // "Next to All Projects put CS button and Designer button. When
            // they click those buttons, the below expands to show each name
            // as a button as it is now... toggle - so when they click CS,
            // then designer, it replaces the CS buttons with designer ones
            // and vice versa"). These two <button>s (dashboard.html, inside
            // .dash-view-tabs next to My View/All Projects) don't switch
            // scope themselves — they just show/hide the .dash-group-tabs
            // row of real scope-switching <a> links underneath. Checked
            // ahead of toggle-card below for the same defensive-ordering
            // reason as the other data-actions above, though there's no
            // actual nesting conflict today either.
            var groupToggle = e.target.closest('[data-action="toggle-group"]');
            if (groupToggle) {
                var group = groupToggle.dataset.group;
                var targetRow = document.querySelector('.dash-group-tabs[data-group="' + group + '"]');
                var wasOpen = targetRow && !targetRow.classList.contains('hidden');

                // Single-open: hide every group row and clear every toggle
                // button's active state first, regardless of which one was
                // clicked — this is what makes clicking Designer while CS is
                // showing REPLACE it instead of showing both at once.
                document.querySelectorAll('.dash-group-tabs').forEach(function (row) {
                    row.classList.add('hidden');
                });
                document.querySelectorAll('.dash-group-toggle-btn').forEach(function (btn) {
                    btn.classList.remove('active');
                });

                // Clicking the ALREADY-open group's button again closes it
                // (both rows now hidden, both buttons now inactive) rather
                // than reopening it — an accordion toggle, not a fixed
                // 2-state switch, since the group buttons aren't tied to a
                // scope of their own (unlike the tab-strip's toggle-card,
                // which always keeps exactly one tab open).
                if (!wasOpen && targetRow) {
                    targetRow.classList.remove('hidden');
                    groupToggle.classList.add('active');
                }
                return;
            }

            var toggleHeader = e.target.closest('[data-action="toggle-card"]');
            if (toggleHeader) {
                // Tab strip (EVERY card including Summary, as of the 15
                // Jul 2026 redesign — see the big comment on
                // .dash-content-tabs in dashboard.css). Single-open
                // page-wide: opening any tab closes whichever OTHER tab
                // was active anywhere on the page and shows this one's
                // body in the single .dash-content-area instead.
                //
                // Clicking the ALREADY-active tab is a no-op (real tab
                // semantics, not accordion toggle-open/toggle-closed) —
                // the content area is meant to always show exactly one
                // card, never nothing, since it's the same box that used
                // to be the permanently-populated "My Day / My Week" area.
                var tab = toggleHeader.closest('.dash-content-tab');
                if (tab) {
                    if (tab.classList.contains('dash-content-tab--muted')) return;
                    if (tab.classList.contains('active')) return; // already showing — nothing to do

                    document.querySelectorAll('.dash-content-tab.active').forEach(function (t) {
                        t.classList.remove('active');
                    });
                    // Scoped to #dash-content-area specifically (added 15
                    // Jul 2026, later still — real bug fix, not a style
                    // nit) — this USED to be an unscoped
                    // document.querySelectorAll('.dash-card-body-content.
                    // expanded'), which was harmless when .dash-card-body-
                    // content only ever appeared inside #dash-content-area.
                    // That stopped being true the moment the Overdue/At
                    // Risk and My Day/My Week toggle boxes started reusing
                    // the SAME class for their own independent collapse
                    // mechanic (see toggle_overdue_at_risk.html/toggle_my_
                    // day_week.html) — without this scoping, clicking ANY
                    // tab in the strip would also silently collapse both
                    // toggle boxes as a side effect, since they'd match the
                    // same blanket query. Single-open page-wide semantics
                    // are still correct WITHIN the tab strip's own content
                    // area — just no longer bleed outside it.
                    document.querySelectorAll('#dash-content-area .dash-card-body-content.expanded').forEach(function (b) {
                        collapseBody(b);
                    });

                    tab.classList.add('active');
                    var body = document.querySelector(
                        '#dash-content-area .dash-card-body-content[data-card="' + tab.dataset.card + '"]');
                    expandBody(body);
                    return;
                }

                return;
            }

            // NOTE: the Due card's filter pills (All Today/Overdue/Due
            // Today/Due This Week, data-action="due-filter") were removed
            // 12 Jul 2026 (fourth follow-up) when that card was narrowed
            // to show ONLY overdue-this-week with no toggles at all — see
            // due.html. If you're looking for that click-handler branch or
            // the "always exactly one active pill" pattern it used, check
            // git history around that date; fetchAndRenderDue() itself is
            // still here (used by the SSE refresh below) but is now always
            // called with 'overdue'.

            var nextActionsBtn = e.target.closest('[data-action="next-actions-tab"]');
            if (nextActionsBtn) {
                // Strict two-way toggle — always exactly one active, same
                // single-select convention the Clashes tab pills use too.
                document.querySelectorAll('[data-action="next-actions-tab"]').forEach(function (btn) {
                    btn.classList.toggle('active', btn === nextActionsBtn);
                });
                fetchAndRenderNextActions(nextActionsBtn.dataset.filter);
                return;
            }

            var clashesBtn = e.target.closest('[data-action="clashes-tab"]');
            if (clashesBtn) { switchClashesTab(clashesBtn.dataset.filter); return; }

            // Toggle boxes (Overdue/At Risk + My Day/My Week, added 15 Jul
            // 2026, later still) — checked here, ahead of nothing in
            // particular (unlike the flag-management/resolve-decision
            // checks at the top of this handler, there's no real bubbling
            // conflict to guard against: the view buttons, collapse
            // button, and box body are all siblings/independent elements,
            // never nested inside one another — see the big comment on
            // .dash-toggle-box-header in dashboard.css).
            var toggleBoxViewBtn = e.target.closest('[data-action="toggle-box-view"]');
            if (toggleBoxViewBtn) {
                switchToggleBoxView(toggleBoxViewBtn.dataset.box, toggleBoxViewBtn.dataset.view);
                return;
            }
            var toggleBoxCollapseBtn = e.target.closest('[data-action="toggle-box-collapse"]');
            if (toggleBoxCollapseBtn) {
                toggleBoxCollapse(toggleBoxCollapseBtn.dataset.box, toggleBoxCollapseBtn);
                return;
            }
            // Click-anywhere-in-header-to-collapse (added 16 Jul 2026) — per
            // Ezekiel: "improve the UX so when you select anywhere in the
            // header that isn't the toggle button - it collapses the
            // header." Reached only when neither of the two checks above
            // matched, i.e. the click landed somewhere in the header OTHER
            // than a view-switch button or the chevron button itself
            // (empty padding, the gap between buttons, etc.) — both of
            // those already returned above, so there's no risk of this
            // double-firing on top of a view switch or the chevron's own
            // click. Reuses toggleBoxCollapse() as-is, just resolving the
            // box key + chevron button from the header itself instead of
            // from a dedicated data-action element, so the chevron still
            // rotates correctly regardless of where in the header the
            // click actually landed.
            var toggleBoxHeader = e.target.closest('.dash-toggle-box-header');
            if (toggleBoxHeader) {
                var headerBox = toggleBoxHeader.closest('[data-toggle-box]');
                var headerChevronBtn = toggleBoxHeader.querySelector('[data-action="toggle-box-collapse"]');
                if (headerBox && headerChevronBtn) {
                    toggleBoxCollapse(headerBox.dataset.toggleBox, headerChevronBtn);
                }
                return;
            }

            // NOTE: the dashboard's deep-dive zone (Projects/Deliverables
            // tabs at the bottom of the page, including its own "All"/
            // "At Risk" filter chips, deadline-sort pills, and side-by-side
            // toggle) was removed entirely 13 Jul 2026 — see CLAUDE.md and
            // git history around that date if any of this needs
            // resurrecting.
        });

        // Average Project Time card's embedded .tt-deliverables <details>
        // (added 15 Jul 2026 — see stat_avg_time.html). The native 'toggle'
        // event does NOT bubble, so this has to be a capture-phase listener
        // on document rather than living inside the click handler above
        // (which relies on bubbling). Fires whether a <details> was opened
        // by the user clicking its <summary> OR programmatically via
        // time_tracking.js's Expand All/Collapse All buttons setting
        // .open directly — both go through the same 'toggle' event per the
        // HTML spec.
        //
        // Necessary because expandBody() only measures scrollHeight ONCE,
        // at the moment the stat_avg_time TAB itself is opened (see the
        // big comment on expandBody/remeasureExpandedBody above) — opening
        // a deliverable breakdown inside an already-open tab body grows
        // that body's real content height past whatever max-height was
        // captured at tab-open time, and without this listener the extra
        // content would be silently clipped by the same overflow:hidden
        // that makes the open/close animation work. Same root cause as the
        // Next Actions "doesn't always load the full list" bug (13 Jul
        // 2026) — see remeasureExpandedBody()'s docstring.
        document.addEventListener('toggle', function (e) {
            if (e.target.classList && e.target.classList.contains('tt-deliverables')) {
                remeasureExpandedBody(e.target.closest('.dash-card-body-content'));
            }
        }, true);
    }

})();
