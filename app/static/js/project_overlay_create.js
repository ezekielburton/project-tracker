// app/static/js/project_overlay_create.js
//
// Create-mode overlay (tasks #61-62) — the "+ New Project" flow's Details
// and Deliverables steps. Deliberately separate from project_overlay.js/
// project_overlay_edit.js/project_deliverables_card.js: those are built
// around the live overlay's sub-tab rail, view/edit toggle, and Save ->
// back-to-read-only flow, none of which fit create mode (a linear 2-step
// wizard with no "read" state to fall back to yet — see task #64 for what
// eventually replaces the current placeholder "Add New Project" action).
//
// Details autosave contract: every [data-create-field] posts ONLY the one
// field that changed to POST /projects/overlay/new, debounced per-field so
// fast typing doesn't fire a request per keystroke. overlay_create_draft()
// treats any field key it doesn't receive as "unchanged", so partial
// payloads are always safe.
//
// Deliverables step deliberately reuses the SAME templates and SAME save
// endpoint (/projects/<id>/overlay/deliverables/edit + /save) the live
// overlay's "Edit Deliverables" already uses — same row-add-by-cloning-a-
// <template>, same team toggles, same Apply Deadline to All, same bulk
// Save. Per Ezekiel (18 Aug 2026): "remember the UX and conventions we're
// using... we dont want adding deliverables to be a pain" — that UX was
// already solved once for the live overlay, so create mode just points at
// it rather than inventing a second way to add a deliverable row.

(function () {
    'use strict';

    var _closeCallback = null;
    var _onFinalized = null;
    var _currentStep = 'details';
    // Tracks the most recent Details-step autosave request so step
    // navigation can wait for it to land before fetching the next step —
    // fixes a real bug (18 Aug 2026, per Ezekiel): picking C&CM customers
    // then immediately clicking "Continue to Deliverables" could race the
    // customer_ids autosave, so the Deliverables step's server-side render
    // ran against a project that didn't have those ProjectCustomer rows
    // yet, and the customers looked like they'd never been picked at all.
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

        // Fresh promise chain for this visit to the Details step — a
        // leftover pending promise from a PREVIOUS visit (already resolved
        // by the time anyone navigates again) would be harmless either way,
        // but resetting here keeps the intent obvious.
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
                    // Initial Deadline is server-computed (see
                    // _recompute_initial_deadline in project_overlay.py) —
                    // every autosave response carries the current value so
                    // this stays live without a full step reload.
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
                autosave({ brief_type: briefType }); // not debounced — this gates what the user sees next, shouldn't lag
            });
        });
        // Restore whichever scope matches an already-saved brief_type (e.g.
        // reopening a draft — see task #65) — the server already renders
        // the right one hidden/shown, this just keeps a freshly-navigated-
        // back-to state consistent with dataset.createBriefType.
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

        // ---- Concept & KV toggle (C&CM) — one merged tickbox, see
        // _details_create.html and overlay_create_draft()'s comment on
        // how has_concept_kv maps onto the model's two separate columns. ----
        var hasConceptKvBox = document.getElementById('overlay-create-has-concept-kv');
        var conceptKvFields = document.getElementById('overlay-create-concept-kv-fields');
        if (hasConceptKvBox && conceptKvFields) {
            hasConceptKvBox.addEventListener('change', function () {
                conceptKvFields.classList.toggle('is-hidden', !hasConceptKvBox.checked);
            });
        }

        // ---- Customer picker (C&CM) ----
        // Not debounced, unlike the plain text fields above — same
        // reasoning as the brief-type buttons: this gates what the
        // Deliverables step can show, so it shouldn't lag, and a debounced
        // save here was the actual cause of the "customers don't show up
        // on Deliverables" bug (see _pendingDetailsSave's comment above).
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

        // ---- Re-run the client/contact directory cascade + "+ Add new…"
        // wiring against this freshly-injected DOM. client_directory.js's
        // own initBriefFormIntegration() only ran once at page load, before
        // this fragment existed — see client_directory.js's exported
        // initBriefFormIntegration for why it needs a manual re-call here. ----
        if (window.ClientDirectoryModals && window.ClientDirectoryModals.initBriefFormIntegration) {
            window.ClientDirectoryModals.initBriefFormIntegration();
        }

        // ---- Job number generator (task #63) ----
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

        // ---- Reference files (task #63) ----
        // Reuses ProjectDetailsCard.init() wholesale rather than rewriting
        // upload/preview/remove/drag-and-drop for a second time — it also
        // wires several avatar pickers (#cs-lead-picker etc.) that don't
        // exist in this DOM at all, but each of those is individually
        // guarded (`if (picker) ...`) in project_details_card.js, so they
        // no-op harmlessly here instead of erroring.
        if (window.ProjectDetailsCard) {
            window.ProjectDetailsCard.init(contentEl, projectId, function () {
                loadDetailsStep(projectId);
            });
        }
    }

    // ════════════════════════════════════════════════════════════════════
    // Step 2: Deliverables — row logic mirrors project_deliverables_card.js's
    // bindEdit() almost exactly (same markup, same endpoints). Duplicated
    // rather than shared, matching this codebase's existing convention of
    // small per-file helpers (see _can_skip_preproduction's docstring on
    // the Python side) — the two Save behaviors genuinely diverge (this one
    // never falls back to a read-only view), so sharing would mean a
    // branch inside the shared function instead of two honest copies.
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
                // Scoped to the visible customer panel on C&CM — "all" means
                // every row currently in view, not every customer's rows.
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
                        // No read-only view to fall back to yet in create mode
                        // (that's the live overlay's Save behavior) — reload
                        // the same edit fragment instead, so newly created
                        // rows pick up real ids (Delete needs one) and rows
                        // marked deleted are actually gone from the DOM.
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
        // overlay_deliverables_edit() falls back to rendering the Standard
        // table for an unset brief_type — fine as a server-side default,
        // but a confusing thing to land a user on if they never actually
        // picked one. Caught here instead so the fix (go pick one) is
        // obvious rather than "why does this look wrong."
        if (!contentEl.dataset.createBriefType) {
            if (window.showToast) window.showToast('Choose Standard or C&CM first.', 'error');
            return;
        }
        // Wait for any in-flight Details autosave (e.g. a customer checkbox
        // just ticked) to actually land server-side before fetching this
        // step — otherwise this can render against a stale project and
        // miss customers/fields that were "saved" a moment too late.
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
                // Wired for real in #64 (confirm summary modal + finalize).
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
    // Confirm summary modal + finalize (task #64)
    // ════════════════════════════════════════════════════════════════════

    function openCreateSummaryModal(projectId, continueBtn) {
        if (continueBtn) continueBtn.disabled = true;
        fetch('/projects/' + projectId + '/overlay/create/summary')
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (continueBtn) continueBtn.disabled = false;
                if (!data.success) {
                    // Standard's "no deliverables" case lands here — a toast,
                    // not a modal, per Ezekiel's original spec for that rule.
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

    // Wires close + step navigation, then binds whichever step's fragment
    // is currently sitting in the DOM. Called once right after the shell
    // HTML first lands (from init(), below) and again every time
    // loadDetailsStep() re-fetches the whole shell (going "back").
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

    // Entry point — called once by project_list.js right after the create
    // shell's HTML is first injected into #project-overlay-mount (see
    // openNewProjectOverlay in project_list.js). onFinalized(projectId) is
    // called after a successful Confirm on the summary modal — project_list.js
    // passes its own openProjectOverlay so the newly-created project opens
    // straight into the full, all-tabs live overlay.
    function init(projectId, closeCallback, onFinalized) {
        _closeCallback = closeCallback;
        _onFinalized = onFinalized;
        initShell(projectId);
    }

    window.ProjectOverlayCreate = { init: init };
})();
