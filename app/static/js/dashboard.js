// app/static/js/dashboard.js
//
// Role-based dashboard. Chunk 1 covers the card expand/collapse mechanic
// and its localStorage persistence — tab switching, filter chips, the Flag
// to Management modal, and SSE live-updates are added in later chunks
// (each appends its own section to this file rather than replacing it).
//
// This page is reachable via the SPA sidebar nav (sidebar.js swaps
// #main-content's innerHTML and re-executes any <script> tags found in it —
// see execScripts() there). That means this whole IIFE can run more than
// once per browser session if the user navigates away and back without a
// full reload. State-restoring code (initCards, side-by-side restore) is
// SAFE to rerun — it just reapplies localStorage to whatever cards/panels
// are in the DOM right now. Event listeners are NOT safe to rerun: attaching
// document.addEventListener() again on a second run would stack a duplicate
// handler on top of the first (same class of bug CLAUDE.md's achievements
// system hit with _helixBound). window._dashboardListenersBound guards
// against that — listeners attach exactly once per page session, ever.

(function () {
    'use strict';

    var STORAGE_PREFIX = 'helixDashCard:';
    var SIDE_BY_SIDE_KEY = 'helixDashSideBySide';

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

    function setStoredOpen(key, open) {
        localStorage.setItem(STORAGE_PREFIX + key, open ? '1' : '0');
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
    // bodyEl is whichever element actually carries the max-height CSS
    // rule — .dash-card-body for Summary, .dash-card-body-content for
    // every tile (see dashboard.css). Both used the same class name,
    // .expanded, for their own "looks like an open card" styling (or, for
    // Summary's body, harmlessly unused — its visuals key off the ANCESTOR
    // .dash-card's .expanded class instead, toggled separately in
    // applyOpenState() below), so these two helpers work for both without
    // needing to know which one they were called on.
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

    function applyOpenState(card, open) {
        card.classList.toggle('expanded', open); // drives the chevron rotation/colour, unchanged
        var body = card.querySelector('.dash-card-body');
        if (open) {
            expandBody(body);
        } else {
            collapseBody(body);
        }
    }

    // ── Card expand/collapse + localStorage ─────────────────────────────
    //
    // On first load via the login redirect (?view=...), the server has
    // already rendered exactly one card as .expanded (see
    // initial_expanded_card in dashboard.py). We persist THAT choice to
    // localStorage so a plain reload afterwards (no ?view=) keeps it.
    //
    // On any other load (no ?view=), localStorage — not the server default
    // — decides each card's state, so the user's own open/closed layout
    // from last time sticks across visits.
    //
    // :not(.dash-card--static) excludes Summary ("My Day / My Week") —
    // changed 12 Jul 2026 (fourth follow-up) to always be open with no
    // toggle at all (see .dash-card-body--static in dashboard.css and the
    // mode=None branch in _dashboard_macros.html). Without this exclusion,
    // a STALE '0' left in localStorage from before that change would call
    // applyOpenState(card, false) below and incorrectly collapse it again.
    // In practice this loop currently matches nothing (Summary was the
    // only card ever using this selector), kept for whatever mode=None
    // card, if any, comes along later that ISN'T meant to be static.
    function initCards() {
        var hasViewParam = new URLSearchParams(window.location.search).has('view');

        document.querySelectorAll('.dash-card[data-card]:not(.dash-card--static)').forEach(function (card) {
            if (card.classList.contains('dash-card--muted')) return; // not togglable

            var key = card.dataset.card;

            // Sync the body's inline max-height to whatever .expanded
            // already says, directly (not via expandBody/collapseBody) —
            // this runs synchronously before first paint, so there's no
            // "previous frame" for the CSS transition to animate from,
            // meaning this appears instantly correct rather than growing
            // into place. Needed because (since 12 Jul 2026) the visible
            // height comes from an inline style JS sets, not a CSS rule
            // keyed off the class, so an already-open card would otherwise
            // render visually collapsed despite having .expanded on it.
            var body = card.querySelector('.dash-card-body');
            if (body && card.classList.contains('expanded')) {
                body.style.maxHeight = body.scrollHeight + 'px';
            }

            if (hasViewParam) {
                setStoredOpen(key, card.classList.contains('expanded'));
                return;
            }

            var stored = localStorage.getItem(STORAGE_PREFIX + key);
            if (stored !== null) {
                applyOpenState(card, stored === '1');
            }
            // No stored preference yet and no ?view= — leave the server
            // default, which is collapsed for every card.
        });

        // Tile bodies (every card except Summary) — same "sync inline
        // height to whatever .expanded already says" idea, for whichever
        // ONE card a ?view= deep link server-rendered as already open. No
        // localStorage path here — see the big comment on the tile branch
        // of the toggle-card click handler further down for why tiles
        // always start fresh/minimized on load otherwise.
        document.querySelectorAll('.dash-card-body-content.expanded').forEach(function (body) {
            body.style.maxHeight = body.scrollHeight + 'px';
        });
    }

    // ── Deep-dive zone: tab switching + side-by-side toggle ─────────────
    // Just the shell mechanic (tab buttons, panel visibility, side-by-side
    // layout toggle). There used to be a second section down here for
    // table content filtering/sorting (applyDeepDiveFilter()/
    // sortDashboardTable()) — removed 10 Jul 2026 when the deep-dive zone
    // became an always-at-risk-only row list (see the big comment above
    // _is_at_risk() in app/routes/dashboard.py): nothing left to filter
    // (every row already IS "at risk") or sort (already server-sorted).

    function switchTab(tabName) {
        document.querySelectorAll('.dash-tab-btn[data-tab]').forEach(function (btn) {
            btn.classList.toggle('active', btn.dataset.tab === tabName);
        });
        document.querySelectorAll('.dash-tab-panel[data-panel]').forEach(function (panel) {
            panel.classList.toggle('hidden', panel.dataset.panel !== tabName);
        });
    }

    function setSideBySide(on) {
        var panels = document.getElementById('dash-deep-dive-panels');
        var toggleBtn = document.getElementById('dash-side-by-side-toggle');
        if (!panels) return;

        panels.classList.toggle('dash-side-by-side', on);
        if (toggleBtn) toggleBtn.classList.toggle('active', on);
        localStorage.setItem(SIDE_BY_SIDE_KEY, on ? '1' : '0');
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
                // see remeasureExpandedBody()'s big comment. Latent here
                // too: an SSE-triggered refresh can grow this list past
                // whatever height was captured when the tile was opened.
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
                var tile = document.querySelector('.dash-tile[data-card="decisions"]');
                var summaryEl = tile ? tile.querySelector('.dash-tile-summary') : null;
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
    // between two pre-built blocks. Structurally identical to switchTab()
    // above (deep-dive zone's Projects/Deliverables tabs), duplicated as
    // its own small function rather than generalized, since it targets a
    // different pair of elements ([data-clashes-panel] instead of
    // [data-panel]) scoped to a single card rather than the whole page.
    function switchClashesTab(filterValue) {
        document.querySelectorAll('[data-action="clashes-tab"]').forEach(function (btn) {
            btn.classList.toggle('active', btn.dataset.filter === filterValue);
        });
        document.querySelectorAll('[data-clashes-panel]').forEach(function (panel) {
            panel.classList.toggle('hidden', panel.dataset.clashesPanel !== filterValue);
        });
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
                // Due tile's three mini-stats — rebuilt wholesale from
                // scratch rather than patched number-by-number; cheap, and
                // guarantees this always matches due.html's exact original
                // markup (see the due_summary Jinja block there). Selector
                // targets .dash-tile (not .dash-card) — every card except
                // Summary moved to the tile/shared-expand layout 12 Jul
                // 2026, see the big comment on .dash-tiles-grid in dashboard.css.
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
                var dueSummaryEl = document.querySelector('.dash-tile[data-card="due"] .dash-tile-summary');
                if (dueSummaryEl) {
                    dueSummaryEl.innerHTML = miniStat(summary.overdue === 0 ? 'green' : 'red', summary.overdue, 'This Week');
                }

                // Matches next_actions.html's next_actions_summary block
                // (reworked 12 Jul 2026 — RAG mini-stats, red=mine,
                // instead of owner-tag/action-tag pills). "Waiting on
                // Others" changed the same day (tenth follow-up) from
                // flat yellow to green-at-zero/orange-otherwise — keep
                // this in sync with next_actions_summary in
                // next_actions.html.
                var nextActionsSummaryEl = document.querySelector('.dash-tile[data-card="next_actions"] .dash-tile-summary');
                if (nextActionsSummaryEl) {
                    nextActionsSummaryEl.innerHTML =
                        miniStat('red', summary.my_actions, 'Needed From Me') +
                        miniStat(summary.others_actions === 0 ? 'green' : 'orange', summary.others_actions, 'Waiting on Others');
                }

                // Matches what_changed.html's what_changed_summary block
                // (reworked 12 Jul 2026 — single green mini-stat instead of
                // an ashen action-tag pill; still flat-coloured regardless
                // of count — informational, not urgent). Keep in sync.
                var whatChangedSummaryEl = document.querySelector('.dash-tile[data-card="what_changed"] .dash-tile-summary');
                if (whatChangedSummaryEl) {
                    whatChangedSummaryEl.innerHTML =
                        miniStat('green', summary.what_changed, 'Update' + (summary.what_changed !== 1 ? 's' : ''));
                }

                // Matches clashes.html's clashes_summary block (reworked 12
                // Jul 2026 — RAG mini-stats, detected=red/potential=yellow,
                // instead of severity-tag pills; needs the clashes_detected/
                // clashes_potential fields _compute_summary() returns
                // alongside the plain clashes total). Keep in sync.
                var clashesTileEl = document.querySelector('.dash-tile[data-card="clashes"]');
                if (clashesTileEl) {
                    var clashesSummaryEl = clashesTileEl.querySelector('.dash-tile-summary');
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
                    // tile's data-action="toggle-card" attribute (set
                    // server-side by the dash_card() macro, see
                    // _dashboard_macros.html — only rendered when NOT muted)
                    // is NOT re-added here — a card that goes from 0 to 1+
                    // clashes without a full page reload will look active but
                    // stay unclickable until the next reload. Small, known
                    // gap; not worth a bigger DOM-attribute dance for
                    // something that self-corrects on the user's next visit.
                    clashesTileEl.classList.toggle('dash-tile--muted', summary.clashes === 0);
                }

                // Matches at_risk.html's at_risk_summary block (added 12
                // Jul 2026) — single mini-stat, red if >0 else green. The
                // row list itself isn't re-fetched here, same as Clashes
                // above — see at_risk.html's docstring for why that's
                // acceptable staleness for this card.
                var atRiskSummaryEl = document.querySelector('.dash-tile[data-card="at_risk"] .dash-tile-summary');
                if (atRiskSummaryEl) {
                    atRiskSummaryEl.innerHTML = miniStat(
                        summary.at_risk_count > 0 ? 'red' : 'green',
                        summary.at_risk_count,
                        'At Risk'
                    );
                }
            })
            .catch(function () {
                // Same "leave it stale on a network blip" convention as
                // every other fetch in this file.
            });

        // Stat tiles (added 12 Jul 2026, own small fetch rather than being
        // folded into the /api/summary handler above — matches
        // _compute_project_stats() in dashboard.py exactly). Rebuilt via
        // miniStat() same as every other tile's mini-stat as of the
        // twelfth follow-up, when these stopped being a separate
        // getElementById-targeted component and became ordinary
        // .dash-tile entries (see stat_active.html/stat_pending.html/
        // stat_total.html/stat_avg_time.html) — label is '' for the first
        // three since the tile's own heading already says what the number
        // means, same as the Jinja templates render an empty label span
        // rather than omitting it, so the two markups stay byte-for-byte
        // matched. stat_avg_time (added 13 Jul 2026) is the one exception —
        // its label is 'HRS', matching stat_avg_time.html exactly, since a
        // bare number there would be ambiguous.
        fetch(withDashScope('/dashboard/api/project-stats'))
            .then(function (r) { return r.json(); })
            .then(function (stats) {
                var statActiveEl = document.querySelector('.dash-tile[data-card="stat_active"] .dash-tile-summary');
                if (statActiveEl) statActiveEl.innerHTML = miniStat('green', stats.your_active, '');

                var statPendingEl = document.querySelector('.dash-tile[data-card="stat_pending"] .dash-tile-summary');
                if (statPendingEl) statPendingEl.innerHTML = miniStat('blue', stats.pending_approval, '');

                var statTotalEl = document.querySelector('.dash-tile[data-card="stat_total"] .dash-tile-summary');
                if (statTotalEl) statTotalEl.innerHTML = miniStat('orange', stats.total_active, '');

                var statAvgTimeEl = document.querySelector('.dash-tile[data-card="stat_avg_time"] .dash-tile-summary');
                if (statAvgTimeEl) statAvgTimeEl.innerHTML = miniStat('oak', stats.average_time, 'HRS');
            })
            .catch(function () {
                // Same "leave it stale on a network blip" convention as
                // every other fetch in this file.
            });

        // Due card's LIST: only worth refetching if actually expanded.
        // No filter pills to read anymore (removed 12 Jul 2026, fourth
        // follow-up — the card only ever shows one thing now: overdue
        // this week), so this always refetches with 'overdue', full stop.
        //
        // Selector targets .dash-card-body-content, not .dash-tile — since
        // 12 Jul 2026 the tile and its body are separate elements (the
        // body lives in the single .dash-shared-expand area, not next to
        // its tile — see dashboard.css), and .expanded lives on/in the
        // body now, not the tile.
        var dueBodyEl = document.querySelector('.dash-card-body-content[data-card="due"]');
        if (dueBodyEl && dueBodyEl.classList.contains('expanded')) {
            fetchAndRenderDue('overdue');
        }

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

    if (localStorage.getItem(SIDE_BY_SIDE_KEY) === '1') {
        setSideBySide(true);
    }

    // ── Runs exactly once per page session — see file header ─────────────

    if (!window._dashboardListenersBound) {
        window._dashboardListenersBound = true;

        document.addEventListener('click', function (e) {
            // These four are checked FIRST, ahead of toggle-card below, on
            // purpose: the "Flag a Project" button lives inside decisions.html's
            // expanded body, which is itself inside .dash-card-body — NOT
            // inside the .dash-card-header that carries data-action="toggle-card"
            // — so there's no actual bubbling conflict here today. They're
            // still ordered first defensively, so that if a future chunk
            // ever moves one of these triggers somewhere that IS nested
            // inside the header, matching happens here before it would
            // reach (and wrongly fire) the toggle-card branch below.
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

            var toggleHeader = e.target.closest('[data-action="toggle-card"]');
            if (toggleHeader) {
                // Tile (every card except Summary, since 12 Jul 2026) —
                // single-open PAGE-WIDE as of the third follow-up the same
                // day (was single-open-per-row, when each row of 3 had its
                // own .dash-row-expand band — see git history around 12
                // Jul 2026 if that's ever needed again). Now there's just
                // one .dash-shared-expand area for the whole tile grid
                // (.dash-tiles-grid, 5 per row — see dashboard.css), so
                // opening any tile closes whichever OTHER tile was active
                // ANYWHERE on the page, not just within the same row. No
                // localStorage here (unlike the old .dash-card path
                // below) — tiles always start fresh/minimized on load,
                // matching the wireframe's default state, except whichever
                // one a ?view= deep link server-rendered as already open.
                var tile = toggleHeader.closest('.dash-tile');
                if (tile) {
                    if (tile.classList.contains('dash-tile--muted')) return;
                    var wasActive = tile.classList.contains('active');

                    document.querySelectorAll('.dash-tile.active').forEach(function (t) {
                        t.classList.remove('active');
                    });
                    document.querySelectorAll('.dash-card-body-content.expanded').forEach(function (b) {
                        collapseBody(b);
                    });

                    if (!wasActive) {
                        tile.classList.add('active');
                        var body = document.querySelector(
                            '.dash-card-body-content[data-card="' + tile.dataset.card + '"]');
                        expandBody(body);
                    }
                    return;
                }

                // No Summary branch here anymore — its header stopped
                // carrying data-action="toggle-card" entirely as of 12
                // Jul 2026's fourth follow-up (always open, no toggle —
                // see .dash-card--static in dashboard.css), so this
                // `if (toggleHeader)` block is now only ever reachable via
                // a tile click above. applyOpenState()/setStoredOpen()
                // are still defined further up for whatever future
                // mode=None card, if any, might need real toggle behaviour.
                return;
            }

            var tabBtn = e.target.closest('[data-action="switch-tab"]');
            if (tabBtn) { switchTab(tabBtn.dataset.tab); return; }

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

            // NOTE: the deep-dive zone's "All"/"At Risk" filter chips and
            // deadline-sort pills were removed 10 Jul 2026 along with their
            // handlers here — see the comment above the tab-switching
            // section further up for why. If you're looking for
            // applyDeepDiveFilter()/sortDashboardTable(), they're gone;
            // check git history if you need to resurrect that mechanic.

            var sideBtn = e.target.closest('[data-action="toggle-side-by-side"]');
            if (sideBtn) {
                var panels = document.getElementById('dash-deep-dive-panels');
                if (panels) setSideBySide(!panels.classList.contains('dash-side-by-side'));
                return;
            }
        });
    }

})();
