window.ProjectDeliverablesCard = (function () {
    function init(rootEl, projectId, onChanged) {
        if (!rootEl) return null;
        var destroyed = false;
        var skipPickerHandle = null;
        var assignPickerHandles = [];
        var statusPickerHandles = [];
        // Apply to Multiple reads committed deliverables server-side, so it
        // needs a clean Save first. Any edit-mode row change sets this;
        // bindEdit() and a successful Save clear it.
        var hasUnsavedChanges = false;
        function markUnsaved() { hasUnsavedChanges = true; }

        // Each picker adds document-level listeners, so the old handles must
        // be destroyed before a re-render replaces them or the listeners pile up.
        function destroyPickers() {
            if (skipPickerHandle) { skipPickerHandle.destroy(); skipPickerHandle = null; }
            assignPickerHandles.forEach(function (h) { h.destroy(); });
            statusPickerHandles.forEach(function (h) { h.destroy(); });
            assignPickerHandles = [];
            statusPickerHandles = [];
        }

        function bindReadOnly() {
            destroyPickers();
            wireDeliverablesRail(rootEl);
            wireFocusToggle(rootEl);
            wireSkipToPreproduction();
            wireSelfAssignTags();
            assignPickerHandles = wireManageAssignPickers();
            statusPickerHandles = wireStatusOverridePickers();

            // Deliverable-scoped flag sections plus each row's ⚑ trigger.
            // Read-only mode only; edit mode has no flag UI.
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

        // ── Skip to Pre-Production: fast-forward the picked deliverables
        // past Submissions and Client Approval. ──
        function wireSkipToPreproduction() {
            var btn = rootEl.querySelector('#overlay-skip-preprod-btn');
            var form = rootEl.querySelector('#overlay-skip-preprod-form');
            var confirmBtn = rootEl.querySelector('#overlay-skip-preprod-confirm');
            var cancelBtn = rootEl.querySelector('#overlay-skip-preprod-cancel');
            var pickerEl = rootEl.querySelector('#overlay-skip-preprod-picker');

            if (pickerEl) skipPickerHandle = window.DeliverablePicker.init(pickerEl);

            // The button always renders; data-skippable-count is 0 when the
            // picker form isn't rendered, so a toast explains why.
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
                    if (form) form.classList.add('is-hidden');
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

        // ── Team-tag assignment. Matches the two modes of
        // deliverable_assign_tag() in _shared_macros.html: a designer's
        // one-click self-toggle, and everyone else's avatar-picker popover. ──
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
                // Self-mode tags are bare buttons with no popover; only
                // manage-mode .avatar-picker wrappers get a picker.
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

        // Admin status override: one .status-picker per row, rendered only
        // when can_override_status.
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
            // C&CM only. Regions are <optgroup>s; the value is the customer id.
            var scopeSelect = rootEl.querySelector('#overlay-deliverables-scope-select');
            if (!scopeSelect) return;
            scopeSelect.addEventListener('change', function () {
                activateCustomerPanel(rootEl, scopeSelect.value);
            });
        }

        function activateCustomerPanel(rootEl, customerId) {
            // Any [data-customer-panel]: the per-customer flag panels sit
            // outside the Deliverables card but switch with it.
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
                var out = {
                    id: row.dataset.deliverableId || null,
                    design_deadline: row.querySelector('.overlay-deliverables-edit-date').value || null,
                    design_deadline_time: row.querySelector('.overlay-deliverables-edit-time').value || null,
                    teams: teams,
                    deleted: row.dataset.deleted === 'true',
                };

                // C&CM rows have a catalog <select>; Standard rows have a
                // plain name <input>. Both go through one save route.
                var typeSelect = row.querySelector('.overlay-deliverables-edit-type-select');
                if (typeSelect) {
                    if (typeSelect.value === '__new__') {
                        var newNameInput = row.querySelector('.overlay-deliverables-edit-new-name');
                        var newName = newNameInput ? newNameInput.value.trim() : '';
                        out.new_type_name = newName;
                        out.name = newName;
                    } else if (typeSelect.value === '__legacy__' || !typeSelect.value) {
                        var legacyOpt = typeSelect.options[typeSelect.selectedIndex];
                        out.name = (legacyOpt && legacyOpt.dataset.name) || '';
                    } else {
                        out.deliverable_type_id = typeSelect.value;
                        var pickedOpt = typeSelect.options[typeSelect.selectedIndex];
                        out.name = (pickedOpt && pickedOpt.dataset.name) || '';
                    }
                } else {
                    out.name = row.querySelector('.overlay-deliverables-edit-name').value.trim();
                }
                return out;
            });
        }

        // Standard has one edit list; C&CM has one per customer panel. Save
        // gathers every list, including hidden panels, so no edits are lost.
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

        // Returns the first name used twice within one customer (or twice on
        // Standard), case-insensitive, or null. Deleted rows are ignored.
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

        // Target list for Add Deliverable / Apply Deadline to All: the
        // visible panel's list on C&CM, the only list on Standard.
        function activeEditList(rootEl) {
            var visiblePanel = rootEl.querySelector('.overlay-deliverables-edit-panel:not(.is-hidden)');
            if (visiblePanel) return visiblePanel.querySelector('.overlay-deliverables-edit-list');
            return rootEl.querySelector('.overlay-deliverables-edit-list');
        }

        function wireRow(row) {
            row.querySelectorAll('.overlay-deliverables-edit-toggle').forEach(function (btn) {
                btn.addEventListener('click', function () { btn.classList.toggle('is-active'); markUnsaved(); });
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
                    markUnsaved();
                });
            }
            // C&CM only: picking "+ Add new deliverable…" reveals the
            // free-text name field.
            var typeSelect = row.querySelector('.overlay-deliverables-edit-type-select');
            var newNameInput = row.querySelector('.overlay-deliverables-edit-new-name');
            if (typeSelect && newNameInput) {
                typeSelect.addEventListener('change', function () {
                    var isNew = typeSelect.value === '__new__';
                    newNameInput.classList.toggle('is-hidden', !isNew);
                    if (isNew) newNameInput.focus();
                });
            }
            row.querySelectorAll('input, select').forEach(function (el) {
                el.addEventListener('input', markUnsaved);
                el.addEventListener('change', markUnsaved);
            });
        }

        function bindEdit() {
            // Edit mode has no pickers; drop the read-only ones it replaced.
            destroyPickers();
            // A fresh edit render always reflects committed state.
            hasUnsavedChanges = false;
            // Standard has one row template; C&CM has one per customer
            // (id suffix) so a new row offers that customer's catalog.
            var template = rootEl.querySelector('#overlay-deliverable-row-template');
            var addBtn = rootEl.querySelector('#overlay-add-deliverable-btn');
            var applyAllBtn = rootEl.querySelector('#overlay-apply-deadline-all-btn');
            var saveBtn = rootEl.querySelector('#overlay-save-deliverables-btn');
            var scopeSelect = rootEl.querySelector('#overlay-deliverables-edit-scope-select');

            function addTemplateFor(listEl) {
                if (template) return template;
                var panel = listEl.closest('[data-customer-panel]');
                return panel ? rootEl.querySelector('#overlay-deliverable-row-template-' + panel.dataset.customerPanel) : null;
            }

            rootEl.querySelectorAll('.overlay-deliverables-edit-row').forEach(wireRow);

            // C&CM only.
            if (scopeSelect) {
                scopeSelect.addEventListener('change', function () {
                    rootEl.querySelectorAll('.overlay-deliverables-edit-panel').forEach(function (panel) {
                        panel.classList.toggle('is-hidden', panel.dataset.customerPanel !== scopeSelect.value);
                    });
                });
            }

            if (addBtn) {
                addBtn.addEventListener('click', function () {
                    var listEl = activeEditList(rootEl);
                    if (!listEl) return;
                    var rowTemplate = addTemplateFor(listEl);
                    if (!rowTemplate) return;
                    var clone = rowTemplate.content.cloneNode(true);
                    var row = clone.querySelector('.overlay-deliverables-edit-row');
                    listEl.appendChild(clone);
                    wireRow(row);
                    markUnsaved();
                    var focusTarget = row.querySelector('.overlay-deliverables-edit-type-select') || row.querySelector('.overlay-deliverables-edit-name');
                    if (focusTarget) focusTarget.focus();
                });
            }

            if (applyAllBtn) {
                applyAllBtn.addEventListener('click', function () {
                    // On C&CM, "all" means the visible customer's rows only.
                    var listEl = activeEditList(rootEl);
                    if (!listEl) return;
                    var rows = listEl.querySelectorAll('.overlay-deliverables-edit-row');
                    if (!rows.length) return;
                    // Source is the first row with a date, so an undated
                    // row can't blank the others.
                    var sourceRow = null;
                    for (var i = 0; i < rows.length; i++) {
                        if (rows[i].querySelector('.overlay-deliverables-edit-date').value) {
                            sourceRow = rows[i];
                            break;
                        }
                    }
                    if (!sourceRow) {
                        showToast('Set a deadline on at least one row before using Apply Deadline to All.', 'error');
                        return;
                    }
                    var sourceDate = sourceRow.querySelector('.overlay-deliverables-edit-date').value;
                    var sourceTime = sourceRow.querySelector('.overlay-deliverables-edit-time').value;
                    Array.prototype.forEach.call(rows, function (row) {
                        if (row === sourceRow) return;
                        row.querySelector('.overlay-deliverables-edit-date').value = sourceDate;
                        row.querySelector('.overlay-deliverables-edit-time').value = sourceTime;
                    });
                    markUnsaved();
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
                            hasUnsavedChanges = false;
                            backToReadOnly();
                        })
                        .catch(function () {
                            saveBtn.disabled = false;
                            saveBtn.textContent = originalText;
                            alert('Something went wrong.');
                        });
                });
            }

            wireApplyToMultiple();
        }

        // ── Apply to Multiple: copy the visible customer's saved
        // deliverables to other customers. The modal renders only on C&CM
        // with 2+ customers. Step 1 picks targets and POSTs /preview (no
        // writes); step 2 sets one deadline per target, ticks missing
        // catalog items, and POSTs /confirm. Needs a clean Save first. ──
        function wireApplyToMultiple() {
            var modal = rootEl.querySelector('#overlay-apply-multiple-modal');
            if (!modal) return;

            var openBtn = rootEl.querySelector('#overlay-apply-multiple-btn');
            var stepSelect = modal.querySelector('#overlay-apply-multiple-step-select');
            var stepReview = modal.querySelector('#overlay-apply-multiple-step-review');
            var sourceLabel = modal.querySelector('#overlay-apply-multiple-source-label');
            var selectError = modal.querySelector('#overlay-apply-multiple-select-error');
            var reviewError = modal.querySelector('#overlay-apply-multiple-review-error');
            var summaryLine = modal.querySelector('#overlay-apply-multiple-summary-line');
            var targetsContainer = modal.querySelector('#overlay-apply-multiple-targets');
            var continueBtn = modal.querySelector('#overlay-apply-multiple-continue');
            var confirmBtn = modal.querySelector('#overlay-apply-multiple-confirm');
            var cancelBtn = modal.querySelector('#overlay-apply-multiple-cancel');
            var backBtn = modal.querySelector('#overlay-apply-multiple-back');
            var timeTemplate = rootEl.querySelector('#overlay-apply-multiple-time-options-template');
            var sourceCustomerId = null;

            function activeSourceCustomerId() {
                var visiblePanel = rootEl.querySelector('.overlay-deliverables-edit-panel:not(.is-hidden)');
                return visiblePanel ? visiblePanel.dataset.customerPanel : null;
            }

            function openModal() {
                if (hasUnsavedChanges) {
                    showToast('Save your changes before using Apply to Multiple.', 'error');
                    return;
                }
                sourceCustomerId = activeSourceCustomerId();
                if (!sourceCustomerId) return;
                var sourcePanel = rootEl.querySelector('.overlay-deliverables-edit-panel[data-customer-panel="' + sourceCustomerId + '"]');
                // Soft-deleted rows are marked by dataset.deleted, same as
                // collectRows() uses.
                var visibleRows = sourcePanel ? Array.prototype.filter.call(
                    sourcePanel.querySelectorAll('.overlay-deliverables-edit-row[data-deliverable-id]'),
                    function (row) { return row.dataset.deleted !== 'true'; }
                ) : [];
                if (!visibleRows.length) {
                    showToast('This customer has no saved deliverables to duplicate.', 'error');
                    return;
                }
                var scopeSelectEl = rootEl.querySelector('#overlay-deliverables-edit-scope-select');
                var sourceName = scopeSelectEl ? scopeSelectEl.options[scopeSelectEl.selectedIndex].textContent : '';
                sourceLabel.textContent = 'Apply ' + sourceName + '’s deliverables to:';

                modal.querySelectorAll('.overlay-apply-multiple-customer-tag').forEach(function (tagEl) {
                    tagEl.classList.remove('is-selected');
                    tagEl.classList.toggle('is-hidden', tagEl.dataset.customerId === sourceCustomerId);
                });
                selectError.classList.add('hidden');
                stepReview.classList.add('hidden');
                stepSelect.classList.remove('hidden');
                modal.classList.remove('hidden');
            }

            function closeModal() {
                modal.classList.add('hidden');
            }

            modal.querySelectorAll('.overlay-apply-multiple-customer-tag').forEach(function (tagEl) {
                tagEl.addEventListener('click', function () {
                    tagEl.classList.toggle('is-selected');
                });
            });

            function selectedTargetIds() {
                return Array.prototype.filter.call(modal.querySelectorAll('.overlay-apply-multiple-customer-tag'), function (tagEl) {
                    return tagEl.classList.contains('is-selected');
                }).map(function (tagEl) { return tagEl.dataset.customerId; });
            }

            // One labelled section of a target customer's review card.
            function buildSection(labelText) {
                var section = document.createElement('div');
                section.className = 'overlay-apply-multiple-target-section';
                if (labelText) {
                    var label = document.createElement('span');
                    label.className = 'overlay-field-label';
                    label.textContent = labelText;
                    section.appendChild(label);
                }
                return section;
            }

            function renderReview(data) {
                targetsContainer.innerHTML = '';
                data.targets.forEach(function (t) {
                    var el = document.createElement('div');
                    el.className = 'overlay-apply-multiple-target';
                    el.dataset.customerId = t.customer_id;

                    // Section 1: customer name and count tags.
                    var header = document.createElement('div');
                    header.className = 'overlay-apply-multiple-target-header';
                    var name = document.createElement('span');
                    name.className = 'overlay-apply-multiple-target-name';
                    name.textContent = t.customer_name;
                    header.appendChild(name);
                    var counts = document.createElement('span');
                    counts.className = 'overlay-apply-multiple-target-counts';
                    if (t.will_add_count) {
                        var addTag = document.createElement('span');
                        addTag.className = 'tag tag--action';
                        addTag.textContent = t.will_add_count + ' to add';
                        counts.appendChild(addTag);
                    }
                    if (t.already_existing.length) {
                        var haveTag = document.createElement('span');
                        haveTag.className = 'tag tag--muted';
                        haveTag.textContent = t.already_existing.length + ' already added';
                        counts.appendChild(haveTag);
                    }
                    header.appendChild(counts);
                    el.appendChild(header);

                    // Section 2: one deadline for everything copied here.
                    var deadlineSection = buildSection('Deadline');
                    var deadlineRow = document.createElement('div');
                    deadlineRow.className = 'overlay-apply-multiple-target-deadline';
                    var dateInput = document.createElement('input');
                    dateInput.type = 'date';
                    dateInput.className = 'overlay-apply-multiple-date';
                    var timeSelect = document.createElement('select');
                    timeSelect.className = 'overlay-apply-multiple-time';
                    if (timeTemplate) timeSelect.innerHTML = timeTemplate.innerHTML;
                    deadlineRow.appendChild(dateInput);
                    deadlineRow.appendChild(timeSelect);
                    deadlineSection.appendChild(deadlineRow);
                    el.appendChild(deadlineSection);

                    // Section 3: only when this customer's catalog lacks
                    // some source deliverables.
                    if (t.missing.length) {
                        var missingSection = buildSection('Add to catalog');
                        missingSection.classList.add('overlay-apply-multiple-missing');
                        t.missing.forEach(function (m) {
                            var row = document.createElement('label');
                            row.className = 'overlay-apply-multiple-missing-item';
                            var cb = document.createElement('input');
                            cb.type = 'checkbox';
                            cb.checked = true;
                            cb.dataset.deliverableId = m.id;
                            row.appendChild(cb);
                            row.appendChild(document.createTextNode(' ' + m.name));
                            missingSection.appendChild(row);
                        });
                        el.appendChild(missingSection);
                    }
                    targetsContainer.appendChild(el);
                });
                var matchedCount = data.total_will_add;
                summaryLine.textContent = matchedCount
                    ? (matchedCount + (matchedCount === 1 ? ' deliverable is ready to add.' : ' deliverables are ready to add.') + ' Check the details below, then press Apply.')
                    : 'None of these deliverables are in the other catalogs yet. Check the details below, then press Apply.';
            }

            if (openBtn) openBtn.addEventListener('click', openModal);
            if (cancelBtn) cancelBtn.addEventListener('click', closeModal);
            if (backBtn) {
                backBtn.addEventListener('click', function () {
                    stepReview.classList.add('hidden');
                    stepSelect.classList.remove('hidden');
                });
            }

            if (continueBtn) {
                continueBtn.addEventListener('click', function () {
                    var targetIds = selectedTargetIds();
                    if (!targetIds.length) {
                        selectError.textContent = 'Select at least one customer.';
                        selectError.classList.remove('hidden');
                        return;
                    }
                    selectError.classList.add('hidden');
                    continueBtn.disabled = true;
                    fetch(`/projects/${projectId}/overlay/deliverables/apply-multiple/preview`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ source_customer_id: sourceCustomerId, target_customer_ids: targetIds }),
                    })
                        .then(function (r) { return r.json(); })
                        .then(function (data) {
                            continueBtn.disabled = false;
                            if (!data.success) {
                                selectError.textContent = data.error || 'Could not preview this duplication.';
                                selectError.classList.remove('hidden');
                                return;
                            }
                            renderReview(data);
                            stepSelect.classList.add('hidden');
                            stepReview.classList.remove('hidden');
                        })
                        .catch(function () {
                            continueBtn.disabled = false;
                            selectError.textContent = 'Something went wrong. Please try again.';
                            selectError.classList.remove('hidden');
                        });
                });
            }

            if (confirmBtn) {
                confirmBtn.addEventListener('click', function () {
                    var targets = {};
                    targetsContainer.querySelectorAll('.overlay-apply-multiple-target').forEach(function (el) {
                        var customerId = el.dataset.customerId;
                        var missingIds = Array.prototype.filter.call(
                            el.querySelectorAll('.overlay-apply-multiple-missing-item input'),
                            function (cb) { return cb.checked; }
                        ).map(function (cb) { return cb.dataset.deliverableId; });
                        targets[customerId] = {
                            date: el.querySelector('.overlay-apply-multiple-date').value || null,
                            time: el.querySelector('.overlay-apply-multiple-time').value || null,
                            create_missing_ids: missingIds,
                        };
                    });
                    confirmBtn.disabled = true;
                    reviewError.classList.add('hidden');
                    fetch(`/projects/${projectId}/overlay/deliverables/apply-multiple/confirm`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            source_customer_id: sourceCustomerId,
                            target_customer_ids: Object.keys(targets),
                            targets: targets,
                        }),
                    })
                        .then(function (r) { return r.json(); })
                        .then(function (data) {
                            confirmBtn.disabled = false;
                            if (!data.success) {
                                reviewError.textContent = data.error || 'Could not apply this duplication.';
                                reviewError.classList.remove('hidden');
                                return;
                            }
                            closeModal();
                            showToast(data.message, 'success');
                            fetch(`/projects/${projectId}/overlay/deliverables/edit`)
                                .then(function (r) { return r.text(); })
                                .then(function (html) {
                                    if (destroyed) return;
                                    rootEl.innerHTML = html;
                                    bindEdit();
                                    if (onChanged) onChanged();
                                });
                        })
                        .catch(function () {
                            confirmBtn.disabled = false;
                            reviewError.textContent = 'Something went wrong. Please try again.';
                            reviewError.classList.remove('hidden');
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
                destroyPickers();
            }
        };
    }
    return { init: init };
})();