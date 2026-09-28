/* Closed page: search over the loaded rows, and the mark-invoiced prompt.
   Init runs inline because the SPA router re-runs this on every visit. The
   modal half no-ops for viewers who can't edit finance. */
(function () {
    var table = document.getElementById('cs-closed-table');
    if (!table) return;

    // ── Search ────────────────────────────────────────────────────────
    var search = document.getElementById('cs-closed-search');
    var count = document.getElementById('cs-closed-count');
    var groups = Array.prototype.slice.call(table.querySelectorAll('.cs-closed-group'));

    function applySearch() {
        var term = (search.value || '').trim().toLowerCase();
        var shown = 0;
        groups.forEach(function (group) {
            var visible = 0;
            Array.prototype.forEach.call(group.querySelectorAll('tr[data-search]'), function (tr) {
                var hit = !term || tr.dataset.search.toLowerCase().indexOf(term) !== -1;
                tr.hidden = !hit;
                if (hit) visible += 1;
            });
            // A month with nothing left in it hides its header too.
            group.hidden = visible === 0;
            shown += visible;
        });
        count.textContent = shown + ' closed project' + (shown === 1 ? '' : 's');
    }

    if (search) search.addEventListener('input', applySearch);

    // ── Mark invoiced ─────────────────────────────────────────────────
    var modal = document.getElementById('cs-closed-invoiced-modal');
    if (!modal) return;

    var subject = document.getElementById('cs-closed-invoiced-subject');
    var dateInput = document.getElementById('cs-closed-invoice-date');
    var valueField = document.getElementById('cs-closed-value-field');
    var valueInput = document.getElementById('cs-closed-value');
    var error = document.getElementById('cs-closed-invoiced-error');
    var save = document.getElementById('cs-closed-invoiced-save');
    var cancel = document.getElementById('cs-closed-invoiced-cancel');
    var pending = null;

    function close() { modal.classList.add('hidden'); }
    function showError(msg) { error.textContent = msg; error.classList.remove('hidden'); }

    table.addEventListener('click', function (e) {
        var btn = e.target.closest ? e.target.closest('.cs-closed-mark') : null;
        if (!btn) return;
        pending = btn.dataset.editUrl;
        subject.textContent = btn.dataset.projectName || '';
        dateInput.value = '';
        valueInput.value = '';
        // Only ask for a value when this row hasn't got one.
        valueField.hidden = btn.dataset.hasValue === '1';
        error.classList.add('hidden');
        save.disabled = false;
        modal.classList.remove('hidden');
    });

    cancel.addEventListener('click', close);
    modal.addEventListener('click', function (e) { if (e.target === modal) close(); });

    /* The edit endpoint takes one field per request. Value is saved first so
       a failure there leaves the row untouched, not invoiced without a value. */
    function patchField(field, value) {
        return fetch(pending, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ field: field, value: value })
        }).then(function (r) {
            return r.json().then(function (d) { return { ok: r.ok, d: d }; });
        });
    }

    save.addEventListener('click', function () {
        if (!dateInput.value) {
            showError('Enter the invoice date.');
            return;
        }
        if (!valueField.hidden && !valueInput.value) {
            showError('Enter the project value.');
            return;
        }
        save.disabled = true;

        var first = valueField.hidden
            ? Promise.resolve({ ok: true, d: {} })
            : patchField('value', valueInput.value);

        first.then(function (res) {
            if (!res.ok) { return res; }
            return patchField('invoice_date', dateInput.value);
        }).then(function (res) {
            if (res.ok) { window.location.reload(); return; }
            showError(res.d.error || 'Could not save that.');
            save.disabled = false;
        }).catch(function () {
            showError('Could not save that.');
            save.disabled = false;
        });
    });
})();
