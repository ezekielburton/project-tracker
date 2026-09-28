// Sizes a box so its bottom edge meets the footer, via a CSS variable.
//
// Flexbox can't do this here: .main-content has no definite height, so a
// flex child grows to its content and the page scrolls instead. A scroll
// box taller than the viewport also hides its own horizontal scrollbar.
//
// Loaded once from base.html. Page scripts call watchFillHeight() on every
// SPA swap; the resize listener is registered once.
(function () {
    // Below this the reading is almost certainly mid-layout rather than a
    // genuinely tiny viewport, and writing it would collapse the box.
    var MIN_HEIGHT = 100;

    function fillHeightToFooter(el, varName) {
        if (!el) { return; }
        // With no footer it fills to the bottom of the viewport.
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
