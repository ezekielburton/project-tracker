// Solve a box's height so its bottom edge meets the footer.
//
// Flexbox fill does not work in this shell: .main-content is a flex ITEM
// with no definite height, so a flex child just grows to its content and
// the page scrolls instead of the box. That matters for more than looks —
// a scroll box taller than the viewport takes its own horizontal scrollbar
// off screen with it, so you have to scroll the page to the bottom before
// you can scroll a wide table sideways.
//
// Client Servicing solved this first, inside syncTableScrollHeight(). HSE
// needed the same solve — second copy, so it moved here (conventions.md)
// rather than being pasted a second time.
//
// Loaded once from base.html. Page scripts call watchFillHeight() on every
// SPA swap; the resize listener is registered once.
(function () {
    // Below this the reading is almost certainly mid-layout rather than a
    // genuinely tiny viewport, and writing it would collapse the box.
    var MIN_HEIGHT = 100;

    function fillHeightToFooter(el, varName) {
        if (!el) { return; }
        // The box's top and the footer's height are both independent of the
        // box's own height, so this solves the target directly instead of
        // nudging a delta and hoping it settles. With no footer on the page
        // it fills to the bottom of the viewport rather than collapsing.
        var footer = document.querySelector('.footer');
        var footerHeight = footer ? footer.getBoundingClientRect().height : 0;
        var target = window.innerHeight
            - el.getBoundingClientRect().top
            - footerHeight;
        if (target > MIN_HEIGHT) {
            el.style.setProperty(varName || '--fill-height', target + 'px');
        }
    }

    function fillAll(selector, varName) {
        document.querySelectorAll(selector).forEach(function (el) {
            fillHeightToFooter(el, varName);
        });
    }

    var watched = [];

    function remeasure() {
        watched.forEach(function (w) { fillAll(w[0], w[1]); });
    }

    // Register a selector to be solved now and on every resize. Safe to
    // call on each SPA swap: the list is deduped, so a page visited five
    // times does not measure five times per resize.
    window.watchFillHeight = function (selector, varName) {
        var known = watched.some(function (w) {
            return w[0] === selector && w[1] === varName;
        });
        if (!known) { watched.push([selector, varName]); }
        fillAll(selector, varName);
        // Again next frame: on a fresh swap the box's top is often still
        // being laid out when the page script runs.
        window.requestAnimationFrame(function () { fillAll(selector, varName); });
    };

    window.fillHeightToFooter = fillHeightToFooter;
    window.addEventListener('resize', remeasure);
}());
