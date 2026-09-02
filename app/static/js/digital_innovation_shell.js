// Digital Innovation — shared .di-shell height sync for every DI screen
// (board.html/templates.html/archive.html/performance.html all share
// .di-page/.di-shell from the module's own CSS, digital_innovation.css).
//
// Why JS and not pure CSS: .di-shell is meant to fill the gap between
// the global fixed header and the global footer so a screen's main
// content (e.g. board.html's .di-columns/.di-closed-strip) can flex to
// fill it. CSS alone doesn't reliably express that here — .main-content
// is only a flex ITEM (flex:1) of body's flex column, not itself a flex
// container with a definite height its own descendants can percentage
// against; client_servicing.css hit and documented this exact problem
// for its own scrolling table (a headless Chromium repro showed the box
// just grows to fit its content, no scroll boundary at all) and fixed
// it the same way this does: measure the real gap with
// getBoundingClientRect() instead of asking CSS to derive it
// (client_servicing.js::syncTableScrollHeight — same approach, mirrored
// here for .di-shell instead of .cs-table-scroll).
(function () {
    function syncDiShellHeight() {
        var shell = document.querySelector('.di-shell');
        var footer = document.querySelector('.footer');
        if (!shell || !footer) return;
        // Height that makes the shell's bottom edge meet the footer's
        // top — shell.top and the footer's height are both independent
        // of the shell's own height, so this solves it directly rather
        // than nudging a delta.
        var shellRect = shell.getBoundingClientRect();
        var footerRect = footer.getBoundingClientRect();
        var target = window.innerHeight - shellRect.top - footerRect.height;
        if (target > 100) { // guard against a mid-layout-thrash reading
            shell.style.setProperty('--di-shell-height', target + 'px');
        }
    }

    syncDiShellHeight();

    // Guard against re-registering a new resize listener on every SPA
    // navigation (sidebar.js swaps #main-content's innerHTML and
    // re-executes any <script> tags it finds, including this one) —
    // same convention as digital_innovation_board.js's
    // _diDispatcherWired. The direct call above still re-measures for
    // whichever .di-shell is live right now, on every execution.
    if (!window._diShellSyncWired) {
        window._diShellSyncWired = true;
        window.addEventListener('resize', syncDiShellHeight);
    }
})();
