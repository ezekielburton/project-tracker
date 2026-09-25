// HSE — the entry overlay.
//
// The modal markup is fetched per open rather than rendered into the page,
// so its dropdowns always show the reference lists as they are now. It is
// appended to <body>, not into the table, so nothing above it can become a
// containing block for it.
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
        // Filing or editing moves the computed columns and the chip counts,
        // so the table is re-rendered from the server rather than patched.
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

    function showErrors(modal, errors) {
        modal.querySelectorAll('.hse-field').forEach(function (group) {
            var slot = group.querySelector('.hse-error');
            var message = errors[group.getAttribute('data-field')];
            group.classList.toggle('has-error', Boolean(message));
            if (slot) {
                slot.textContent = message || '';
                slot.hidden = !message;
            }
        });
    }

    function collect(modal) {
        var payload = {};
        modal.querySelectorAll('.hse-field').forEach(function (group) {
            payload[group.getAttribute('data-field')] = fieldValue(group);
        });
        // Opened from a planned occurrence on the calendar. Sent as a pair
        // or not at all; the server verifies the occurrence is real before
        // stamping it onto the entry.
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
                    // Straight into edit mode on the new entry, so attaching
                    // the report is the next thing rather than a second trip.
                    open('/hse/entry/' + result.body.id + '/form');
                } else {
                    close();
                }
                return;
            }
            button.disabled = false;
            if (result.body && result.body.errors) {
                showErrors(modal, result.body.errors);
                note.textContent = 'Check the highlighted fields.';
            } else {
                note.textContent = (result.body && result.body.error) || 'Could not save.';
            }
        }).catch(function () {
            button.disabled = false;
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
                // Reopen so the list matches the server rather than a guess.
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

    // Adds a missing option without leaving the form, then selects it. The
    // server reuses an existing name and revives a deactivated one, so
    // typing something that already exists cannot create a duplicate the
    // dropdown then shows twice.
    function quickAdd(panel) {
        var input = panel.querySelector('.hse-quick-input');
        var label = input.value.trim();
        if (!label) return;

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
            // A field backed by a column stores the id; one that falls into
            // JSONB stores the label. Same rule the form and table follow.
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
                // The list was empty, so this field rendered as a locked box
                // rather than a dropdown. Turn it into a real select now that
                // it has something in it.
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
            releaseSaveIfNothingBlocking(modal);
        }).catch(function () {
            note.disabled = false;
        });
    }

    // Save is disabled while a required list is empty. Once the last one has
    // something in it, filing is possible again.
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

    // The one seam other HSE pages open the form through. The calendar's
    // register picker builds its own URL (it stamps on the open day), so it
    // cannot go through the [data-hse-form-url] delegation like everything
    // else. Exported rather than duplicated: there must be one place that
    // knows how this overlay is mounted.
    window.hseOpenEntryForm = open;

    // One document-level listener for everything the overlay does, so the
    // fetched markup needs no wiring of its own.
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
            return;
        }
        if (e.target.closest('#hse-modal-save')) {
            save(modal);
            return;
        }

        var preview = e.target.closest('.hse-file-preview');
        if (preview && window.openFilePreview) {
            // The shared modal from base.html — the same one the project
            // reference files open. Nothing to load, nothing to duplicate.
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
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && document.getElementById('hse-entry-modal')) close();
    });
})();
