// Client Servicing table page. This script re-executes on every SPA
// navigation onto the page (its tag is in {% block extra_js %}), so it needs
// no helix:navigated listener. polling.js calls
// window.helixRefreshClientServicingTable() on each SSE ping to swap the rows.
//
// Cell editing: every .cs-editable <td> edits in place (click → input → save
// on blur), delegated on #client-servicing-table-body so it survives refresh
// swaps. Scope and Client SPOC can also be created inline via a "+ Add new..."
// option. Click-to-sort is client-side only (module-scope `currentSort`), not
// persisted; it resets on reload and re-applies after a live refresh.
(function () {
    var body = document.getElementById('client-servicing-table-body');
    if (!body) return;

    // Sticky Project column: its left offset must equal the "Open in Projects"
    // column's rendered width, measured here and handed to the CSS as a custom
    // property. Re-run after every refresh (the whole table is replaced).
    function syncStickyProjectOffset() {
        var table = document.getElementById('cs-table');
        var openHeaderCell = table && table.querySelector('thead th.cs-col-open');
        if (!table || !openHeaderCell) return;
        table.style.setProperty('--cs-sticky-project-left', openHeaderCell.getBoundingClientRect().width + 'px');
    }

    // Measures the table-box height live and sets it as a CSS custom
    // property the box's `height` reads; the CSS calc(100vh - 180px) is
    // only the pre-JS fallback.
    function syncTableScrollHeight() {
        // The solve moved to core/shared/js/fill_height.js when HSE needed
        // the same one — second copy, so it was extracted (conventions.md).
        // The call sites below are unchanged. If that file ever fails to
        // load, .cs-table-scroll falls back to its own calc() in the CSS.
        if (!window.fillHeightToFooter) return;
        window.fillHeightToFooter(document.getElementById('cs-table-scroll'),
                                  '--cs-table-scroll-height');
    }

    // ── Click-to-sort ─────────────────────────────────────────────
    // Columns whose data-sort-value is a plain number, not text/an ISO
    // date string — everything else sorts lexicographically, which
    // already works correctly for ISO dates (YYYY-MM-DD sorts
    // chronologically as a string) and for names/labels.
    var NUMERIC_SORT_COLUMNS = { value: true, cost_to_client: true, inward_cost: true, margin_percent: true };
    var currentSort = null; // { key: 'value', dir: 'asc' } | null (null = default server order)

    function applySort() {
        var table = document.getElementById('cs-table');
        var tbody = table && table.querySelector('tbody');
        if (!tbody) return;
        var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr[data-project-id]'));
        if (!rows.length) return;

        if (!currentSort) {
            // Back to the server's own order — every row carries the
            // position it was rendered in (table.py sorts by Project
            // name), so this needs no re-fetch to restore.
            rows.sort(function (a, b) { return Number(a.dataset.rowOrder) - Number(b.dataset.rowOrder); });
        } else {
            var key = currentSort.key;
            var dir = currentSort.dir === 'desc' ? -1 : 1;
            var numeric = !!NUMERIC_SORT_COLUMNS[key];
            rows.sort(function (a, b) {
                var aTd = a.querySelector('td[data-col-key="' + key + '"]');
                var bTd = b.querySelector('td[data-col-key="' + key + '"]');
                var aVal = aTd ? aTd.dataset.sortValue || '' : '';
                var bVal = bTd ? bTd.dataset.sortValue || '' : '';
                // Blank cells sort to the bottom no matter the direction —
                // an ascending sort on Due Date shouldn't put "no date
                // set" rows before every real date.
                if (aVal === '' && bVal === '') return 0;
                if (aVal === '') return 1;
                if (bVal === '') return -1;
                if (numeric) return (parseFloat(aVal) - parseFloat(bVal)) * dir;
                return aVal.localeCompare(bVal, undefined, { sensitivity: 'base', numeric: true }) * dir;
            });
        }
        rows.forEach(function (tr) { tbody.appendChild(tr); }); // appendChild on an existing node moves it
    }

    function updateSortIndicators() {
        var table = document.getElementById('cs-table');
        if (!table) return;
        Array.prototype.forEach.call(table.querySelectorAll('thead th[data-col-key]'), function (th) {
            th.classList.remove('cs-th-sorted-asc', 'cs-th-sorted-desc');
            if (currentSort && th.dataset.colKey === currentSort.key) {
                th.classList.add(currentSort.dir === 'desc' ? 'cs-th-sorted-desc' : 'cs-th-sorted-asc');
            }
        });
    }

    function toggleSort(key) {
        if (currentSort && currentSort.key === key) {
            currentSort = currentSort.dir === 'asc' ? { key: key, dir: 'desc' } : null;
        } else {
            currentSort = { key: key, dir: 'asc' };
        }
        applySort();
        updateSortIndicators();
    }

    window.helixRefreshClientServicingTable = function () {
        fetch('/client-servicing/table-rows')
            .then(function (response) { return response.ok ? response.text() : null; })
            .then(function (html) {
                if (html === null) return;
                body.innerHTML = html;
                syncStickyProjectOffset();
                applySort(); // keep whatever sort was active through the swap
                updateSortIndicators();
            })
            .catch(function () {
                // Network blip — silently skip, same as every other poll/stream
                // callback in this app. The next ping tries again.
            });
    };

    // field -> options list (for the select-type fields). cs_lead_id and
    // project_owner_id are global lists; contact_id's depends on the
    // row's client, resolved from the td's data-client-id at build time.
    var SELECT_FIELDS = {
        scope_id: function () { return window.__csScopeOptions || []; },
        cs_status: function () { return window.__csStatusOptions || []; },
        cs_lead_id: function () { return window.__csLeadOptions || []; },
        project_owner_id: function () { return window.__csProjectOwnerOptions || []; },
        contact_id: function (td) {
            var clientId = td.dataset.clientId;
            var byClient = window.__csContactsByClient || {};
            return (clientId && byClient[clientId]) || [];
        },
    };

    // Sentinel value picked from a SELECT_FIELDS dropdown to start the
    // inline "add new" flow instead of saving a real value.
    var ADD_NEW_VALUE = '__cs_add_new__';

    // field -> quick-add config. `create` posts the new name, resolves
    // to {id, name}, and updates the client-side option cache so the
    // new record shows up immediately in any other cell of the same kind.
    var QUICK_ADD = {
        scope_id: {
            label: '+ Add new scope...',
            prompt: 'New scope name',
            create: function (td, name) {
                return fetch('/client-servicing/scopes/quick-add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: name }),
                })
                    .then(function (r) {
                        return r.json().catch(function () { return {}; })
                            .then(function (data) { return { ok: r.ok, data: data }; });
                    })
                    .then(function (result) {
                        if (!result.ok) throw new Error(result.data.error || 'could not add scope');
                        var options = window.__csScopeOptions || (window.__csScopeOptions = []);
                        if (!options.some(function (o) { return String(o.id) === String(result.data.id); })) {
                            options.push({ id: result.data.id, name: result.data.name });
                        }
                        return { id: result.data.id, name: result.data.name };
                    });
            },
        },
        contact_id: {
            label: '+ Add new contact...',
            prompt: 'New contact name',
            // Can't create a contact without knowing which client it belongs to.
            available: function (td) { return !!td.dataset.clientId; },
            create: function (td, name) {
                var clientId = td.dataset.clientId;
                return fetch('/directory/clients/contacts', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: name, client_id: clientId }),
                })
                    .then(function (r) {
                        return r.json().catch(function () { return {}; })
                            .then(function (data) { return { ok: r.ok, data: data }; });
                    })
                    .then(function (result) {
                        if (!result.ok || !result.data.success) {
                            throw new Error((result.data && result.data.error) || 'could not add contact');
                        }
                        var contact = result.data.contact;
                        var byClient = window.__csContactsByClient || (window.__csContactsByClient = {});
                        if (!byClient[clientId]) byClient[clientId] = [];
                        byClient[clientId].push({ id: contact.id, name: contact.name });
                        return { id: contact.id, name: contact.name };
                    });
            },
        },
    };

    function buildInput(td, field, rawValue) {
        if (SELECT_FIELDS[field]) {
            var select = document.createElement('select');
            var blank = document.createElement('option');
            blank.value = '';
            blank.textContent = '—';
            select.appendChild(blank);
            SELECT_FIELDS[field](td).forEach(function (opt) {
                var option = document.createElement('option');
                option.value = opt.id;
                option.textContent = opt.name;
                if (String(opt.id) === String(rawValue)) option.selected = true;
                select.appendChild(option);
            });
            var quickAdd = QUICK_ADD[field];
            if (quickAdd && (!quickAdd.available || quickAdd.available(td))) {
                var addOption = document.createElement('option');
                addOption.value = ADD_NEW_VALUE;
                addOption.textContent = quickAdd.label;
                select.appendChild(addOption);
            }
            return select;
        }

        var input = document.createElement('input');
        if (field === 'removal_date' || field === 'installation_date' || field === 'first_output_deadline') {
            input.type = 'date';
        } else if (field === 'invoice_month_date') {
            input.type = 'month';
        } else if (field === 'cost_to_client' || field === 'inward_cost' || field === 'value') {
            input.type = 'number';
            input.step = '0.01';
            input.min = '0';
        } else {
            input.type = 'text';
        }
        input.value = rawValue || '';
        return input;
    }

    // Rebuilds the status cell (pill + indicator chips + auto hint) from
    // the effective status the edit endpoint returns, so a cs_status edit
    // shows manual-vs-auto and the right chips immediately.
    var STATUS_CHIP_VARIANT = { '2D': '2d', '3D': '3d', 'Technical': 'technical' };
    function renderStatusCell(td, status) {
        td.innerHTML = '';
        td.dataset.sortValue = status.label || '';
        var pill = document.createElement('span');
        pill.className = 'status-pill status-pill--' + status.modifier;
        pill.textContent = status.label;
        td.appendChild(pill);
        (status.indicators || []).forEach(function (chip) {
            td.appendChild(document.createTextNode(' '));
            var t = document.createElement('span');
            t.className = 'tag tag--' + (STATUS_CHIP_VARIANT[chip] || 'muted');
            t.textContent = chip;
            td.appendChild(t);
        });
        if (status.is_auto) {
            td.appendChild(document.createTextNode(' '));
            var auto = document.createElement('small');
            auto.className = 'cs-muted';
            auto.textContent = 'auto';
            td.appendChild(auto);
        }
    }

    // Builds the same .person-chip markup the server's person_chip()
    // Jinja macro renders, so a CS Lead/Project Owner edit shows the real
    // avatar immediately instead of plain text until the next refresh.
    function renderPersonChip(person) {
        var chip = document.createElement('span');
        chip.className = 'person-chip';

        var avatar = document.createElement('span');
        avatar.className = 'person-avatar';
        if (person.avatar_filename) {
            var img = document.createElement('img');
            img.loading = 'lazy';
            img.alt = '';
            img.src = '/static/avatars/' + person.avatar_filename;
            avatar.appendChild(img);
        } else {
            var initials = document.createElement('span');
            initials.className = 'person-avatar-initials';
            initials.textContent = person.name.charAt(0).toUpperCase();
            avatar.appendChild(initials);
        }
        chip.appendChild(avatar);

        var name = document.createElement('span');
        name.className = 'person-name';
        name.textContent = person.name;
        chip.appendChild(name);

        return chip;
    }

    function saveField(td, field, rawInputValue, originalHtml) {
        var tr = td.closest('tr');
        var projectId = tr ? tr.dataset.projectId : null;
        td.classList.remove('cs-cell-editing');
        if (!projectId) {
            td.innerHTML = originalHtml;
            return;
        }

        fetch('/client-servicing/' + projectId, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ field: field, value: rawInputValue }),
        })
            .then(function (response) {
                return response.json().catch(function () { return {}; })
                    .then(function (data) { return { ok: response.ok, data: data }; });
            })
            .then(function (result) {
                if (!result.ok) {
                    td.innerHTML = originalHtml;
                    td.title = result.data.error || 'could not save';
                    td.classList.add('cs-cell-error');
                    setTimeout(function () {
                        td.classList.remove('cs-cell-error');
                        td.removeAttribute('title');
                    }, 2500);
                    return;
                }
                td.removeAttribute('title');
                td.dataset.value = rawInputValue;
                if (result.data.status) {
                    renderStatusCell(td, result.data.status);
                } else if (result.data.person) {
                    td.innerHTML = '';
                    td.appendChild(renderPersonChip(result.data.person));
                } else {
                    td.textContent = result.data.value || '—';
                }
                if (tr && 'margin_percent' in result.data) {
                    var marginCell = tr.querySelector('[data-field="margin_percent"]');
                    if (marginCell) {
                        marginCell.textContent = result.data.margin_percent !== null
                            ? result.data.margin_percent.toFixed(1) + '%'
                            : '—';
                    }
                }
            })
            .catch(function () {
                // Network blip — revert to the last known-good value; the
                // next click retries the edit fresh.
                td.innerHTML = originalHtml;
            });
    }

    // Inline "name + Add/Cancel" form replacing the select when "+ Add new..."
    // is picked. On Add, creates the record then saves the new id like any
    // edit; Cancel/Escape/failure restore the cell.
    function startQuickAdd(td, quickAdd, originalHtml, onCreated) {
        td.innerHTML = '';

        var wrap = document.createElement('div');
        wrap.className = 'cs-quick-add';

        var nameInput = document.createElement('input');
        nameInput.type = 'text';
        nameInput.className = 'cs-quick-add-input';
        nameInput.placeholder = quickAdd.prompt;
        wrap.appendChild(nameInput);

        var actions = document.createElement('div');
        actions.className = 'cs-quick-add-actions';
        // Reuse the app's existing btn-primary/btn-secondary classes so the
        // colours (and dark-mode overrides) are the ones already proven
        // elsewhere — cs-quick-add-btn in the CSS only shrinks them to fit.
        var addBtn = document.createElement('button');
        addBtn.type = 'button';
        addBtn.className = 'btn-primary cs-quick-add-btn';
        addBtn.textContent = 'Add';
        var cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.className = 'btn-secondary cs-quick-add-btn';
        cancelBtn.textContent = 'Cancel';
        actions.appendChild(addBtn);
        actions.appendChild(cancelBtn);
        wrap.appendChild(actions);

        td.appendChild(wrap);
        nameInput.focus();

        function restore() {
            td.classList.remove('cs-cell-editing');
            td.innerHTML = originalHtml;
        }

        function fail(message) {
            restore();
            td.classList.add('cs-cell-error');
            td.title = message || 'could not add';
            setTimeout(function () {
                td.classList.remove('cs-cell-error');
                td.removeAttribute('title');
            }, 2500);
        }

        function submit() {
            var name = nameInput.value.trim();
            if (!name) { nameInput.focus(); return; }
            addBtn.disabled = true;
            quickAdd.create(td, name).then(function (created) {
                onCreated(created.id);
            }).catch(function (err) {
                fail(err && err.message);
            });
        }

        addBtn.addEventListener('click', submit);
        cancelBtn.addEventListener('click', restore);
        nameInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                submit();
            } else if (e.key === 'Escape') {
                e.preventDefault();
                restore();
            }
        });
    }

    function startEdit(td) {
        if (td.classList.contains('cs-cell-editing')) return;
        var field = td.dataset.field;
        var rawValue = td.dataset.value || '';
        var originalHtml = td.innerHTML;

        td.classList.add('cs-cell-editing');
        td.innerHTML = '';
        var input = buildInput(td, field, rawValue);
        td.appendChild(input);
        input.focus();
        if (input.select) input.select();

        var settled = false;

        function commit(value) {
            if (settled) return;
            settled = true;
            saveField(td, field, value, originalHtml);
        }

        var quickAdd = QUICK_ADD[field];
        if (quickAdd && input.tagName === 'SELECT') {
            input.addEventListener('change', function () {
                if (input.value !== ADD_NEW_VALUE) return;
                settled = true; // stop the blur handler below from saving "__cs_add_new__"
                startQuickAdd(td, quickAdd, originalHtml, function (newId) {
                    settled = false;
                    commit(String(newId));
                });
            });
        }

        input.addEventListener('blur', function () {
            commit(input.value);
        });
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                input.blur();
            } else if (e.key === 'Escape') {
                e.preventDefault();
                settled = true;
                td.classList.remove('cs-cell-editing');
                td.innerHTML = originalHtml;
            }
        });
    }

    body.addEventListener('click', function (e) {
        var td = e.target.closest('.cs-editable');
        if (!td || td.classList.contains('cs-cell-editing')) return;
        startEdit(td);
    });

    // ── Column resize ─────────────────────────────────────────────
    // Delegated on `body`, not the table — the table is replaced on every
    // live refresh, so a handle-bound listener would stop working after one.
    var MIN_COL_WIDTH = 60;
    var layoutSaveTimer = null;

    function scheduleLayoutSave(table) {
        clearTimeout(layoutSaveTimer);
        layoutSaveTimer = setTimeout(function () {
            var saveUrl = table.dataset.saveLayoutUrl;
            var tableKey = table.dataset.tableKey;
            if (!saveUrl || !tableKey) return;
            var layout = Array.prototype.slice.call(table.querySelectorAll('colgroup col[data-col-key]'))
                .map(function (col) { return { key: col.dataset.colKey, width: col.offsetWidth }; });
            fetch(saveUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ table_key: tableKey, layout: layout }),
            }).catch(function () {
                // Best-effort, silent — the next resize just tries again.
            });
        }, 400);
    }

    body.addEventListener('mousedown', function (e) {
        var handle = e.target.closest('.cs-resize-handle');
        if (!handle) return;
        e.preventDefault();

        var table = handle.closest('table');
        var th = handle.closest('th');
        var col = table && table.querySelector('colgroup col[data-col-key="' + handle.dataset.colKey + '"]');
        if (!table || !th || !col) return;

        var startX = e.clientX;
        var startWidth = th.getBoundingClientRect().width;
        handle.classList.add('cs-resize-handle--active');

        function onMove(ev) {
            var newWidth = Math.max(MIN_COL_WIDTH, Math.round(startWidth + (ev.clientX - startX)));
            col.style.width = newWidth + 'px';
        }
        function onUp() {
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
            handle.classList.remove('cs-resize-handle--active');
            scheduleLayoutSave(table);
        }
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
    });

    // ── Column reorder ────────────────────────────────────────────
    // Delegated on `body` (survives refresh swaps); skips the resize handle's
    // own mousedown. Moves the dragged column's <th>/<col>/<td>s live via
    // insertBefore; scheduleLayoutSave() persists the order and the next
    // refresh re-renders it via table.py's _ordered_columns().
    var DRAG_THRESHOLD = 4; // px of movement before a mousedown becomes a drag, not a stray click

    // A header click sorts; a drag reorders. Set when a real drag ends so the
    // click handler below can tell the two apart from the same mouse pair.
    var suppressNextClick = false;

    function findColumnCells(table, key) {
        return {
            th: table.querySelector('thead th[data-col-key="' + key + '"]'),
            col: table.querySelector('colgroup col[data-col-key="' + key + '"]'),
            tds: Array.prototype.slice.call(table.querySelectorAll('tbody td[data-col-key="' + key + '"]')),
        };
    }

    function moveColumn(table, draggedKey, targetKey, after) {
        if (draggedKey === targetKey) return;
        var dragged = findColumnCells(table, draggedKey);
        var target = findColumnCells(table, targetKey);
        if (!dragged.th || !dragged.col || !target.th || !target.col) return;

        var refTh = after ? target.th.nextElementSibling : target.th;
        dragged.th.parentNode.insertBefore(dragged.th, refTh);

        var refCol = after ? target.col.nextElementSibling : target.col;
        dragged.col.parentNode.insertBefore(dragged.col, refCol);

        dragged.tds.forEach(function (td, i) {
            var targetTd = target.tds[i];
            if (!targetTd) return;
            var refTd = after ? targetTd.nextElementSibling : targetTd;
            targetTd.parentNode.insertBefore(td, refTd);
        });
    }

    body.addEventListener('mousedown', function (e) {
        if (e.target.closest('.cs-resize-handle')) return; // the resize handler above owns this
        var th = e.target.closest('th[data-col-key]');
        // Project is pinned right after "Open in Projects" (sticky CSS
        // below assumes it never moves) — same as the Projects page
        // excluding its own Name column from reorder entirely.
        if (!th || th.dataset.colKey === 'project') return;
        e.preventDefault();

        var table = th.closest('table');
        var draggedKey = th.dataset.colKey;
        var startX = e.clientX;
        var startY = e.clientY;
        var dragging = false;

        function onMove(ev) {
            if (!dragging) {
                if (Math.abs(ev.clientX - startX) < DRAG_THRESHOLD && Math.abs(ev.clientY - startY) < DRAG_THRESHOLD) return;
                dragging = true;
                th.classList.add('cs-th-dragging');
            }
            var hovered = document.elementFromPoint(ev.clientX, ev.clientY);
            var targetTh = hovered && hovered.closest('th[data-col-key]');
            if (!targetTh || targetTh === th || targetTh.dataset.colKey === 'project') return; // pinned — not a drop target either

            var rect = targetTh.getBoundingClientRect();
            var after = ev.clientX > rect.left + rect.width / 2;
            moveColumn(table, draggedKey, targetTh.dataset.colKey, after);
        }
        function onUp() {
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
            th.classList.remove('cs-th-dragging');
            if (dragging) {
                suppressNextClick = true; // this mouseup's 'click' is the drag ending, not a sort request
                scheduleLayoutSave(table);
            }
        }
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
    });

    // A non-drag click sorts by that column. Covers Project too — sortable
    // though not draggable.
    body.addEventListener('click', function (e) {
        if (suppressNextClick) { suppressNextClick = false; return; }
        if (e.target.closest('.cs-resize-handle')) return;
        var th = e.target.closest('th[data-col-key]');
        if (!th) return;
        toggleSort(th.dataset.colKey);
    });

    // ── Sticky column wiring ──────────────────────────────────────────
    // Both run now, for this visit's freshly-swapped table.
    syncStickyProjectOffset();
    syncTableScrollHeight();

    // Bound once for the session. This file re-executes on every SPA nav
    // (execScripts re-runs the fragment's script tags), and both handlers
    // re-query the DOM on each call, so one registration serves every visit —
    // without the guard each navigation stacked another pair. Same reasoning
    // as the filter panel's outside-click listener below.
    if (!window.__csTableResizeBound) {
        window.__csTableResizeBound = true;
        window.addEventListener('resize', syncStickyProjectOffset);
        window.addEventListener('resize', syncTableScrollHeight);
    }
})();


/* ── Table search + filter (client-side over the loaded rows) ────────────
   Reads the same data-sort-value hooks the sort uses, hides non-matching
   rows, and re-runs after each SSE live refresh. Self-contained; no server,
   no new data. Chip options are built from the rows themselves so they
   always match what's in the table. */
(function () {
    var searchInput = document.getElementById('cs-search');
    var table = document.getElementById('cs-table');
    var bodyWrap = document.getElementById('client-servicing-table-body');
    if (!searchInput || !table || !bodyWrap) return;

    var searchClear = document.getElementById('cs-search-clear');
    var toggleBtn = document.getElementById('cs-filter-toggle');
    var panel = document.getElementById('cs-filter-panel');
    var columnsEl = document.getElementById('cs-filter-columns');
    var countEl = document.getElementById('cs-filter-count');
    var clearBtn = document.getElementById('cs-filter-clear');

    // Filter field key = the column's data-col-key; its data-sort-value holds
    // the value we filter on.
    var FIELDS = [
        { key: 'client', label: 'Client' },
        { key: 'cs_lead', label: 'CS Contact' },
        { key: 'project_owner', label: 'Project Owner' },
        { key: 'status', label: 'Status' },
        { key: 'scope', label: 'Scope' },
        { key: 'priority', label: 'Priority' }
    ];
    var SEARCH_COLS = ['client', 'project', 'job_number'];
    var BLANK = '__blank__';        // internal token for an empty cell, shown as "—"

    var selected = {};           // field key -> { token: true }
    FIELDS.forEach(function (f) { selected[f.key] = {}; });

    function rows() {
        return Array.prototype.slice.call(table.querySelectorAll('tbody tr[data-project-id]'));
    }

    function cellValue(tr, key) {
        var td = tr.querySelector('td[data-col-key="' + key + '"]');
        return td ? (td.getAttribute('data-sort-value') || '') : '';
    }

    function tokenOf(tr, key) {
        var v = cellValue(tr, key);
        return v === '' ? BLANK : v;
    }

    function matchesSearch(tr, term) {
        if (!term) return true;
        for (var i = 0; i < SEARCH_COLS.length; i++) {
            if (cellValue(tr, SEARCH_COLS[i]).toLowerCase().indexOf(term) !== -1) return true;
        }
        return false;
    }

    function matchesField(tr, key) {
        var sel = selected[key];
        if (!Object.keys(sel).length) return true;
        return !!sel[tokenOf(tr, key)];
    }

    // Passes the search plus every field EXCEPT `except` (used for faceted counts;
    // pass null to test all fields).
    function passes(tr, term, except) {
        if (!matchesSearch(tr, term)) return false;
        for (var i = 0; i < FIELDS.length; i++) {
            var k = FIELDS[i].key;
            if (k === except) continue;
            if (!matchesField(tr, k)) return false;
        }
        return true;
    }

    function displayLabel(token) {
        return token === BLANK ? '—' : token;
    }

    // Build the chip columns from the current rows, preserving selections.
    function buildChips() {
        table = document.getElementById('cs-table');
        if (!table) return;
        var all = rows();
        columnsEl.innerHTML = '';
        FIELDS.forEach(function (f) {
            var tokens = {};
            all.forEach(function (tr) { tokens[tokenOf(tr, f.key)] = true; });
            var list = Object.keys(tokens).sort(function (a, b) {
                if (a === BLANK) return 1;
                if (b === BLANK) return -1;
                return a.toLowerCase().localeCompare(b.toLowerCase());
            });

            var col = document.createElement('div');
            col.className = 'cs-filter-column';
            var label = document.createElement('div');
            label.className = 'cs-filter-column-label';
            label.textContent = f.label;
            var listEl = document.createElement('div');
            listEl.className = 'cs-filter-column-list';

            list.forEach(function (token) {
                var chip = document.createElement('button');
                chip.type = 'button';
                chip.className = 'cs-chip';
                chip.dataset.field = f.key;
                chip.dataset.token = token;
                var text = document.createElement('span');
                text.className = 'cs-chip-text';
                text.textContent = displayLabel(token);
                var cnt = document.createElement('span');
                cnt.className = 'cs-chip-count';
                chip.appendChild(text);
                chip.appendChild(cnt);
                listEl.appendChild(chip);
            });

            col.appendChild(label);
            col.appendChild(listEl);
            columnsEl.appendChild(col);
        });
    }

    function setNoMatches(on) {
        var tb = table.querySelector('tbody');
        if (!tb) return;
        var existing = tb.querySelector('.cs-no-matches');
        if (on && !existing) {
            var tr = document.createElement('tr');
            tr.className = 'cs-no-matches';
            var td = document.createElement('td');
            td.colSpan = table.querySelectorAll('thead th').length || 1;
            td.textContent = 'No projects match your search or filters.';
            tr.appendChild(td);
            tb.appendChild(tr);
        } else if (!on && existing) {
            existing.remove();
        }
    }

    // Recompute chip counts (faceted) + selected states.
    function updateChips(all, term) {
        var chips = columnsEl.querySelectorAll('.cs-chip');
        // base sets per field: rows passing search + all OTHER fields
        var baseByField = {};
        FIELDS.forEach(function (f) {
            baseByField[f.key] = all.filter(function (tr) { return passes(tr, term, f.key); });
        });
        Array.prototype.forEach.call(chips, function (chip) {
            var field = chip.dataset.field;
            var token = chip.dataset.token;
            var n = 0, base = baseByField[field];
            for (var i = 0; i < base.length; i++) { if (tokenOf(base[i], field) === token) n++; }
            chip.querySelector('.cs-chip-count').textContent = n;
            var isSel = !!selected[field][token];
            chip.classList.toggle('is-selected', isSel);
        });
    }

    function updateBadge() {
        var n = 0;
        FIELDS.forEach(function (f) { n += Object.keys(selected[f.key]).length; });
        toggleBtn.textContent = n ? 'Filter / ' + n : 'Filter';
        toggleBtn.classList.toggle('is-active', n > 0);
        return n;
    }

    function apply() {
        table = document.getElementById('cs-table');
        if (!table) return;
        var term = (searchInput.value || '').trim().toLowerCase();
        var all = rows();
        var visible = 0;
        all.forEach(function (tr) {
            var show = passes(tr, term, null);
            tr.style.display = show ? '' : 'none';
            if (show) visible++;
        });
        setNoMatches(all.length > 0 && visible === 0);
        updateChips(all, term);
        var filterN = updateBadge();
        searchClear.hidden = !term;
        countEl.textContent = (term || filterN) ? ('Showing ' + visible + ' of ' + all.length) : 'Showing all';
    }

    // ── events ──
    var searchTimer = null;
    searchInput.addEventListener('input', function () {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(apply, 120);
    });
    searchClear.addEventListener('click', function () {
        searchInput.value = '';
        apply();
        searchInput.focus();
    });

    toggleBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        panel.hidden = !panel.hidden;
    });
    // Outside-click close. Bound on document (persistent across SPA nav), so
    // bind ONCE for the session and re-resolve the current panel each click —
    // otherwise every navigation would stack another live listener.
    if (!window.__csFilterOutsideBound) {
        window.__csFilterOutsideBound = true;
        document.addEventListener('click', function (e) {
            var p = document.getElementById('cs-filter-panel');
            if (p && !p.hidden && !e.target.closest('.cs-filter')) p.hidden = true;
        });
    }

    clearBtn.addEventListener('click', function () {
        FIELDS.forEach(function (f) { selected[f.key] = {}; });
        searchInput.value = '';
        apply();
    });

    // Chip clicks (delegated on the columns container, which is rebuilt on
    // refresh — the listener sits on the container, so it survives).
    columnsEl.addEventListener('click', function (e) {
        var chip = e.target.closest('.cs-chip');
        if (!chip) return;
        var field = chip.dataset.field, token = chip.dataset.token;
        if (selected[field][token]) delete selected[field][token];
        else selected[field][token] = true;
        apply();
    });

    // Re-apply after the SSE live refresh swaps the table rows. Disconnect any
    // observer from a previous SPA visit so only one is ever active.
    if (window.__csFilterObserver) window.__csFilterObserver.disconnect();
    var refreshTimer = null;
    var mo = new MutationObserver(function () {
        clearTimeout(refreshTimer);
        refreshTimer = setTimeout(function () { buildChips(); apply(); }, 0);
    });
    mo.observe(bodyWrap, { childList: true });
    window.__csFilterObserver = mo;

    buildChips();
    apply();
})();
