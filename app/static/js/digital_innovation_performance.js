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
            var subrow = projectId && document.querySelector('[data-di-project-features="' + projectId + '"]');
            if (!subrow) return;

            var expanded = expandBtn.getAttribute('aria-expanded') === 'true';
            subrow.classList.toggle('hidden', expanded);
            expandBtn.setAttribute('aria-expanded', String(!expanded));
            expandBtn.innerHTML = expanded ? '&#9656;' : '&#9662;';
        });
    }
})();
