// Digital Innovation: sizes .di-shell to fill the space above the footer.
//
// CSS alone cannot: .main-content is a flex item with no definite height, so
// the page would scroll instead of the shell. The shared helper
// (core/shared/static/js/fill_height.js) measures the gap and writes it to
// --di-shell-height, which digital_innovation.css reads.
(function () {
    // Re-measured on every SPA swap (this script re-runs) and on resize
    // (the helper owns one app-wide listener).
    if (window.watchFillHeight) {
        window.watchFillHeight('.di-shell', '--di-shell-height');
    }
}());
