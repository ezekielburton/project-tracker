// Digital Innovation — Performance page. No server round-trips here: the
// Weekly/Monthly/Quarterly tabs and the prev/next period arrows are
// plain links (SPA-nav swaps the whole page, same as any other DI
// sidebar link — see spa-navigation.md), so the only client-side
// behaviour this page needs is expanding/collapsing a project row's
// already-rendered feature list.
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
