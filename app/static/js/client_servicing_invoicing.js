/* Invoicing page JS — the Days Pending threshold modal (admin/management)
   and inline finance-cell editing (admin/cs/finance). IIFE + direct init
   so it re-runs on SPA nav; each feature no-ops if its DOM isn't present. */
(function () {
    var VALIDATION = {
        valid: ['Valid', 'clover'],
        pending: ['Pending', 'canary'],
        no_lpo: ['No LPO', 'salmon'],
        overdue: ['Overdue', 'salmon']
    };

    // ── Threshold settings modal ──────────────────────────────────────
    function initThresholds() {
        var btn = document.getElementById('cs-inv-thresholds-btn');
        var modal = document.getElementById('cs-inv-thresholds-modal');
        if (!btn || !modal) return;

        var green = document.getElementById('cs-inv-green');
        var red = document.getElementById('cs-inv-red');
        var err = document.getElementById('cs-inv-thresholds-error');
        var save = document.getElementById('cs-inv-thresholds-save');
        var cancel = document.getElementById('cs-inv-thresholds-cancel');

        function open() { err.classList.add('hidden'); modal.classList.remove('hidden'); }
        function close() { modal.classList.add('hidden'); }
        function showError(msg) { err.textContent = msg; err.classList.remove('hidden'); }

        btn.addEventListener('click', open);
        cancel.addEventListener('click', close);
        modal.addEventListener('click', function (e) { if (e.target === modal) close(); });

        save.addEventListener('click', function () {
            var payload = { days_green_max: parseInt(green.value, 10), days_red_max: parseInt(red.value, 10) };
            save.disabled = true;
            fetch(save.dataset.url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            }).then(function (r) {
                return r.json().then(function (d) { return { ok: r.ok, d: d }; });
            }).then(function (res) {
                if (res.ok) { window.location.reload(); }
                else { showError(res.d.error || 'Could not save.'); save.disabled = false; }
            }).catch(function () { showError('Could not save.'); save.disabled = false; });
        });
    }

    // ── Inline finance-cell editing ───────────────────────────────────
    function patch(tr, field, value) {
        return fetch(tr.dataset.editUrl, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ field: field, value: value })
        }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); });
    }

    function numLike(type) { return type === 'money' || type === 'num'; }

    function editText(cell) {
        var type = cell.dataset.type;
        var input = document.createElement('input');
        input.type = type === 'date' ? 'date' : (type === 'money' ? 'number' : 'text');
        if (type === 'money') { input.step = '0.01'; input.min = '0'; }
        input.className = 'cs-inv-edit-input';
        input.value = cell.dataset.value || '';
        var original = cell.textContent;
        cell.textContent = '';
        cell.appendChild(input);
        input.focus();
        if (input.select) { try { input.select(); } catch (e) {} }

        var done = false;
        function commit() {
            if (done) return; done = true;
            var val = input.value;
            patch(cell.closest('tr'), cell.dataset.field, val).then(function (res) {
                if (!res.ok) { cell.textContent = original; return; }
                cell.dataset.value = val;
                var shown = (res.d.value === null || res.d.value === undefined || res.d.value === '') ? '—' : res.d.value;
                cell.classList.remove('cs-inv-none', 'cs-inv-num', 'cs-inv-muted');
                cell.classList.add(shown === '—' ? 'cs-inv-none' : (numLike(type) ? 'cs-inv-num' : 'cs-inv-muted'));
                cell.textContent = shown;
            }).catch(function () { cell.textContent = original; });
        }
        function cancel() { if (done) return; done = true; cell.textContent = original; }

        input.addEventListener('keydown', function (ev) {
            if (ev.key === 'Enter') { ev.preventDefault(); commit(); }
            else if (ev.key === 'Escape') { ev.preventDefault(); cancel(); }
        });
        input.addEventListener('blur', commit);
    }

    function toggleBool(span) {
        var next = span.dataset.value !== 'true';
        patch(span.closest('tr'), span.dataset.field, next ? 'true' : 'false').then(function (res) {
            if (!res.ok) return;
            span.dataset.value = next ? 'true' : 'false';
            span.textContent = 'GR ' + (next ? '✓' : '—');
            span.classList.toggle('cs-inv-gr--on', next);
            span.classList.toggle('cs-inv-gr--off', !next);
        });
    }

    function renderValidation(val) {
        var span = document.createElement('span');
        span.dataset.field = 'validation_status';
        span.dataset.value = val || '';
        span.classList.add('cs-inv-editable-select');
        if (val && VALIDATION[val]) {
            span.classList.add('status-pill', 'cs-inv-badge', 'status-pill--' + VALIDATION[val][1]);
            span.textContent = VALIDATION[val][0];
        } else {
            span.classList.add('cs-inv-none');
            span.textContent = 'set…';
        }
        return span;
    }

    function editSelect(span) {
        var tr = span.closest('tr');
        var parent = span.parentNode;
        var sel = document.createElement('select');
        sel.className = 'cs-inv-edit-input';
        var opts = [['', '—']];
        Object.keys(VALIDATION).forEach(function (k) { opts.push([k, VALIDATION[k][0]]); });
        opts.forEach(function (o) {
            var opt = document.createElement('option');
            opt.value = o[0]; opt.textContent = o[1];
            if (o[0] === (span.dataset.value || '')) opt.selected = true;
            sel.appendChild(opt);
        });
        parent.replaceChild(sel, span);
        sel.focus();

        var done = false;
        function finish(save) {
            if (done) return; done = true;
            if (!save) { parent.replaceChild(span, sel); return; }
            patch(tr, 'validation_status', sel.value).then(function (res) {
                parent.replaceChild(res.ok ? renderValidation(sel.value) : span, sel);
            }).catch(function () { parent.replaceChild(span, sel); });
        }
        sel.addEventListener('change', function () { finish(true); });
        sel.addEventListener('blur', function () { finish(false); });
        sel.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') finish(false); });
    }

    function initInlineEdit() {
        var table = document.querySelector('.cs-inv-table');
        if (!table || !table.querySelector('.cs-inv-editable, .cs-inv-editable-bool, .cs-inv-editable-select')) return;

        table.addEventListener('click', function (e) {
            var boolCell = e.target.closest('.cs-inv-editable-bool');
            if (boolCell) { toggleBool(boolCell); return; }
            var selCell = e.target.closest('.cs-inv-editable-select');
            if (selCell) { editSelect(selCell); return; }
            var cell = e.target.closest('.cs-inv-editable');
            if (cell && !cell.querySelector('input')) { editText(cell); }
        });
    }

    initThresholds();
    initInlineEdit();
})();
