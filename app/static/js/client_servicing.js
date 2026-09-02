// Client Servicing page. This file's script tag lives in the page's own
// {% block extra_js %}, so it re-executes fresh on every SPA navigation
// onto this page (see app/__init__.py's spa_strip_response) — no
// helix:navigated listener needed here.
//
// polling.js opens a stream to /sse/dashboard (the generic "some project
// changed somewhere" doorbell) whenever .client-servicing-page is on
// screen, and calls window.helixRefreshClientServicingTable() on every
// ping — same convention as project_list.js's helixRefreshProjectTable.
//
// Cell editing: every .cs-editable <td> edits in place — click it, it
// turns into the right input, saves on blur. No overlay, no modal, no
// popover; the whole thing happens inside the table cell. Click handling
// is delegated on #client-servicing-table-body (never replaced itself,
// only its innerHTML), so it survives every live-refresh swap without
// needing to be rebound.
//
// Scope and Client SPOC can also be created inline: their
// select gets a trailing "+ Add new..." option; picking it swaps the
// select for a tiny name field + Add/Cancel, still inside the same td.
// On Add it posts to the field's own quick-add endpoint, then saves the
// new record's id through the normal saveField() path — same PATCH,
// same error handling, nothing duplicated.
//
// Click-to-sort: click a header to sort by that
// column, click again to reverse, a third click clears back to the
// server's default order (Project name, A-Z). Deliberately lighter than
// the Projects page's Sort popout — no query params, no multi-field
// sort, nothing saved to the server — just a live re-order of the rows
// already on screen, entirely in this module-scope `currentSort`
// variable. That also means it resets on every page load/SPA
// navigation for free (this whole file re-executes fresh each time, per
// the top-of-file note), matching what Ezekiel asked for; it does
// survive a live SSE refresh, since applySort() re-runs after every
// helixRefreshClientServicingTable() swap so a background edit from
// someone else doesn't silently undo the sort you're mid-review of.
(function () {
    var body = document.getElementById('client-servicing-table-body');
    if (!body) return;

    // Sticky Project-name column, mirroring the Projects page's pinned
    // Expand+Name pair: "Open in Projects" and Project both stay put as
    // the table scrolls right (CSS below). Project's sticky "left" has
    // to equal the Open column's actual rendered width — unlike the
    // Projects page's fixed-size icon-only Expand column, "Open in
    // Projects" is a text button with no fixed width to hard-code, so
    // it's measured here instead and handed to the CSS as a custom
    // property. Re-run after every refresh, since the whole <table> (and
    // any inline style on it) is replaced wholesale each time.
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
        var box = document.getElementById('cs-table-scroll');
        var footer = document.querySelector('.footer');
        if (!box || !footer) return;
        // Height that makes the box's bottom edge meet the footer's top.
        // box.top and the footer height are independent of the box's own
        // height, so this solves it directly rather than nudging a delta.
        var boxRect = box.getBoundingClientRect();
        var footerRect = footer.getBoundingClientRect();
        var target = window.innerHeight - boxRect.top - footerRect.height;
        if (target > 100) { // guard against a mid-layout-thrash reading
            box.style.setProperty('--cs-table-scroll-height', target + 'px');
        }
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
        } else if (field === 'invoice_month') {
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
                if (result.data.person) {
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

    // Small inline "name + Add/Cancel" form, replacing the select inside
    // the same td — used when someone picks "+ Add new..." instead of an
    // existing option. On Add, creates the record via quickAdd.create()
    // then hands the new id to onCreated (which saves it like any other
    // edit). Never leaves the page without a value: Cancel/Escape/a
    // failed create all restore the cell to what it was before editing
    // started.
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
    // Delegated on `body`, not the <table> itself — the whole table gets
    // replaced wholesale on every live refresh (same reasoning as the
    // click-to-edit handler above), so a listener bound to individual
    // .cs-resize-handle elements would stop working after the first
    // refresh.
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
    // Same delegation reasoning as resize above: bound on `body`, not the
    // <table>, so it survives every live-refresh swap. Guards against the
    // resize handle's own mousedown — the handle sits inside its <th>, so
    // without that check every resize-drag would also start a reorder.
    //
    // Moves the dragged column's <th> (thead), <col> (colgroup), and every
    // row's <td> (tbody) live via insertBefore as the user drags. Like
    // resize, the server render is the ultimate source of truth:
    // scheduleLayoutSave() (above) persists whatever order the colgroup
    // ends up in, and the next full refresh re-renders in that saved
    // order via table.py's _ordered_columns() — these DOM moves just keep
    // the current view honest until that happens.
    var DRAG_THRESHOLD = 4; // px of movement before a mousedown becomes a drag, not a stray click

    // A plain click on a header (no movement past DRAG_THRESHOLD) sorts
    // instead of reordering — set right before the browser's own 'click'
    // event fires for a drag that DID move, so that click handler below
    // can tell "just dragged" apart from "just clicked" using the same
    // mousedown/mouseup pair the reorder logic already tracked.
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

    // A click that wasn't a drag sorts by that column. Delegated the same
    // way as every other handler here (survives live-refresh swaps);
    // covers Project too, even though Project is excluded from the
    // reorder-drag above — it's still sortable, just not draggable.
    body.addEventListener('click', function (e) {
        if (suppressNextClick) { suppressNextClick = false; return; }
        if (e.target.closest('.cs-resize-handle')) return;
        var th = e.target.closest('th[data-col-key]');
        if (!th) return;
        toggleSort(th.dataset.colKey);
    });

    // ── Sticky column wiring ──────────────────────────────────────────
    syncStickyProjectOffset();
    window.addEventListener('resize', syncStickyProjectOffset);

    // Runs after syncStickyProjectOffset (harmless either order, kept
    // together since both are "measure real chrome, don't guess"
    // fixes) — see the function's own comment above for why this
    // exists instead of a fixed CSS value.
    syncTableScrollHeight();
    window.addEventListener('resize', syncTableScrollHeight);
})();
