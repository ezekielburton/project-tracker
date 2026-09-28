// Routes module rail links (_shared_macros.html's module_rail) through
// sidebar.js's navigateTo. sidebar.js only intercepts .sidebar-item--nav.
//
// Loaded once from base.html; delegated on document, with a guard so it
// never binds twice. A disabled item is a <span> with no href and stays inert.
//
// Phones: a section with sub-pages toggles its list instead of navigating;
// mobile_menu.js keeps the menu open for it.
(function () {
    if (window._moduleRailNavWired) return;
    window._moduleRailNavWired = true;

    var phone = window.matchMedia('(max-width: 48em)');

    document.addEventListener('click', function (e) {
        var item = e.target.closest('.module-rail-item');
        if (!item) return;
        // Modified and non-left clicks keep the browser's new tab/window behaviour.
        if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;

        // On a wide screen the section link goes straight to its first page.
        if (phone.matches && item.classList.contains('module-rail-item--parent')) {
            e.preventDefault();
            var list = item.nextElementSibling;
            if (list && list.classList.contains('module-rail-children')) {
                list.classList.toggle('module-rail-children--closed');
            }
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
