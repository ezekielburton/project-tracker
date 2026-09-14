// SPA-ifies the shared module rail.
//
// The global SPA nav (sidebar.js) only intercepts links carrying
// `sidebar-item--nav` — the app's main left sidebar. A module's own rail
// (_shared_macros.html's module_rail) is plain <a href> tags outside that
// system, so without this every rail click is a full page reload.
//
// Loaded once from base.html rather than per page: the listener is
// delegated on document, so it never needs to re-run after an SPA swap.
// The guard keeps a second listener from stacking if it ever does.
//
// A disabled rail item renders as a <span> with no href, so it falls out
// here and stays inert.
(function () {
    if (window._moduleRailNavWired) return;
    window._moduleRailNavWired = true;

    document.addEventListener('click', function (e) {
        var item = e.target.closest('.module-rail-item');
        if (!item) return;
        var url = item.getAttribute('href');
        if (!url) return;
        e.preventDefault();
        if (window.navigateTo) {
            window.navigateTo(url);
        } else {
            window.location.href = url;
        }
    });
})();
