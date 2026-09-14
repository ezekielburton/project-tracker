/*
 * HSE — the Schedule tab.
 *
 * One side panel, two modes. The options are already on the page, so unlike
 * the entry overlay this does not fetch anything to open.
 *
 * IIFE with init called at the bottom: SPA navigation runs this through
 * execScripts() after DOMContentLoaded has long gone, so waiting for that
 * event would leave the page dead.
 */
(function () {
    'use strict';

    var form, tableBody, assetsBox, assetList, assetsLabel, freqBox;
    var options, people, assets, forms;
    var editingId = null;
    var previewTimer = null;

    function el(id) { return document.getElementById(id); }
    function field(name) { return form.querySelector('[name="' + name + '"]'); }

    function option(value, label) {
        var o = document.createElement('option');
        o.value = (value === null || value === undefined) ? '' : String(value);
        o.textContent = label;
        return o;
    }

    function fill(select, items, placeholder) {
        select.innerHTML = '';
        if (placeholder) { select.appendChild(option('', placeholder)); }
        items.forEach(function (item) {
            select.appendChild(option(item.value, item.label));
        });
    }

    function registerByKey(key) {
        var found = null;
        options.registers.forEach(function (r) { if (r.key === key) { found = r; } });
        return found;
    }

    // --- frequency, as a segmented control --------------------------------

    function buildFrequency() {
        freqBox.innerHTML = '';
        options.frequencies.forEach(function (f) {
            var button = document.createElement('button');
            button.type = 'button';
            button.className = 'hse-seg';
            button.setAttribute('data-value', f.value);
            button.textContent = f.label;
            freqBox.appendChild(button);
        });
    }

    function setFrequency(value) {
        field('frequency').value = value || 'weekly';
        freqBox.querySelectorAll('.hse-seg').forEach(function (b) {
            b.classList.toggle('is-selected',
                b.getAttribute('data-value') === field('frequency').value);
        });
        syncFrequency();
    }

    function syncFrequency() {
        var freq = field('frequency').value;
        var monthly = options.monthly_frequencies.indexOf(freq) !== -1;
        form.querySelectorAll('[data-when="weekly"]').forEach(function (n) {
            n.hidden = freq !== 'weekly';
        });
        form.querySelectorAll('[data-when="monthly"]').forEach(function (n) {
            n.hidden = !monthly;
        });
    }

    // --- assets -----------------------------------------------------------

    function checkedAssetIds() {
        var out = [];
        assetList.querySelectorAll('input[type="checkbox"]').forEach(function (box) {
            if (box.checked) { out.push(parseInt(box.value, 10)); }
        });
        return out;
    }

    function syncAssets(keepChecked) {
        var reg = registerByKey(field('register').value);
        var checked = keepChecked ? checkedAssetIds() : [];
        if (!reg || !reg.asset_label) {
            assetsBox.hidden = true;
            assetList.innerHTML = '';
            return;
        }
        assetsBox.hidden = false;
        assetsLabel.textContent = reg.asset_required
            ? reg.asset_label + ' (pick at least one)'
            : reg.asset_label;

        assetList.innerHTML = '';
        assets.forEach(function (asset) {
            var label = document.createElement('label');
            label.className = 'hse-sched-asset';
            var box = document.createElement('input');
            box.type = 'checkbox';
            box.value = String(asset.id);
            box.checked = checked.indexOf(asset.id) !== -1;
            label.appendChild(box);
            label.appendChild(document.createTextNode(
                asset.label + (asset.ref ? ' · ' + asset.ref : '')));
            assetList.appendChild(label);
        });
    }

    // --- reading and writing the panel ------------------------------------

    function payload() {
        var freq = field('frequency').value;
        return {
            label: field('label').value,
            register: field('register').value,
            frequency: freq,
            interval: field('interval').value,
            weekday: freq === 'weekly' ? field('weekday').value : '',
            day_of_month: options.monthly_frequencies.indexOf(freq) !== -1
                ? field('day_of_month').value : '',
            starts_on: field('starts_on').value,
            ends_on: field('ends_on').value,
            owner_id: field('owner_id').value,
            asset_ids: checkedAssetIds()
        };
    }

    function clearErrors() {
        form.querySelectorAll('[data-error-for]').forEach(function (n) {
            n.textContent = '';
        });
    }

    function showErrors(errors) {
        clearErrors();
        Object.keys(errors || {}).forEach(function (name) {
            var slot = form.querySelector('[data-error-for="' + name + '"]');
            if (slot) { slot.textContent = errors[name]; }
        });
    }

    function load(values) {
        field('label').value = values.label || '';
        field('register').value = values.register || '';
        field('interval').value = values.interval || 1;
        field('weekday').value = (values.weekday === null || values.weekday === undefined)
            ? '' : String(values.weekday);
        field('day_of_month').value = values.day_of_month || '';
        field('starts_on').value = values.starts_on || '';
        field('ends_on').value = values.ends_on || '';
        field('owner_id').value = (values.owner_id === null || values.owner_id === undefined)
            ? '' : String(values.owner_id);
        setFrequency(values.frequency);
        syncAssets(false);
        (values.asset_ids || []).forEach(function (id) {
            var box = assetList.querySelector('input[value="' + id + '"]');
            if (box) { box.checked = true; }
        });
    }

    function today() {
        var d = new Date();
        return d.getFullYear() + '-' +
            String(d.getMonth() + 1).padStart(2, '0') + '-' +
            String(d.getDate()).padStart(2, '0');
    }

    function rowFor(id) {
        return tableBody.querySelector('[data-schedule-id="' + id + '"]');
    }

    function open(id) {
        editingId = id || null;
        clearErrors();
        el('hse-sched-form-title').textContent = id ? 'Edit schedule' : 'New schedule';
        el('hse-sched-save').textContent = id ? 'Save changes' : 'Save schedule';

        var retire = el('hse-sched-retire');
        var row = id ? rowFor(id) : null;
        retire.hidden = !id;
        if (id && row) {
            retire.textContent = row.classList.contains('is-off') ? 'Restore' : 'Retire';
        }

        if (id && forms[id]) {
            load(forms[id]);
        } else {
            load({ frequency: 'weekly', interval: 1, starts_on: today() });
        }
        form.hidden = false;
        refreshPreview();
        field('label').focus();
    }

    function close() {
        form.hidden = true;
        editingId = null;
        clearErrors();
    }

    // --- the preview ------------------------------------------------------

    function renderPreview(dates) {
        var slot = el('hse-sched-preview-dates');
        if (!dates || !dates.length) { slot.textContent = '—'; return; }
        slot.textContent = dates.map(function (iso) {
            var parts = iso.split('-');
            var d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
            return d.toLocaleDateString('en-GB',
                { day: '2-digit', month: 'short' });
        }).join(' · ');
    }

    function refreshPreview() {
        if (previewTimer) { window.clearTimeout(previewTimer); }
        previewTimer = window.setTimeout(function () {
            fetch('/hse/calendar/schedules/preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload())
            }).then(function (r) {
                return r.ok ? r.json() : { dates: [] };
            }).then(function (data) {
                renderPreview(data.dates);
            }).catch(function () {
                renderPreview([]);
            });
        }, 250);
    }

    // --- saving -----------------------------------------------------------

    function paint(row, schedule) {
        var cells = row.querySelectorAll('td');
        cells[0].innerHTML = '';
        var what = document.createElement('div');
        what.className = 'hse-sched-what';
        what.textContent = schedule.label;
        var reg = document.createElement('div');
        reg.className = 'hse-sched-reg';
        reg.textContent = schedule.register_label;
        cells[0].appendChild(what);
        cells[0].appendChild(reg);
        if (!schedule.active) {
            var tag = document.createElement('span');
            tag.className = 'hse-tag';
            tag.textContent = 'Retired';
            cells[0].appendChild(tag);
        }
        cells[1].textContent = schedule.applies_to;
        cells[2].textContent = schedule.cadence_short;
        cells[3].textContent = schedule.due.date_label || '—';
        if (schedule.due.label) {
            var badge = document.createElement('span');
            badge.className = 'hse-sched-badge' +
                (schedule.due.overdue_days ? ' is-overdue' : '');
            badge.textContent = schedule.due.label;
            cells[3].appendChild(document.createTextNode(' '));
            cells[3].appendChild(badge);
        }
        cells[4].textContent = schedule.last_done_label || '—';
        cells[5].textContent = schedule.owner || '—';
        row.classList.toggle('is-off', !schedule.active);
    }

    function save(event) {
        event.preventDefault();
        var button = el('hse-sched-save');
        button.disabled = true;
        var url = editingId
            ? '/hse/calendar/schedules/' + editingId
            : '/hse/calendar/schedules';

        fetch(url, {
            method: editingId ? 'PATCH' : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload())
        }).then(function (response) {
            return response.json().then(function (data) {
                return { ok: response.ok, data: data };
            });
        }).then(function (result) {
            button.disabled = false;
            if (!result.ok) { showErrors(result.data.errors); return; }
            // A new schedule changes the table's shape and the header count,
            // not just a row, so the page is re-fetched rather than
            // half-patched by hand.
            if (!editingId) { window.location.reload(); return; }
            forms[editingId] = result.data.form;
            var row = rowFor(editingId);
            if (row) { paint(row, result.data.schedule); }
            close();
        }).catch(function () {
            button.disabled = false;
        });
    }

    function retire() {
        if (!editingId) { return; }
        var row = rowFor(editingId);
        var reactivate = row && row.classList.contains('is-off');
        fetch('/hse/calendar/schedules/' + editingId, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ active: !!reactivate })
        }).then(function (r) { return r.ok ? r.json() : null; })
          .then(function (data) {
              if (!data) { return; }
              if (row) { paint(row, data.schedule); }
              close();
          });
    }

    // --- wiring -----------------------------------------------------------

    function init() {
        tableBody = el('hse-sched-rows');
        if (!tableBody) { return; }

        options = window.HSE_SCHED_OPTIONS ||
            { registers: [], frequencies: [], weekdays: [], monthly_frequencies: [] };
        people = window.HSE_SCHED_PEOPLE || [];
        assets = window.HSE_SCHED_ASSETS || [];
        forms = window.HSE_SCHED_FORMS || {};

        form = el('hse-sched-form');
        if (!form) { return; }   // read-only viewer: the table is the page

        assetsBox = el('hse-sched-assets');
        assetList = el('hse-sched-asset-list');
        assetsLabel = el('hse-sched-assets-label');
        freqBox = el('hse-sched-freq');

        // The whole row opens the panel — the wireframe has no action
        // column, and a Retire button on every row is a row of invitations
        // to break something.
        tableBody.addEventListener('click', function (event) {
            var row = event.target.closest('[data-schedule-id]');
            if (!row) { return; }
            open(parseInt(row.getAttribute('data-schedule-id'), 10));
        });

        fill(field('register'), options.registers.map(function (r) {
            return { value: r.key, label: r.label };
        }), 'Pick a register');
        fill(field('weekday'), options.weekdays, 'Same day as the start date');
        fill(field('owner_id'), people.map(function (p) {
            return { value: p.id, label: p.label };
        }), 'Nobody in particular');
        buildFrequency();

        freqBox.addEventListener('click', function (e) {
            var seg = e.target.closest('.hse-seg');
            if (!seg) { return; }
            setFrequency(seg.getAttribute('data-value'));
            refreshPreview();
        });

        field('register').addEventListener('change', function () { syncAssets(true); });
        ['interval', 'weekday', 'day_of_month', 'starts_on', 'ends_on'].forEach(function (name) {
            field(name).addEventListener('change', refreshPreview);
            field(name).addEventListener('input', refreshPreview);
        });

        form.addEventListener('submit', save);
        el('hse-sched-cancel').addEventListener('click', close);
        el('hse-sched-retire').addEventListener('click', retire);
        el('hse-sched-new').addEventListener('click', function () { open(null); });
    }

    init();
}());
