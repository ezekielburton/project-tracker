// app/modules/projects/static/js/project_overlay_create.js
//
// Create-mode overlay: the "+ New Project" wizard (Details, Deliverables,
// then a confirm summary that finalizes the draft). Separate from the live
// overlay's scripts because create mode has no read-only state.
//
// Details autosave: each [data-create-field] posts only the changed field to
// POST /projects/overlay/new, debounced per field. overlay_create_draft()
// treats missing keys as unchanged, so partial payloads are safe.
//
// The Deliverables step reuses the live overlay's edit templates and
// endpoints (/projects/<id>/overlay/deliverables/edit + /save).

(function () {
    'use strict';

    var _closeCallback = null;
    var _onFinalized = null;
    var _currentStep = 'details';
    // Latest Details autosave. The Deliverables step waits on it, or its
    // server render can miss C&CM customers ticked a moment before.
    var _pendingDetailsSave = Promise.resolve();

    function debounce(fn, wait) {
        var timers = {};
        return function (key, payload) {
            clearTimeout(timers[key]);
            timers[key] = setTimeout(function () { fn(payload); }, wait);
        };
    }

    // ════════════════════════════════════════════════════════════════════
    // Step 1: Details
    // ════════════════════════════════════════════════════════════════════

    function bindDetailsStep(contentEl, footerEl, projectId, headerNameEl) {
        var statusEl = footerEl ? footerEl.querySelector('#project-overlay-create-autosave-status') : null;
        var initialDeadlineEl = document.getElementById('overlay-create-initial-deadline-value');

        _pendingDetailsSave = Promise.resolve();

        function setStatus(text) {
            if (statusEl) statusEl.textContent = text;
        }

        function autosave(payload) {
            payload.project_id = projectId;
            setStatus('Saving…');
            _pendingDetailsSave = fetch('/projects/overlay/new', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
                .then(function (res) { return res.json(); })
                .then(function (data) {
                    if (!data.success) {
                        setStatus('Could not save');
                        if (window.showToast) window.showToast(data.error || 'Could not save changes.', 'error');
                        return;
                    }
                    setStatus('Draft saved');
                    if ('name' in payload && headerNameEl) {
                        headerNameEl.textContent = payload.name || 'Untitled Draft';
                    }
                    // Initial Deadline is server-computed; each response carries it.
                    if (initialDeadlineEl) {
                        initialDeadlineEl.textContent = data.first_output_deadline || 'Auto - Based on earliest deadline added';
                    }
                })
                .catch(function () {
                    setStatus('Could not save');
                });
            return _pendingDetailsSave;
        }

        var debouncedAutosave = debounce(autosave, 500);

        // ---- Plain fields (text/select/date/textarea) ----
        contentEl.querySelectorAll('[data-create-field]').forEach(function (el) {
            var field = el.dataset.createField;
            var eventName = (el.tagName === 'SELECT' || el.type === 'checkbox' || el.type === 'date') ? 'change' : 'input';
            el.addEventListener(eventName, function () {
                var value = el.type === 'checkbox' ? el.checked : el.value;
                var payload = {};
                payload[field] = value;
                debouncedAutosave(field, payload);
            });
        });

        // ---- Teams checkboxes (2D/3D/Technical -> comma string) ----
        var teamBoxes = contentEl.querySelectorAll('[data-create-team]');
        function currentTeams() {
            return Array.prototype.filter.call(teamBoxes, function (b) { return b.checked; })
                .map(function (b) { return b.dataset.createTeam; });
        }
        teamBoxes.forEach(function (box) {
            box.addEventListener('change', function () {
                debouncedAutosave('design_teams', { design_teams: currentTeams() });
            });
        });

        // ---- Brief type selector ----
        contentEl.querySelectorAll('[data-brief-type]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var briefType = btn.dataset.briefType;
                contentEl.querySelectorAll('[data-brief-type]').forEach(function (b) {
                    b.classList.toggle('active', b === btn);
                });
                contentEl.querySelectorAll('[data-create-scope]').forEach(function (scope) {
                    scope.classList.toggle('is-hidden', scope.dataset.createScope !== briefType);
                });
                contentEl.dataset.createBriefType = briefType;
                autosave({ brief_type: briefType }); // not debounced: it gates what shows next
            });
        });
        // Show the scope matching an already-saved brief_type (e.g. a reopened draft).
        var savedBriefType = contentEl.dataset.createBriefType;
        if (savedBriefType) {
            contentEl.querySelectorAll('[data-create-scope]').forEach(function (scope) {
                scope.classList.toggle('is-hidden', scope.dataset.createScope !== savedBriefType);
            });
        }

        // ---- Production Only toggle (Standard) ----
        var productionOnlyBox = document.getElementById('overlay-create-production-only');
        var productionOnlyFields = document.getElementById('overlay-create-production-only-requirements');
        if (productionOnlyBox && productionOnlyFields) {
            productionOnlyBox.addEventListener('change', function () {
                productionOnlyFields.classList.toggle('is-hidden', !productionOnlyBox.checked);
            });
        }

        // ---- Concept & KV toggle (C&CM): one tickbox for two model columns,
        // see overlay_create_draft(). ----
        var hasConceptKvBox = document.getElementById('overlay-create-has-concept-kv');
        var conceptKvFields = document.getElementById('overlay-create-concept-kv-fields');
        if (hasConceptKvBox && conceptKvFields) {
            hasConceptKvBox.addEventListener('change', function () {
                conceptKvFields.classList.toggle('is-hidden', !hasConceptKvBox.checked);
            });
        }

        // ---- Customer picker (C&CM) ----
        // Not debounced: the Deliverables step depends on these customers
        // (see _pendingDetailsSave).
        var customerBoxes = contentEl.querySelectorAll('[data-create-customer-id]');
        function currentCustomerIds() {
            return Array.prototype.filter.call(customerBoxes, function (b) { return b.checked; })
                .map(function (b) { return parseInt(b.dataset.createCustomerId, 10); });
        }
        customerBoxes.forEach(function (box) {
            box.addEventListener('change', function () {
                autosave({ customer_ids: currentCustomerIds() });
            });
        });
        contentEl.querySelectorAll('.overlay-create-select-all').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var region = btn.dataset.createRegion;
                var regionBoxes = contentEl.querySelectorAll('[data-create-customer-id][data-create-region="' + region + '"]');
                var allChecked = Array.prototype.every.call(regionBoxes, function (b) { return b.checked; });
                regionBoxes.forEach(function (b) { b.checked = !allChecked; });
                autosave({ customer_ids: currentCustomerIds() });
            });
        });

        // ---- Client/contact directory wiring: client_directory.js ran at
        // page load, before this fragment existed, so re-run it here. ----
        if (window.ClientDirectoryModals && window.ClientDirectoryModals.initBriefFormIntegration) {
            window.ClientDirectoryModals.initBriefFormIntegration();
        }

        // ---- Job number generator ----
        var jobNumberInput = document.getElementById('overlay-create-job-number');
        var generateBtn = document.getElementById('overlay-create-generate-job-number-btn');
        if (generateBtn && jobNumberInput) {
            generateBtn.addEventListener('click', function () {
                generateBtn.disabled = true;
                fetch('/projects/generate-job-number')
                    .then(function (res) { return res.json(); })
                    .then(function (data) {
                        generateBtn.disabled = false;
                        if (!data.job_number) return;
                        jobNumberInput.value = data.job_number;
                        autosave({ job_number: data.job_number });
                    })
                    .catch(function () {
                        generateBtn.disabled = false;
                        if (window.showToast) window.showToast('Could not generate a job number.', 'error');
                    });
            });
        }

        // ---- Reference files ----
        // Reuses ProjectDetailsCard.init() for uploads. Its avatar pickers are
        // absent here; each is null-guarded in project_details_card.js.
        if (window.ProjectDetailsCard) {
            window.ProjectDetailsCard.init(contentEl, projectId, function () {
                loadDetailsStep(projectId);
            });
        }
    }

    // ════════════════════════════════════════════════════════════════════
    // Step 2: Deliverables. Row logic copies project_deliverables_card.js's
    // bindEdit() (same markup and endpoints); keep the two in step. Only
    // Save differs: this one reloads the edit view.
    // ════════════════════════════════════════════════════════════════════

    function bindDeliverablesStep(contentEl, projectId) {
        var template = contentEl.querySelector('#overlay-deliverable-row-template');
        var addBtn = contentEl.querySelector('#overlay-add-deliverable-btn');
        var applyAllBtn = contentEl.querySelector('#overlay-apply-deadline-all-btn');
        var saveBtn = contentEl.querySelector('#overlay-save-deliverables-btn');
        var scopeSelect = contentEl.querySelector('#overlay-deliverables-edit-scope-select');

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
        contentEl.querySelectorAll('.overlay-deliverables-edit-row').forEach(wireRow);

        if (scopeSelect) {
            scopeSelect.addEventListener('change', function () {
                contentEl.querySelectorAll('.overlay-deliverables-edit-panel').forEach(function (panel) {
                    panel.classList.toggle('is-hidden', panel.dataset.customerPanel !== scopeSelect.value);
                });
            });
        }

        function activeEditList() {
            var visiblePanel = contentEl.querySelector('.overlay-deliverables-edit-panel:not(.is-hidden)');
            if (visiblePanel) return visiblePanel.querySelector('.overlay-deliverables-edit-list');
            return contentEl.querySelector('.overlay-deliverables-edit-list');
        }

        if (addBtn && template) {
            addBtn.addEventListener('click', function () {
                var listEl = activeEditList();
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
                // On C&CM, "all" means the visible customer panel only.
                var listEl = activeEditList();
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

        function collectAllRows() {
            var out = [];
            contentEl.querySelectorAll('.overlay-deliverables-edit-list').forEach(function (listEl) {
                var customerId = listEl.dataset.customerId || null;
                collectRows(listEl).forEach(function (row) {
                    row.project_customer_id = customerId;
                    out.push(row);
                });
            });
            return out;
        }

        if (saveBtn) {
            saveBtn.addEventListener('click', function () {
                var deliverables = collectAllRows();
                saveBtn.disabled = true;
                var originalText = saveBtn.textContent;
                saveBtn.textContent = 'Saving…';
                fetch('/projects/' + projectId + '/overlay/deliverables/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ deliverables: deliverables })
                })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (!data.success) {
                            saveBtn.disabled = false;
                            saveBtn.textContent = originalText;
                            if (window.showToast) window.showToast(data.error || 'Could not save deliverables.', 'error');
                            return;
                        }
                        // Reload the edit fragment so new rows get real ids
                        // (Delete needs one) and deleted rows leave the DOM.
                        loadDeliverablesStep(projectId);
                        if (window.showToast) window.showToast('Deliverables saved.', 'success');
                    })
                    .catch(function () {
                        saveBtn.disabled = false;
                        saveBtn.textContent = originalText;
                        if (window.showToast) window.showToast('Something went wrong. Please try again.', 'error');
                    });
            });
        }
    }

    // ════════════════════════════════════════════════════════════════════
    // Step navigation + shell wiring
    // ════════════════════════════════════════════════════════════════════

    function setActiveStep(stepKey) {
        _currentStep = stepKey;
        document.querySelectorAll('[data-create-step]').forEach(function (btn) {
            btn.classList.toggle('active', btn.dataset.createStep === stepKey);
        });
    }

    function loadDetailsStep(projectId) {
        var mount = document.getElementById('project-overlay-mount');
        if (!mount) return;
        return fetch('/projects/' + projectId + '/overlay/create')
            .then(function (res) { return res.text(); })
            .then(function (html) {
                mount.innerHTML = html;
                initShell(projectId);
            });
    }

    function loadDeliverablesStep(projectId) {
        var contentEl = document.getElementById('project-overlay-content');
        var footerEl = document.getElementById('project-overlay-create-footer');
        if (!contentEl) return;
        // The server renders Standard for an unset brief_type, so ask the
        // user to pick one first.
        if (!contentEl.dataset.createBriefType) {
            if (window.showToast) window.showToast('Choose Standard or C&CM first.', 'error');
            return;
        }
        // Wait for any in-flight Details autosave so the render isn't stale.
        return _pendingDetailsSave.then(function () {
            return fetch('/projects/' + projectId + '/overlay/deliverables/edit');
        })
            .then(function (res) { return res.text(); })
            .then(function (html) {
                contentEl.innerHTML = html;
                setActiveStep('deliverables');
                var statusEl = footerEl ? footerEl.querySelector('#project-overlay-create-autosave-status') : null;
                if (statusEl) statusEl.textContent = '';
                var continueBtn = footerEl ? footerEl.querySelector('#project-overlay-create-continue') : null;
                // On this step, Continue opens the confirm summary (wireStepNav).
                if (continueBtn) continueBtn.textContent = 'Add New Project →';
                bindDeliverablesStep(contentEl, projectId);
            });
    }

    function wireStepNav(projectId) {
        document.querySelectorAll('[data-create-step]').forEach(function (stepBtn) {
            stepBtn.addEventListener('click', function () {
                if (stepBtn.classList.contains('active')) return;
                if (stepBtn.dataset.createStep === 'deliverables') {
                    loadDeliverablesStep(projectId);
                } else {
                    loadDetailsStep(projectId);
                }
            });
        });
        var footerEl = document.getElementById('project-overlay-create-footer');
        var continueBtn = footerEl ? footerEl.querySelector('#project-overlay-create-continue') : null;
        if (continueBtn) {
            continueBtn.addEventListener('click', function () {
                if (_currentStep === 'details') {
                    loadDeliverablesStep(projectId);
                } else {
                    openCreateSummaryModal(projectId, continueBtn);
                }
            });
        }
    }

    // ════════════════════════════════════════════════════════════════════
    // Confirm summary modal + finalize
    // ════════════════════════════════════════════════════════════════════

    function openCreateSummaryModal(projectId, continueBtn) {
        if (continueBtn) continueBtn.disabled = true;
        fetch('/projects/' + projectId + '/overlay/create/summary')
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (continueBtn) continueBtn.disabled = false;
                if (!data.success) {
                    // e.g. Standard with no deliverables: shown as a toast.
                    if (window.showToast) window.showToast(data.error || 'Could not prepare summary.', 'error');
                    return;
                }
                var wrapper = document.createElement('div');
                wrapper.innerHTML = data.html;
                var modal = wrapper.firstElementChild;
                document.body.appendChild(modal);
                if (window.helixPolling) window.helixPolling.pause();

                var cancelBtn = document.getElementById('overlay-create-summary-cancel');
                var confirmBtn = document.getElementById('overlay-create-summary-confirm');
                var errorEl = document.getElementById('overlay-create-summary-error');

                function closeModal() {
                    modal.remove();
                    if (window.helixPolling) window.helixPolling.resume();
                }
                if (cancelBtn) cancelBtn.addEventListener('click', closeModal);
                modal.addEventListener('click', function (e) {
                    if (e.target === modal) closeModal();
                });
                if (confirmBtn) {
                    confirmBtn.addEventListener('click', function () {
                        confirmBtn.disabled = true;
                        if (errorEl) errorEl.classList.add('hidden');
                        fetch('/projects/' + projectId + '/overlay/create/finalize', { method: 'POST' })
                            .then(function (res) { return res.json(); })
                            .then(function (result) {
                                if (!result.success) {
                                    confirmBtn.disabled = false;
                                    if (errorEl) {
                                        errorEl.textContent = result.error || 'Could not create this project.';
                                        errorEl.classList.remove('hidden');
                                    }
                                    return;
                                }
                                closeModal();
                                if (_onFinalized) _onFinalized(result.project_id);
                            })
                            .catch(function () {
                                confirmBtn.disabled = false;
                                if (errorEl) {
                                    errorEl.textContent = 'Something went wrong. Please try again.';
                                    errorEl.classList.remove('hidden');
                                }
                            });
                    });
                }
            })
            .catch(function () {
                if (continueBtn) continueBtn.disabled = false;
                if (window.showToast) window.showToast('Could not prepare summary.', 'error');
            });
    }

    // Wires close + step navigation, then binds whichever step is in the DOM.
    // Runs on init() and each time loadDetailsStep() re-fetches the shell.
    function initShell(projectId) {
        var closeBtn = document.getElementById('project-overlay-close');
        if (closeBtn && _closeCallback) closeBtn.addEventListener('click', _closeCallback);

        wireStepNav(projectId);

        var contentEl = document.getElementById('project-overlay-content');
        var footerEl = document.getElementById('project-overlay-create-footer');
        var nameEl = document.getElementById('project-overlay-create-name');
        if (!contentEl) return;

        if (contentEl.querySelector('#overlay-save-deliverables-btn')) {
            setActiveStep('deliverables');
            bindDeliverablesStep(contentEl, projectId);
        } else {
            setActiveStep('details');
            bindDetailsStep(contentEl, footerEl, projectId, nameEl);
        }
    }

    // Entry point, called by project_list.js's openCreateShellForDraft once
    // the shell is in #project-overlay-mount. onFinalized(projectId) runs
    // after Confirm; project_list.js passes openProjectOverlay.
    function init(projectId, closeCallback, onFinalized) {
        _closeCallback = closeCallback;
        _onFinalized = onFinalized;
        initShell(projectId);
    }

    window.ProjectOverlayCreate = { init: init };
})();
