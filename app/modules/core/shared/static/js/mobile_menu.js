// The phone menu. On a small screen the app sidebar and a module's rail are
// drawers (mobile.css); this opens and closes them.
//
// The header's menu button opens the page's module rail when it has one,
// otherwise the app sidebar. The rail's own "Module" button swaps to the app
// sidebar, which is where every module lives.
//
// Wired once on the document, so it keeps working after SPA page swaps.
// Must load after sidebar.js: sidebar.js collapses the sidebar on any
// outside click, and this has to run after it on the same click.
(function () {
    if (window._mobileMenuWired) return;
    window._mobileMenuWired = true;

    var body = document.body;
    var sidebar = document.getElementById('sidebar');
    var phone = window.matchMedia('(max-width: 48em)');

    function isOpen() {
        return body.classList.contains('mobile-nav--rail') || body.classList.contains('mobile-nav--app');
    }

    function setExpanded(open) {
        document.querySelectorAll('.mobile-menu-btn').forEach(function (btn) {
            btn.setAttribute('aria-expanded', open ? 'true' : 'false');
        });
    }

    function close() {
        body.classList.remove('mobile-nav--rail', 'mobile-nav--app');
        // The drawer shows the sidebar in its expanded look; put it back.
        if (sidebar) sidebar.classList.remove('sidebar--expanded');
        setExpanded(false);
    }

    function openRail() {
        close();
        body.classList.add('mobile-nav--rail');
        setExpanded(true);
    }

    function openApp() {
        close();
        body.classList.add('mobile-nav--app');
        if (sidebar) sidebar.classList.add('sidebar--expanded');
        setExpanded(true);
    }

    document.addEventListener('click', function (e) {
        var trigger = e.target.closest('[data-mobile-menu]');
        if (trigger) {
            var which = trigger.getAttribute('data-mobile-menu');
            if (which === 'close') close();
            else if (which === 'app') openApp();
            else if (document.querySelector('.module-rail')) openRail();
            else openApp();
            return;
        }
        if (!isOpen()) return;
        if (e.target.closest('.mobile-scrim')) {
            close();
            return;
        }
        // A section with sub-pages only opens its list (module_rail.js), so
        // the menu stays open for the pick.
        if (e.target.closest('.module-rail-item--parent')) return;
        // Something chosen inside the menu: let it do its job, then close.
        if (e.target.closest('.module-rail a, .sidebar a, .sidebar button.sidebar-item, #sidebar-toggle-btn')) {
            close();
        }
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && isOpen()) close();
    });

    // A new page, or the window growing past phone width, closes it.
    document.addEventListener('helix:navigated', close);
    if (phone.addEventListener) {
        phone.addEventListener('change', close);
    }
})();
