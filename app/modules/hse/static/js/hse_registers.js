// HSE register surface — client-side search.
//
// The tab and chip SPA routing that used to live here is now hse_nav.js:
// the lists page was loading this whole file for that one block, and the
// calendar needs it too. Second copy, so it was extracted rather than
// pasted (conventions.md).
//
// IIFE with no DOMContentLoaded gate: page scripts re-run on every SPA
// swap and that event never fires again (spa-navigation.md, trap 1).
(function () {
    // Search filters the rows already on the page — the status chips are
    // what narrows the set server-side.
    function initSearch() {
        var input = document.getElementById('hse-search');
        var table = document.getElementById('hse-table');
        var empty = document.getElementById('hse-no-matches');
        if (!input || !table) return;

        var rows = Array.prototype.slice.call(
            table.querySelectorAll('tbody tr[data-search]'));

        input.addEventListener('input', function () {
            var term = input.value.trim().toLowerCase();
            var shown = 0;
            rows.forEach(function (row) {
                var hit = !term || row.getAttribute('data-search').indexOf(term) !== -1;
                row.hidden = !hit;
                if (hit) shown++;
            });
            if (empty) empty.hidden = !(rows.length && shown === 0);
        });
    }

    initSearch();
})();
