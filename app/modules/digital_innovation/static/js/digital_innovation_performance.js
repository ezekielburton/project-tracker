// Digital Innovation Performance page: expands/collapses a project's feature
// rows, and live-refreshes the stat cards + table on a DI-wide SSE ping.
// Tabs and period arrows are plain links (digital_innovation_nav.js).
//
// SPA nav re-runs this script, so the click listener is wired once behind a flag.
(function () {
    if (!window._diPerfDispatcherWired) {
        window._diPerfDispatcherWired = true;

        document.addEventListener('click', function (e) {
            var expandBtn = e.target.closest('.di-perf-expand-btn');
            if (!expandBtn) return;

            var row = expandBtn.closest('.di-perf-project-row');
            var projectId = row && row.getAttribute('data-di-project-row');
            if (!projectId) return;
            // Each feature is its own <tr>, so toggle every row in the group.
            var featureRows = document.querySelectorAll('[data-di-project-features="' + projectId + '"]');
            if (!featureRows.length) return;

            var expanded = expandBtn.getAttribute('aria-expanded') === 'true';
            featureRows.forEach(function (featureRow) {
                featureRow.classList.toggle('hidden', expanded);
            });
            // CSS rotates the glyph on [aria-expanded="true"].
            expandBtn.setAttribute('aria-expanded', String(!expanded));
        });
    }
})();


// Re-fetches _performance_table.html for the view/period in the URL's
// querystring and replaces #di-perf-table-body. The fragment is its own
// wrapper, so the node is replaced, not its innerHTML.
function diRefreshPerformanceTable() {
    var container = document.getElementById('di-perf-table-body');
    if (!container) return;

    // Fresh renders arrive collapsed; remember expanded rows to re-open them.
    var expandedIds = Array.prototype.map.call(
        document.querySelectorAll('.di-perf-expand-btn[aria-expanded="true"]'),
        function (btn) {
            var row = btn.closest('.di-perf-project-row');
            return row && row.getAttribute('data-di-project-row');
        }
    ).filter(Boolean);

    fetch('/digital-innovation/performance/table' + window.location.search)
        .then(function (res) {
            if (!res.ok) throw new Error('failed to refresh performance table');
            return res.text();
        })
        .then(function (html) {
            var wrapper = document.createElement('div');
            wrapper.innerHTML = html;
            var fresh = wrapper.firstElementChild;
            if (!fresh) return;
            container.replaceWith(fresh);

            expandedIds.forEach(function (projectId) {
                var btn = fresh.querySelector('.di-perf-project-row[data-di-project-row="' + projectId + '"] .di-perf-expand-btn');
                var featureRows = fresh.querySelectorAll('[data-di-project-features="' + projectId + '"]');
                if (!btn || !featureRows.length) return;
                btn.setAttribute('aria-expanded', 'true');
                featureRows.forEach(function (row) { row.classList.remove('hidden'); });
            });
        })
        .catch(function () {
            // Silent: the page keeps its last state.
        });
}

diWatchDashboardStream('performance', '#di-perf-table-body', diRefreshPerformanceTable);
