// A scrolling box keeps the mouse wheel only while its content overflows it;
// when everything fits, the wheel scrolls the page as if the box weren't there.
// Boxes opt in with the class "scroll-hold" (and set their own overflow); this
// marks them "is-scrollable" while they overflow, which turns on
// overscroll-behavior: contain in shared.css.
//
// Loaded once from base.html. Boxes on the page are checked on load and after
// every SPA swap, and again whenever they or their first child resize. A page
// that replaces a box's content calls window.markScrollable(container) after.
(function () {
    var BOX = '.scroll-hold';
    var seen = typeof WeakSet !== 'undefined' ? new WeakSet() : null;

    function mark(box) {
        box.classList.toggle('is-scrollable', box.scrollHeight > box.clientHeight + 1);
    }

    var sizes = window.ResizeObserver ? new ResizeObserver(function (entries) {
        entries.forEach(function (entry) {
            var box = entry.target.closest(BOX);
            if (box) mark(box);
        });
    }) : null;

    function watch(box) {
        mark(box);
        if (!sizes || !seen || seen.has(box)) return;
        seen.add(box);
        sizes.observe(box);
        if (box.firstElementChild) sizes.observe(box.firstElementChild);
    }

    // Check every opted-in box inside `root` (the whole page by default),
    // including root itself when it is one.
    window.markScrollable = function (root) {
        var scope = root || document;
        if (scope.matches && scope.matches(BOX)) watch(scope);
        scope.querySelectorAll(BOX).forEach(watch);
    };

    document.addEventListener('DOMContentLoaded', function () { window.markScrollable(); });
    document.addEventListener('helix:navigated', function () { window.markScrollable(); });
}());
