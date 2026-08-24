window.ProjectDetailsCard = (function () {
    function init(rootEl, projectId, onChanged) {
        if (!rootEl) return null;
        var pickerHandles = [];
        function handleResponse(res) { return res.json().then(function (data) { if (data.success) { onChanged(); } else { alert(data.error || 'Something went wrong.'); } }); }
        function postForm(url, body) { fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body }).then(handleResponse); }
        function postJson(url, body) { fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(handleResponse); }

        var csLeadPicker = rootEl.querySelector('#cs-lead-picker');
        if (csLeadPicker) pickerHandles.push(window.AvatarPicker.init(csLeadPicker, function (userId) { postJson(`/projects/${projectId}/reassign-cs-lead`, { new_cs_lead_id: userId }); }));

        var secondaryCsAddPicker = rootEl.querySelector('#secondary-cs-add-picker');
        if (secondaryCsAddPicker) pickerHandles.push(window.AvatarPicker.init(secondaryCsAddPicker, function (userId) { postForm(`/projects/${projectId}/secondary-cs`, `user_id=${userId}`); }));

        var ownerPicker = rootEl.querySelector('#project-owner-picker');
        if (ownerPicker) pickerHandles.push(window.AvatarPicker.init(ownerPicker, function (userId) { postForm(`/projects/${projectId}/set-project-owner`, `user_id=${userId}`); }));

        var conceptKvPicker = rootEl.querySelector('#concept-kv-designer-picker');
        if (conceptKvPicker) pickerHandles.push(window.AvatarPicker.init(conceptKvPicker, function (userId) { postForm(`/projects/${projectId}/assign-concept-kv`, `concept_designer_id=${userId}&kv_designer_id=${userId}`); }));

        rootEl.querySelectorAll('.avatar-picker[data-team]').forEach(function (pickerEl) {
            pickerHandles.push(window.AvatarPicker.init(pickerEl, function (userId) {
                postJson(`/projects/${projectId}/assign-lead`, { team: pickerEl.dataset.team, new_designer_id: userId });
            }));
        });

        // Project-level admin status override picker (back 24 Aug 2026, per
        // Ezekiel — see _details_top_cards.html/project_overlay.py's
        // override_project_status() for what this actually does: a bulk
        // WRITE to every deliverable + C&CM channel on the project, not a
        // stored override of this pill). Only renders at all for an admin
        // (can_override_project_status). Same StatusPicker component and
        // same fetch-on-select shape as project_deliverables_card.js's
        // wireStatusOverridePickers() — just one picker here instead of
        // one per row, and onChanged() re-fetches the whole Details tab on
        // success same as every other mutation in this file.
        var projectStatusPicker = rootEl.querySelector('#project-status-picker');
        if (projectStatusPicker && window.StatusPicker) {
            var projectStatusHandle = window.StatusPicker.init(projectStatusPicker, function (statusValue, el) {
                fetch(el.dataset.targetUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ status: statusValue }),
                })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (!data.success) {
                            alert(data.error || 'Could not update this status.');
                            return;
                        }
                        onChanged();
                    })
                    .catch(function () {
                        alert('Something went wrong. Please try again.');
                    });
            });
            if (projectStatusHandle) pickerHandles.push(projectStatusHandle);
        }

        rootEl.querySelectorAll('.overlay-secondary-cs-remove').forEach(function (btn) {
            btn.addEventListener('click', function () { postForm(`/projects/${projectId}/secondary-cs/${btn.dataset.userId}/remove`, ''); });
        });

        // ── Reference Files: upload, preview, remove, download all ─────
        var refFileBtn = rootEl.querySelector('#overlay-reference-file-btn');
        var refFileInput = rootEl.querySelector('#overlay-reference-file-input');
        if (refFileBtn && refFileInput) {
            refFileBtn.addEventListener('click', function () { refFileInput.click(); });

            refFileInput.addEventListener('change', function () {
                var file = refFileInput.files[0];
                if (!file) return;
                var status = rootEl.querySelector('#overlay-reference-file-status');
                if (status) status.textContent = 'Uploading...';

                var formData = new FormData();
                formData.append('file', file);

                fetch(`/projects/${projectId}/upload-file`, { method: 'POST', body: formData })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (!data.success) {
                            if (status) status.textContent = '';
                            alert(data.error || 'File could not be saved.');
                            return;
                        }
                        onChanged();
                    })
                    .catch(function () {
                        if (status) status.textContent = '';
                        alert('Upload failed. Please try again.');
                    });
            });
        }

        enableDragAndDrop();

        rootEl.querySelectorAll('.overlay-reference-file-remove').forEach(function (btn) {
            btn.addEventListener('click', function () {
                showConfirm('Remove this file? This cannot be undone.', function () {
                    fetch(`/projects/files/${btn.dataset.fileId}/delete`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' }
                    })
                        .then(function (r) { return r.json(); })
                        .then(function (data) {
                            if (!data.success) { alert(data.error || 'Could not delete file.'); return; }
                            onChanged();
                        });
                });
            });
        });

        rootEl.querySelectorAll('.overlay-reference-file-preview').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var item = btn.closest('.overlay-reference-file-item');
                var nameEl = item ? item.querySelector('.overlay-reference-file-name') : null;
                window.openFilePreview(btn.dataset.previewUrl, btn.dataset.downloadUrl, nameEl ? nameEl.textContent : 'file');
            });
        });

        // ── Start Project: the manual "Briefed" -> "In Design" gate ────
        var startProjectBtn = rootEl.querySelector('#overlay-start-project-btn');
        if (startProjectBtn) {
            startProjectBtn.addEventListener('click', function () {
                startProjectBtn.disabled = true;
                fetch(`/projects/${projectId}/overlay/start`, { method: 'POST' })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (!data.success) {
                            startProjectBtn.disabled = false;
                            alert(data.error || 'Could not start this project.');
                            return;
                        }
                        onChanged();
                    })
                    .catch(function () {
                        startProjectBtn.disabled = false;
                        alert('Something went wrong. Please try again.');
                    });
            });
        }

        // Cancel / Reactivate and Put on Hold / Resume now live in the
        // overlay sidebar, wired once per overlay-open in project_list.js
        // (see wireProjectLifecycleActions) — not here, since this init()
        // reruns on every Details sub-tab load and the sidebar isn't.

        var downloadAllBtn = rootEl.querySelector('#overlay-download-all-files');
        if (downloadAllBtn) {
            downloadAllBtn.addEventListener('click', function () {
                var originalText = downloadAllBtn.textContent;
                downloadAllBtn.disabled = true;
                downloadAllBtn.textContent = 'Zipping...';
                fetch(downloadAllBtn.dataset.downloadAllUrl)
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        downloadAllBtn.disabled = false;
                        downloadAllBtn.textContent = originalText;
                        if (!data.success) { alert(data.error || 'Could not build zip.'); return; }
                        window.location = data.download_url;
                    })
                    .catch(function () {
                        downloadAllBtn.disabled = false;
                        downloadAllBtn.textContent = originalText;
                        alert('Something went wrong.');
                    });
            });
        }

        // Flags (task #42) — Details' Flags card (project/concept/kv scope).
        // Reruns every load same as everything else in this file, since
        // project_flags.js just re-wires whatever .overlay-flag-section
        // elements are in the fresh HTML.
        if (window.ProjectFlags) window.ProjectFlags.init(rootEl, projectId, onChanged);

        // ── Cancel Customer panel toggle (23 Aug 2026, per Ezekiel — "a
        // cancel customer button next to flag history - blue. becomes
        // cancel when pressed to go back") — swaps the whole Properties/
        // Design Leads/Reference Files body for the Customers card in
        // place, same "Edit -> Save/Cancel" label-swap vocabulary the
        // overlay header's own Edit button already uses (see
        // project_overlay_edit.js), just a single toggle button here
        // instead of a three-button set since there's no draft state to
        // save — flipping is-hidden on both views is instant either way.
        var cancelCustomerToggleBtn = rootEl.querySelector('#overlay-cancel-customer-toggle-btn');
        var detailsMainView = rootEl.querySelector('#overlay-details-main-view');
        var detailsCancelView = rootEl.querySelector('#overlay-details-cancel-view');
        if (cancelCustomerToggleBtn && detailsMainView && detailsCancelView) {
            cancelCustomerToggleBtn.addEventListener('click', function () {
                var showingCancelView = detailsCancelView.classList.contains('is-hidden');
                detailsMainView.classList.toggle('is-hidden', showingCancelView);
                detailsCancelView.classList.toggle('is-hidden', !showingCancelView);
                cancelCustomerToggleBtn.textContent = showingCancelView
                    ? cancelCustomerToggleBtn.dataset.labelActive
                    : cancelCustomerToggleBtn.dataset.labelDefault;
            });
        }

        // ── Cancel/Reactivate Customer (23 Aug 2026, per Ezekiel) — C&CM
        // only, one .overlay-customer-item per row in the Customers card
        // (_details_ccm.html). Same reveal-form/confirm/cancel shape as
        // Cancel Project in project_list.js's wireProjectLifecycleActions,
        // just scoped per-row here instead of once for the whole sidebar —
        // each row carries its own project-customer-id via the closest
        // .overlay-customer-item, and each row's own cancel form/error box
        // rather than one shared pair. Lives here (not project_list.js)
        // since the Customers card is part of the Details sub-tab's own
        // content, which reruns init() on every load same as everything
        // else in this file.
        rootEl.querySelectorAll('.overlay-customer-cancel-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var item = btn.closest('.overlay-customer-item');
                var form = item ? item.querySelector('.overlay-customer-cancel-form') : null;
                if (!form) return;
                btn.classList.add('is-hidden');
                form.classList.remove('is-hidden');
            });
        });
        rootEl.querySelectorAll('.overlay-customer-cancel-cancel').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var item = btn.closest('.overlay-customer-item');
                if (!item) return;
                var form = item.querySelector('.overlay-customer-cancel-form');
                var cancelBtn = item.querySelector('.overlay-customer-cancel-btn');
                var errorEl = item.querySelector('.overlay-customer-cancel-error');
                if (form) form.classList.add('is-hidden');
                if (cancelBtn) cancelBtn.classList.remove('is-hidden');
                if (errorEl) errorEl.classList.add('hidden');
            });
        });
        rootEl.querySelectorAll('.overlay-customer-cancel-confirm').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var item = btn.closest('.overlay-customer-item');
                if (!item) return;
                var pcId = item.dataset.projectCustomerId;
                var reasonInput = item.querySelector('.overlay-customer-cancel-reason-input');
                var errorEl = item.querySelector('.overlay-customer-cancel-error');
                var reason = reasonInput ? reasonInput.value.trim() : '';
                if (!reason) {
                    if (errorEl) { errorEl.textContent = 'A reason is required.'; errorEl.classList.remove('hidden'); }
                    return;
                }
                btn.disabled = true;
                if (errorEl) errorEl.classList.add('hidden');
                fetch(`/project-customers/${pcId}/cancel`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ reason: reason }),
                })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        btn.disabled = false;
                        if (!data.success) {
                            if (errorEl) { errorEl.textContent = data.error || 'Could not cancel this customer.'; errorEl.classList.remove('hidden'); }
                            return;
                        }
                        onChanged();
                    });
            });
        });
        rootEl.querySelectorAll('.overlay-customer-uncancel-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var item = btn.closest('.overlay-customer-item');
                if (!item) return;
                var pcId = item.dataset.projectCustomerId;
                btn.disabled = true;
                fetch(`/project-customers/${pcId}/uncancel`, { method: 'POST' })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        btn.disabled = false;
                        if (!data.success) { alert(data.error || 'Could not reactivate this customer.'); return; }
                        onChanged();
                    });
            });
        });

        return { destroy: function () { pickerHandles.forEach(function (h) { if (h) h.destroy(); }); } };
    }
    return { init: init };
})();