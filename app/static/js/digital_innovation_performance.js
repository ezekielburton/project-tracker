// Digital Innovation — Performance page. The Weekly/Monthly/Quarterly
// tabs and the prev/next period arrows are plain links (SPA-nav swaps
// the whole page, same as any other DI sidebar link — see
// spa-navigation.md); this file's own job is expanding/collapsing a
// project row's already-rendered feature list, plus (3 Sep 2026) a live
// refresh of the stat cards + table on a DI-wide SSE ping, since other
// users' cost entries, feature moves and project closes/archives should
// show up here without a manual reload — see digital_innovation_live.js
// for the shared connection-watching helper this calls into.
//
// Delegated + guarded against double-wiring on repeat SPA-nav visits to
// this page, same pattern digital_innovation_board.js uses for its own
// dispatcher (per spa-navigation.md's Trap 1 — this file's <script> tag
// re-executes on every visit, so re-adding the same document-level
// listener each time would fire every handler N times after N visits).
(function () {
    if (!window._diPerfDispatcherWired) {
        window._diPerfDispatcherWired = true;

        document.addEventListener('click', function (e) {
            var expandBtn = e.target.closest('.di-perf-expand-btn');
            if (!expandBtn) return;

            var row = expandBtn.closest('.di-perf-project-row');
            var projectId = row && row.getAttribute('data-di-project-row');
            if (!projectId) return;
            // One <tr> per feature now (they render as their own rows
            // under the project's own columns, not a single subrow
            // holding a nested table) — toggle every row in the group,
            // not just the first match.
            var featureRows = document.querySelectorAll('[data-di-project-features="' + projectId + '"]');
            if (!featureRows.length) return;

            var expanded = expandBtn.getAttribute('aria-expanded') === 'true';
            featureRows.forEach(function (featureRow) {
                featureRow.classList.toggle('hidden', expanded);
            });
            // The glyph itself doesn't change — digital_innovation.css
            // rotates it 90° on [aria-expanded="true"] instead.
            expandBtn.setAttribute('aria-expanded', String(!expanded));
        });
    }
})();


// Re-fetches _performance_table.html fresh for whatever view/period is
// currently on screen (read straight off the URL, same querystring
// routes/performance.py::_resolve_view_and_period() already reads) and
// swaps #di-perf-table-body wholesale — same "replace the whole wrapper
// node, don't touch innerHTML" reasoning digital_innovation_board.js's
// diRefreshBoard uses, so there's no risk of ending up with the wrapper
// nested inside itself.
function diRefreshPerformanceTable() {
    var container = document.getElementById('di-perf-table-body');
    if (!container) return;

    // A fresh render always starts every project row collapsed — capture
    // which ones are currently expanded so a live ping doesn't quietly
    // close a row someone's actually looking at.
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
            // A failed live refresh isn't worth surfacing to the user —
            // the page just stays showing what it last successfully
            // loaded, same as if the ping had never arrived.
        });
}

diWatchDashboardStream('performance', '#di-perf-table-body', diRefreshPerformanceTable);
