// polling.js — live refresh for whichever page is showing.
// Each page type opens an EventSource on an /sse/... route that pings when
// data changes. If SSE is unsupported or drops, _connectLiveStream() polls
// every second instead until the stream recovers.
// This file decides WHEN to refresh; each page owns the HOW through a
// window.helix*Refresh*() hook.
//
// SPA: init() runs on load and after every 'helix:navigated' (sidebar.js);
// teardown() closes the previous page's streams first so nothing stacks.

(function () {
    'use strict';

    // One handle per page type, so teardown() can close them all before init()
    // opens the next page's. Each page type has its own variable even where
    // two can never be open together.
    var _roleDashboardStream = null;
    // Project overlay on the Projects list page. Not part of init()/teardown():
    // project_list.js starts and stops it around overlay open/close.
    var _overlayStream = null;
    var _projectTableStream = null;
    var _clientServicingTableStream = null;
    var _clientServicingCalendarStream = null;

    var _clientServicingDashboardStream = null;

    // Friction Log in the Signal tray. Like the overlay stream, it sits outside
    // init()/teardown(): signal_tray.js starts and stops it with the tab.
    var _frictionStream = null;

    // Fallback poll cadence while SSE is unavailable.
    var _FALLBACK_INTERVAL_MS = 1000;
    // The Friction Log reload is a whole list, so its fallback polls slower.
    var _FRICTION_FALLBACK_MS = 5000;
    // Last /api/version check; module-level so the debounce spans navigations.
    var _lastVersionCheck = 0;

    // Opens an EventSource at `url` and calls onEvent(data) per message; data
    // is the server's payload (a project_id for /sse/dashboard and
    // /sse/projects/<id>, see sse_relay.py). If EventSource is missing or
    // errors, calls onEvent() with NO argument every intervalMs until a
    // message or reconnect arrives (EventSource retries by itself).
    // Returns { close }.
    function _connectLiveStream(url, onEvent, intervalMs) {
        var fallbackInterval = null;

        function startFallback() {
            if (fallbackInterval !== null) return;
            fallbackInterval = setInterval(onEvent, intervalMs);
        }

        function stopFallback() {
            if (fallbackInterval !== null) {
                clearInterval(fallbackInterval);
                fallbackInterval = null;
            }
        }

        if (typeof EventSource === 'undefined') {
            // No SSE in this browser: poll only.
            startFallback();
            return { close: stopFallback };
        }

        var source = new EventSource(url);

        source.onopen = stopFallback;
        source.onmessage = function (e) {
            stopFallback();
            onEvent(e.data);
        };
        source.onerror = function () {
            // Poll until SSE recovers; a reconnect blip may cause a redundant poll or two.
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
    // TEARDOWN — close the previous page's streams/intervals.
    // Also exposed as helixPolling.pause(). Does not touch _overlayStream.
    // ─────────────────────────────────────────────────────────────────────────

    function teardown() {
        if (_roleDashboardStream !== null) {
            _roleDashboardStream.close();
            _roleDashboardStream = null;
        }
        if (_projectTableStream !== null) {
            _projectTableStream.close();
            _projectTableStream = null;
        }
        if (_clientServicingTableStream !== null) {
            _clientServicingTableStream.close();
            _clientServicingTableStream = null;
        }
        if (_clientServicingCalendarStream !== null) {
            _clientServicingCalendarStream.close();
            _clientServicingCalendarStream = null;
        }
        if (_clientServicingDashboardStream !== null) {
            _clientServicingDashboardStream.close();
            _clientServicingDashboardStream = null;
        }
    }

    function stopOverlayStream() {
        if (_overlayStream !== null) {
            _overlayStream.close();
            _overlayStream = null;
        }
    }

    function startOverlayStream(projectId, onChange) {
        stopOverlayStream();
        _overlayStream = _connectLiveStream('/sse/projects/' + projectId, onChange, _FALLBACK_INTERVAL_MS);
    }

    function stopFrictionStream() {
        if (_frictionStream !== null) {
            _frictionStream.close();
            _frictionStream = null;
        }
    }

    function startFrictionStream(onChange) {
        stopFrictionStream();
        _frictionStream = _connectLiveStream('/sse/friction', onChange, _FRICTION_FALLBACK_MS);
    }


    // ─────────────────────────────────────────────────────────────────────────
    // INIT — detect which page is showing and start its live stream.
    // Runs on load, after every SPA navigation, and as helixPolling.resume().
    // ─────────────────────────────────────────────────────────────────────────

    function init() {
        teardown();
        
        // Redeploy check: reload if the server's version stamp differs from
        // HELIX_VERSION (base.html). At most once per 10s, so rapid navigation
        // doesn't spend connection slots on it.
        var _now = Date.now();
        if (_now - _lastVersionCheck > 10000) {
            _lastVersionCheck = _now;
            fetch('/api/version')
                .then(function (response) { return response.json(); })
                .then(function (data) {
                    if (data.version !== HELIX_VERSION) { window.location.reload(); }
                })
                .catch(function () { });
        }
        
        // Role dashboard (dashboard module): .dash-content-tabs always renders
        // there and nowhere else. /sse/dashboard is a generic "some project
        // changed" ping, so several page types share it. Refresh is owned by
        // dashboard.js via window.helixDashboardRefresh().
        if (document.querySelector('.dash-content-tabs')) {
            _roleDashboardStream = _connectLiveStream('/sse/dashboard', function () {
                if (window.helixDashboardRefresh) window.helixDashboardRefresh();
            }, _FALLBACK_INTERVAL_MS);
        }

        // Projects list page (.project-list-page). The SSE payload's project id
        // goes to window.helixRefreshProjectTable() so it can update one row.
        if (document.querySelector('.project-list-page')) {
            _projectTableStream = _connectLiveStream('/sse/dashboard', function (projectId) {
                if (window.helixRefreshProjectTable) window.helixRefreshProjectTable(projectId);
            }, _FALLBACK_INTERVAL_MS);
        }

        // Client Servicing table: window.helixRefreshClientServicingTable() (client_servicing.js).
        if (document.getElementById('client-servicing-table-body')) {
            _clientServicingTableStream = _connectLiveStream('/sse/dashboard', function () {
                if (window.helixRefreshClientServicingTable) window.helixRefreshClientServicingTable();
            }, _FALLBACK_INTERVAL_MS);
        }

        // Client Servicing calendar: window.helixRefreshClientServicingCalendar().
        if (document.querySelector('.cs-cal-page')) {
            _clientServicingCalendarStream = _connectLiveStream('/sse/dashboard', function () {
                if (window.helixRefreshClientServicingCalendar) window.helixRefreshClientServicingCalendar();
            }, _FALLBACK_INTERVAL_MS);
        }

        // Client Servicing dashboard (.cs-dash): window.helixRefreshCSDashboard()
        // (client_servicing_dashboard.js).
        if (document.querySelector('.cs-dash')) {
            _clientServicingDashboardStream = _connectLiveStream('/sse/dashboard', function () {
                if (window.helixRefreshCSDashboard) window.helixRefreshCSDashboard();
            }, _FALLBACK_INTERVAL_MS);
        }
    }


    // ─────────────────────────────────────────────────────────────────────────
    // WIRE UP
    // ─────────────────────────────────────────────────────────────────────────

    // Modals pause live refresh while open. resume() is a full init().
    window.helixPolling = {
        pause: teardown,
        resume: init,
        startOverlayStream: startOverlayStream,
        stopOverlayStream: stopOverlayStream,
        startFrictionStream: startFrictionStream,
        stopFrictionStream: stopFrictionStream
    };

    init();

    // sidebar.js fires 'helix:navigated' after swapping #main-content.
    document.addEventListener('helix:navigated', function () {
        init();
    });

})();
