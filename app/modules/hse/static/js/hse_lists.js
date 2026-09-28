// HSE Lists & people: the index, the open list and the people panel.
// Adding, retiring and saving a person reload the page from the server,
// since counts and ordering shift. Editing a name or code saves in place.
//
// No DOMContentLoaded gate: page scripts re-run on every SPA swap and that
// event never fires again. Every listener is delegated from document and
// bound once; handlers look the page up at event time.
(function () {
    if (window._hseListsWired) { return; }
    window._hseListsWired = true;

    function card() { return document.querySelector('.hse-lists-card'); }

    function go(url) {
        if (window.navigateTo) { window.navigateTo(url); } else { window.location.href = url; }
    }

    function refresh() { go(window.location.pathname + window.location.search); }

    function note(text, slot) {
        var target = slot || (card() && card().querySelector('.hse-lists-foot .hse-lists-note'));
        if (target) { target.textContent = text || ''; }
    }

    // The template renders each endpoint with id 0; swap in the real id.
    function updateUrl(id) {
        return card().getAttribute('data-update-url').replace(/\/0$/, '/' + id);
    }

    function send(url, method, body) {
        return fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        }).then(function (res) {
            return res.json().catch(function () { return {}; })
                .then(function (b) { return { ok: res.ok, body: b }; });
        });
    }

    function failed(result, fallback, slot) {
        note((result.body && result.body.error) || fallback, slot);
    }

    // ── Adding to a list ──────────────────────────────────────────────

    function add() {
        var row = card().querySelector('.hse-lists-add');
        var label = row.querySelector('[data-add="label"]').value.trim();
        if (!label) { note('Type a name first.'); return; }

        var kind = card().getAttribute('data-kind');
        var key = card().getAttribute('data-key');
        var payload = { kind: key, label: label };
        if (kind === 'asset') {
            var ref = row.querySelector('[data-add="ref"]');
            var serial = row.querySelector('[data-add="serial_no"]');
            payload.ref = ref ? ref.value : '';
            payload.serial_no = serial ? serial.value : '';
        }
        note('Saving…');
        send(card().getAttribute('data-create-url'), 'POST', payload).then(function (result) {
            if (!result.ok) { failed(result, 'Could not add that.'); return; }
            refresh();
        }).catch(function () { note('Could not reach the server.'); });
    }

    // ── Editing a name or code in place ───────────────────────────────

    function saveCell(input) {
        var value = input.value.trim();
        var before = input.getAttribute('data-value');
        if (value === before) { input.value = before; return; }
        var field = input.getAttribute('data-field');
        if (field === 'label' && !value) {
            input.value = before;
            note('A name cannot be blank.');
            return;
        }
        var body = {};
        body[field] = value;
        note('Saving…');
        send(updateUrl(input.closest('tr').getAttribute('data-id')), 'PATCH', body)
            .then(function (result) {
                if (!result.ok) {
                    input.value = before;
                    failed(result, 'Could not save that.');
                    return;
                }
                var saved = result.body.row[field] || '';
                input.value = saved;
                input.setAttribute('data-value', saved);
                note('Saved.');
            })
            .catch(function () {
                input.value = before;
                note('Could not reach the server.');
            });
    }

    // ── Retiring and reactivating ─────────────────────────────────────

    function toggle(id, turnOn, slot) {
        note(turnOn ? 'Reactivating…' : 'Deactivating…', slot);
        send(updateUrl(id), 'PATCH', { active: turnOn }).then(function (result) {
            if (!result.ok) { failed(result, 'Could not change that.', slot); return; }
            refresh();
        }).catch(function () { note('Could not reach the server.', slot); });
    }

    // ── Filtering ─────────────────────────────────────────────────────

    function filterIndex(query) {
        var q = query.trim().toLowerCase();
        document.querySelectorAll('.hse-lists-group').forEach(function (group) {
            var shown = 0;
            group.querySelectorAll('.hse-lists-link').forEach(function (link) {
                var match = !q || link.getAttribute('data-label').indexOf(q) !== -1;
                link.hidden = !match;
                if (match) { shown += 1; }
            });
            group.hidden = shown === 0;
        });
    }

    function filterRows(query) {
        var q = query.trim().toLowerCase();
        card().querySelectorAll('.hse-lists-row').forEach(function (row) {
            row.hidden = !!q && row.getAttribute('data-filter').indexOf(q) === -1;
        });
    }

    // ── The people panel ──────────────────────────────────────────────

    function panel() { return card() && card().querySelector('.hse-lists-panel'); }

    function openPerson(row) {
        var p = panel();
        var form = p.querySelector('.hse-person-form');
        var person = row ? JSON.parse(row.getAttribute('data-person')) : null;
        var toggleBtn = form.querySelector('[data-person-toggle]');

        form.reset();
        form.setAttribute('data-id', person ? person.id : '');
        form.querySelector('.hse-lists-panel-title').textContent = person ? person.label : 'Add a person';
        if (person) {
            form.elements.name.value = person.label || '';
            form.elements.role.value = person.role || '';
            form.elements.organisation.value = person.organisation || '';
            form.elements.is_external.checked = !!person.is_external;
            form.elements.can_hold_actions.checked = !!person.can_hold_actions;
            form.elements.email.value = person.email || '';
            form.elements.phone.value = person.phone || '';
        }
        toggleBtn.hidden = !person;
        toggleBtn.textContent = person && !person.active ? 'Reactivate' : 'Deactivate';
        toggleBtn.setAttribute('data-on', person && !person.active ? 'yes' : 'no');
        note('', form.querySelector('[data-person-note]'));

        card().querySelectorAll('.hse-lists-row.is-open').forEach(function (r) {
            r.classList.remove('is-open');
        });
        if (row) { row.classList.add('is-open'); }
        p.hidden = false;
        form.elements.name.focus();
    }

    function closePerson() {
        var p = panel();
        if (!p) { return; }
        p.hidden = true;
        card().querySelectorAll('.hse-lists-row.is-open').forEach(function (r) {
            r.classList.remove('is-open');
        });
    }

    function savePerson(form) {
        var slot = form.querySelector('[data-person-note]');
        var name = form.elements.name.value.trim();
        if (!name) { note('Type a name first.', slot); form.elements.name.focus(); return; }

        var id = form.getAttribute('data-id');
        var payload = {
            name: name,
            role: form.elements.role.value,
            organisation: form.elements.organisation.value,
            is_external: form.elements.is_external.checked,
            can_hold_actions: form.elements.can_hold_actions.checked,
            email: form.elements.email.value,
            phone: form.elements.phone.value
        };
        note('Saving…', slot);
        var request = id ? send(updateUrl(id), 'PATCH', payload)
                         : send(card().getAttribute('data-create-url'), 'POST', payload);
        request.then(function (result) {
            if (!result.ok) { failed(result, 'Could not save this person.', slot); return; }
            refresh();
        }).catch(function () { note('Could not reach the server.', slot); });
    }

    // ── Wiring ────────────────────────────────────────────────────────

    document.addEventListener('click', function (e) {
        if (!card()) { return; }

        // Index links route through the SPA; modified clicks are left alone.
        var link = e.target.closest('.hse-lists-link');
        if (link) {
            if (e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) { return; }
            e.preventDefault();
            go(link.getAttribute('href'));
            return;
        }

        if (e.target.closest('[data-add-submit]')) { add(); return; }

        var rename = e.target.closest('[data-rename]');
        if (rename) {
            var nameInput = rename.closest('tr').querySelector('[data-field="label"]');
            nameInput.focus();
            nameInput.select();
            return;
        }

        var toggleBtn = e.target.closest('[data-toggle]');
        if (toggleBtn) {
            toggle(toggleBtn.closest('tr').getAttribute('data-id'),
                   toggleBtn.getAttribute('data-toggle') === 'on');
            return;
        }

        var more = e.target.closest('[data-show-retired]');
        if (more) {
            var retired = card().querySelector('.hse-lists-retired');
            var opening = retired.hidden;
            retired.hidden = !opening;
            more.setAttribute('aria-expanded', opening ? 'true' : 'false');
            more.textContent = (opening ? 'Hide retired (' : 'Show retired (')
                + more.getAttribute('data-count') + ')';
            return;
        }

        if (e.target.closest('[data-person-open]')) { openPerson(null); return; }
        if (e.target.closest('[data-person-close]')) { closePerson(); return; }

        var personToggle = e.target.closest('[data-person-toggle]');
        if (personToggle) {
            var form = personToggle.closest('.hse-person-form');
            toggle(form.getAttribute('data-id'), personToggle.getAttribute('data-on') === 'yes',
                   form.querySelector('[data-person-note]'));
            return;
        }

        var personRow = e.target.closest('.hse-lists-row[data-person]');
        if (personRow) { openPerson(personRow); }
    });

    document.addEventListener('submit', function (e) {
        var form = e.target.closest('.hse-person-form');
        if (!form) { return; }
        e.preventDefault();
        savePerson(form);
    });

    // An edited cell saves when it is left.
    document.addEventListener('change', function (e) {
        if (e.target.classList.contains('hse-lists-cell')) { saveCell(e.target); return; }
        if (e.target.id === 'hse-lists-picker') { go(e.target.value); }
    });

    document.addEventListener('input', function (e) {
        if (e.target.id === 'hse-lists-find') { filterIndex(e.target.value); return; }
        if (e.target.id === 'hse-lists-filter') { filterRows(e.target.value); }
    });

    // Enter adds from the add row and commits a cell; Escape undoes a cell
    // or closes the panel.
    document.addEventListener('keydown', function (e) {
        if (!card()) { return; }
        var cell = e.target.classList && e.target.classList.contains('hse-lists-cell') ? e.target : null;
        if (e.key === 'Enter') {
            if (cell) { e.preventDefault(); cell.blur(); return; }
            if (e.target.matches('.hse-lists-row[data-person]')) { openPerson(e.target); return; }
            if (e.target.closest('.hse-lists-add')) { e.preventDefault(); add(); }
            return;
        }
        if (e.key === 'Escape') {
            if (cell) {
                cell.value = cell.getAttribute('data-value');
                cell.blur();
                return;
            }
            if (panel() && !panel().hidden) { closePerson(); }
        }
    });
}());
