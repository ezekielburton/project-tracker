window.ProjectDeliverablesCard = (function () {
    function init(rootEl, projectId, onChanged) {
        if (!rootEl) return null;
        var destroyed = false;
        var skipPickerHandle = null;
        var assignPickerHandles = [];
        var statusPickerHandles = [];

        function bindReadOnly() {
            wireDeliverablesRail(rootEl);
            wireFocusToggle(rootEl);
            wireSkipToPreproduction();
            wireSelfAssignTags();
            assignPickerHandles = wireManageAssignPickers();
            statusPickerHandles = wireStatusOverridePickers();

            // Flags (task #42) — deliverable-scoped flag sections (one per
            // C&CM customer panel, one for Standard's flat list) plus every
            // row's ⚑ trigger. Reuses the same onChanged the rest of this
            // card uses (loadSubTabContent re-fetch via project_list.js) so
            // a flag action refreshes the whole tab exactly like every
            // other action here. Edit mode has no flag UI, so this only
            // runs here, not in bindEdit().
            if (window.ProjectFlags) window.ProjectFlags.init(rootEl, projectId, onChanged);

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

            // Button always renders (see _deliverables_standard.html /
            // _deliverables_ccm.html) so it doesn't just vanish unexplained
            // — data-skippable-count is 0 whenever the picker form (and its
            // deliverable list) weren't rendered at all, so a toast explains
            // why instead of nothing happening.
            if (btn) {
                btn.addEventListener('click', function () {
                    if (btn.dataset.skippableCount === '0') {
                        showToast('Add at least one deliverable before skipping to Pre-Production.', 'error');
                        return;
                    }
                    if (!form) return;
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

        // ── Team-tag assignment (22 Aug 2026) — the Deliverables roster's
        // Team column now doubles as the assign control. Two independent
        // wire-ups, matching the two modes deliverable_assign_tag() renders
        // (_shared_macros.html): a plain designer's one-click self-toggle
        // (no popover), and everyone else's avatar-picker popover. ──
        function wireSelfAssignTags() {
            rootEl.querySelectorAll('.deliverable-assign-tag[data-mode="self"]').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    btn.disabled = true;
                    fetch(`/projects/${projectId}/overlay/deliverables/assign`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            deliverable_id: btn.dataset.deliverableId,
                            team: btn.dataset.team,
                            self_toggle: true,
                        }),
                    })
                        .then(function (r) { return r.json(); })
                        .then(function (data) {
                            if (!data.success) {
                                btn.disabled = false;
                                showToast(data.error || 'Could not update your assignment.', 'error');
                                return;
                            }
                            if (onChanged) onChanged();
                        })
                        .catch(function () {
                            btn.disabled = false;
                            showToast('Something went wrong. Please try again.', 'error');
                        });
                });
            });
        }

        function wireManageAssignPickers() {
            var handles = [];
            rootEl.querySelectorAll('.deliverable-assign-tag[data-team]').forEach(function (pickerEl) {
                // Only the manage-mode wrapper (a real .avatar-picker div)
                // gets AvatarPicker.init — the self-mode tag is a bare
                // <button>, no popover, handled entirely above.
                if (!pickerEl.classList.contains('avatar-picker')) return;
                var handle = window.AvatarPicker.init(pickerEl, function (userId, el) {
                    fetch(`/projects/${projectId}/overlay/deliverables/assign`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            deliverable_id: el.dataset.deliverableId,
                            team: el.dataset.team,
                            designer_id: userId || null,
                        }),
                    })
                        .then(function (r) { return r.json(); })
                        .then(function (data) {
                            if (!data.success) {
                                showToast(data.error || 'Could not update this assignment.', 'error');
                                return;
                            }
                            if (onChanged) onChanged();
                        })
                        .catch(function () {
                            showToast('Something went wrong. Please try again.', 'error');
                        });
                });
                if (handle) handles.push(handle);
            });
            return handles;
        }

        // Admin status override (22 Aug 2026, per Ezekiel) — only rendered
        // at all when can_override_status (see _deliverables_standard.html
        // / _deliverables_ccm.html), one .status-picker per deliverable
        // row. onChanged() re-fetches the whole tab on success, same as
        // every other mutation in this card.
        function wireStatusOverridePickers() {
            var handles = [];
            rootEl.querySelectorAll('.status-picker').forEach(function (pickerEl) {
                var handle = window.StatusPicker.init(pickerEl, function (statusValue, el) {
                    fetch(el.dataset.targetUrl, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ status: statusValue }),
                    })
                        .then(function (r) { return r.json(); })
                        .then(function (data) {
                            if (!data.success) {
                                showToast(data.error || 'Could not update this status.', 'error');
                                return;
                            }
                            if (onChanged) onChanged();
                        })
                        .catch(function () {
                            showToast('Something went wrong. Please try again.', 'error');
                        });
                });
                if (handle) handles.push(handle);
            });
            return handles;
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
            // Generic [data-customer-panel] selector rather than
            // .overlay-deliverables-panel specifically — the per-customer
            // flag panel (see _deliverables_ccm.html) sits outside the
            // Deliverables card entirely now but still needs to toggle in
            // lockstep with the same customer switch.
            rootEl.querySelectorAll('[data-customer-panel]').forEach(function (panel) {
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

        // Standard has one edit list; C&CM has one per customer panel (only
        // one visible at a time — see _deliverables_ccm_edit.html). Save
        // always gathers every list so switching the customer picker never
        // drops unsaved edits in a panel you're not currently looking at.
        function collectAllRows(rootEl) {
            var out = [];
            rootEl.querySelectorAll('.overlay-deliverables-edit-list').forEach(function (listEl) {
                var customerId = listEl.dataset.customerId || null;
                collectRows(listEl).forEach(function (row) {
                    row.project_customer_id = customerId;
                    out.push(row);
                });
            });
            return out;
        }

        // Every row here is a free-text name rather than a picked-from-
        // catalogue type, so nothing stops two rows under the same customer
        // (or both un-scoped, on Standard) ending up with the identical
        // name by accident — catches that before Save rather than after,
        // returning the first duplicate name found, or null if none.
        function findDuplicateName(deliverables) {
            var seen = {};
            for (var i = 0; i < deliverables.length; i++) {
                var row = deliverables[i];
                if (row.deleted || !row.name) continue;
                var key = (row.project_customer_id || '') + '::' + row.name.toLowerCase();
                if (seen[key]) return row.name;
                seen[key] = true;
            }
            return null;
        }

        // The list Add Deliverable / Apply Deadline to All should target:
        // the visible customer panel's list on C&CM, or the only list on
        // Standard (no panels there at all).
        function activeEditList(rootEl) {
            var visiblePanel = rootEl.querySelector('.overlay-deliverables-edit-panel:not(.is-hidden)');
            if (visiblePanel) return visiblePanel.querySelector('.overlay-deliverables-edit-list');
            return rootEl.querySelector('.overlay-deliverables-edit-list');
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
            var template = rootEl.querySelector('#overlay-deliverable-row-template');
            var addBtn = rootEl.querySelector('#overlay-add-deliverable-btn');
            var applyAllBtn = rootEl.querySelector('#overlay-apply-deadline-all-btn');
            var saveBtn = rootEl.querySelector('#overlay-save-deliverables-btn');
            var scopeSelect = rootEl.querySelector('#overlay-deliverables-edit-scope-select');

            rootEl.querySelectorAll('.overlay-deliverables-edit-row').forEach(wireRow);

            // C&CM only — Standard has no panels/select, so this is a no-op there.
            if (scopeSelect) {
                scopeSelect.addEventListener('change', function () {
                    rootEl.querySelectorAll('.overlay-deliverables-edit-panel').forEach(function (panel) {
                        panel.classList.toggle('is-hidden', panel.dataset.customerPanel !== scopeSelect.value);
                    });
                });
            }

            if (addBtn && template) {
                addBtn.addEventListener('click', function () {
                    var listEl = activeEditList(rootEl);
                    if (!listEl) return;
                    var clone = template.content.cloneNode(true);
                    var row = clone.querySelector('.overlay-deliverables-edit-row');
                    listEl.appendChild(clone);
                    wireRow(row);
                    row.querySelector('.overlay-deliverables-edit-name').focus();
                });
            }

            if (applyAllBtn) {
                applyAllBtn.addEventListener('click', function () {
                    // Scoped to the visible customer panel on C&CM — "all"
                    // means every row you're currently looking at, not
                    // every deliverable across every customer.
                    var listEl = activeEditList(rootEl);
                    if (!listEl) return;
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

            if (saveBtn) {
                saveBtn.addEventListener('click', function () {
                    var deliverables = collectAllRows(rootEl);
                    var duplicateName = findDuplicateName(deliverables);
                    if (duplicateName) {
                        showToast('"' + duplicateName + '" is on this list more than once — give each deliverable a unique name before saving.', 'error');
                        return;
                    }
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

        return {
            destroy: function () {
                destroyed = true;
                if (skipPickerHandle) skipPickerHandle.destroy();
                assignPickerHandles.forEach(function (h) { h.destroy(); });
                statusPickerHandles.forEach(function (h) { h.destroy(); });
            }
        };
    }
    return { init: init };
})();