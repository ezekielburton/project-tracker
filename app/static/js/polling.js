// app/static/js/polling.js
//
// Background polling for the dashboard and project detail pages.
// Runs silently — no spinners or loading states shown to the user.
// All network errors are swallowed so a brief blip never breaks the UI.
//
// Dashboard: polls every 30s. Patches changed status badges in-place.
//            Falls back to a full reload only if a project was added or removed.
// Detail:    polls every 15s. Updates the status badge and on-hold banner.
//
// SPA-aware: sidebar.js dispatches 'helix:navigated' after every content swap.
// init() is called on both the initial page load and after every navigation,
// so the right poller is always running for whichever page is currently visible.

(function () {
    'use strict';

    // Track the active interval IDs so teardown() can clear them before
    // init() sets up new ones for the next page. Without this, navigating
    // between pages would stack up duplicate intervals.
    var _dashboardInterval = null;
    var _detailInterval    = null;


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
    // TEARDOWN — clear any running intervals from the previous page
    // Called at the start of init() so navigating never stacks up duplicates
    // ─────────────────────────────────────────────────────────────────────────

    function teardown() {
        if (_dashboardInterval !== null) {
            clearInterval(_dashboardInterval);
            _dashboardInterval = null;
        }
        if (_detailInterval !== null) {
            clearInterval(_detailInterval);
            _detailInterval = null;
        }
    }


    // ─────────────────────────────────────────────────────────────────────────
    // INIT — detect which page is showing and start the right poller
    // Called on initial page load AND after every SPA navigation
    // ─────────────────────────────────────────────────────────────────────────

    function init() {
        // Always tear down before reinitialising — prevents duplicate intervals
        // when the user navigates between pages via the sidebar
        teardown();

        // Dashboard: identified by one of the view container IDs that only exist
        // on dashboard pages. We do NOT use .dashboard-toggle here because that
        // class is also on the notification panel in base.html, which would make
        // this condition true on every page including project detail.
        if (document.querySelector('#my-projects-view, #all-projects-view, #team-view, #personal-view')) {
            _dashboardInterval = setInterval(pollDashboard, 2000);
        }

        // Detail page: identified by #section-assignments (unique to detail.html)
        // Extract the project ID from the URL so we don't need an extra template attribute
        var pathMatch = window.location.pathname.match(/\/projects\/(\d+)/);
        if (document.querySelector('#section-assignments') && pathMatch) {
            var projectId = pathMatch[1];
            // Wrap pollDetail in a closure so the projectId is captured correctly
            _detailInterval = setInterval(function () {
                pollDetail(projectId);
            }, 2000);
        }
    }


    // ─────────────────────────────────────────────────────────────────────────
    // WIRE UP
    // ─────────────────────────────────────────────────────────────────────────

    // Run on the initial full page load
    init();

    // Re-run after every SPA navigation — sidebar.js dispatches 'helix:navigated'
    // once the new page content has been swapped into #main-content
    document.addEventListener('helix:navigated', function () {
        init();
    });

})();
