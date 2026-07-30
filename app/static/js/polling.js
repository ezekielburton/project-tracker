// app/static/js/polling.js
//
// Live updates for the old role dashboards, the project detail page, and
// (as of UI Chunk 9) the new role-based dashboard (app/templates/dashboard.html).
// Runs silently — no spinners or loading states shown to the user.
// All network errors are swallowed so a brief blip never breaks the UI.
//
// SSE redesign (Stage 5): the actual fetch/compare/patch logic below
// (pollDashboard, pollDetail, and their helpers) is UNCHANGED from the old
// setInterval-based design — only what TRIGGERS them changed. Each page
// now opens an EventSource to the matching /sse/... route (Stage 4), which
// pushes a tiny "something changed" ping the moment a Postgres NOTIFY
// fires (Stage 2/3) instead of waiting for a timer. If the SSE connection
// ever fails — old browser, proxy that blocks streaming, network hiccup —
// _connectLiveStream() transparently falls back to the original 1s
// setInterval polling until SSE recovers, so this never becomes a hard
// dependency on the new transport.
//
// Old dashboard: patches changed status badges in-place.
//                Falls back to a full reload only if a project was added or removed.
// Detail:        reloads the page if anything in its fingerprint changed.
// New dashboard: refresh logic lives in dashboard.js, not here — see the
//                big comment on the .dash-content-tabs check in init() below.
//
// SPA-aware: sidebar.js dispatches 'helix:navigated' after every content swap.
// init() is called on both the initial page load and after every navigation,
// so the right stream is always running for whichever page is currently visible.

(function () {
    'use strict';

    // Track the active stream handles so teardown() can close them before
    // init() sets up new ones for the next page. Without this, navigating
    // between pages would stack up duplicate connections/intervals.
    var _dashboardStream = null;
    var _detailStream    = null;
    // Separate from _dashboardStream above on purpose, even though the two
    // can never both be open at once (the OLD dashboard and the NEW
    // role-based dashboard are different pages/routes) — keeping them in
    // distinct variables avoids any ambiguity about which page's stream is
    // being torn down, and matches this file's existing one-variable-per-
    // page-type convention (_dashboardStream / _detailStream).
    var _roleDashboardStream = null;

    // How often the fallback interval polls, when SSE isn't available or
    // has dropped — matches the cadence the old setInterval-only design used.
    var _FALLBACK_INTERVAL_MS = 1000;

    // Opens an EventSource at `url` and calls `onEvent` every time it pushes
    // a message. If EventSource isn't supported at all, or the connection
    // errors out (proxy issue, network blip, server restart), falls back to
    // calling `onEvent` on a plain setInterval every `intervalMs` — the
    // exact behavior this file used before SSE existed — until/unless the
    // stream reconnects on its own (native EventSource retries
    // automatically) or a fresh message arrives, at which point the
    // fallback interval is cleared again.
    //
    // Returns { close } so callers can tear everything down on navigation.
    function _connectLiveStream(url, onEvent, intervalMs) {
        var fallbackInterval = null;

        function startFallback() {
            if (fallbackInterval !== null) return; // already running
            fallbackInterval = setInterval(onEvent, intervalMs);
        }

        function stopFallback() {
            if (fallbackInterval !== null) {
                clearInterval(fallbackInterval);
                fallbackInterval = null;
            }
        }

        if (typeof EventSource === 'undefined') {
            // No SSE support at all in this browser — just poll like before.
            startFallback();
            return { close: stopFallback };
        }

        var source = new EventSource(url);

        source.onopen = stopFallback;
        source.onmessage = function () {
            stopFallback();
            onEvent();
        };
        source.onerror = function () {
            // SSE dropped or failed to (re)connect — keep the UI live via
            // polling as a safety net. Worst case during a brief reconnect
            // blip is a redundant poll or two running alongside SSE.
            startFallback();
        };

        return {
            close: function () {
                source.close();
                stopFallback();
            }
        };
    }


    // ─────────────────────────────────────────────────────────────────────────
    // SHARED HELPERS
    // All functions are declared at the top of the IIFE — not inside if-blocks.
    // Block-level function declarations in strict mode behave inconsistently
    // across browsers and can silently prevent the entire script from running.
    // ─────────────────────────────────────────────────────────────────────────

    // Maps each dashboard toggle button ID to the key the API uses in its 'tabs' response.
    // null means "don't poll this tab" (Approved projects are static once locked).
    var TAB_KEY_MAP = {
        'btn-my-projects':       'my',
        'btn-all-projects':      'all',
        'btn-team-view':         'team',
        'btn-personal-view':     'my',   // designer Personal tab maps to the 'my' API key
        'btn-approved-projects': null,
    };

    // Maps each API tab key to the DOM container(s) that hold its project rows.
    // 'my' maps to two IDs because CS uses #my-projects-view while designer uses #personal-view.
    var CONTAINER_MAP = {
        'my':   ['#my-projects-view', '#personal-view'],
        'all':  ['#all-projects-view'],
        'team': ['#team-view'],
    };

    // Returns the API tab key for whichever toggle button is currently active,
    // or null if the visible tab doesn't need polling (e.g. Approved).
    //
    // WHY getElementById loop instead of querySelector('.toggle-btn.active'):
    // base.html's notification panel also uses class="toggle-btn active" on its
    // Inbox button. It appears earlier in the DOM than the dashboard tab buttons,
    // so a generic querySelector would always return that button first, making
    // this function always return null on dashboard pages. Looking up each known
    // button by its exact ID is immune to that collision.
    function getActiveTabKey() {
        var knownIds = Object.keys(TAB_KEY_MAP);
        for (var i = 0; i < knownIds.length; i++) {
            var btn = document.getElementById(knownIds[i]);
            if (btn && btn.classList.contains('active')) {
                return TAB_KEY_MAP[knownIds[i]];
            }
        }
        return null;
    }

    // Builds a map of { project_id → fingerprint } for all rows currently in the DOM
    // for the given tab key. Used to detect both structural changes (IDs) and
    // assignment changes (fingerprint) without re-implementing Jinja logic in JS.
    function getDomProjectMap(tabKey) {
        var selectors = CONTAINER_MAP[tabKey];
        if (!selectors) return {};

        var map = {};
        selectors.forEach(function (sel) {
            var container = document.querySelector(sel);
            if (!container) return;
            container.querySelectorAll('[data-project-id]').forEach(function (el) {
                var id = parseInt(el.dataset.projectId, 10);
                // data-fp holds sorted designer user IDs, set by the Jinja template
                map[id] = el.dataset.fp || '';
            });
        });

        return map;
    }

    // Updates any status badge in the dashboard table whose status has changed.
    // Only touches the DOM for rows that actually differ — avoids unnecessary repaints.
    function patchStatusBadges(serverProjects) {
        serverProjects.forEach(function (p) {
            // Find the <tr> for this project anywhere on the page
            var row = document.querySelector('[data-project-id="' + p.id + '"]');
            if (!row) return;

            // The badge must have data-status (added in Step 3 of this feature)
            var badge = row.querySelector('.status-badge[data-status]');
            if (!badge) return;

            // Skip this badge — nothing has changed
            if (badge.dataset.status === p.status) return;

            // Remove the old s-* CSS class (e.g. "s-in_progress") and apply the new one
            badge.className = badge.className.replace(/\bs-\S+/g, '').trim();
            badge.classList.add('s-' + p.status);

            // Update the stored value so the next poll compares against the new status
            badge.dataset.status = p.status;

            // Reformat to human-readable: "revision_in_progress" → "Revision In Progress"
            badge.textContent = p.status
                .replace(/_/g, ' ')
                .replace(/\b\w/g, function (c) { return c.toUpperCase(); });
        });
    }


    // ─────────────────────────────────────────────────────────────────────────
    // DASHBOARD POLL
    // ─────────────────────────────────────────────────────────────────────────

    function pollDashboard() {
        var activeTabKey = getActiveTabKey();

        // No point polling if the active tab isn't tracked (e.g. Approved tab)
        if (!activeTabKey) return;

        fetch('/api/projects/poll')
            .then(function (response) {
                if (!response.ok) return null; // server error — skip this cycle
                return response.json();
            })
            .then(function (data) {
                if (!data) return;

                var tabs       = data.tabs || {};
                var serverList = tabs[activeTabKey] || [];

                // Build a sorted ID list from the server response for structural comparison
                var serverIds = serverList
                    .map(function (p) { return p.id; })
                    .sort(function (a, b) { return a - b; });

                // Get the current DOM state: { id → fingerprint } for the active tab
                var domMap = getDomProjectMap(activeTabKey);
                var domIds = Object.keys(domMap)
                    .map(Number)
                    .sort(function (a, b) { return a - b; });

                // 1. If IDs differ, a project was added or removed — full reload
                if (JSON.stringify(serverIds) !== JSON.stringify(domIds)) {
                    window.location.reload();
                    return;
                }

                // 2. If any project's fingerprint changed (designer assigned/removed),
                //    reload — we can't re-render designer avatars in JS
                var fpChanged = serverList.some(function (p) {
                    return domMap[p.id] !== p.fp;
                });
                if (fpChanged) {
                    window.location.reload();
                    return;
                }

                // 3. IDs and fingerprints all match — only status may have changed.
                //    Patch just the status badges in-place for a smooth, flicker-free update.
                //    Flatten all tabs so badges in hidden tabs are updated too.
                var allProjects = [];
                Object.values(tabs).forEach(function (list) {
                    allProjects = allProjects.concat(list);
                });
                patchStatusBadges(allProjects);
            })
            .catch(function () {
                // Network blip or malformed JSON — silently skip, try again next cycle
            });
    }


    // ─────────────────────────────────────────────────────────────────────────
    // DETAIL POLL
    // ─────────────────────────────────────────────────────────────────────────

    function pollDetail(projectId) {
        fetch('/api/projects/' + projectId + '/poll')
            .then(function (response) {
                if (!response.ok) return null;
                return response.json();
            })
            .then(function (data) {
                if (!data) return;

                // Compare the full page fingerprint against what was rendered on load.
                // If anything changed (status, designers, flags, submissions, revisions,
                // concept/KV state), reload — the detail page is complex enough that
                // re-rendering everything in JS would duplicate all the Jinja logic.
                var container = document.getElementById('section-assignments');
                if (container && container.dataset.fp !== data.fp) {
                    window.location.reload();
                    return;
                }

                // Fingerprint matches — nothing has changed, nothing to do.
                // (The on-hold banner and status badge are covered by the reload path above.)
            })
            .catch(function () {
                // Network blip — silently skip
            });
    }


    // ─────────────────────────────────────────────────────────────────────────
    // TEARDOWN — close any running stream/interval from the previous page
    // Called at the start of init() so navigating never stacks up duplicates
    // ─────────────────────────────────────────────────────────────────────────

    function teardown() {
        if (_dashboardStream !== null) {
            _dashboardStream.close();
            _dashboardStream = null;
        }
        if (_detailStream !== null) {
            _detailStream.close();
            _detailStream = null;
        }
        if (_roleDashboardStream !== null) {
            _roleDashboardStream.close();
            _roleDashboardStream = null;
        }
    }


    // ─────────────────────────────────────────────────────────────────────────
    // INIT — detect which page is showing and start the right live stream
    // Called on initial page load AND after every SPA navigation
    // ─────────────────────────────────────────────────────────────────────────

    function init() {
        // Always tear down before reinitialising — prevents duplicate
        // streams/intervals when the user navigates via the sidebar
        teardown();
        
        fetch('/api/version')
            .then(function(response) {
                return response.json();
            })
            .then(function(data) {
                if (data.version !== HELIX_VERSION) {
                    window.location.reload();
                }
            })
            .catch(function() {

            });
        
        // Dashboard: identified by one of the view container IDs that only exist
        // on dashboard pages. We do NOT use .dashboard-toggle here because that
        // class is also on the notification panel in base.html, which would make
        // this condition true on every page including project detail.
        if (document.querySelector('#my-projects-view, #all-projects-view, #team-view, #personal-view')) {
            _dashboardStream = _connectLiveStream('/sse/dashboard', pollDashboard, _FALLBACK_INTERVAL_MS);
        }

        // Detail page: identified by #section-assignments (unique to detail.html)
        // Extract the project ID from the URL so we don't need an extra template attribute
        var pathMatch = window.location.pathname.match(/\/projects\/(\d+)/);
        if (document.querySelector('#section-assignments') && pathMatch) {
            var projectId = pathMatch[1];
            _detailStream = _connectLiveStream('/sse/projects/' + projectId, function () {
                pollDetail(projectId);
            }, _FALLBACK_INTERVAL_MS);
        }

        // New role-based dashboard (app/templates/dashboard.html): identified
        // by .dash-content-tabs, unique to that page (same idea as the old
        // dashboard's container-ID check above — pick a marker that can't
        // also appear on other pages). Was .dash-cards-grid before the 15
        // Jul 2026 tab-strip redesign (see CLAUDE.md) — that class was
        // deleted along with the old Summary-only card wrapper it marked,
        // so this had to move to a class that still renders unconditionally
        // for every role. .dash-content-tabs (the tab strip itself) fits:
        // every role's card_order has at least 'summary' in it, so this div
        // always renders on this page, and only this page. Reuses the SAME
        // /sse/dashboard route the old dashboard subscribes to above —
        // sse.py's dashboard_stream() is a generic "something about some
        // project changed" doorbell (see CLAUDE.md's Live Updates section),
        // not tied to either dashboard's specific markup, so both pages can
        // safely listen to it at once (never simultaneously in practice,
        // since they're different pages, but nothing here assumes otherwise).
        //
        // Unlike pollDashboard()/pollDetail() above, this page's own refresh
        // logic doesn't live in this file — it's owned by dashboard.js
        // (which already has every fetch/render function this page needs,
        // built up over UI Chunks 1-8) via window.helixDashboardRefresh().
        // polling.js deliberately doesn't know anything about this new
        // dashboard's cards/DOM beyond "does this marker exist" — same
        // separation-of-concerns sse.py's own comment describes for itself.
        if (document.querySelector('.dash-content-tabs')) {
            _roleDashboardStream = _connectLiveStream('/sse/dashboard', function () {
                if (window.helixDashboardRefresh) window.helixDashboardRefresh();
            }, _FALLBACK_INTERVAL_MS);
        }
    }


    // ─────────────────────────────────────────────────────────────────────────
    // WIRE UP
    // ─────────────────────────────────────────────────────────────────────────

    // Expose pause/resume so modals can stop polling while they're open
    window.helixPolling = {
        pause:  teardown,
        resume: init
    };

    // Run on the initial full page load
    init();

    // Re-run after every SPA navigation — sidebar.js dispatches 'helix:navigated'
    // once the new page content has been swapped into #main-content
    document.addEventListener('helix:navigated', function () {
        init();
    });

})();
