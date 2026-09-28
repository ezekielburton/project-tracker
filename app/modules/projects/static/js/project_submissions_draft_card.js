window.ProjectSubmissionsDraftCard = (function () {
    function escapeHtml(str) {
        var div = document.createElement('div');
        div.textContent = str == null ? '' : String(str);
        return div.innerHTML;
    }

    // Last cleanup listeners bound to the shared #confirm-modal, so the
    // custom modal steps don't stack duplicates. Picker handles live here
    // too so the next init() can destroy them.
    var _lastCancelCleanup = null;
    var _lastBackdropCleanup = null;
    var _deliverablePickerHandle = null;
    var _approvePickerHandle = null;
    var _revisionPickerHandle = null;

    function init(contentEl, projectId, params, refresh) {
        if (!contentEl) return;
         
        // ── Wire rich editors in the new fragment. rich-editor.js only
        // auto-wires on page load and helix:navigated, so call it here.
        // Safe to repeat: initEditor() skips already-wired editors. ──
        if (window.initRichEditors) window.initRichEditors();

        // Destroy the previous picker first: each one adds document-level
        // listeners that would otherwise pile up on every refresh.
        if (_deliverablePickerHandle) {
            _deliverablePickerHandle.destroy();
            _deliverablePickerHandle = null;
        }
        var deliverablePickerEl = contentEl.querySelector('#overlay-submit-review-deliverable-picker');
        if (deliverablePickerEl) {
            _deliverablePickerHandle = window.DeliverablePicker.init(deliverablePickerEl);
        }

        // Mark Approved's picker (starts with nothing selected).
        if (_approvePickerHandle) {
            _approvePickerHandle.destroy();
            _approvePickerHandle = null;
        }
        var approvePickerEl = contentEl.querySelector('#overlay-mark-approved-picker');
        if (approvePickerEl) {
            // Opens above the trigger, centered (deliverable_picker.js).
            approvePickerEl.dataset.popoverAlign = 'above-center';
            _approvePickerHandle = window.DeliverablePicker.init(approvePickerEl);
        }

        if (_revisionPickerHandle) {
            _revisionPickerHandle.destroy();
            _revisionPickerHandle = null;
        }
        var revisionPickerEl = contentEl.querySelector('#overlay-client-revision-picker');
        if (revisionPickerEl) {
            revisionPickerEl.dataset.popoverAlign = 'above-center';
            _revisionPickerHandle = window.DeliverablePicker.init(revisionPickerEl);
        }
        

        var ckvToggle = contentEl.querySelector('#overlay-submit-review-ckv-toggle');
        if (ckvToggle) {
            ckvToggle.querySelectorAll('.overlay-focus-toggle-btn').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    btn.classList.toggle('active');
                });
            });
        }

        // ── Draft / History view toggle. Both panels are server-rendered. ──
        var viewToggleBtns = contentEl.querySelectorAll('.overlay-draft-view-toggle-btn');
        if (viewToggleBtns.length) {
            var draftView = contentEl.querySelector('#overlay-draft-view');
            var historyView = contentEl.querySelector('#overlay-history-view');
            viewToggleBtns.forEach(function (btn) {
                btn.addEventListener('click', function () {
                    viewToggleBtns.forEach(function (b) { b.classList.toggle('active', b === btn); });
                    var showHistory = btn.dataset.view === 'history';
                    if (draftView) draftView.classList.toggle('is-hidden', showHistory);
                    if (historyView) historyView.classList.toggle('is-hidden', !showHistory);
                });
            });
        }

        // ── Scope-level Current / History toggle: swaps the whole working
        // area for the list of decks sent to the client. Both panels are
        // server-rendered. project_submissions_card.js moves these buttons
        // into the header after init(). ──
        var subViewBtns = contentEl.querySelectorAll('.overlay-submissions-view-toggle-btn');
        if (subViewBtns.length) {
            var currentPanel = contentEl.querySelector('#overlay-submissions-current');
            var historyPanel = contentEl.querySelector('#overlay-submissions-history');
            subViewBtns.forEach(function (btn) {
                btn.addEventListener('click', function () {
                    subViewBtns.forEach(function (b) { b.classList.toggle('active', b === btn); });
                    var showHistory = btn.dataset.subView === 'history';
                    if (currentPanel) currentPanel.classList.toggle('is-hidden', showHistory);
                    if (historyPanel) historyPanel.classList.toggle('is-hidden', !showHistory);
                });
            });
        }

        // ── Preview: opens the global file-preview modal (preview.js).
        // Download is a plain <a>, so it needs no JS. ──
        contentEl.querySelectorAll('.overlay-draft-file-preview').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var item = btn.closest('.overlay-reference-file-item');
                var nameEl = item ? item.querySelector('.overlay-reference-file-name') : null;
                window.openFilePreview(
                    btn.dataset.previewUrl,
                    btn.dataset.downloadUrl,
                    nameEl ? nameEl.textContent.trim() : 'file'
                );
            });
        });

        // Collapsed "N deliverables ▾" toggles. The list must be the
        // button's next sibling.
        contentEl.querySelectorAll('.overlay-inc-toggle').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var list = btn.nextElementSibling;
                if (!list) return;
                var open = list.classList.toggle('is-hidden') === false;
                btn.classList.toggle('is-open', open);
                btn.setAttribute('aria-expanded', open ? 'true' : 'false');
            });
        });


        // ── Submit for Review: sends the note plus the deliverable picker
        // or Concept & KV toggles, and locks the draft. ──
        var submitReviewBtn = contentEl.querySelector('#overlay-submit-review-btn');
        if (submitReviewBtn) {
            submitReviewBtn.addEventListener('click', function () {
                var errorEl = contentEl.querySelector('#overlay-submit-review-error');
                var noteEl = contentEl.querySelector('#overlay-submit-review-note');
                var payload = {
                    scope: params.scope || 'ckv',
                    customer_id: params.customer_id || null,
                    note: noteEl ? noteEl.value.trim() : '',
                };

                if (ckvToggle) {
                    payload.includes_concept = !!ckvToggle.querySelector('[data-ckv="concept"].active');
                    payload.includes_kv = !!ckvToggle.querySelector('[data-ckv="kv"].active');
                } else {
                    var ids = _deliverablePickerHandle ? _deliverablePickerHandle.getSelectedIds() : [];
                    payload.deliverable_ids = ids.map(Number);
                }

                submitReviewBtn.disabled = true;
                if (errorEl) errorEl.classList.add('hidden');

                fetch(`/projects/${projectId}/overlay/submissions/draft/submit-for-review`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (!data.success) {
                            submitReviewBtn.disabled = false;
                            if (errorEl) {
                                errorEl.textContent = data.error || 'Could not submit for review.';
                                errorEl.classList.remove('hidden');
                            }
                            return;
                        }
                        refresh();
                    })
                    .catch(function () {
                        submitReviewBtn.disabled = false;
                        if (errorEl) {
                            errorEl.textContent = 'Something went wrong. Please try again.';
                            errorEl.classList.remove('hidden');
                        }
                    });
            });
        }
        // ── CS review row: Flag Internal Revision. ──
        var flagBtn = contentEl.querySelector('#overlay-flag-revision-btn');
        var flagActions = contentEl.querySelector('.overlay-cs-review-actions');
        var flagForm = contentEl.querySelector('#overlay-flag-revision-form');
        var flagConfirmBtn = contentEl.querySelector('#overlay-flag-revision-confirm');
        var flagCancelBtn = contentEl.querySelector('#overlay-flag-revision-cancel');

        if (flagBtn && flagForm) {
            flagBtn.addEventListener('click', function () {
                flagActions.classList.add('is-hidden');
                flagForm.classList.remove('is-hidden');
            });
        }

        if (flagCancelBtn) {
            flagCancelBtn.addEventListener('click', function () {
                flagForm.classList.add('is-hidden');
                flagActions.classList.remove('is-hidden');
                if (window.clearRichContent) window.clearRichContent('overlay-flag-revision-message');
                var errorEl = contentEl.querySelector('#overlay-flag-revision-error');
                if (errorEl) errorEl.classList.add('hidden');
            });
        }

        if (flagConfirmBtn) {
            flagConfirmBtn.addEventListener('click', function () {
                var errorEl = contentEl.querySelector('#overlay-flag-revision-error');
                var message = window.getRichContent ? window.getRichContent('overlay-flag-revision-message') : '';

                if (!message) {
                    if (errorEl) {
                        errorEl.textContent = 'Please describe the revision required.';
                        errorEl.classList.remove('hidden');
                    }
                    return;
                }

                flagConfirmBtn.disabled = true;
                if (errorEl) errorEl.classList.add('hidden');

                fetch(`/projects/${projectId}/overlay/submissions/draft/flag-internal-revision`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        scope: params.scope || 'ckv',
                        customer_id: params.customer_id || null,
                        message: message,
                    }),
                })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (!data.success) {
                            flagConfirmBtn.disabled = false;
                            if (errorEl) {
                                errorEl.textContent = data.error || 'Could not flag this submission.';
                                errorEl.classList.remove('hidden');
                            }
                            return;
                        }
                        refresh();
                    })
                    .catch(function () {
                        flagConfirmBtn.disabled = false;
                        if (errorEl) {
                            errorEl.textContent = 'Something went wrong. Please try again.';
                            errorEl.classList.remove('hidden');
                        }
                    });
            });
        }

        // ── Mark Approved (on the Submitted-to-Client indicator) ──────────
        // With no picker on screen, deliverable_ids is omitted and the
        // server approves everything pending. With a picker, its selection
        // is always sent; the server rejects an empty list.
        var maBtn = contentEl.querySelector('#overlay-mark-approved-btn');
        var maForm = contentEl.querySelector('#overlay-mark-approved-form');
        var maConfirm = contentEl.querySelector('#overlay-mark-approved-confirm');
        var maCancel = contentEl.querySelector('#overlay-mark-approved-cancel');

        if (maBtn && maForm) {
            maBtn.addEventListener('click', function () {
                maBtn.classList.add('is-hidden');
                maForm.classList.remove('is-hidden');
                // One action at a time; Cancel brings Request Client
                // Revision back. (crBtn is declared below; var hoisting.)
                if (crBtn) crBtn.classList.add('is-hidden');
            });
        }

        if (maCancel) {
            maCancel.addEventListener('click', function () {
                maForm.classList.add('is-hidden');
                if (maBtn) maBtn.classList.remove('is-hidden');
                if (crBtn) crBtn.classList.remove('is-hidden');
                var errorEl = contentEl.querySelector('#overlay-mark-approved-error');
                if (errorEl) errorEl.classList.add('hidden');
            });
        }

        if (maConfirm) {
            maConfirm.addEventListener('click', function () {
                var errorEl = contentEl.querySelector('#overlay-mark-approved-error');
                var body = { scope: params.scope || 'ckv', customer_id: params.customer_id || null };
                if (_approvePickerHandle) body.deliverable_ids = _approvePickerHandle.getSelectedIds();
                var noteEl = contentEl.querySelector('#overlay-mark-approved-note');
                if (noteEl) body.note = noteEl.value;

                maConfirm.disabled = true;
                if (errorEl) errorEl.classList.add('hidden');
                fetch(`/projects/${projectId}/overlay/submissions/approve`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (!data.success) {
                            maConfirm.disabled = false;
                            if (errorEl) {
                                errorEl.textContent = data.error || 'Could not approve this submission.';
                                errorEl.classList.remove('hidden');
                            }
                            return;
                        }
                        refresh();
                    })
                    .catch(function () {
                        maConfirm.disabled = false;
                        if (errorEl) {
                            errorEl.textContent = 'Something went wrong. Please try again.';
                            errorEl.classList.remove('hidden');
                        }
                    });
            });
        }

        // ── Request Client Revision (on the Active-with-Client indicator) ──
        // On success, refresh() re-renders the indicator in its "Revision
        // Requested" state.
        var crBtn = contentEl.querySelector('#overlay-client-revision-btn');
        var crForm = contentEl.querySelector('#overlay-client-revision-form');
        var crConfirm = contentEl.querySelector('#overlay-client-revision-confirm');
        var crCancel = contentEl.querySelector('#overlay-client-revision-cancel');

        if (crBtn && crForm) {
            crBtn.addEventListener('click', function () {
                crBtn.classList.add('is-hidden');
                crForm.classList.remove('is-hidden');
                if (maBtn) maBtn.classList.add('is-hidden');
            });
        }

        if (crCancel) {
            crCancel.addEventListener('click', function () {
                crForm.classList.add('is-hidden');
                if (crBtn) crBtn.classList.remove('is-hidden');
                if (maBtn) maBtn.classList.remove('is-hidden');
                if (window.clearRichContent) window.clearRichContent('overlay-client-revision-message');
                var errorEl = contentEl.querySelector('#overlay-client-revision-error');
                if (errorEl) errorEl.classList.add('hidden');
            });
        }

        if (crConfirm) {
            crConfirm.addEventListener('click', function () {
                var errorEl = contentEl.querySelector('#overlay-client-revision-error');
                var message = window.getRichContent ? window.getRichContent('overlay-client-revision-message') : '';
                if (!message) {
                    if (errorEl) {
                        errorEl.textContent = 'Please describe the revision the client requested.';
                        errorEl.classList.remove('hidden');
                    }
                    return;
                }
                var body = {
                    scope: params.scope || 'ckv',
                    customer_id: params.customer_id || null,
                    message: message,
                };
                if (_revisionPickerHandle) body.deliverable_ids = _revisionPickerHandle.getSelectedIds();

                crConfirm.disabled = true;
                if (errorEl) errorEl.classList.add('hidden');
                fetch(`/projects/${projectId}/overlay/submissions/client-revision`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (!data.success) {
                            crConfirm.disabled = false;
                            if (errorEl) {
                                errorEl.textContent = data.error || 'Could not request a client revision.';
                                errorEl.classList.remove('hidden');
                            }
                            return;
                        }
                        refresh();
                    })
                    .catch(function () {
                        crConfirm.disabled = false;
                        if (errorEl) {
                            errorEl.textContent = 'Something went wrong. Please try again.';
                            errorEl.classList.remove('hidden');
                        }
                    });
            });
        }

        // ── Submit to Client ────────────────────────────────────
        // Fetches the summary as a modal; confirm POSTs and refresh()es into
        // the read-only Sent-to-Client state.
        var submitToClientBtn = contentEl.querySelector('#overlay-submit-to-client-btn');
        if (submitToClientBtn) {
            submitToClientBtn.addEventListener('click', function () {
                var scope = params.scope || 'ckv';
                var customerId = params.customer_id || '';
                submitToClientBtn.disabled = true;
                fetch(`/projects/${projectId}/overlay/submissions/submit-summary`
                    + `?scope=${encodeURIComponent(scope)}&customer_id=${encodeURIComponent(customerId)}`)
                    .then(function (res) {
                        if (!res.ok) {
                            return res.json().then(function (data) {
                                alert(data.error || 'Could not open the submission summary.');
                                return null;
                            });
                        }
                        return res.text();
                    })
                    .then(function (html) {
                        submitToClientBtn.disabled = false;
                        if (html) showSubmitSummaryModal(html, scope, customerId);
                    })
                    .catch(function () {
                        submitToClientBtn.disabled = false;
                        alert('Something went wrong opening the summary.');
                    });
            });
        }

        function closeSubmitSummaryModal(modal) {
            if (modal && modal.parentNode) modal.parentNode.removeChild(modal);
            if (window.helixPolling) window.helixPolling.resume();
        }

        function showSubmitSummaryModal(html, scope, customerId) {
            // Mount on <body> so the fixed modal escapes the overlay's
            // stacking and clipping context.
            var stale = document.getElementById('overlay-submit-summary-modal');
            if (stale && stale.parentNode) stale.parentNode.removeChild(stale);

            var wrapper = document.createElement('div');
            wrapper.innerHTML = html;
            var modal = wrapper.querySelector('#overlay-submit-summary-modal');
            if (!modal) return;
            document.body.appendChild(modal);
            if (window.helixPolling) window.helixPolling.pause();

            var cancelBtn = modal.querySelector('#overlay-submit-summary-cancel');
            var confirmBtn = modal.querySelector('#overlay-submit-summary-confirm');
            var errorEl = modal.querySelector('#overlay-submit-summary-error');
            var keepRevisionEl = modal.querySelector('#overlay-submit-summary-keep-revision');

            if (cancelBtn) {
                cancelBtn.addEventListener('click', function () { closeSubmitSummaryModal(modal); });
            }
            modal.addEventListener('click', function (e) {
                if (e.target === modal) closeSubmitSummaryModal(modal);
            });

            if (confirmBtn) {
                confirmBtn.addEventListener('click', function () {
                    confirmBtn.disabled = true;
                    if (errorEl) errorEl.classList.add('hidden');
                    fetch(`/projects/${projectId}/overlay/submissions/draft/submit-to-client`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            scope: scope, customer_id: customerId || null,
                            keep_revision_label: !!(keepRevisionEl && keepRevisionEl.checked),
                        }),
                    })
                        .then(function (r) { return r.json(); })
                        .then(function (data) {
                            if (!data.success) {
                                confirmBtn.disabled = false;
                                if (errorEl) {
                                    errorEl.textContent = data.error || 'Could not submit to client.';
                                    errorEl.classList.remove('hidden');
                                }
                                return;
                            }
                            closeSubmitSummaryModal(modal);
                            refresh();
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
        }

        // ── Upload ──────────────────────────────────────────────
        var uploadBtn = contentEl.querySelector('#overlay-draft-file-btn');
        var uploadInput = contentEl.querySelector('#overlay-draft-file-input');
        if (uploadBtn && uploadInput) {
            uploadBtn.addEventListener('click', function () { uploadInput.click(); });
            uploadInput.addEventListener('change', function () {
                var file = uploadInput.files[0];
                if (file) uploadFile(file);
            });
        }

        function uploadFile(file) {
            var status = contentEl.querySelector('#overlay-draft-file-status');
            if (status) status.textContent = 'Uploading...';
            var formData = new FormData();
            formData.append('file', file);
            formData.append('scope', params.scope || 'ckv');
            if (params.customer_id) formData.append('customer_id', params.customer_id);

            fetch(`/projects/${projectId}/overlay/submissions/draft/upload`, { method: 'POST', body: formData })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.success) {
                        if (status) status.textContent = '';
                        alert(data.error || 'File could not be saved.');
                        return;
                    }
                    refresh();
                })
                .catch(function () {
                    if (status) status.textContent = '';
                    alert('Upload failed. Please try again.');
                });
        }

        enableDragAndDrop();

        // ── Main deck toggle ──────────
        // Flips the highlight optimistically, then (after the request and a
        // short pause) re-fetches the sorted list and FLIP-animates rows.
        contentEl.querySelectorAll('.overlay-draft-main-deck-btn:not([disabled])').forEach(function (btn) {
            btn.addEventListener('click', function () { promoteMainDeck(btn); });
        });

        function promoteMainDeck(btn) {
            var fileId = btn.dataset.fileId;
            var list = contentEl.querySelector('#overlay-draft-files-list');
            var newItem = list ? list.querySelector('.overlay-reference-file-item[data-file-id="' + fileId + '"]') : null;
            var oldItem = list ? list.querySelector('.overlay-draft-file-item--main-deck') : null;

            flipMainDeckVisuals(newItem, oldItem);

            var request = fetch(`/projects/${projectId}/overlay/submissions/draft/file/${fileId}/set-main-deck`, { method: 'POST' })
                .then(function (r) { return r.json(); });
            var settle = new Promise(function (resolve) { setTimeout(resolve, 350); });

            Promise.all([request, settle]).then(function (results) {
                var data = results[0];
                if (!data.success) {
                    alert(data.error || 'Could not update main deck.');
                    refresh();
                    return;
                }
                reorderAndRefresh(list);
            }).catch(function () {
                alert('Something went wrong. Please try again.');
                refresh();
            });
        }

        function flipMainDeckVisuals(newItem, oldItem) {
            if (newItem) {
                newItem.classList.add('overlay-draft-file-item--main-deck');
                var newBtn = newItem.querySelector('.overlay-draft-main-deck-btn');
                if (newBtn) {
                    newBtn.textContent = 'Main Deck';
                    newBtn.classList.add('overlay-draft-main-deck-btn--active');
                    newBtn.disabled = true;
                }
            }
            if (oldItem && oldItem !== newItem) {
                oldItem.classList.remove('overlay-draft-file-item--main-deck');
                var oldBtn = oldItem.querySelector('.overlay-draft-main-deck-btn');
                if (oldBtn) {
                    oldBtn.textContent = 'Set as Main Deck';
                    oldBtn.classList.remove('overlay-draft-main-deck-btn--active');
                    oldBtn.disabled = false;
                }
            }
        }

        function reorderAndRefresh(list) {
            var firstRects = {};
            if (list) {
                list.querySelectorAll('.overlay-reference-file-item').forEach(function (el) {
                    firstRects[el.dataset.fileId] = el.getBoundingClientRect();
                });
            }
            // Reload through the card's refresh so the Current/History toggle
            // lands in the header slot like any other load; animate after that.
            refresh(function () { animateReorder(firstRects); });
        }

        function animateReorder(firstRects) {
            var newList = contentEl.querySelector('#overlay-draft-files-list');
            if (!newList) return;
            newList.querySelectorAll('.overlay-reference-file-item').forEach(function (el) {
                var oldRect = firstRects[el.dataset.fileId];
                if (!oldRect) return;
                var newRect = el.getBoundingClientRect();
                var dy = oldRect.top - newRect.top;
                if (!dy) return;
                el.style.transition = 'none';
                el.style.transform = 'translateY(' + dy + 'px)';
                requestAnimationFrame(function () {
                    requestAnimationFrame(function () {
                        el.style.transition = 'transform 0.35s ease';
                        el.style.transform = '';
                        el.addEventListener('transitionend', function () {
                            el.style.transition = '';
                        }, { once: true });
                    });
                });
            });
        }

        // ── Remove: a standard confirm. Removing the main deck while other
        // files remain returns 409, and #confirm-modal reopens to pick a
        // replacement. ─────────────────────────
        contentEl.querySelectorAll('.overlay-draft-file-remove').forEach(function (btn) {
            btn.addEventListener('click', function () {
                showConfirm('Remove this file from the draft? This cannot be undone.', function () {
                    removeFile(btn.dataset.fileId);
                });
            });
        });

        function removeFile(fileId, extraBody) {
            var body = extraBody || new URLSearchParams();
            fetch(`/projects/${projectId}/overlay/submissions/draft/file/${fileId}/remove`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: body,
            })
                .then(function (r) { return r.json().then(function (data) { return { status: r.status, data: data }; }); })
                .then(function (result) {
                    if (result.status === 409) {
                        showResolveStep(fileId, result.data.other_files || []);
                        return;
                    }
                    if (!result.data.success) { alert(result.data.error || 'Could not remove file.'); return; }
                    refresh();
                })
                .catch(function () { alert('Something went wrong. Please try again.'); });
        }

        function showResolveStep(fileId, otherFiles) {
            var optionsHtml = otherFiles.map(function (f) {
                return '<button type="button" class="btn-secondary overlay-draft-resolve-option" data-promote-id="' + f.id + '">' + escapeHtml(f.original_filename) + '</button>';
            }).join('');

            window.showConfirm('', function () { }, 'Choose a new main deck');

            var modal = document.getElementById('confirm-modal');
            var body = document.getElementById('confirm-modal-body');
            var okBtn = document.getElementById('confirm-modal-ok');
            var cancelBtn = document.getElementById('confirm-modal-cancel');
            var card = modal ? modal.querySelector('.confirm-modal-card') : null;
            if (!modal || !body) return;

            body.innerHTML =
                '<span class="confirm-modal-message">This file is the main deck — pick a replacement before removing it, or upload a new one.</span>' +
                '<span class="overlay-draft-resolve-options">' + optionsHtml +
                '<button type="button" class="btn-secondary" id="overlay-draft-resolve-upload-btn">Upload a new file</button>' +
                '</span>' +
                '<input type="file" id="overlay-draft-resolve-upload-input" class="hidden">';

            body.classList.add('confirm-modal-body--options');
            if (card) card.classList.add('confirm-modal-card--wide');
            if (okBtn) okBtn.style.display = 'none';

            function cleanupModalState() {
                body.classList.remove('confirm-modal-body--options');
                if (card) card.classList.remove('confirm-modal-card--wide');
                if (okBtn) okBtn.style.display = '';
            }
            function backdropCleanup(e) {
                if (e.target === modal) cleanupModalState();
            }

            if (_lastCancelCleanup && cancelBtn) cancelBtn.removeEventListener('click', _lastCancelCleanup);
            if (_lastBackdropCleanup && modal) modal.removeEventListener('click', _lastBackdropCleanup);
            _lastCancelCleanup = cleanupModalState;
            _lastBackdropCleanup = backdropCleanup;
            if (cancelBtn) cancelBtn.addEventListener('click', cleanupModalState);
            modal.addEventListener('click', backdropCleanup);

            body.querySelectorAll('.overlay-draft-resolve-option').forEach(function (optBtn) {
                optBtn.addEventListener('click', function () {
                    var promoteBody = new URLSearchParams();
                    promoteBody.set('new_main_deck_file_id', optBtn.dataset.promoteId);
                    cleanupModalState();
                    modal.classList.add('hidden');
                    if (window.helixPolling) window.helixPolling.resume();
                    removeFile(fileId, promoteBody);
                });
            });

            var uploadBtn2 = body.querySelector('#overlay-draft-resolve-upload-btn');
            var uploadInput2 = body.querySelector('#overlay-draft-resolve-upload-input');
            uploadBtn2.addEventListener('click', function () { uploadInput2.click(); });
            uploadInput2.addEventListener('change', function () {
                var file = uploadInput2.files[0];
                if (!file) return;
                var formData = new FormData();
                formData.append('file', file);
                cleanupModalState();
                modal.classList.add('hidden');
                if (window.helixPolling) window.helixPolling.resume();
                fetch(`/projects/${projectId}/overlay/submissions/draft/file/${fileId}/remove`, { method: 'POST', body: formData })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (!data.success) { alert(data.error || 'Could not remove file.'); return; }
                        refresh();
                    });
            });
        }
        // ── Edit: designer reopens a locked (internal_review) draft, with a
        // required reason. Uses its own submit button because the shared
        // OK button always closes the modal and can't validate. ──
        var editBtn = contentEl.querySelector('#overlay-draft-edit-btn');
        if (editBtn) {
            editBtn.addEventListener('click', function () { showEditReasonStep(); });
        }

        function showEditReasonStep() {
            window.showConfirm('', function () { }, 'Edit this submission');

            var modal = document.getElementById('confirm-modal');
            var body = document.getElementById('confirm-modal-body');
            var okBtn = document.getElementById('confirm-modal-ok');
            var cancelBtn = document.getElementById('confirm-modal-cancel');
            var actions = modal ? modal.querySelector('.confirm-modal-actions') : null;
            var card = modal ? modal.querySelector('.confirm-modal-card') : null;
            if (!modal || !body || !actions) return;

            body.innerHTML =
                '<span class="confirm-modal-message">This submission is locked for internal review. Editing will reopen it for changes — describe what you\'re fixing.</span>' +
                '<textarea class="overlay-edit-reason-input" id="overlay-edit-reason-input" rows="3" placeholder="What are you changing?"></textarea>' +
                '<span class="overlay-edit-reason-error hidden" id="overlay-edit-reason-error"></span>';

            body.classList.add('confirm-modal-body--options');
            if (card) card.classList.add('confirm-modal-card--wide');
            if (okBtn) okBtn.style.display = 'none';

            // Placed in the actions row where OK normally sits.
            var submitBtn = document.createElement('button');
            submitBtn.type = 'button';
            submitBtn.className = 'btn-primary';
            submitBtn.id = 'overlay-edit-reason-submit';
            submitBtn.textContent = 'Confirm Edit';
            actions.insertBefore(submitBtn, okBtn);

            function cleanupModalState() {
                body.classList.remove('confirm-modal-body--options');
                if (card) card.classList.remove('confirm-modal-card--wide');
                if (okBtn) okBtn.style.display = '';
                if (submitBtn && submitBtn.parentNode) submitBtn.parentNode.removeChild(submitBtn);
            }
            function backdropCleanup(e) {
                if (e.target === modal) cleanupModalState();
            }

            if (_lastCancelCleanup && cancelBtn) cancelBtn.removeEventListener('click', _lastCancelCleanup);
            if (_lastBackdropCleanup && modal) modal.removeEventListener('click', _lastBackdropCleanup);
            _lastCancelCleanup = cleanupModalState;
            _lastBackdropCleanup = backdropCleanup;
            if (cancelBtn) cancelBtn.addEventListener('click', cleanupModalState);
            modal.addEventListener('click', backdropCleanup);

            var reasonInput = body.querySelector('#overlay-edit-reason-input');
            var errorEl = body.querySelector('#overlay-edit-reason-error');

            submitBtn.addEventListener('click', function () {
                var reason = reasonInput.value.trim();
                if (!reason) {
                    errorEl.textContent = 'A reason is required.';
                    errorEl.classList.remove('hidden');
                    reasonInput.focus();
                    return;
                }
                submitBtn.disabled = true;

                fetch(`/projects/${projectId}/overlay/submissions/draft/edit`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        scope: params.scope || 'ckv',
                        customer_id: params.customer_id || null,
                        reason: reason,
                    }),
                })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (!data.success) {
                            submitBtn.disabled = false;
                            errorEl.textContent = data.error || 'Could not start editing.';
                            errorEl.classList.remove('hidden');
                            return;
                        }
                        cleanupModalState();
                        modal.classList.add('hidden');
                        if (window.helixPolling) window.helixPolling.resume();
                        refresh();
                    })
                    .catch(function () {
                        submitBtn.disabled = false;
                        errorEl.textContent = 'Something went wrong. Please try again.';
                        errorEl.classList.remove('hidden');
                    });
            });
        }
    }
    
    return { init: init };
})();