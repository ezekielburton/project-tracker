// HSE register page: auto-submits the server-side filter bar (on select
// change or after typing stops), shows the row hover card and remembers
// the spend strip open. The page still works without this file.
//
// No DOMContentLoaded gate: page scripts re-run on every SPA swap and that
// event never fires again.
(function () {
    var DEBOUNCE_MS = 350;

    function initFilters() {
        var form = document.querySelector('.hse-filters');
        if (!form) return;

        function go() {
            // Use the SPA router when present so the shell does not reload.
            var url = form.action + '?' + new URLSearchParams(new FormData(form)).toString();
            if (window.navigateTo) window.navigateTo(url);
            else window.location.assign(url);
        }

        form.querySelectorAll('select').forEach(function (select) {
            select.addEventListener('change', go);
        });

        // Phones: the Filters button shows or hides the dropdowns.
        var toggle = form.querySelector('.hse-filters-toggle');
        if (toggle) {
            toggle.addEventListener('click', function () {
                var open = form.classList.toggle('is-open');
                toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
            });
        }

        var search = form.querySelector('input[type="search"]');
        if (search) {
            var timer = null;
            search.addEventListener('input', function () {
                window.clearTimeout(timer);
                timer = window.setTimeout(go, DEBOUNCE_MS);
            });
            // Enter would post the form and reload the shell; route it instead.
            search.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') { e.preventDefault(); window.clearTimeout(timer); go(); }
            });
        }
    }

    // Row hover card: fields not shown in the table plus the full text of
    // truncated cells. Document-delegated and guarded, so SPA re-runs never
    // stack listeners.
    function initPeek() {
        if (window._hsePeekWired) return;
        // Skipped on touch screens: a tap would flash the card on its way to
        // opening the form.
        if (window.matchMedia('(hover: none)').matches) return;
        window._hsePeekWired = true;

        var DELAY_MS = 350;
        var card = null;
        var timer = null;
        var current = null;
        var cursorX = 0;

        function hide() {
            window.clearTimeout(timer);
            current = null;
            if (card) card.hidden = true;
        }

        function line(item) {
            var row = document.createElement('div');
            row.className = 'hse-peek-row';
            var label = document.createElement('span');
            label.className = 'hse-peek-label';
            label.textContent = item.label;
            var text = document.createElement('span');
            text.className = 'hse-peek-text';
            text.textContent = item.text;
            row.appendChild(label);
            row.appendChild(text);
            return row;
        }

        function show(row) {
            var items;
            try { items = JSON.parse(row.getAttribute('data-peek')); } catch (e) { return; }
            if (!items || !items.length) return;
            if (!card) {
                card = document.createElement('div');
                card.className = 'hse-peek';
                card.setAttribute('role', 'tooltip');
                document.body.appendChild(card);
            }
            card.innerHTML = '';
            var head = document.createElement('div');
            head.className = 'hse-peek-head';
            head.textContent = row.getAttribute('data-ref');
            card.appendChild(head);
            items.forEach(function (item) { card.appendChild(line(item)); });
            card.hidden = false;

            // Under the row at the cursor; flipped above near the window bottom.
            var box = row.getBoundingClientRect();
            var left = Math.min(Math.max(8, cursorX + 12), window.innerWidth - card.offsetWidth - 8);
            var top = box.bottom + 6;
            if (top + card.offsetHeight > window.innerHeight - 8) {
                top = Math.max(8, box.top - card.offsetHeight - 6);
            }
            card.style.left = left + 'px';
            card.style.top = top + 'px';
        }

        document.addEventListener('mouseover', function (e) {
            cursorX = e.clientX;
            var row = e.target.closest('#hse-table tbody tr[data-peek]');
            if (row === current) return;
            hide();
            if (!row) return;
            current = row;
            timer = window.setTimeout(function () {
                if (current === row) show(row);
            }, DELAY_MS);
        });
        document.addEventListener('mousemove', function (e) { cursorX = e.clientX; }, { passive: true });
        document.addEventListener('scroll', hide, true);
        document.addEventListener('click', hide, true);
        window.addEventListener('blur', hide);
    }

    // Spend strip: stays open across filter changes and registers while
    // this tab lives. Storage can throw (private mode); then it just closes.
    function initSpend() {
        var strip = document.getElementById('hse-spend');
        if (!strip) return;
        var KEY = 'hse-spend-open';
        try { strip.open = window.sessionStorage.getItem(KEY) === '1'; } catch (e) { /* closed */ }
        strip.addEventListener('toggle', function () {
            try { window.sessionStorage.setItem(KEY, strip.open ? '1' : '0'); } catch (e) { /* not kept */ }
        });
    }

    initFilters();
    initPeek();
    initSpend();
})();
