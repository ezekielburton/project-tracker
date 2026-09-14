// SPA routing for the HSE tab strips and filter chips.
//
// The shared rail is handled by core/shared's module_rail.js. Tabs and
// chips are plain <a href> outside that system, so without this every tab
// click is a full page reload.
//
// This used to live inside hse_registers.js, which meant the lists page
// loaded a file named "registers" for one block it happened to contain.
// The calendar needed it too — second copy, so it was extracted rather
// than pasted (conventions.md).
//
// IIFE with no DOMContentLoaded gate: page scripts re-run on every SPA
// swap and that event never fires again (spa-navigation.md, trap 1). The
// listener is document-delegated and guarded, so re-running never stacks
// a second one.
(function () {
    // Give the page a definite height so its panels, and the table's scroll
    // box, can fill it — .main-content is a flex item with no height of its
    // own, so a pure CSS chain just grows to its content. Deliberately
    // outside the wiring guard below: the listener is wired once, but every
    // swap lands on a fresh box that has to be measured again.
    if (window.watchFillHeight) {
        window.watchFillHeight('.hse-inner--fill', '--fill-height');
    }

    if (window._hseTabNavWired) { return; }
    window._hseTabNavWired = true;

    document.addEventListener('click', function (e) {
        var link = e.target.closest('.hse-tab, .hse-chip');
        if (!link) { return; }
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
