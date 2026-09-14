// HSE register surface — the filter bar.
//
// Search and the two dropdowns are server-side now, so this file's whole
// job is saving a click: change a select, or stop typing, and it submits.
// Remove the file and the page still works — the form has a submit button
// and Enter posts it.
//
// The tab and chip SPA routing lives in hse_nav.js.
//
// IIFE with no DOMContentLoaded gate: page scripts re-run on every SPA
// swap and that event never fires again (spa-navigation.md, trap 1).
(function () {
    var DEBOUNCE_MS = 350;

    function initFilters() {
        var form = document.querySelector('.hse-filters');
        if (!form) return;

        function go() {
            // Through the SPA router when it is there, so the page swaps
            // instead of reloading the whole shell.
            var url = form.action + '?' + new URLSearchParams(new FormData(form)).toString();
            if (window.navigateTo) window.navigateTo(url);
            else window.location.assign(url);
        }

        form.querySelectorAll('select').forEach(function (select) {
            select.addEventListener('change', go);
        });

        var search = form.querySelector('input[type="search"]');
        if (search) {
            var timer = null;
            search.addEventListener('input', function () {
                window.clearTimeout(timer);
                timer = window.setTimeout(go, DEBOUNCE_MS);
            });
            // Enter would post the form and reload the shell; route it the
            // same way everything else goes.
            search.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') { e.preventDefault(); window.clearTimeout(timer); go(); }
            });
        }
    }

    initFilters();
})();
