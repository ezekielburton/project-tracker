// Live refresh for the CS Dashboard. polling.js calls
// window.helixRefreshCSDashboard() on each SSE ping; this re-fetches the
// panels fragment and swaps it in. No DOMContentLoaded: the SPA router re-runs
// this on every visit, reassigning the global, which looks up its mount per call.
(function () {
    var PANELS_URL = '/client-servicing/dashboard-panels';

    window.helixRefreshCSDashboard = function () {
        fetch(PANELS_URL, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function (r) { return r.ok ? r.text() : null; })
            .then(function (html) {
                if (html === null) return;
                var mount = document.getElementById('cs-dash-panels');
                if (mount) mount.innerHTML = html;
            })
            .catch(function () { /* network blip: the next ping retries */ });
    };
})();
