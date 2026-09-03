// Digital Innovation — SPA-ifies the module's OWN internal navigation.
//
// The app's global SPA nav (sidebar.js) only intercepts clicks on links
// carrying the `sidebar-item--nav` class, which belongs to the main left
// sidebar. DI's own secondary sidebar (_sidebar.html — Board/Performance/
// Edit Templates, the project list, Archive) and Performance's own
// Weekly/Monthly/Quarterly tabs + prev/next period arrows are plain
// <a href> tags outside that system, so every click among them used to
// trigger a full page reload. This file closes that gap by routing them
// through the same window.navigateTo() the rest of the app already uses
// — same fallback-safe pattern as main.js's project-row click and
// notifications.js's notification-row click:
//   if (window.navigateTo) { window.navigateTo(url) } else { window.location.href = url }
// so navigation never breaks even if this script somehow loads before
// sidebar.js defines navigateTo.
//
// Deliberately NOT included: the Export-to-Excel link (.di-perf-export-btn)
// and the project Close button (.di-project-close-btn, already a <button>
// wired to its own fetch handler in digital_innovation_archive.js/board.js)
// — neither is a page navigation.
//
// Included on all four DI screens (board.html/templates.html/archive.html/
// performance.html), same as digital_innovation_shell.js — a document-level
// delegated listener, so it works regardless of which screen's markup is
// currently in the DOM and survives SPA swaps without re-wiring.
(function () {
    var NAV_SELECTOR = '.di-nav-item, .di-project-item, .di-perf-tab, .di-perf-nav-arrow';

    // Guard against re-registering a second document-level listener on
    // every SPA nav (sidebar.js swaps #main-content's innerHTML and
    // re-executes any <script> tags it finds, including this one) — same
    // convention as digital_innovation_board.js's _diDispatcherWired.
    if (window._diNavDispatcherWired) return;
    window._diNavDispatcherWired = true;

    document.addEventListener('click', function (e) {
        var item = e.target.closest(NAV_SELECTOR);
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
