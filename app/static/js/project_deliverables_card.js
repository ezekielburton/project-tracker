window.ProjectDeliverablesCard = (function () {
    function init(rootEl, projectId, onChanged) {
        if (!rootEl) return null;
        var destroyed = false;
        var skipPickerHandle = null;

        function bindReadOnly() {
            wireDeliverablesRail(rootEl);
            wireFocusToggle(rootEl);
            wireSkipToPreproduction();

            var editBtn = rootEl.querySelector('#overlay-edit-deliverables-btn');
            if (editBtn) {
                editBtn.addEventListener('click', function () {
                    fetch(`/projects/${projectId}/overlay/deliverables/edit`)
                        .then(function (r) { return r.text(); })
                        .then(function (html) {
                            if (destroyed) return;
                            rootEl.innerHTML = html;
                            bindEdit();
                        });
                });
            }
        }

        // ── Skip to Pre-Production — select deliverables (or Select All in
        // the picker's own popover) and fast-forward them, bypassing
        // Submissions/Client Approval entirely. ──
        function wireSkipToPreproduction() {
            var btn = rootEl.querySelector('#overlay-skip-preprod-btn');
            var form = rootEl.querySelector('#overlay-skip-preprod-form');
            var confirmBtn = rootEl.querySelector('#overlay-skip-preprod-confirm');
            var cancelBtn = rootEl.querySelector('#overlay-skip-preprod-cancel');
            var pickerEl = rootEl.querySelector('#overlay-skip-preprod-picker');

            if (pickerEl) skipPickerHandle = window.DeliverablePicker.init(pickerEl);

            if (btn && form) {
                btn.addEventListener('click', function () {
                    btn.classList.add('is-hidden');
                    form.classList.remove('is-hidden');
                });
            }
            if (cancelBtn) {
                cancelBtn.addEventListener('click', function () {
                    form.classList.add('is-hidden');
                    if (btn) btn.classList.remove('is-hidden');
                    var errorEl = rootEl.querySelector('#overlay-skip-preprod-error');
                    if (errorEl) errorEl.classList.add('hidden');
                });
            }
            if (confirmBtn) {
                confirmBtn.addEventListener('click', function () {
                    var errorEl = rootEl.querySelector('#overlay-skip-preprod-error');
                    var deliverableIds = skipPickerHandle ? skipPickerHandle.getSelectedIds() : [];
                    if (!deliverableIds.length) {
                        if (errorEl) { errorEl.textContent = 'Select at least one deliverable.'; errorEl.classList.remove('hidden'); }
                        return;
                    }
                    confirmBtn.disabled = true;
                    if (errorEl) errorEl.classList.add('hidden');
                    fetch(`/projects/${projectId}/preproduction/skip`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ deliverable_ids: deliverableIds }),
                    })
                        .then(function (r) { return r.json(); })
                        .then(function (data) {
                            if (!data.success) {
                                confirmBtn.disabled = false;
                                if (errorEl) { errorEl.textContent = data.error || 'Could not skip to Pre-Production.'; errorEl.classList.remove('hidden'); }
                                return;
                            }
                            if (onChanged) onChanged();
                        })
                        .catch(function () {
                            confirmBtn.disabled = false;
                            if (errorEl) { errorEl.textContent = 'Something went wrong. Please try again.'; errorEl.classList.remove('hidden'); }
                        });
                });
            }
        }

        function backToReadOnly() {
            fetch(`/projects/${projectId}/overlay/deliverables`)
                .then(function (r) { return r.text(); })
                .then(function (html) {
                    if (destroyed) return;
                    rootEl.innerHTML = html;
                    bindReadOnly();
                    if (onChanged) onChanged();
                });
        }

        function wireDeliverablesRail(rootEl) {
            // Region is just an <optgroup> label inside the select now (see
            // _deliverables_ccm.html) — the panel switch only ever needs the
            // customer id, so one change listener replaces the old region-tab
            // + customer-pill click chain entirely.
            var scopeSelect = rootEl.querySelector('#overlay-deliverables-scope-select');
            if (!scopeSelect) return;
            scopeSelect.addEventListener('change', function () {
                activateCustomerPanel(rootEl, scopeSelect.value);
            });
        }

        function activateCustomerPanel(rootEl, customerId) {
            rootEl.querySelectorAll('.overlay-deliverables-panel').forEach(function (panel) {
                panel.classList.toggle('is-hidden', panel.dataset.customerPanel !== customerId);
            });
        }

        function wireFocusToggle(rootEl) {
            var toggle = rootEl.querySelector('#overlay-deliverables-focus-toggle');
            var body = rootEl.querySelector('#overlay-deliverables-body');
            if (!toggle || !body) return;
            toggle.querySelectorAll('.overlay-focus-toggle-btn').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    if (btn.classList.contains('active')) return;
                    toggle.querySelectorAll('.overlay-focus-toggle-btn').forEach(function (b) {
                        b.classList.toggle('active', b === btn);
                    });
                    body.classList.toggle('is-focused', btn.dataset.scope === 'focused');
                });
            });
        }

        function collectRows(listEl) {
            return Array.prototype.map.call(listEl.querySelectorAll('.overlay-deliverables-edit-row'), function (row) {
                var teams = Array.prototype.filter.call(
                    row.querySelectorAll('.overlay-deliverables-edit-toggle'),
                    function (btn) { return btn.classList.contains('is-active'); }
                ).map(function (btn) { return btn.dataset.team; });
                return {
                    id: row.dataset.deliverableId || null,
                    name: row.querySelector('.overlay-deliverables-edit-name').value.trim(),
                    design_deadline: row.querySelector('.overlay-deliverables-edit-date').value || null,
                    design_deadline_time: row.querySelector('.overlay-deliverables-edit-time').value || null,
                    teams: teams,
                    deleted: row.dataset.deleted === 'true',
                };
            });
        }

        function wireRow(row) {
            row.querySelectorAll('.overlay-deliverables-edit-toggle').forEach(function (btn) {
                btn.addEventListener('click', function () { btn.classList.toggle('is-active'); });
            });
            var deleteBtn = row.querySelector('.overlay-deliverables-edit-delete');
            if (deleteBtn) {
                deleteBtn.addEventListener('click', function () {
                    if (row.dataset.deliverableId) {
                        row.dataset.deleted = 'true';
                        row.style.display = 'none';
                    } else {
                        row.remove();
                    }
                });
            }
        }

        function bindEdit() {
            var listEl = rootEl.querySelector('#overlay-deliverables-edit-list');
            var template = rootEl.querySelector('#overlay-deliverable-row-template');
            var addBtn = rootEl.querySelector('#overlay-add-deliverable-btn');
            var applyAllBtn = rootEl.querySelector('#overlay-apply-deadline-all-btn');
            var saveBtn = rootEl.querySelector('#overlay-save-deliverables-btn');

            if (listEl) { listEl.querySelectorAll('.overlay-deliverables-edit-row').forEach(wireRow); }

            if (addBtn && template && listEl) {
                addBtn.addEventListener('click', function () {
                    var clone = template.content.cloneNode(true);
                    var row = clone.querySelector('.overlay-deliverables-edit-row');
                    listEl.appendChild(clone);
                    wireRow(row);
                    row.querySelector('.overlay-deliverables-edit-name').focus();
                });
            }

            if (applyAllBtn && listEl) {
                applyAllBtn.addEventListener('click', function () {
                    var rows = listEl.querySelectorAll('.overlay-deliverables-edit-row');
                    if (!rows.length) return;
                    var sourceDate = rows[0].querySelector('.overlay-deliverables-edit-date').value;
                    var sourceTime = rows[0].querySelector('.overlay-deliverables-edit-time').value;
                    Array.prototype.forEach.call(rows, function (row, i) {
                        if (i === 0) return;
                        row.querySelector('.overlay-deliverables-edit-date').value = sourceDate;
                        row.querySelector('.overlay-deliverables-edit-time').value = sourceTime;
                    });
                });
            }

            if (saveBtn && listEl) {
                saveBtn.addEventListener('click', function () {
                    var deliverables = collectRows(listEl);
                    saveBtn.disabled = true;
                    var originalText = saveBtn.textContent;
                    saveBtn.textContent = 'Saving…';
                    fetch(`/projects/${projectId}/overlay/deliverables/save`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ deliverables: deliverables }),
                    })
                        .then(function (r) { return r.json(); })
                        .then(function (data) {
                            if (!data.success) {
                                saveBtn.disabled = false;
                                saveBtn.textContent = originalText;
                                alert(data.error || 'Could not save deliverables.');
                                return;
                            }
                            backToReadOnly();
                        })
                        .catch(function () {
                            saveBtn.disabled = false;
                            saveBtn.textContent = originalText;
                            alert('Something went wrong.');
                        });
                });
            }
        }

        if (rootEl.querySelector('#overlay-save-deliverables-btn')) {
            bindEdit();
        } else {
            bindReadOnly();
        }

        return { destroy: function () { destroyed = true; if (skipPickerHandle) skipPickerHandle.destroy(); } };
    }
    return { init: init };
})();