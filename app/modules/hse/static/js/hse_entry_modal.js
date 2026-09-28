// HSE entry overlay: create/edit form, file uploads, and quick-add options.
//
// Markup is fetched on each open so dropdowns show current reference lists.
// It mounts on <body> so no ancestor becomes its containing block.
(function () {
    var MOUNT_ID = 'hse-modal-mount';

    function mount() {
        var el = document.getElementById(MOUNT_ID);
        if (!el) {
            el = document.createElement('div');
            el.id = MOUNT_ID;
            document.body.appendChild(el);
        }
        return el;
    }

    function close() {
        mount().innerHTML = '';
        document.body.classList.remove('hse-modal-open');
        // A save shifts computed columns and counts, so re-render the
        // current page from the server.
        if (window._hseTableStale) {
            window._hseTableStale = false;
            if (window.navigateTo) {
                window.navigateTo(window.location.pathname + window.location.search);
            } else {
                window.location.reload();
            }
        }
    }

    function fieldValue(group) {
        var input = group.querySelector('input, select, textarea');
        return input ? input.value : null;
    }

    // The field's own label, without the required-field asterisk.
    function fieldLabel(group) {
        var label = group.querySelector('label');
        return label ? label.firstChild.textContent.trim() : group.getAttribute('data-field');
    }

    // Marks invalid fields and focuses the first. Returns their labels.
    function showErrors(modal, errors) {
        var invalid = [];
        modal.querySelectorAll('.hse-field').forEach(function (group) {
            var slot = group.querySelector('.hse-error');
            var message = errors[group.getAttribute('data-field')];
            group.classList.toggle('has-error', Boolean(message));
            if (slot) {
                slot.textContent = message || '';
                slot.hidden = !message;
            }
            if (message) invalid.push(group);
        });
        if (invalid.length) {
            invalid[0].scrollIntoView({ block: 'center', behavior: 'smooth' });
            var control = invalid[0].querySelector(
                'select, textarea, .hse-seg, input:not([type="hidden"])');
            if (control) control.focus({ preventScroll: true });
        }
        return invalid.map(fieldLabel);
    }

    // Clears a field's error state once the user edits it.
    function clearError(group) {
        if (!group || !group.classList.contains('has-error')) return;
        group.classList.remove('has-error');
        var slot = group.querySelector('.hse-error');
        if (slot) {
            slot.textContent = '';
            slot.hidden = true;
        }
    }

    function errorNote(names) {
        if (!names.length) return 'Check the form and try again.';
        if (names.length === 1) return 'Fix this field: ' + names[0];
        return names.length + ' fields need fixing: ' + names.join(', ');
    }

    function collect(modal) {
        var payload = {};
        modal.querySelectorAll('.hse-field').forEach(function (group) {
            payload[group.getAttribute('data-field')] = fieldValue(group);
        });
        // Set when opened from a planned calendar occurrence. Sent as a pair
        // or not at all; the server verifies the occurrence.
        var scheduleId = modal.getAttribute('data-schedule-id');
        var occurrence = modal.getAttribute('data-occurrence-date');
        if (scheduleId && occurrence) {
            payload.schedule_id = parseInt(scheduleId, 10);
            payload.occurrence_date = occurrence;
        }
        return payload;
    }

    function save(modal) {
        var button = modal.querySelector('#hse-modal-save');
        var note = modal.querySelector('#hse-modal-note');
        button.disabled = true;
        note.classList.remove('is-error');
        note.textContent = 'Saving…';

        fetch(modal.getAttribute('data-save-url'), {
            method: modal.getAttribute('data-method'),
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(collect(modal))
        }).then(function (res) {
            return res.json().then(function (body) { return { ok: res.ok, body: body }; });
        }).then(function (result) {
            if (result.ok) {
                window._hseTableStale = true;
                if (modal.getAttribute('data-method') === 'POST' && result.body.id) {
                    // Reopen the new entry in edit mode so files can be attached.
                    open('/hse/entry/' + result.body.id + '/form');
                } else {
                    close();
                }
                return;
            }
            button.disabled = false;
            note.classList.add('is-error');
            if (result.body && result.body.errors) {
                note.textContent = errorNote(showErrors(modal, result.body.errors));
            } else {
                note.textContent = (result.body && result.body.error) || 'Could not save.';
            }
        }).catch(function () {
            button.disabled = false;
            note.classList.add('is-error');
            note.textContent = 'Could not reach the server.';
        });
    }

    function note(text) {
        var slot = document.getElementById('hse-file-note');
        if (slot) slot.textContent = text;
    }

    function uploadFile(input) {
        var panel = document.getElementById('hse-files');
        if (!panel || !input.files.length) return;
        var body = new FormData();
        body.append('file', input.files[0]);
        note('Uploading…');

        fetch(panel.getAttribute('data-upload-url'), { method: 'POST', body: body })
            .then(function (res) {
                return res.json().then(function (b) { return { ok: res.ok, body: b }; });
            })
            .then(function (result) {
                input.value = '';
                if (!result.ok) {
                    note(result.body.error || 'Upload failed.');
                    return;
                }
                note('Stored on the NAS under /HSE.');
                window._hseTableStale = true;
                // Reopen so the file list matches the server.
                var modal = document.getElementById('hse-entry-modal');
                open('/hse/entry/' + modal.getAttribute('data-entry-id') + '/form');
            })
            .catch(function () {
                input.value = '';
                note('Could not reach the server.');
            });
    }

    function removeFile(button) {
        var row = button.closest('.hse-file');
        note('Removing…');
        fetch(button.getAttribute('data-remove-url'), { method: 'DELETE' })
            .then(function (res) {
                if (!res.ok) throw new Error('delete failed');
                row.remove();
                note('Removed.');
                window._hseTableStale = true;
            })
            .catch(function () { note('Could not remove that file.'); });
    }

    // Adds a missing option from inside the form and selects it. The server
    // reuses or revives a matching name, so duplicates cannot appear.
    function quickAdd(panel) {
        var input = panel.querySelector('.hse-quick-input');
        var label = input.value.trim();
        if (!label) return;

        var modal = panel.closest('#hse-entry-modal');
        var group = panel.closest('.hse-field');
        var select = group.querySelector('select');
        var note = panel.querySelector('.hse-quick-save');
        note.disabled = true;

        fetch('/hse/lists/reference/quick-add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ kind: panel.getAttribute('data-kind'), label: label })
        }).then(function (res) {
            return res.json().then(function (b) { return { ok: res.ok, body: b }; });
        }).then(function (result) {
            note.disabled = false;
            if (!result.ok) {
                var slot = group.querySelector('.hse-error');
                slot.textContent = result.body.error || 'Could not add that.';
                slot.hidden = false;
                return;
            }
            var row = result.body.row;
            // Column-backed fields store the id; JSONB fields store the label
            // (same rule as the form and table).
            var value = panel.getAttribute('data-stores') === 'label' ? row.label : String(row.id);

            if (select) {
                if (!select.querySelector('option[value="' + value + '"]')) {
                    var option = document.createElement('option');
                    option.value = value;
                    option.textContent = row.label;
                    select.appendChild(option);
                }
                select.value = value;
            } else {
                // An empty list renders as a locked box; swap in a real select.
                var box = group.querySelector('.hse-empty-choice');
                var hidden = group.querySelector('input[type="hidden"]');
                if (box && hidden) {
                    var built = document.createElement('select');
                    built.className = 'form-input';
                    built.id = hidden.id;
                    built.innerHTML = '<option value="">—</option>';
                    var only = document.createElement('option');
                    only.value = value;
                    only.textContent = row.label;
                    built.appendChild(only);
                    built.value = value;
                    hidden.remove();
                    box.replaceWith(built);
                }
            }

            input.value = '';
            panel.hidden = true;
            clearError(group);
            releaseSaveIfNothingBlocking(modal);
        }).catch(function () {
            note.disabled = false;
        });
    }

    // Shows the picked machine's serial, carried on its <option>.
    function showSerial(select) {
        var line = select.closest('.hse-field').querySelector('[data-serial-line]');
        if (!line) return;
        var option = select.options[select.selectedIndex];
        var picked = Boolean(option && option.value);
        var serial = picked ? option.getAttribute('data-serial') : '';
        line.hidden = !picked;
        line.textContent = !picked ? '' : (serial ? 'Serial no. ' + serial : 'No serial on file');
    }

    // Picking the closing status fills an empty closed date with today; any
    // other status clears it, as the server does on save.
    function syncClosedDate(select) {
        var closedStatus = select.getAttribute('data-closed-status');
        var modal = select.closest('#hse-entry-modal');
        var input = closedStatus && modal.querySelector('#hse-f-' + select.getAttribute('data-closed-field'));
        if (!input) return;
        if (select.value === closedStatus && !input.value) {
            input.value = select.getAttribute('data-today');
            clearError(input.closest('.hse-field'));
        } else if (select.value !== closedStatus) {
            input.value = '';
        }
    }

    // Save stays disabled while any required list is empty.
    function releaseSaveIfNothingBlocking(modal) {
        if (modal.querySelector('.hse-empty-choice')) return;
        var blocked = modal.querySelector('.hse-modal-blocked');
        if (blocked) blocked.remove();
        var save = modal.querySelector('#hse-modal-save');
        if (save) save.disabled = false;
    }

    function open(url) {
        fetch(url, { headers: { 'X-Requested-With': 'fetch' } })
            .then(function (res) {
                if (!res.ok) throw new Error('load failed');
                return res.text();
            })
            .then(function (html) {
                mount().innerHTML = html;
                document.body.classList.add('hse-modal-open');
            })
            .catch(function () {
                window.alert('Could not open the form.');
            });
    }

    // Used by hse_calendar.js, which builds its own form URL (with the open
    // day) and cannot use the [data-hse-form-url] delegation.
    window.hseOpenEntryForm = open;

    // Document-delegated so fetched markup needs no wiring; guarded so SPA
    // re-runs never stack listeners.
    if (window._hseEntryModalWired) return;
    window._hseEntryModalWired = true;

    document.addEventListener('click', function (e) {
        var opener = e.target.closest('[data-hse-form-url]');
        if (opener) {
            e.preventDefault();
            open(opener.getAttribute('data-hse-form-url'));
            return;
        }

        var modal = document.getElementById('hse-entry-modal');
        if (!modal) return;

        if (e.target.closest('#hse-modal-close, #hse-modal-cancel')) {
            close();
            return;
        }
        if (e.target === modal) {          // click on the backdrop itself
            close();
            return;
        }
        var seg = e.target.closest('.hse-seg');
        if (seg) {
            var group = seg.closest('.hse-field');
            group.querySelectorAll('.hse-seg').forEach(function (b) {
                b.classList.toggle('is-selected', b === seg);
            });
            group.querySelector('input[type="hidden"]').value = seg.getAttribute('data-value');
            clearError(group);
            return;
        }
        if (e.target.closest('#hse-modal-save')) {
            save(modal);
            return;
        }

        var preview = e.target.closest('.hse-file-preview');
        if (preview && window.openFilePreview) {
            // Shared file-preview modal from base.html.
            window.openFilePreview(preview.getAttribute('data-preview-url'),
                                   preview.getAttribute('data-download-url'),
                                   preview.getAttribute('data-file-name'),
                                   preview.getAttribute('data-file-type'));
            return;
        }

        var remove = e.target.closest('.hse-file-remove');
        if (remove) {
            removeFile(remove);
            return;
        }

        var quickLink = e.target.closest('.hse-quick-link');
        if (quickLink) {
            var panel = modal.querySelector(
                '.hse-quick-add[data-quick-for="' + quickLink.getAttribute('data-quick-add') + '"]');
            panel.hidden = !panel.hidden;
            if (!panel.hidden) panel.querySelector('.hse-quick-input').focus();
            return;
        }

        if (e.target.closest('.hse-quick-save')) {
            quickAdd(e.target.closest('.hse-quick-add'));
        }
    });

    document.addEventListener('change', function (e) {
        if (e.target.id === 'hse-file-input') uploadFile(e.target);
        if (e.target.tagName === 'SELECT' && e.target.closest('#hse-entry-modal')) {
            showSerial(e.target);
            syncClosedDate(e.target);
        }
    });

    // Typing or picking in an invalid field clears its error.
    ['input', 'change'].forEach(function (type) {
        document.addEventListener(type, function (e) {
            var modal = document.getElementById('hse-entry-modal');
            if (modal && modal.contains(e.target)) clearError(e.target.closest('.hse-field'));
        });
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && document.getElementById('hse-entry-modal')) close();
    });
})();
