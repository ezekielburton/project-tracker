// app/static/js/time_tracking.js
//
// Project + deliverable business-hours breakdown page (added 13 Jul
// 2026). Own dedicated JS file per this project's "every new feature
// gets its own route/JS/CSS" convention — see CLAUDE.md.
//
// The deliverable expand/collapse itself is plain <details>/<summary> in
// time_tracking.html — works with zero JS. This file only adds the
// "Expand All"/"Collapse All" convenience buttons on top, same IIFE
// pattern as achievements.js (not gated on DOMContentLoaded) so it would
// still work if this page is ever reached via the SPA sidebar nav's
// script-re-execution behaviour, matching the established pattern
// documented in this project's memory for SPA navigation.

(function () {
    var expandAllBtn = document.querySelector('[data-action="expand-all"]');
    var collapseAllBtn = document.querySelector('[data-action="collapse-all"]');

    if (expandAllBtn) {
        expandAllBtn.addEventListener('click', function () {
            document.querySelectorAll('.tt-deliverables').forEach(function (el) {
                el.open = true;
            });
        });
    }

    if (collapseAllBtn) {
        collapseAllBtn.addEventListener('click', function () {
            document.querySelectorAll('.tt-deliverables').forEach(function (el) {
                el.open = false;
            });
        });
    }
})();
