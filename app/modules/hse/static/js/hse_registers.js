// HSE register page: auto-submits the server-side filter bar (on select
// change or after typing stops), shows the row hover card, remembers the
// spend strip open and records stock movements. The page still works
// without this file, except for stock movements.
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

    // Stock movement popover: + Received, − Issued and Count on a stock
    // line's row. Built on open and removed on close, placed by
    // PopoverPosition. Document-delegated and guarded, like the hover card.
    function initMoves() {
        // A popover left open by the previous SPA page goes with it.
        if (window._hseMovesClose) window._hseMovesClose();
        if (window._hseMovesWired) return;
        window._hseMovesWired = true;

        var TITLES = { received: 'Stock received', issued: 'Stock issued', count: 'Stock count' };
        var QTY_LABELS = { received: 'Quantity in', issued: 'Quantity out', count: 'Counted on hand' };
        var FIELD_NAMES = { date: 'Date', qty: 'Quantity', note: 'Note', kind: 'Movement' };
        var pop = null;

        function isoToday() {
            var d = new Date();
            return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') +
                '-' + String(d.getDate()).padStart(2, '0');
        }

        function close() {
            if (!pop) return;
            pop.remove();
            pop = null;
        }
        window._hseMovesClose = close;

        function field(name, label, input) {
            var wrap = document.createElement('label');
            wrap.className = 'hse-move-pop-field hse-move-pop-field--' + name;
            var text = document.createElement('span');
            text.className = 'hse-move-pop-label';
            text.textContent = label;
            input.name = name;
            input.className = 'form-input';
            wrap.appendChild(text);
            wrap.appendChild(input);
            return wrap;
        }

        function build(button) {
            var kind = button.getAttribute('data-move');
            var row = button.closest('tr');
            var el = document.createElement('div');
            el.className = 'hse-move-pop';
            el.setAttribute('role', 'dialog');
            el.setAttribute('aria-label', TITLES[kind]);

            var head = document.createElement('div');
            head.className = 'hse-move-pop-head';
            var title = document.createElement('div');
            title.className = 'hse-move-pop-title';
            title.textContent = TITLES[kind];
            var sub = document.createElement('div');
            sub.className = 'hse-move-pop-sub';
            var balance = row.querySelector('td[data-label="Balance"]');
            sub.textContent = row.getAttribute('data-title') +
                (balance ? ' · balance ' + balance.textContent.trim() : '');
            head.appendChild(title);
            head.appendChild(sub);

            var date = document.createElement('input');
            date.type = 'date';
            date.value = isoToday();
            date.max = date.value;
            var qty = document.createElement('input');
            qty.type = 'number';
            qty.inputMode = 'numeric';
            qty.step = '1';
            qty.min = kind === 'count' ? '0' : '1';
            var note = document.createElement('input');
            note.type = 'text';
            note.maxLength = 200;
            note.placeholder = 'Optional';

            var grid = document.createElement('div');
            grid.className = 'hse-move-pop-grid';
            grid.appendChild(field('date', 'Date', date));
            grid.appendChild(field('qty', QTY_LABELS[kind], qty));
            grid.appendChild(field('note', 'Note', note));

            var error = document.createElement('div');
            error.className = 'hse-error hse-move-pop-error';
            error.hidden = true;

            var foot = document.createElement('div');
            foot.className = 'hse-move-pop-foot';
            foot.innerHTML = '<button type="button" class="hse-btn" data-move-cancel>Cancel</button>' +
                '<button type="button" class="hse-btn hse-btn--primary" data-move-save>Save</button>';

            el.appendChild(head);
            el.appendChild(grid);
            el.appendChild(error);
            el.appendChild(foot);
            el._trigger = button;
            el._kind = kind;
            el._row = row;
            el._url = button.closest('.hse-row-actions').getAttribute('data-move-url');
            return el;
        }

        function open(button) {
            close();
            pop = build(button);
            document.body.appendChild(pop);
            window.PopoverPosition.place(pop, button);
            pop.querySelector('input[name="qty"]').focus({ preventScroll: true });
        }

        function showErrors(errors) {
            var lines = [];
            pop.querySelectorAll('.hse-move-pop-field').forEach(function (wrap) {
                var name = wrap.querySelector('input').name;
                wrap.classList.toggle('has-error', Boolean(errors[name]));
            });
            Object.keys(errors).forEach(function (name) {
                lines.push((FIELD_NAMES[name] || name) + ': ' + errors[name]);
            });
            var slot = pop.querySelector('.hse-move-pop-error');
            slot.textContent = lines.join(' · ');
            slot.hidden = false;
        }

        function save() {
            var current = pop;
            var button = current.querySelector('[data-move-save]');
            var value = function (name) { return current.querySelector('input[name="' + name + '"]').value; };
            button.disabled = true;
            fetch(current._url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ kind: current._kind, date: value('date'),
                                       qty: value('qty'), note: value('note') })
            }).then(function (res) {
                return res.json().then(function (body) { return { ok: res.ok, body: body }; });
            }).then(function (result) {
                if (current !== pop) return;
                button.disabled = false;
                if (!result.ok) {
                    showErrors(result.body.errors || { kind: result.body.error || 'Could not save.' });
                    return;
                }
                // The balance cell is found by its column name (lib/table.py).
                var cell = current._row.querySelector('td[data-label="Balance"]');
                if (cell) {
                    cell.textContent = result.body.balance_text;
                    cell.classList.toggle('hse-low', result.body.low);
                    if (result.body.low) cell.title = 'At or below the reorder level';
                    else cell.removeAttribute('title');
                    cell.classList.remove('is-updated');
                    void cell.offsetWidth;  // restart the highlight
                    cell.classList.add('is-updated');
                }
                close();
            }).catch(function () {
                if (current !== pop) return;
                button.disabled = false;
                showErrors({ kind: 'Could not reach the server.' });
            });
        }

        document.addEventListener('click', function (e) {
            var trigger = e.target.closest('.hse-row-actions [data-move]');
            if (trigger) {
                if (pop && pop._trigger === trigger) close();
                else open(trigger);
                return;
            }
            if (!pop) return;
            if (e.target.closest('[data-move-save]')) { save(); return; }
            if (e.target.closest('[data-move-cancel]') || !pop.contains(e.target)) close();
        });

        document.addEventListener('keydown', function (e) {
            if (!pop) return;
            if (e.key === 'Escape') close();
            else if (e.key === 'Enter' && pop.contains(e.target) && e.target.tagName === 'INPUT') {
                e.preventDefault();
                save();
            }
        });

        // Follow the row while the table or page scrolls.
        document.addEventListener('scroll', function () {
            if (!pop) return;
            if (pop._trigger.isConnected) window.PopoverPosition.place(pop, pop._trigger);
            else close();
        }, true);
        window.addEventListener('resize', function () {
            if (pop && pop._trigger.isConnected) window.PopoverPosition.place(pop, pop._trigger);
        });
    }

    initFilters();
    initPeek();
    initSpend();
    initMoves();
})();
