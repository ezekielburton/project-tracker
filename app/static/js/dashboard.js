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

    // ── CS-only redesigned dashboard: relative "last updated" ticker ────
    // (added 16 Jul 2026, dashboard_cs.html only — #dash-last-updated
    // doesn't exist on the old dashboard.html, so tickLastUpdated() below
    // is a harmless no-op there via the standard `if (el)` guard.) Per
    // Ezekiel: "Have the last updates at the top like 'last updated 5s
    // ago'. Since it refreshes every time something new is to display
    // anyway by our polling, it reinforces that the data is accurate."
    // _dashLastUpdatedAt resets to Date.now() at page load AND every time
    // refreshDashboardFromSSE() actually runs (see that function, below)
    // — SSE only fires when something genuinely changed server-side
    // (sse.py's "deliberately dumb doorbell" design, see CLAUDE.md's Live
    // Updates section), so every reset really does mean "the data just
    // got fresher", not a cosmetic/fake tick.
    var _dashLastUpdatedAt = Date.now();

    function formatRelativeTime(fromMs) {
        var seconds = Math.max(0, Math.round((Date.now() - fromMs) / 1000));
        if (seconds < 5) return 'Last updated just now';
        if (seconds < 60) return 'Last updated ' + seconds + 's ago';
        var minutes = Math.floor(seconds / 60);
        if (minutes < 60) return 'Last updated ' + minutes + 'm ago';
        var hours = Math.floor(minutes / 60);
        return 'Last updated ' + hours + 'h ago';
    }

    function tickLastUpdated() {
        var el = document.getElementById('dash-last-updated');
        if (el) el.textContent = formatRelativeTime(_dashLastUpdatedAt);
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
    //
    // showWaiting param (added 16 Jul 2026) mirrors dash_due_row()'s new
    // show_waiting arg in _dashboard_macros.html — defaults false so
    // Overdue/Today/This Week (the other three callers of this function)
    // render exactly as before. Only fetchAndRenderNextActions('others')
    // passes true. item.waiting_since_display/waiting_reason/waiting_color
    // are always present on the payload regardless of this flag — see
    // _compute_next_actions()'s docstring in dashboard.py — this param only
    // gates whether they're rendered.
    function renderDueRow(item, showWaiting) {
        var title;
        if (item.type === 'deliverable') {
            title = escapeHtml(item.deliverable_name) + ' <span class="dash-row-title-detail">— ' + escapeHtml(item.project_name) + '</span>';
        } else if (item.type === 'customer' && item.customer_name) {
            title = escapeHtml(item.customer_name) + ' <span class="dash-row-title-detail">— ' + escapeHtml(item.project_name) + '</span>';
        } else {
            title = escapeHtml(item.project_name);
        }

        var people = personPeopleRow(item.cs_lead, item.designers);

        var waiting = '';
        if (showWaiting && item.waiting_since_display) {
            waiting = '<span class="dash-row-waiting">' +
                '<span class="dash-waiting-tag dash-waiting-tag--' + item.waiting_color + '">Waiting since: ' + escapeHtml(item.waiting_since_display) + '</span>' +
                (item.waiting_reason ? '<span class="dash-waiting-tag dash-waiting-tag--' + item.waiting_color + '">Waiting for: ' + escapeHtml(item.waiting_reason) + '</span>' : '') +
                '</span>';
        }

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
            waiting +
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
                    // NOTE: deliberately NOT items.map(renderDueRow) — Array.map
                    // passes (item, index, array) to its callback, and
                    // renderDueRow's 2nd param is now showWaiting (added 16 Jul
                    // 2026), so a bare map would leak the row's numeric INDEX in
                    // as a truthy showWaiting for every row past the first. Due
                    // never shows waiting tags (see dash_due_row()'s doc comment —
                    // that's Others' Actions/Decisions only), so this is called
                    // with showWaiting omitted (undefined, falsy) explicitly.
                    container.innerHTML = items.map(function (item) { return renderDueRow(item); }).join('');
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
        var waitingCountTag = (item.days_waiting !== null && item.days_waiting !== undefined)
            ? '<span class="dash-action-tag">' + item.days_waiting + ' day' + (item.days_waiting !== 1 ? 's' : '') + ' waiting</span>'
            : '';

        var resolveBtn = isManagementOrAdmin()
            ? '<button type="button" class="dash-resolve-btn" data-action="resolve-decision" data-project-id="' + item.project_id + '">✓ Resolve</button>'
            : '';

        // #dash-decisions-list is shared by decisions.html (old dashboard,
        // designer/team_lead) AND dashboard_leadership.html's Decision
        // Needed Queue — only one of those two pages is ever rendered at
        // once, but this one JS function serves both, so it branches on a
        // marker unique to the leadership page (16 Jul 2026, same-day
        // follow-up — the queue's row markup became a true CSS Grid, see
        // .dash-decision-queue-card in dashboard.css) rather than
        // duplicating refreshDecisionsCard()/resolveDecision() into a
        // second copy just for one page.
        if (document.querySelector('.dash-decision-queue-card')) {
            // Avatar+name chip (16 Jul 2026, same-day follow-up — per
            // Ezekiel: "the name tag should follow our image + name
            // system we are using everywhere else on the dashboard"),
            // via the same personChip() helper renderDueRow() already
            // uses — mirrors dashboard_leadership.html's
            // dash_person_chip(d.raised_by) exactly. item.raised_by now
            // carries avatar_filename (_serialize_person(), dashboard.py).
            var ownerChip = personChip(item.raised_by);
            // Inline style="" attributes (16 Jul 2026, fourth attempt) —
            // mirrors dashboard_leadership.html's SSR markup exactly. The
            // external .dash-decision-queue-card .dash-decision-row/.dash-row
            // !important rules in dashboard.css were confirmed, via live
            // DevTools inspection, to never actually apply in the browser
            // for a reason never identified (see that template's big
            // comment) — inline styles can't be silently skipped the same
            // way, so a JS-rebuilt row (after Resolve) must carry the same
            // inline declarations or it would regress back to the broken
            // flex layout on the very next refresh.
            var gridRowStyle = 'display: grid !important; grid-template-columns: 2fr 2fr 1fr 1fr 130px 100px !important; align-items: center !important; gap: 1rem !important;';
            var gridRow = '<a class="dash-row" href="/projects/' + item.project_id + '?from=dashboard" style="display: contents !important;">' +
                '<span class="dash-row-title">' + escapeHtml(item.project_name) + '</span>' +
                '<span class="dash-row-sub">' + escapeHtml(item.note) + '</span>' +
                '<span class="dash-decision-cell">' + ownerChip + '</span>' +
                '<span class="dash-decision-cell">' + waitingCountTag + '</span>' +
                '<span class="dash-decision-date">' + escapeHtml(formatDubaiTime(item.raised_at)) + '</span>' +
                '</a>';
            return '<div class="dash-decision-row" style="' + gridRowStyle + '">' + gridRow + resolveBtn + '</div>';
        }

        // decisions.html / old dashboard.html — still the plain text
        // .dash-owner-tag pill, unchanged (this page wasn't part of
        // Ezekiel's request, which was specifically about the leadership
        // dashboard's Decision Needed Queue).
        var ownerTag = item.raised_by ? '<span class="dash-owner-tag">' + escapeHtml(item.raised_by.name) + '</span>' : '';

        // decisions.html / old dashboard.html — unchanged flex layout,
        // including the waiting-since/for tags block (added 16 Jul 2026,
        // mirrors decisions.html's dash-row-waiting block; the leadership
        // queue's SSR row never had this block, so the branch above
        // deliberately omits it too). waiting_color is always 'red' here
        // (see _compute_decisions()'s docstring) but rendered via
        // item.waiting_color rather than hardcoded, matching the template.
        var waiting = '';
        if (item.waiting_since_display) {
            waiting = '<span class="dash-row-waiting">' +
                '<span class="dash-waiting-tag dash-waiting-tag--' + item.waiting_color + '">Waiting since: ' + escapeHtml(item.waiting_since_display) + '</span>' +
                (item.waiting_reason ? '<span class="dash-waiting-tag dash-waiting-tag--' + item.waiting_color + '">Waiting for: ' + escapeHtml(item.waiting_reason) + '</span>' : '') +
                '</span>';
        }

        // Same hardcoded-URL caveat as renderDueRow() above — no url_for()
        // available client-side.
        var row = '<a class="dash-row" href="/projects/' + item.project_id + '?from=dashboard">' +
            '<span class="dash-row-main">' +
            '<span class="dash-row-title">' + escapeHtml(item.project_name) + '</span>' +
            '<span class="dash-row-sub">' + escapeHtml(item.note) + '</span>' +
            '<span class="dash-row-tags">' + ownerTag + waitingCountTag + '</span>' +
            waiting +
            '</span>' +
            '<span style="text-align:right; flex-shrink:0; font-size:0.8rem; color:var(--grey-dark);">' +
            escapeHtml(formatDubaiTime(item.raised_at)) + '</span>' +
            '</a>';

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

    // ── Leadership dashboard: Reassign CS Lead / Assign Designer modals ──
    // (added 16 Jul 2026, dashboard_leadership.html only — see the big
    // comment on _compute_risk_overdue() in dashboard.py). Same
    // open/close/submit shape as openFlagManagementModal() above, just two
    // modals instead of one. Both are harmless no-ops on every other page
    // (getElementById returns null, guarded by `if (!overlay) return`).
    var _reassignCsLeadProjectId = null;
    var _assignDesignerProjectId = null;

    function openReassignCsLeadModal(projectId, projectName) {
        var overlay = document.getElementById('reassign-cs-lead-modal');
        var nameEl = document.getElementById('reassign-cs-lead-project-name');
        var selectEl = document.getElementById('reassign-cs-lead-select');
        var errorEl = document.getElementById('reassign-cs-lead-error');
        if (!overlay) return;

        _reassignCsLeadProjectId = projectId;
        nameEl.textContent = projectName || '';
        selectEl.value = '';
        errorEl.classList.add('hidden');
        errorEl.textContent = '';

        overlay.classList.remove('hidden');
        if (window.helixPolling) window.helixPolling.pause();
    }

    function closeReassignCsLeadModal() {
        var overlay = document.getElementById('reassign-cs-lead-modal');
        if (overlay) overlay.classList.add('hidden');
        if (window.helixPolling) window.helixPolling.resume();
    }

    function submitReassignCsLead() {
        var selectEl = document.getElementById('reassign-cs-lead-select');
        var errorEl = document.getElementById('reassign-cs-lead-error');
        var newCsLeadId = selectEl.value;

        if (!newCsLeadId) {
            errorEl.textContent = 'Please select a CS lead.';
            errorEl.classList.remove('hidden');
            return;
        }

        fetch('/projects/' + _reassignCsLeadProjectId + '/reassign-cs-lead', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ new_cs_lead_id: newCsLeadId })
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.success) {
                    errorEl.textContent = data.error || 'Something went wrong.';
                    errorEl.classList.remove('hidden');
                    return;
                }
                closeReassignCsLeadModal();
                showToast('CS lead reassigned', 'success');
                // No live re-render of the Risk/Overdue row list (that
                // card is server-rendered once on load, same as At Risk/
                // Clashing Projects elsewhere on this page — no fetch
                // mechanism exists to refresh just this list). A full
                // reload is the simplest way to reflect the change
                // everywhere it might now matter (the row's own person
                // chip, its bucket membership, the Leadership Focus
                // count) without building a second parallel refresh path.
                setTimeout(function () { window.location.reload(); }, 700);
            })
            .catch(function () {
                errorEl.textContent = 'Something went wrong. Please try again.';
                errorEl.classList.remove('hidden');
            });
    }

    // Rebuilds the Designer <select> to only the people on the given team
    // — reads from LEADERSHIP_DESIGNERS (dashboard_leadership.html's
    // page-level {id, name, team} array, see CLAUDE.md's "JS in
    // templates — JSON data" rule). Called on modal open (for whichever
    // team is selected first) and again on the Team <select>'s own
    // change event.
    function populateAssignDesignerDesigners(team) {
        var designerSelect = document.getElementById('assign-designer-select');
        if (!designerSelect) return;
        var options = '<option value="">Select a designer…</option>';
        (window.LEADERSHIP_DESIGNERS || []).forEach(function (d) {
            if (d.team === team) {
                options += '<option value="' + d.id + '">' + escapeHtml(d.name) + '</option>';
            }
        });
        designerSelect.innerHTML = options;
    }

    function openAssignDesignerModal(projectId, projectName, missingTeamsCsv) {
        var overlay = document.getElementById('assign-designer-modal');
        var nameEl = document.getElementById('assign-designer-project-name');
        var teamSelect = document.getElementById('assign-designer-team-select');
        var errorEl = document.getElementById('assign-designer-error');
        if (!overlay) return;

        _assignDesignerProjectId = projectId;
        nameEl.textContent = projectName || '';
        errorEl.classList.add('hidden');
        errorEl.textContent = '';

        // Team options come from the button's own data-missing-teams —
        // "based on the active teams requested for that project" (per
        // Ezekiel), i.e. only teams THIS project actually asked for and
        // is short-staffed on, never every team in the company.
        var teams = (missingTeamsCsv || '').split(',').filter(function (t) { return t; });
        teamSelect.innerHTML = teams.map(function (t) {
            return '<option value="' + t + '">' + t + '</option>';
        }).join('');
        populateAssignDesignerDesigners(teams[0] || '');

        overlay.classList.remove('hidden');
        if (window.helixPolling) window.helixPolling.pause();
    }

    function closeAssignDesignerModal() {
        var overlay = document.getElementById('assign-designer-modal');
        if (overlay) overlay.classList.add('hidden');
        if (window.helixPolling) window.helixPolling.resume();
    }

    function submitAssignDesigner() {
        var teamSelect = document.getElementById('assign-designer-team-select');
        var designerSelect = document.getElementById('assign-designer-select');
        var errorEl = document.getElementById('assign-designer-error');
        var team = teamSelect.value;
        var designerId = designerSelect.value;

        if (!team || !designerId) {
            errorEl.textContent = 'Please select a team and a designer.';
            errorEl.classList.remove('hidden');
            return;
        }

        fetch('/projects/' + _assignDesignerProjectId + '/assign-lead', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ team: team, new_designer_id: designerId })
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.success) {
                    errorEl.textContent = data.error || 'Something went wrong.';
                    errorEl.classList.remove('hidden');
                    return;
                }
                closeAssignDesignerModal();
                showToast('Designer assigned', 'success');
                // Same "reload rather than build a second live-refresh
                // path" reasoning as submitReassignCsLead() above.
                setTimeout(function () { window.location.reload(); }, 700);
            })
            .catch(function () {
                errorEl.textContent = 'Something went wrong. Please try again.';
                errorEl.classList.remove('hidden');
            });
    }

    // ── Designer dashboard: Flag to CS Lead modal (16 Jul 2026) ─────────
    // (dashboard_designer.html only — see the big comment on
    // _compute_designer_work_queue() in dashboard.py). Same open/close/
    // submit shape as the modals above; harmless no-op on every other
    // page (getElementById returns null, guarded by `if (!overlay)
    // return`). POSTs to the EXISTING /projects/<id>/flags/create route
    // (the same "flag module" the project detail page's own Flag an
    // Issue UI already uses — see _designer_flag_modal.html's own big
    // comment on why this is NOT the Flag to Management system above),
    // flag_type hardcoded 'project' since a Blocked queue row has no
    // single deliverable to scope the flag to.
    var _designerFlagProjectId = null;

    function openDesignerFlagModal(projectId, projectName) {
        var overlay = document.getElementById('designer-flag-modal');
        var nameEl = document.getElementById('designer-flag-project-name');
        var messageEl = document.getElementById('designer-flag-message');
        var errorEl = document.getElementById('designer-flag-error');
        if (!overlay) return;

        _designerFlagProjectId = projectId;
        nameEl.textContent = projectName || '';
        messageEl.value = '';
        errorEl.classList.add('hidden');
        errorEl.textContent = '';

        overlay.classList.remove('hidden');
        if (window.helixPolling) window.helixPolling.pause();
    }

    function closeDesignerFlagModal() {
        var overlay = document.getElementById('designer-flag-modal');
        if (overlay) overlay.classList.add('hidden');
        if (window.helixPolling) window.helixPolling.resume();
    }

    function submitDesignerFlag() {
        var messageEl = document.getElementById('designer-flag-message');
        var errorEl = document.getElementById('designer-flag-error');
        var message = messageEl.value.trim();

        if (!message) {
            errorEl.textContent = 'Please describe what information is needed.';
            errorEl.classList.remove('hidden');
            return;
        }

        fetch('/projects/' + _designerFlagProjectId + '/flags/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ flag_type: 'project', message: message })
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.error) {
                    errorEl.textContent = data.error;
                    errorEl.classList.remove('hidden');
                    return;
                }
                closeDesignerFlagModal();
                showToast('Flag sent to CS lead', 'success');
                // Same "reload rather than build a second live-refresh
                // path" reasoning as submitReassignCsLead()/
                // submitAssignDesigner() above — the Blocked bucket's
                // membership and the Metrics Summary Blocked count both
                // need a fresh server-side re-classification, no fetch
                // mechanism exists to refresh just those two.
                setTimeout(function () { window.location.reload(); }, 700);
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
                    // showWaiting=true for BOTH tabs (widened 16 Jul 2026,
                    // same-day follow-up, per Ezekiel: "Apply those changes
                    // to the my actions tab too, it's only on other's
                    // actions" — originally 'others'-only). See
                    // renderDueRow()'s doc comment and dash_due_row()'s
                    // show_waiting param in _dashboard_macros.html.
                    container.innerHTML = items.map(function (item) { return renderDueRow(item, true); }).join('');
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

    // ── Role Snapshot clickable tiles (added 16 Jul 2026, later still) ──
    //
    // Per Ezekiel: "the client servicing and designers toggle that shows
    // their cards, these need to be clickable, that shows a hidden div
    // below that shows the details of the info card row by row." One
    // shared #dash-role-snapshot-expand div (see dashboard_leadership.html)
    // serves every tile in both the CS and Designers panels — clicking a
    // tile looks its rows up in the page-level ROLE_SNAPSHOT_TILES blob
    // (no fetch needed, this data is already fully computed on page load)
    // and renders them using the exact same .dash-row/.dash-row-date/
    // .dash-row-title/.dash-action-tag shell dash_stat_project_row()
    // renders server-side for Your Active/Pending Approval/Total Active —
    // reused here as a JS mirror rather than inventing a new row shape.
    function roleSnapshotProjectRow(item) {
        return '<a class="dash-row" href="/projects/' + item.project_id + '?from=dashboard">' +
            '<span class="dash-row-date">' + (item.deadline ? item.deadline : 'No deadline') + '</span>' +
            '<span class="dash-row-main">' +
                '<span class="dash-row-title">' + escapeHtml(item.name) + '</span>' +
                '<span class="dash-row-tags"><span class="dash-action-tag">' + escapeHtml(item.status_label) + '</span></span>' +
            '</span>' +
        '</a>';
    }

    function toggleRoleTile(tileEl) {
        var userId = parseInt(tileEl.dataset.userId, 10);
        var expandArea = document.getElementById('dash-role-snapshot-expand');
        if (!expandArea) return;

        var alreadyActive = tileEl.classList.contains('dash-role-tile--active');

        // Single-open, same accordion idea as every other toggle on this
        // page — clear every tile's active state first regardless of what
        // happens next.
        document.querySelectorAll('.dash-role-tile--active').forEach(function (el) {
            el.classList.remove('dash-role-tile--active');
        });

        if (alreadyActive) {
            // Clicking the same tile again closes the detail area.
            expandArea.classList.add('hidden');
            expandArea.querySelector('.dash-role-snapshot-expand-title').textContent = '';
            expandArea.querySelector('.dash-role-snapshot-expand-rows').innerHTML = '';
        } else {
            var data = (window.ROLE_SNAPSHOT_TILES || []).find(function (t) { return t.user_id === userId; });
            tileEl.classList.add('dash-role-tile--active');
            expandArea.classList.remove('hidden');
            expandArea.querySelector('.dash-role-snapshot-expand-title').textContent =
                tileEl.dataset.name + '’s Active Projects';
            var rowsHtml = data && data.rows.length
                ? data.rows.map(roleSnapshotProjectRow).join('')
                : '<p class="dash-empty-state">No active projects.</p>';
            expandArea.querySelector('.dash-role-snapshot-expand-rows').innerHTML = rowsHtml;
        }

        // Same "content height changed, re-measure the ancestor's inline
        // max-height" fix every other AJAX/DOM-swapped case on this page
        // needs — see switchToggleBoxView()'s comment just above for the
        // full root-cause writeup. No-ops if the box is collapsed.
        remeasureExpandedBody(document.querySelector('[data-toggle-box-body="role_snapshot"]'));
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
        // CS-only redesigned dashboard's "last updated" ticker (added 16
        // Jul 2026 — see the big comment on tickLastUpdated() above).
        // Reset unconditionally the moment this function is CALLED, not
        // after any individual fetch resolves — being called at all is
        // already the freshness signal (SSE only fires on a real server-
        // side change), and this function makes several independent
        // fetches below, so there's no single "the" response to key off.
        // No-op visually on the old dashboard.html (no #dash-last-updated
        // element there).
        _dashLastUpdatedAt = Date.now();
        tickLastUpdated();

        fetch(withDashScope('/dashboard/api/summary'))
            .then(function (r) { return r.json(); })
            .then(function (summary) {
                // CS-only redesigned dashboard's Today's Focus bar (added
                // 16 Jul 2026, dashboard_cs.html only) — plain number
                // swaps, no mini-stat markup to rebuild since these pills
                // are static text, not the RAG dot-component elsewhere on
                // this page. No-op via the standard `if (el)` guards below
                // on the old dashboard.html, which doesn't render any of
                // these ids.
                var focusMyActionsEl = document.getElementById('dash-focus-my-actions');
                if (focusMyActionsEl) focusMyActionsEl.textContent = summary.my_actions;
                var focusDueTodayEl = document.getElementById('dash-focus-due-today');
                if (focusDueTodayEl) focusDueTodayEl.textContent = summary.due_today;
                var focusOverdueEl = document.getElementById('dash-focus-overdue');
                if (focusOverdueEl) focusOverdueEl.textContent = summary.overdue;
                var focusClashesEl = document.getElementById('dash-focus-clashes');
                if (focusClashesEl) focusClashesEl.textContent = summary.clashes;
                var focusDecisionsEl = document.getElementById('dash-focus-decisions');
                if (focusDecisionsEl) focusDecisionsEl.textContent = summary.decisions_needed;

                // Due card's badge, reached via the CS-only dashboard's
                // Secondary Metrics tab strip (dash_card mode='tab') —
                // NOT a duplicate of the toggleBoxBadge('overdue_at_risk',
                // 'overdue', ...) call further below, which targets
                // `[data-toggle-box="overdue_at_risk"] .dash-toggle-box-btn`,
                // an element that doesn't exist on dashboard_cs.html at all
                // (Overdue isn't in a toggle box there — see
                // _CS_SECONDARY_METRICS in dashboard.py). No-op on the old
                // dashboard.html, which never renders a
                // `.dash-content-tab[data-card="due"]` element (due.html is
                // orphaned there — see that file's own docstring).
                var dueTabBadgeEl = document.querySelector('.dash-content-tab[data-card="due"] .dash-content-tab-badge');
                if (dueTabBadgeEl) dueTabBadgeEl.innerHTML = miniStat(summary.overdue === 0 ? 'green' : 'red', summary.overdue, 'This Week');

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
                        miniStat('red', summary.my_actions, 'Actions Needed') +
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

    // CS-only redesigned dashboard's "last updated" ticker (added 16 Jul
    // 2026 — see tickLastUpdated()'s big comment near the top of this
    // file). Reassigned unconditionally on every execution, same reasoning
    // as window.helixDashboardRefresh just above — this is a plain
    // setInterval, not a document-level event listener, so it's NOT inside
    // the once-ever _dashboardListenersBound guard below: an SPA renav back
    // to this page must retarget the fresh #dash-last-updated element in
    // the newly-swapped DOM, not keep ticking a detached one from a
    // previous visit. clearInterval() on whatever ran before (if anything)
    // prevents two intervals silently stacking and double-updating the
    // same element. No-op in effect on the old dashboard.html — the
    // interval still runs, but tickLastUpdated()'s own `if (el)` guard
    // means it never finds anything to update there.
    if (window._dashLastUpdatedInterval) clearInterval(window._dashLastUpdatedInterval);
    _dashLastUpdatedAt = Date.now();
    tickLastUpdated();
    window._dashLastUpdatedInterval = setInterval(tickLastUpdated, 1000);

    // ── Runs exactly once per page session — see file header ─────────────

    if (!window._dashboardListenersBound) {
        window._dashboardListenersBound = true;

        document.addEventListener('click', function (e) {
            // These four are checked FIRST, ahead of toggle-card below, on
            // purpose: the "Escalate" button (renamed from "Flag a Project"
            // 16 Jul 2026 — see decisions.html) lives inside decisions.html's
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

            // Leadership dashboard: Reassign CS Lead / Assign Designer
            // modals (added 16 Jul 2026, dashboard_leadership.html only —
            // see the big comment on _compute_risk_overdue() in
            // dashboard.py). Checked in the same defensively-ordered spot
            // as the flag-management/resolve-decision triggers above,
            // same reasoning — these buttons live as .dash-decision-row
            // siblings, not nested inside a toggle-card element, but kept
            // ahead of it regardless.
            var openReassignBtn = e.target.closest('[data-action="open-reassign-cs-lead-modal"]');
            if (openReassignBtn) {
                openReassignCsLeadModal(
                    openReassignBtn.getAttribute('data-project-id'),
                    openReassignBtn.getAttribute('data-project-name')
                );
                return;
            }
            if (e.target.closest('[data-action="close-reassign-cs-lead-modal"]')) {
                closeReassignCsLeadModal();
                return;
            }
            var reassignOverlay = e.target.closest('[data-action="close-reassign-cs-lead-overlay"]');
            if (reassignOverlay && e.target === reassignOverlay) {
                closeReassignCsLeadModal();
                return;
            }
            if (e.target.closest('[data-action="submit-reassign-cs-lead"]')) {
                submitReassignCsLead();
                return;
            }
            var openAssignBtn = e.target.closest('[data-action="open-assign-designer-modal"]');
            if (openAssignBtn) {
                openAssignDesignerModal(
                    openAssignBtn.getAttribute('data-project-id'),
                    openAssignBtn.getAttribute('data-project-name'),
                    openAssignBtn.getAttribute('data-missing-teams')
                );
                return;
            }
            var openDesignerFlagBtn = e.target.closest('[data-action="open-designer-flag-modal"]');
            if (openDesignerFlagBtn) {
                openDesignerFlagModal(
                    openDesignerFlagBtn.getAttribute('data-project-id'),
                    openDesignerFlagBtn.getAttribute('data-project-name')
                );
                return;
            }
            if (e.target.closest('[data-action="close-designer-flag-modal"]')) {
                closeDesignerFlagModal();
                return;
            }
            var designerFlagOverlay = e.target.closest('[data-action="close-designer-flag-overlay"]');
            if (designerFlagOverlay && e.target === designerFlagOverlay) {
                closeDesignerFlagModal();
                return;
            }
            if (e.target.closest('[data-action="submit-designer-flag"]')) {
                submitDesignerFlag();
                return;
            }
            if (e.target.closest('[data-action="close-assign-designer-modal"]')) {
                closeAssignDesignerModal();
                return;
            }
            var assignOverlay = e.target.closest('[data-action="close-assign-designer-overlay"]');
            if (assignOverlay && e.target === assignOverlay) {
                closeAssignDesignerModal();
                return;
            }
            if (e.target.closest('[data-action="submit-assign-designer"]')) {
                submitAssignDesigner();
                return;
            }

            // CS-only redesigned dashboard: Waiting on Others expand/
            // collapse (added 16 Jul 2026, dashboard_cs.html only). THREE
            // different elements carry this same data-action (the whole
            // card header, its small chevron button, and the standalone
            // "Open waiting list" button below the teaser text) — closest()
            // matches whichever one was actually clicked (or its nearest
            // ancestor carrying the attribute), so all three trigger the
            // exact same toggle with no risk of double-firing regardless of
            // which one the user clicks. Reuses expandBody()/collapseBody()
            // directly rather than toggleBoxCollapse() — this card isn't
            // one of the two toggle boxes (no data-toggle-box/data-toggle-
            // box-body scoping, no view-switch buttons, just one list to
            // show or hide), so the simpler direct call fits better than
            // reusing a function built for a different shape. No-op on the
            // old dashboard.html, which has no [data-waiting-list-body]
            // element at all.
            var waitingToggle = e.target.closest('[data-action="toggle-waiting-list"]');
            if (waitingToggle) {
                var waitingBody = document.querySelector('[data-waiting-list-body]');
                if (!waitingBody) return;
                var waitingNowExpanded = !waitingBody.classList.contains('expanded');
                if (waitingNowExpanded) { expandBody(waitingBody); } else { collapseBody(waitingBody); }
                var waitingChevronBtn = document.querySelector('.dash-waiting-card [data-action="toggle-waiting-list"].dash-toggle-box-collapse-btn');
                if (waitingChevronBtn) waitingChevronBtn.classList.toggle('expanded', waitingNowExpanded);
                var waitingOpenBtn = document.querySelector('.dash-waiting-open-btn');
                if (waitingOpenBtn) waitingOpenBtn.textContent = waitingNowExpanded ? 'Close waiting list' : 'Open waiting list';
                return;
            }

            // CS-only redesigned dashboard: Due Today expand/collapse
            // (added 16 Jul 2026, per Ezekiel: "Due today should open a
            // new section when clicked which shows what is due today and
            // who is the owner of what is due"). Same shape as the
            // Waiting on Others toggle directly above — one collapsible
            // body, no toggle-box view-switching — except the ONLY
            // trigger is the Focus bar's "due today" pill itself (every
            // other Focus pill stays inert per the original spec), so
            // there's no second header/button to keep a chevron or label
            // in sync with here. No-op on any page without a
            // [data-due-today-body] element (every dashboard except
            // dashboard_cs.html).
            var dueTodayToggle = e.target.closest('[data-action="toggle-due-today-list"]');
            if (dueTodayToggle) {
                var dueTodayBody = document.querySelector('[data-due-today-body]');
                if (!dueTodayBody) return;
                var dueTodayNowExpanded = !dueTodayBody.classList.contains('expanded');
                if (dueTodayNowExpanded) { expandBody(dueTodayBody); } else { collapseBody(dueTodayBody); }
                dueTodayToggle.classList.toggle('dash-focus-pill--active', dueTodayNowExpanded);
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
            // Role Snapshot clickable tiles (added 16 Jul 2026, later
            // still) — checked here, ahead of nothing in particular, same
            // reasoning as the toggle-box checks just above: tiles live
            // inside .dash-card-body-inner, never nested inside a header
            // or another clickable element, so there's no bubbling
            // conflict to guard against.
            var roleTileEl = e.target.closest('[data-action="toggle-role-tile"]');
            if (roleTileEl) {
                toggleRoleTile(roleTileEl);
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

        // Keyboard support for the "due today" Focus pill (16 Jul 2026) —
        // it's a <span role="button" tabindex="0">, not a real <button>,
        // to stay visually identical to every other (inert) Focus pill on
        // the same row, so it doesn't get a native click-on-Enter/Space
        // for free the way a real button would. This dispatches a real
        // 'click' event at the element on Enter/Space, which the click
        // listener above picks up via its normal data-action matching —
        // no separate toggle logic duplicated here. Space is also
        // preventDefault()'d so the page doesn't scroll while the pill is
        // focused, matching standard button behaviour.
        document.addEventListener('keydown', function (e) {
            if (e.key !== 'Enter' && e.key !== ' ') return;
            // Widened 16 Jul 2026 to also cover Role Snapshot's clickable
            // tiles (role="button" tabindex="0", same accessibility
            // pattern as the Due Today pill above) — same synthetic-click
            // approach, no separate toggle logic duplicated here.
            var target = e.target.closest('[data-action="toggle-due-today-list"], [data-action="toggle-role-tile"]');
            if (!target) return;
            e.preventDefault();
            target.click();
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

        // Assign Designer modal's Team select — re-filters the Designer
        // select whenever the team changes (a project can be missing more
        // than one team at once). Delegated on `document` like every
        // other listener in this guarded block, rather than binding
        // directly to the <select> element, since that element doesn't
        // exist until the modal's template renders and this whole block
        // only runs once per page load. Harmless no-op on every page
        // without an #assign-designer-team-select element.
        document.addEventListener('change', function (e) {
            if (e.target && e.target.id === 'assign-designer-team-select') {
                populateAssignDesignerDesigners(e.target.value);
            }
        });
    }

})();
