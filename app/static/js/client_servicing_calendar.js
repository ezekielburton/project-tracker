// Client Servicing — Installation Calendar (Month + Agenda). Like
// client_servicing.js, this file's tag lives in the page's own
// {% block extra_js %}, so it re-executes on every SPA navigation onto the
// page. Everything binds on elements inside the swapped-in content
// (.cs-cal-page and below), never on document, so listeners can't stack
// across navigations.
(function () {
    var page = document.querySelector('.cs-cal-page');
    if (!page) return;

    var RISK_OPTIONS = window.__csRiskOptions || [];
    var STATUS_OPTIONS = window.__csStatusOptions || [];
    var OPTIONS_BY_FIELD = { risk: RISK_OPTIONS, cs_status: STATUS_OPTIONS };

    // ── Month: day cell → drawer fragment ─────────────────────────
    var grid = page.querySelector('.cs-cal-grid');
    var drawer = document.getElementById('cs-cal-drawer');
    // The open day, kept across live-refresh swaps so it can be restored.
    var selectedDate = null;

    function loadDay(dateStr) {
        if (!drawer || !dateStr) return;
        fetch('/client-servicing/calendar/day/' + dateStr)
            .then(function (r) { return r.ok ? r.text() : null; })
            .then(function (html) { if (html !== null) drawer.innerHTML = html; })
            .catch(function () { /* network blip — leave the drawer as-is */ });
    }

    function markSelected(dateStr) {
        if (!grid) return;
        grid.querySelectorAll('.cs-cal-cell--sel').forEach(function (c) { c.classList.remove('cs-cal-cell--sel'); });
        if (!dateStr) return;
        var cell = grid.querySelector('.cs-cal-cell--has[data-date="' + dateStr + '"]');
        if (cell) cell.classList.add('cs-cal-cell--sel');
    }

    function selectDay(cell) {
        if (!cell || !cell.dataset.date) return;
        selectedDate = cell.dataset.date;
        markSelected(selectedDate);
        loadDay(selectedDate);
    }

    if (grid && drawer) {
        grid.addEventListener('click', function (e) {
            selectDay(e.target.closest('.cs-cal-cell--has'));
        });
    }

    // ── Agenda: client-side search + risk filter ──────────────────
    var agenda = document.getElementById('cs-cal-agenda');
    var search = document.getElementById('cs-cal-search');
    var riskFilter = page.querySelector('.cs-cal-filter[data-filter="risk"]');
    var RISK_CYCLE = ['', 'atrisk', 'attention', 'ontrack', 'done'];
    var RISK_LABEL = { '': 'All', atrisk: 'At risk', attention: 'Attention', ontrack: 'On track', done: 'Done' };

    function applyAgendaFilter() {
        if (!agenda) return;
        var q = (search && search.value || '').trim().toLowerCase();
        var risk = riskFilter ? (riskFilter.dataset.value || '') : '';
        agenda.querySelectorAll('.cs-cal-daygroup').forEach(function (group) {
            var shown = 0;
            group.querySelectorAll('.cs-cal-arow').forEach(function (row) {
                var okText = !q || (row.dataset.search || '').indexOf(q) !== -1;
                var okRisk = !risk || row.dataset.risk === risk;
                var show = okText && okRisk;
                row.hidden = !show;
                if (show) shown++;
            });
            group.hidden = shown === 0;
        });
    }
    if (search) search.addEventListener('input', applyAgendaFilter);
    if (riskFilter) {
        riskFilter.addEventListener('click', function () {
            var next = (RISK_CYCLE.indexOf(riskFilter.dataset.value) + 1) % RISK_CYCLE.length;
            riskFilter.dataset.value = RISK_CYCLE[next];
            riskFilter.classList.toggle('cs-cal-filter--active', !!RISK_CYCLE[next]);
            riskFilter.querySelector('.cs-muted').textContent = '· ' + RISK_LABEL[RISK_CYCLE[next]];
            applyAgendaFilter();
        });
    }

    // ── Inline edit (risk / action_owner / next_action) ───────────
    var FLAG_SVG = '<svg class="cs-cal-flag" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/></svg>';

    // Next-action footer: flag icon + amber when a warning risk is active,
    // plain "Next:" otherwise. Text set via textContent (never innerHTML).
    function renderNext(cell, value) {
        var flagged = cell.classList.contains('cs-cal-na--flag');
        cell.dataset.value = value || '';
        cell.innerHTML = flagged ? FLAG_SVG : '';
        var span = document.createElement('span');
        span.className = 'cs-cal-na-txt';
        span.textContent = (flagged ? '' : 'Next: ') + (value || '—');
        cell.appendChild(span);
    }

    function renderOwner(cell, value) {
        cell.dataset.value = value || '';
        cell.innerHTML = '<span class="cs-cal-k">Owner</span>';
        cell.appendChild(document.createTextNode(value || '—'));
    }

    // Install qty — an empty value renders the dashed 'Set qty' prompt.
    function renderQty(cell, value) {
        var has = value !== null && value !== undefined && value !== '';
        cell.dataset.value = has ? value : '';
        cell.className = 'cs-cal-qty cs-editable' + (has ? '' : ' cs-cal-qty--empty');
        cell.textContent = has ? ('Qty ' + value) : 'Set qty';
    }

    function renderRisk(cell, risk) {
        var job = cell.closest('.cs-cal-job');
        cell.className = 'cs-cal-risk cs-cal-risk--' + risk.modifier + ' cs-editable';
        cell.dataset.field = 'risk';
        cell.dataset.value = risk.is_auto ? '' : risk.label;
        cell.innerHTML = '<span class="cs-cal-rd cs-cal-rd--' + risk.modifier + '"></span>';
        cell.appendChild(document.createTextNode(risk.label + ' '));
        if (risk.is_auto) {
            var au = document.createElement('span');
            au.className = 'cs-cal-risk-auto';
            au.textContent = 'auto';
            cell.appendChild(au);
        }
        if (job) {
            // Risk is the card's frame — swap the left-border modifier class.
            job.className = 'cs-cal-job cs-cal-job--' + risk.modifier;
            job.dataset.riskClass = risk.modifier;
            var na = job.querySelector('.cs-cal-na');
            if (na) {
                na.classList.toggle('cs-cal-na--flag', risk.modifier === 'atrisk' || risk.modifier === 'attention');
                renderNext(na, na.dataset.value || '');
            }
            var arow = job.closest('.cs-cal-arow');
            if (arow) arow.dataset.risk = risk.modifier;
        }
    }

    // Status pill — writes the same cs_status the CS table edits, so a
    // change here shows on the table and vice versa. Response carries the
    // recomputed effective status (manual override or derived).
    function renderStatus(cell, status) {
        cell.dataset.value = status.is_auto ? '' : status.label;
        cell.innerHTML = '';
        var pill = document.createElement('span');
        pill.className = 'status-pill status-pill--' + status.modifier;
        pill.textContent = status.label;
        cell.appendChild(pill);
        if (status.is_auto) {
            cell.appendChild(document.createTextNode(' '));
            var au = document.createElement('span');
            au.className = 'cs-cal-risk-auto';
            au.textContent = 'auto';
            cell.appendChild(au);
        }
    }

    function saveField(cell, field, rawValue, originalHtml) {
        var job = cell.closest('.cs-cal-job');
        var projectId = job ? job.dataset.projectId : null;
        cell.classList.remove('cs-cell-editing');
        if (!projectId) { cell.innerHTML = originalHtml; return; }
        fetch('/client-servicing/' + projectId, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ field: field, value: rawValue }),
        })
            .then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { return { ok: r.ok, data: d }; }); })
            .then(function (res) {
                if (!res.ok) {
                    cell.innerHTML = originalHtml;
                    cell.title = res.data.error || 'could not save';
                    cell.classList.add('cs-cell-error');
                    setTimeout(function () { cell.classList.remove('cs-cell-error'); cell.removeAttribute('title'); }, 2500);
                    return;
                }
                cell.removeAttribute('title');
                if (res.data.risk) renderRisk(cell, res.data.risk);
                else if (res.data.status) renderStatus(cell, res.data.status);
                else if (field === 'action_owner') renderOwner(cell, res.data.value);
                else if (field === 'install_qty') renderQty(cell, res.data.value);
                else renderNext(cell, res.data.value);
            })
            .catch(function () { cell.innerHTML = originalHtml; });
    }

    function startEdit(cell) {
        if (cell.classList.contains('cs-cell-editing')) return;
        var field = cell.dataset.field;
        var rawValue = cell.dataset.value || '';
        var originalHtml = cell.innerHTML;
        cell.classList.add('cs-cell-editing');
        cell.innerHTML = '';

        var input;
        if (OPTIONS_BY_FIELD[field]) {
            input = document.createElement('select');
            var blank = document.createElement('option');
            blank.value = ''; blank.textContent = '— (auto)';
            input.appendChild(blank);
            OPTIONS_BY_FIELD[field].forEach(function (opt) {
                var o = document.createElement('option');
                o.value = opt; o.textContent = opt;
                if (opt === rawValue) o.selected = true;
                input.appendChild(o);
            });
        } else {
            input = document.createElement('input');
            if (field === 'install_qty') { input.type = 'number'; input.min = '1'; input.step = '1'; }
            else { input.type = 'text'; }
            input.value = rawValue;
        }
        cell.appendChild(input);
        input.focus();
        if (input.select) input.select();

        var settled = false;
        function commit(value) { if (settled) return; settled = true; saveField(cell, field, value, originalHtml); }
        input.addEventListener('blur', function () { commit(input.value); });
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
            else if (e.key === 'Escape') { e.preventDefault(); settled = true; cell.classList.remove('cs-cell-editing'); cell.innerHTML = originalHtml; }
        });
    }

    // Delegated on the page root (re-created each SPA nav) so it also covers
    // drawer content swapped in after a day click.
    page.addEventListener('click', function (e) {
        var cell = e.target.closest('.cs-editable');
        if (!cell || cell.classList.contains('cs-cell-editing')) return;
        if (e.target.closest('.cs-cal-goto')) return; // the open-in-projects link
        startEdit(cell);
    });

    // Live refresh (SSE doorbell via polling.js): re-fetch this same view and
    // swap only the data regions in place, so the open day and the agenda
    // search/filter survive. Skipped mid-edit — the next ping catches up.
    window.helixRefreshClientServicingCalendar = function () {
        if (page.querySelector('.cs-cell-editing')) return;
        fetch(window.location.pathname + window.location.search, { headers: { 'X-Nav-Request': '1' } })
            .then(function (r) { return r.ok ? r.text() : null; })
            .then(function (html) {
                if (html === null) return;
                var doc = new DOMParser().parseFromString(html, 'text/html');
                var freshKpis = doc.getElementById('cs-cal-kpis');
                var liveKpis = document.getElementById('cs-cal-kpis');
                if (freshKpis && liveKpis) liveKpis.innerHTML = freshKpis.innerHTML;

                var freshGrid = doc.getElementById('cs-cal-grid');
                if (freshGrid && grid) {
                    grid.innerHTML = freshGrid.innerHTML;
                    markSelected(selectedDate);
                    if (selectedDate) loadDay(selectedDate);
                }

                var freshAgenda = doc.getElementById('cs-cal-agenda');
                if (freshAgenda && agenda) {
                    agenda.innerHTML = freshAgenda.innerHTML;
                    applyAgendaFilter();
                }
            })
            .catch(function () { /* transient — next doorbell retries */ });
    };
})();
