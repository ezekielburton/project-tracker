// "Expand All" / "Collapse All" for the .tt-deliverables <details> blocks.
// Also loaded by the dashboard templates for the Average Time card.
// Runs immediately (no DOMContentLoaded) so it works after SPA navigation.

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
