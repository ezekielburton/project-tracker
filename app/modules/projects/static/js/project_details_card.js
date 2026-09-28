window.ProjectDetailsCard = (function () {
    // Cleanup handlers from the last custom #confirm-modal this file built,
    // kept module-level so re-opening it doesn't stack listeners on the
    // shared modal (same pattern as project_submissions_draft_card.js).
    var _lastCancelCleanup = null;
    var _lastBackdropCleanup = null;

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

        // Admin-only project status picker. Bulk-writes the status to every
        // deliverable and C&CM channel (override_project_status()).
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
                window.openFilePreview(btn.dataset.previewUrl, btn.dataset.downloadUrl,
                    nameEl ? nameEl.textContent : 'file', btn.dataset.fileType);
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

        // Cancel/Reactivate and Hold/Resume are sidebar actions, wired once
        // per overlay open in project_list.js (wireProjectLifecycleActions).
        // This init() reruns on every Details load, so don't wire them here.

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

        // Details' Flags card (project/concept/kv scope).
        if (window.ProjectFlags) window.ProjectFlags.init(rootEl, projectId, onChanged);

        // ── Add Customer (C&CM): toggle button reveals an inline form.
        var addCustomerToggleBtn = rootEl.querySelector('#overlay-customer-add-toggle-btn');
        var addCustomerForm = rootEl.querySelector('#overlay-customer-add-form');
        if (addCustomerToggleBtn && addCustomerForm) {
            addCustomerToggleBtn.addEventListener('click', function () {
                addCustomerToggleBtn.classList.add('is-hidden');
                addCustomerForm.classList.remove('is-hidden');
            });
        }
        var addCustomerCancelBtn = rootEl.querySelector('#overlay-customer-add-cancel');
        if (addCustomerCancelBtn && addCustomerToggleBtn && addCustomerForm) {
            addCustomerCancelBtn.addEventListener('click', function () {
                addCustomerForm.classList.add('is-hidden');
                addCustomerToggleBtn.classList.remove('is-hidden');
                var errorEl = rootEl.querySelector('#overlay-customer-add-error');
                if (errorEl) errorEl.classList.add('hidden');
            });
        }
        var addCustomerConfirmBtn = rootEl.querySelector('#overlay-customer-add-confirm');
        if (addCustomerConfirmBtn) {
            addCustomerConfirmBtn.addEventListener('click', function () {
                var select = rootEl.querySelector('#overlay-customer-add-select');
                var errorEl = rootEl.querySelector('#overlay-customer-add-error');
                var customerId = select ? select.value : '';
                if (!customerId) {
                    if (errorEl) { errorEl.textContent = 'Select a customer first.'; errorEl.classList.remove('hidden'); }
                    return;
                }
                addCustomerConfirmBtn.disabled = true;
                if (errorEl) errorEl.classList.add('hidden');
                fetch(`/projects/${projectId}/customers/add`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ customer_id: customerId }),
                })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        addCustomerConfirmBtn.disabled = false;
                        if (!data.success) {
                            if (errorEl) { errorEl.textContent = data.error || 'Could not add this customer.'; errorEl.classList.remove('hidden'); }
                            return;
                        }
                        onChanged();
                    })
                    .catch(function () {
                        addCustomerConfirmBtn.disabled = false;
                        if (errorEl) { errorEl.textContent = 'Something went wrong. Please try again.'; errorEl.classList.remove('hidden'); }
                    });
            });
        }

        // ── Manage Customers toggle: swaps the main Details view for the
        // Customers card and swaps the button label.
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

        // ── Cancel/Reactivate Customer (C&CM): each .overlay-customer-item
        // has its own id, reveal form and error box.
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
        // Cancelling a customer requires a reason and a showConfirm() gate.
        // When it's the project's last active customer, the confirm widens
        // to offer cancelling the whole project in the same step.
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

                function doCancel(alsoCancelProject) {
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
                            if (!alsoCancelProject) { onChanged(); return; }
                            // Best-effort: the customer cancel already succeeded;
                            // on failure the user finishes via the sidebar.
                            fetch(`/projects/${projectId}/overlay/cancel`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ reason: reason }),
                            })
                                .then(function (r2) { return r2.json(); })
                                .then(function (data2) {
                                    if (!data2.success) {
                                        alert('The customer was cancelled, but the project could not be cancelled automatically (' + (data2.error || 'unknown error') + '). Use "Cancel Project" in the sidebar to finish.');
                                    }
                                    onChanged();
                                });
                        });
                }

                // Zero other active customers means this is the last one.
                var otherActiveCustomers = 0;
                rootEl.querySelectorAll('.overlay-customer-item').forEach(function (el) {
                    if (el !== item && !el.classList.contains('is-cancelled')) otherActiveCustomers++;
                });

                if (otherActiveCustomers > 0) {
                    window.showConfirm('Cancel this customer? This freezes their state for invoicing until reactivated.', function () { doCancel(false); }, 'Cancel Customer');
                    return;
                }

                // Last active customer: custom confirm with two buttons.
                // Hide the shared OK button; never add a handler to it, since
                // it is reused by every confirm in the app and a leftover
                // handler would fire doCancel() on an unrelated confirm.
                window.showConfirm('', function () { }, 'Cancel Customer');
                var modal = document.getElementById('confirm-modal');
                var modalBody = document.getElementById('confirm-modal-body');
                var okBtn = document.getElementById('confirm-modal-ok');
                var cancelBtnModal = document.getElementById('confirm-modal-cancel');
                var actions = modal ? modal.querySelector('.confirm-modal-actions') : null;
                var card = modal ? modal.querySelector('.confirm-modal-card') : null;
                if (!modal || !modalBody || !actions || !okBtn) { doCancel(false); return; }

                modalBody.innerHTML =
                    '<span class="confirm-modal-message">Cancel this customer? This freezes their state for invoicing until reactivated.</span>' +
                    '<span class="confirm-modal-message">This is the only active customer left on this project — you can cancel the project at the same time instead of doing it as a separate step afterward.</span>';
                modalBody.classList.add('confirm-modal-body--options');
                if (card) card.classList.add('confirm-modal-card--wide');
                okBtn.style.display = 'none';

                var customerOnlyBtn = document.createElement('button');
                customerOnlyBtn.type = 'button';
                customerOnlyBtn.className = 'btn-primary';
                customerOnlyBtn.id = 'overlay-cancel-customer-only-btn';
                customerOnlyBtn.textContent = 'Cancel Customer Only';
                actions.insertBefore(customerOnlyBtn, okBtn);

                var bothBtn = document.createElement('button');
                bothBtn.type = 'button';
                bothBtn.className = 'btn-danger';
                bothBtn.id = 'overlay-cancel-customer-and-project-btn';
                bothBtn.textContent = 'Cancel Customer & Project';
                actions.insertBefore(bothBtn, okBtn);

                function cleanupModalState() {
                    modalBody.classList.remove('confirm-modal-body--options');
                    if (card) card.classList.remove('confirm-modal-card--wide');
                    okBtn.style.display = '';
                    if (customerOnlyBtn.parentNode) customerOnlyBtn.parentNode.removeChild(customerOnlyBtn);
                    if (bothBtn.parentNode) bothBtn.parentNode.removeChild(bothBtn);
                }
                function backdropCleanup(e) { if (e.target === modal) cleanupModalState(); }

                if (_lastCancelCleanup && cancelBtnModal) cancelBtnModal.removeEventListener('click', _lastCancelCleanup);
                if (_lastBackdropCleanup && modal) modal.removeEventListener('click', _lastBackdropCleanup);
                _lastCancelCleanup = cleanupModalState;
                _lastBackdropCleanup = backdropCleanup;
                if (cancelBtnModal) cancelBtnModal.addEventListener('click', cleanupModalState);
                modal.addEventListener('click', backdropCleanup);

                function closeAndRun(alsoCancelProject) {
                    cleanupModalState();
                    modal.classList.add('hidden');
                    if (window.helixPolling) window.helixPolling.resume();
                    doCancel(alsoCancelProject);
                }
                customerOnlyBtn.addEventListener('click', function () { closeAndRun(false); });
                bothBtn.addEventListener('click', function () { closeAndRun(true); });
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