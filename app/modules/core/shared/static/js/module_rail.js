// Routes module rail links (_shared_macros.html's module_rail) through
// sidebar.js's navigateTo. sidebar.js only intercepts .sidebar-item--nav.
//
// Loaded once from base.html; delegated on document, with a guard so it
// never binds twice. A disabled item is a <span> with no href and stays inert.
//
// A section with sub-pages opens its list instead of loading a page, and
// closes any other open list, so one section is open at a time.
// mobile_menu.js keeps the phone menu open for it.
(function () {
    if (window._moduleRailNavWired) return;
    window._moduleRailNavWired = true;

    var CLOSED = 'module-rail-children--closed';

    document.addEventListener('click', function (e) {
        var item = e.target.closest('.module-rail-item');
        if (!item) return;
        // Modified and non-left clicks keep the browser's new tab/window behaviour.
        if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;

        if (item.classList.contains('module-rail-item--parent')) {
            e.preventDefault();
            var list = item.nextElementSibling;
            if (!list || !list.classList.contains('module-rail-children')) return;
            var opening = list.classList.contains(CLOSED);
            var nav = item.closest('.module-rail-nav');
            if (opening && nav) {
                nav.querySelectorAll('.module-rail-children').forEach(function (other) {
                    other.classList.add(CLOSED);
                });
            }
            list.classList.toggle(CLOSED, !opening);
            return;
        }

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
