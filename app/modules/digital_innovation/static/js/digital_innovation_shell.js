// Digital Innovation — the .di-shell height solve.
//
// The maths used to live here in full. It now lives in
// core/shared/js/fill_height.js: Client Servicing had it first for its
// scrolling table, this file mirrored it for .di-shell, and HSE needed it a
// third time. Three copies is the bug, so it was extracted (conventions.md).
//
// Why JS and not CSS at all: .main-content is a flex ITEM with no definite
// height, so a flex child just grows to its content and the page scrolls
// instead of the shell. The shared helper measures the real gap between the
// shell's top and the footer and writes it to --di-shell-height, which is
// the variable digital_innovation.css already reads — so the CSS is
// unchanged and every DI screen keeps working the way it did.
(function () {
    // Re-measured on every SPA swap (this script re-executes) and on resize
    // (the helper registers one listener for the whole app).
    if (window.watchFillHeight) {
        window.watchFillHeight('.di-shell', '--di-shell-height');
    }
}());
