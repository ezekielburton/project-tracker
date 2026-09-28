// SPA routing for HSE .hse-tab links (e.g. Month / Agenda) and filter
// chips. The rail is routed by module_rail.js; these are plain <a href>, so
// without this each click is a full page reload.
//
// No DOMContentLoaded gate: page scripts re-run on every SPA swap and that
// event never fires again. The document listener is guarded so re-runs
// never stack a second one.
(function () {
    // Give the page a definite height so panels and the table's scroll box
    // can fill it (.main-content has no height of its own). Outside the
    // guard: every swap brings a fresh box to measure.
    if (window.watchFillHeight) {
        window.watchFillHeight('.hse-inner--fill', '--fill-height');
    }

    // On a phone the charts scroll sideways (hse.css); start them at the
    // latest month.
    if (window.matchMedia('(max-width: 48em)').matches) {
        document.querySelectorAll('.hse-pf-card, .hse-st-spend-chart').forEach(function (card) {
            if (card.querySelector('.hse-pf-svg')) { card.scrollLeft = card.scrollWidth; }
        });
    }

    if (window._hseTabNavWired) { return; }
    window._hseTabNavWired = true;

    document.addEventListener('click', function (e) {
        var link = e.target.closest('.hse-tab, .hse-chip');
        if (!link) { return; }
        // New-tab links (the report's Print / Export) and modifier-clicks
        // are left to the browser, or the report opens inside the app shell.
        if (link.target === '_blank' || e.ctrlKey || e.metaKey || e.shiftKey) { return; }
        var url = link.getAttribute('href');
        if (!url || url === '#') { return; }
        e.preventDefault();
        if (window.navigateTo) {
            window.navigateTo(url);
        } else {
            window.location.href = url;
        }
    });
}());
