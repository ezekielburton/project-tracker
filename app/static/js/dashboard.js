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

    function setStoredOpen(key, open) {
        localStorage.setItem(STORAGE_PREFIX + key, open ? '1' : '0');
    }

    function applyOpenState(card, open) {
        card.classList.toggle('expanded', open);
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
    function initCards() {
        var hasViewParam = new URLSearchParams(window.location.search).has('view');

        document.querySelectorAll('.dash-card[data-card]').forEach(function (card) {
            if (card.classList.contains('dash-card--muted')) return; // not togglable

            var key = card.dataset.card;

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
    }

    // ── Deep-dive zone: tab switching + side-by-side toggle ─────────────
    // Just the shell mechanic (tab buttons, panel visibility, side-by-side
    // layout toggle) — table CONTENT filtering/sorting is its own section
    // further down (applyDeepDiveFilter()/sortDashboardTable()).

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

    // item.owner from the API is polymorphic — null | {id,name} | [{id,name}, ...] —
    // see the big comment on dash_due_row in _dashboard_macros.html for why.
    // Returns a plain display string, or '' if there's no owner to show.
    function ownerNames(owner) {
        if (!owner) return '';
        if (Array.isArray(owner)) return owner.map(function (u) { return u.name; }).join(', ');
        return owner.name;
    }

    // Builds the exact same markup dash_due_row() produces server-side —
    // see the comment above this section for why these two must be kept in sync.
    function renderDueRow(item) {
        var title = item.project_name;
        if (item.type === 'deliverable') title += ' — ' + item.deliverable_name;
        if (item.type === 'customer' && item.customer_name) title += ' — ' + item.customer_name;

        var subParts = [item.guidance];
        var owners = ownerNames(item.owner);
        if (owners) subParts.push(owners);

        // NOTE: this URL is hardcoded to match project_detail.detail's
        // route (/projects/<id>) rather than built with Flask's url_for —
        // JS has no access to url_for, it only exists at Jinja render
        // time. If that route's URL pattern ever changes, this must be
        // updated to match by hand.
        return '<a class="dash-row" href="/projects/' + item.project_id + '?from=dashboard">' +
            '<span class="rag-badge rag-' + item.rag + '">' + escapeHtml(item.deadline) + '</span>' +
            '<span class="dash-row-main">' +
            '<span class="dash-row-title">' + escapeHtml(title) + '</span>' +
            '<span class="dash-row-sub">' + escapeHtml(subParts.join(' · ')) + '</span>' +
            '</span>' +
            '</a>';
    }

    function fetchAndRenderDue(filterValue) {
        var container = document.getElementById('dash-due-list');
        if (!container) return;

        fetch('/dashboard/api/due?filter=' + encodeURIComponent(filterValue))
            .then(function (r) { return r.json(); })
            .then(function (items) {
                if (!items.length) {
                    container.innerHTML = '<p class="dash-empty-state">Nothing matches this filter.</p>';
                    return;
                }
                container.innerHTML = items.map(renderDueRow).join('');
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
    // sync if you change what a decision row looks like.
    function renderDecisionRow(item) {
        var meta = '';
        if (item.raised_by) meta += 'Raised by ' + escapeHtml(item.raised_by.name) + '<br>';
        meta += escapeHtml(formatDubaiTime(item.raised_at)) + '<br>';
        if (item.days_waiting !== null && item.days_waiting !== undefined) {
            meta += item.days_waiting + ' day' + (item.days_waiting !== 1 ? 's' : '') + ' waiting';
        }

        // Same hardcoded-URL caveat as renderDueRow() above — no url_for()
        // available client-side.
        return '<a class="dash-row" href="/projects/' + item.project_id + '?from=dashboard">' +
            '<span class="dash-row-main">' +
            '<span class="dash-row-title">' + escapeHtml(item.project_name) + '</span>' +
            '<span class="dash-row-sub">' + escapeHtml(item.note) + '</span>' +
            '</span>' +
            '<span style="text-align:right; flex-shrink:0; font-size:0.8rem; color:var(--grey-dark);">' + meta + '</span>' +
            '</a>';
    }

    // Re-fetches the whole queue after a successful flag submission and
    // rebuilds BOTH the collapsed count (always) and the expanded row list
    // (only if the card happens to be open right now — dash-decisions-list
    // won't exist in the DOM otherwise, hence the null check). A newly
    // flagged project is essentially always a different project than the
    // ones already showing, so a full replace is simpler and always
    // correct — same reasoning fetchAndRenderDue() uses for the Due card.
    function refreshDecisionsCard() {
        fetch('/dashboard/api/decisions')
            .then(function (r) { return r.json(); })
            .then(function (items) {
                var card = document.querySelector('.dash-card[data-card="decisions"]');
                var summaryEl = card ? card.querySelector('.dash-card-summary') : null;
                if (summaryEl) {
                    summaryEl.textContent = items.length + ' project' + (items.length !== 1 ? 's' : '') + ' flagged';
                }

                var list = document.getElementById('dash-decisions-list');
                if (!list) return; // card isn't expanded right now — nothing else to update
                list.innerHTML = items.length
                    ? items.map(renderDecisionRow).join('')
                    : '<p class="dash-empty-state">No decisions currently needed.</p>';
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

    // Hand-written JS mirror of the row markup in next_actions.html — same
    // duplication tradeoff as renderDueRow()/renderDecisionRow() above.
    // Unlike those two, this render function needs to know which tab is
    // active: the owner's name is only ever shown on the Others' Actions
    // tab (see the big comment in next_actions.html for why), so
    // fetchAndRenderNextActions() passes the current filter through.
    function renderNextActionRow(item, filterType) {
        var ownerLine = '';
        if (filterType === 'others') {
            var owners = ownerNames(item.owner);
            ownerLine = '<span class="dash-row-sub">' + escapeHtml(owners || 'Unassigned') + '</span>';
        }

        return '<a class="dash-row" href="/projects/' + item.project_id + '?from=dashboard">' +
            '<span class="rag-badge rag-' + item.rag + '">' + escapeHtml(item.deadline || 'No deadline') + '</span>' +
            '<span class="dash-row-main">' +
            '<span class="dash-row-title">' + escapeHtml(item.project_name) + '</span>' +
            '<span class="dash-row-sub">' + escapeHtml(item.guidance) + '</span>' +
            ownerLine +
            '</span>' +
            '</a>';
    }

    function fetchAndRenderNextActions(filterType) {
        var container = document.getElementById('dash-next-actions-list');
        if (!container) return;

        fetch('/dashboard/api/next-actions?filter=' + encodeURIComponent(filterType))
            .then(function (r) { return r.json(); })
            .then(function (items) {
                if (!items.length) {
                    container.innerHTML = '<p class="dash-empty-state">' +
                        (filterType === 'mine' ? 'Nothing needs your action right now.' : 'Nothing is currently waiting on anyone else.') +
                        '</p>';
                    return;
                }
                container.innerHTML = items.map(function (item) { return renderNextActionRow(item, filterType); }).join('');
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

    // ── Deep-dive zone: filter chips + deadline sort ─────────────────────
    //
    // Both #dash-deep-dive-projects-tbody and #dash-deep-dive-deliverables-tbody
    // are fully server-rendered with every scoped row already in the DOM
    // (see _compute_deep_dive_projects()/_compute_deep_dive_deliverables()
    // in dashboard.py) — same convention the OLD role dashboards use for
    // their own project tables (app/templates/dashboards/cs.html). Both
    // the "All"/"At Risk" filter chips and the deadline sort act entirely
    // against each row's data-* attributes already sitting in the DOM —
    // no fetch, nothing to re-render, just show/hide and reorder.

    // "All" / "At Risk" chips. `scope` is 'projects' or 'deliverables' —
    // each table has its own independent pair of chips (see data-scope on
    // the buttons in dashboard.html), so filtering one tab never touches
    // the other's rows.
    function applyDeepDiveFilter(scope, filterValue) {
        var tbody = document.getElementById('dash-deep-dive-' + scope + '-tbody');
        if (!tbody) return;
        Array.from(tbody.rows).forEach(function (row) {
            var show = filterValue === 'all' || row.dataset.atRisk === 'true';
            row.classList.toggle('hidden', !show);
        });
    }

    // CLAUDE.md documents a "Dashboard sort toggle" pattern — a
    // .deadline-sort-wrap[data-tbody] holding data-deadline-sort pills —
    // as already "used on all dashboards". It turns out nothing in this
    // codebase actually implements it yet (checked: zero matches for
    // data-deadline-sort anywhere before this chunk); the OLD dashboards
    // sort via a <select> dropdown wired to sortTableBy() in main.js
    // instead. This function is that documented pattern's first real
    // implementation, and deliberately reuses main.js's exact algorithm
    // (read row.dataset[field], '9999-12-31' fallback for a missing date,
    // localeCompare on the resulting ISO strings) so sorting behaves
    // identically everywhere in the app — it just doesn't need
    // sortTableBy()'s expansion-row-grouping step, since no table on this
    // new dashboard has expansion rows.
    function sortDashboardTable(tbodyId, field) {
        var tbody = document.getElementById(tbodyId);
        if (!tbody) return;
        var rows = Array.from(tbody.rows);
        rows.sort(function (a, b) {
            var aVal = a.dataset[field] || '9999-12-31';
            var bVal = b.dataset[field] || '9999-12-31';
            return aVal.localeCompare(bVal);
        });
        rows.forEach(function (row) { tbody.appendChild(row); });
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
        fetch('/dashboard/api/summary')
            .then(function (r) { return r.json(); })
            .then(function (summary) {
                // Due card's three collapsed pills — rebuilt wholesale from
                // scratch rather than patched number-by-number; cheap, and
                // guarantees this always matches due.html's exact original
                // markup (see the due_summary Jinja block there).
                var dueSummaryEl = document.querySelector('.dash-card[data-card="due"] .dash-card-summary');
                if (dueSummaryEl) {
                    dueSummaryEl.innerHTML =
                        '<span class="rag-badge rag-red">' + summary.overdue + ' Overdue</span>' +
                        '<span class="rag-badge rag-red">' + summary.due_today + ' Today</span>' +
                        '<span class="rag-badge rag-yellow">' + summary.due_week + ' This Week</span>';
                }

                var nextActionsSummaryEl = document.querySelector('.dash-card[data-card="next_actions"] .dash-card-summary');
                if (nextActionsSummaryEl) {
                    nextActionsSummaryEl.textContent =
                        summary.my_actions + ' action' + (summary.my_actions !== 1 ? 's' : '') + ' needed from me, ' +
                        summary.others_actions + ' waiting on others';
                }

                var whatChangedSummaryEl = document.querySelector('.dash-card[data-card="what_changed"] .dash-card-summary');
                if (whatChangedSummaryEl) {
                    whatChangedSummaryEl.textContent =
                        summary.what_changed + ' update' + (summary.what_changed !== 1 ? 's' : '') + ' since yesterday';
                }

                var clashesCardEl = document.querySelector('.dash-card[data-card="clashes"]');
                if (clashesCardEl) {
                    var clashesSummaryEl = clashesCardEl.querySelector('.dash-card-summary');
                    if (clashesSummaryEl) {
                        clashesSummaryEl.textContent = summary.clashes > 0
                            ? (summary.clashes + ' clash' + (summary.clashes !== 1 ? 'es' : '') + ' detected')
                            : 'No clashes';
                    }
                    // NOTE: this toggles the muted VISUAL state live, but the
                    // header <button>'s disabled attribute (set server-side
                    // by the dash_card() macro, see _dashboard_macros.html)
                    // is NOT re-toggled here — a card that goes from 0 to 1+
                    // clashes without a full page reload will look active but
                    // stay unclickable until the next reload. Small, known
                    // gap; not worth a bigger DOM-attribute dance for
                    // something that self-corrects on the user's next visit.
                    clashesCardEl.classList.toggle('dash-card--muted', summary.clashes === 0);
                }
            })
            .catch(function () {
                // Same "leave it stale on a network blip" convention as
                // every other fetch in this file.
            });

        // Due card's LIST: only worth refetching if actually expanded.
        // Reads whichever filter pill(s) are currently active rather than
        // tracking separate state — due-filter's click handler (below) is
        // the only thing that ever changes which pills are active, so the
        // DOM is always the source of truth. More than one active pill only
        // happens in the untouched "Overdue + Today" combined default (see
        // due.html) — the API's own combined value for that state is
        // 'overdue_today', so that's what gets requested in that case.
        var dueCardEl = document.querySelector('.dash-card[data-card="due"]');
        if (dueCardEl && dueCardEl.classList.contains('expanded')) {
            var activeDueBtns = dueCardEl.querySelectorAll('[data-action="due-filter"].active');
            var dueFilterValue = activeDueBtns.length > 1
                ? 'overdue_today'
                : (activeDueBtns[0] && activeDueBtns[0].dataset.filter);
            if (dueFilterValue) fetchAndRenderDue(dueFilterValue);
        }

        // Decisions: refreshDecisionsCard() already updates both the
        // collapsed count and the expanded list (only if expanded) in one
        // call — cheap enough to just always run it, no expanded-check needed.
        refreshDecisionsCard();

        // Next Actions' LIST: same "only if expanded" idea as Due above,
        // using whichever tab (My/Others) is currently active.
        var nextActionsCardEl = document.querySelector('.dash-card[data-card="next_actions"]');
        if (nextActionsCardEl && nextActionsCardEl.classList.contains('expanded')) {
            var activeNextActionsBtn = nextActionsCardEl.querySelector('[data-action="next-actions-tab"].active');
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

            var toggleHeader = e.target.closest('[data-action="toggle-card"]');
            if (toggleHeader) {
                var card = toggleHeader.closest('.dash-card');
                if (card && !card.classList.contains('dash-card--muted')) {
                    var nowOpen = !card.classList.contains('expanded');
                    applyOpenState(card, nowOpen);
                    setStoredOpen(card.dataset.card, nowOpen);
                }
                return;
            }

            var tabBtn = e.target.closest('[data-action="switch-tab"]');
            if (tabBtn) { switchTab(tabBtn.dataset.tab); return; }

            var dueFilterBtn = e.target.closest('[data-action="due-filter"]');
            if (dueFilterBtn) {
                // Radio-style: exactly one pill active at a time. The
                // initial page load is the one exception — both Overdue
                // and Due Today start active together (server-rendered, see
                // due.html) to represent the "overdue_today" combined
                // default — but the first click on ANY pill here collapses
                // that back down to single-category mode.
                document.querySelectorAll('[data-action="due-filter"]').forEach(function (btn) {
                    btn.classList.toggle('active', btn === dueFilterBtn);
                });
                fetchAndRenderDue(dueFilterBtn.dataset.filter);
                return;
            }

            var nextActionsBtn = e.target.closest('[data-action="next-actions-tab"]');
            if (nextActionsBtn) {
                // Strict two-way toggle — always exactly one active, unlike
                // the Due card's "both start active, first click collapses
                // to one" pattern (see the comment on due-filter above).
                document.querySelectorAll('[data-action="next-actions-tab"]').forEach(function (btn) {
                    btn.classList.toggle('active', btn === nextActionsBtn);
                });
                fetchAndRenderNextActions(nextActionsBtn.dataset.filter);
                return;
            }

            var clashesBtn = e.target.closest('[data-action="clashes-tab"]');
            if (clashesBtn) { switchClashesTab(clashesBtn.dataset.filter); return; }

            var deepDiveFilterBtn = e.target.closest('[data-action="deep-dive-filter"]');
            if (deepDiveFilterBtn) {
                var ddScope = deepDiveFilterBtn.dataset.scope;
                // Scoped to [data-scope="..."] so toggling the Projects
                // tab's chips never touches the Deliverables tab's chips.
                document.querySelectorAll('[data-action="deep-dive-filter"][data-scope="' + ddScope + '"]').forEach(function (btn) {
                    btn.classList.toggle('active', btn === deepDiveFilterBtn);
                });
                applyDeepDiveFilter(ddScope, deepDiveFilterBtn.dataset.filter);
                return;
            }

            // CLAUDE.md's documented data-deadline-sort pattern — see the
            // big comment on sortDashboardTable() above. data-tbody comes
            // off the closest .deadline-sort-wrap, exactly as documented.
            var deadlineSortBtn = e.target.closest('[data-deadline-sort]');
            if (deadlineSortBtn) {
                var sortWrap = deadlineSortBtn.closest('.deadline-sort-wrap');
                if (sortWrap) {
                    sortWrap.querySelectorAll('[data-deadline-sort]').forEach(function (btn) {
                        btn.classList.toggle('active', btn === deadlineSortBtn);
                    });
                    sortDashboardTable(sortWrap.dataset.tbody, deadlineSortBtn.dataset.deadlineSort);
                }
                return;
            }

            var sideBtn = e.target.closest('[data-action="toggle-side-by-side"]');
            if (sideBtn) {
                var panels = document.getElementById('dash-deep-dive-panels');
                if (panels) setSideBySide(!panels.classList.contains('dash-side-by-side'));
                return;
            }
        });
    }

})();
