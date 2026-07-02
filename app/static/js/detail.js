// detail.js — Vitamin-E
// Project detail page: post-redirect toast, expandable rows, status dropdowns,
// submission flow, C&KV, POSM channels, start project, lead designer, channel uploads.
// Depends on: showToast(), showConfirm() — defined in main.js.
//             openApprovalModal() — defined in detail.html inline script block.
// Loaded after main.js.

    // ── Post-redirect Toast ──────────────────────────────────────
    var urlParams = new URLSearchParams(window.location.search);
    var toastMsg = urlParams.get('toast');
    if (toastMsg) {
        showToast(decodeURIComponent(toastMsg), 'success');
    }

    // ── Expandable customer rows ──────────────────────────────
    document.querySelectorAll('tr[data-expand]').forEach(function (row) {
        row.addEventListener('click', function (e) {
            if (e.target.closest('a, button, select')) return;
            var expandRow = this.nextElementSibling;
            if (!expandRow || !expandRow.classList.contains('expansion-row')) return;
            expandRow.classList.toggle('hidden');
            var icon = this.querySelector('.chevron-icon');
            if (icon) icon.classList.toggle('rotated');
            var expandRow = this.nextElementSibling;
        });
    });

    // ── Status dropdowns ─────────────────────────────────────
    function updateStatus(select) {
        var url = select.dataset.url;
        var status = select.value;
        fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: status })
        })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.error) {
                    showToast(data.error, 'error');
                } else {
                    applyStatusClass(select, status);
                    showToast('Status updated', 'success');
                }
            })
            .catch(function () {
                showToast('Something went wrong', 'error');
            });
    }



    function applyStatusClass(select, status) {
        // Full list of status classes — must include every value that appears in any dropdown
        var classes = [
            's-briefed', 's-in_queue', 's-in_progress', 's-submitted',
            's-internal_review', 's-internal_revision', 's-submitted_to_client',
            's-revision_in_queue', 's-revision_in_progress', 's-approved', 's-on_hold'
        ];
        select.classList.remove.apply(select.classList, classes);
        select.classList.add('s-' + status);
    }

    document.querySelectorAll('.status-select').forEach(function (select) {
        applyStatusClass(select, select.value);
    });

    function flagRevision(deliverableId, projectId) {
        var url = '/projects/' + projectId + '/deliverable/' + deliverableId + '/flag-revision';
        fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' } })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.error) {
                    showToast(data.error, 'error');
                } else {
                    showToast('Deliverable flagged for revision', 'warning');
                    // Swap the flag button for the Flagged badge and update the status dropdown
                    var btn = document.querySelector('[onclick="flagRevision(' + deliverableId + ', ' + projectId + ')"]');
                    if (btn) {
                        var badge = document.createElement('span');
                        badge.className = 'revision-flagged-badge';
                        badge.textContent = '⚑ Flagged';
                        btn.replaceWith(badge);
                    }
                    // Update the status dropdown to revision_in_queue
                    var row = document.querySelector('[data-url*="/deliverable/' + deliverableId + '/set-status"]');
                    if (row) {
                        row.value = 'revision_in_queue';
                        applyStatusClass(row, 'revision_in_queue');
                    }
                }
            })
            .catch(function () { showToast('Something went wrong', 'error'); });
    }

    // ── Client Submission ─────────────────────────────────────────────────────────

    // ── Client Submission Flow ────────────────────────────────────────────────────
    // Pull project ID from the URL — detail page is always at /projects/<id>
    var detailProjectId = parseInt(window.location.pathname.split('/')[2]);

    // ── Step 1: Upload deck ───────────────────────────────────────────────────────
    // The designer clicks "Upload Client Deck" or "Reupload Deck", picks a file,
    // and we POST it to the server. On success the page reloads into State 2
    // (deliverable picker) with the new submission pre-selected.
    var submissionUploadBtn = document.getElementById('submissionUploadBtn');
    var submissionFileInput = document.getElementById('submissionFileInput');
    var submissionUploadStatus = document.getElementById('submissionUploadStatus');

    if (submissionUploadBtn && submissionFileInput) {
        submissionUploadBtn.addEventListener('click', function () {
            submissionFileInput.click();
        });

        submissionFileInput.addEventListener('change', function () {
            var file = submissionFileInput.files[0];
            if (!file) return;

            submissionUploadStatus.textContent = 'Uploading...';

            var formData = new FormData();
            formData.append('file', file);

            fetch('/projects/' + detailProjectId + '/submission/upload', {
                method: 'POST',
                body: formData
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.success) {
                        submissionUploadStatus.textContent = 'Error: ' + data.error;
                        return;
                    }
                    // Reload so the template renders the correct state (State 2: picker)
                    window.location.reload();
                })
                .catch(function () {
                    submissionUploadStatus.textContent = 'Upload failed.';
                });
        });
    }

    // ── Shared deliverable picker builder ────────────────────────────────────────
    // Used by both the submission picker (State 2) and the revision picker (State 5).
    // Renders checkboxes into `containerEl`, defaulting all to checked.
    // For CCM briefs (deliverables have customer_name), groups by customer with
    // per-customer Select/Deselect All buttons rendered inside a bordered box.
    // `globalSelectEl` and `globalDeselectEl` wire up the global controls (optional).
    function buildPickerInto(containerEl, globalSelectEl, globalDeselectEl, filterCustomerIds) {
        if (!containerEl || !window.PAGE.projectDeliverables) return;

        var deliverables = window.PAGE.projectDeliverables;

        // Approved deliverables are locked — exclude from the picker entirely
        deliverables = deliverables.filter(function (d) { return d.status !== 'approved'; });

        // If a customer ID filter is provided, restrict to only those customers' deliverables
        if (filterCustomerIds && filterCustomerIds.length > 0) {
            var _idSet = {};
            filterCustomerIds.forEach(function (id) { _idSet[id] = true; });
            deliverables = deliverables.filter(function (d) { return d.customer_id && _idSet[d.customer_id]; });
        }

        // One checkbox row: a <label class="picker-row"> containing a checkbox + name span.
        function makeRow(d) {
            var label = document.createElement('label');
            label.className = 'picker-row';
            var cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.value = d.id;
            cb.checked = true;
            cb.dataset.deliverableId = d.id;
            var span = document.createElement('span');
            span.textContent = d.name;
            label.appendChild(cb);
            label.appendChild(span);
            return label;
        }

        var isCCM = deliverables.some(function (d) { return d.customer_name; });

        if (isCCM) {
            // CCM brief: group deliverables by customer, render one bordered box per customer
            // with per-group Select All / Deselect All buttons above the checkbox rows.
            var groups = {}, order = [];
            deliverables.forEach(function (d) {
                var key = d.customer_id || '__none__';
                if (!groups[key]) {
                    groups[key] = { name: d.customer_name || 'Other', items: [] };
                    order.push(key);
                }
                groups[key].items.push(d);
            });
            order.forEach(function (key) {
                var g = groups[key];
                // Bordered box wrapping one customer's deliverables
                var wrap = document.createElement('div');
                wrap.style.cssText = 'border:1px solid var(--border);border-radius:6px;padding:0.65rem 0.75rem;margin-bottom:0.5rem;';
                // Customer name header
                var header = document.createElement('div');
                header.style.cssText = 'font-size:0.7rem;font-weight:700;letter-spacing:0.06em;color:var(--tangerine);text-transform:uppercase;margin-bottom:0.4rem;';
                header.textContent = g.name;
                wrap.appendChild(header);
                // Per-group Select All / Deselect All
                var actions = document.createElement('div');
                actions.style.cssText = 'display:flex;gap:0.4rem;margin-bottom:0.4rem;';
                var selAll = document.createElement('button');
                selAll.type = 'button';
                selAll.className = 'btn-secondary btn-sm';
                selAll.textContent = 'Select All';
                var deselAll = document.createElement('button');
                deselAll.type = 'button';
                deselAll.className = 'btn-secondary btn-sm';
                deselAll.textContent = 'Deselect All';
                selAll.addEventListener('click', function () {
                    wrap.querySelectorAll('input[type="checkbox"]').forEach(function (cb) { cb.checked = true; });
                });
                deselAll.addEventListener('click', function () {
                    wrap.querySelectorAll('input[type="checkbox"]').forEach(function (cb) { cb.checked = false; });
                });
                actions.appendChild(selAll);
                actions.appendChild(deselAll);
                wrap.appendChild(actions);
                // Deliverable rows
                g.items.forEach(function (d) { wrap.appendChild(makeRow(d)); });
                containerEl.appendChild(wrap);
            });
        } else {
            // Standard brief: flat list with optional global Select / Deselect All controls
            deliverables.forEach(function (d) { containerEl.appendChild(makeRow(d)); });
            if (globalSelectEl) {
                globalSelectEl.addEventListener('click', function () {
                    containerEl.querySelectorAll('input[type="checkbox"]').forEach(function (cb) { cb.checked = true; });
                });
            }
            if (globalDeselectEl) {
                globalDeselectEl.addEventListener('click', function () {
                    containerEl.querySelectorAll('input[type="checkbox"]').forEach(function (cb) { cb.checked = false; });
                });
            }
        }
    }

    // ── Step 2: Deliverable picker (submission) ───────────────────────────────────
    // Shown in State 2 (deck uploaded, not yet in review).
    // For CCM briefs this is the concept/KV phase — only Concept and Initial KV
    // campaign assets are selectable. Regular deliverables are handled per-customer
    // during the POSM phase via the channel pickers (ch-picker-list-*).
    // For Standard briefs this renders the flat deliverable list via buildPickerInto.
    (function () {
        var pickerList = document.getElementById('pickerList');
        if (!pickerList) return;

        var selAll = document.getElementById('pickerSelectAll');
        var deselAll = document.getElementById('pickerDeselectAll');

        if (window.PAGE.projectHasConcept || window.PAGE.projectHasKV) {
            // CCM concept/KV phase: only show campaign asset checkboxes
            function makeCampaignRow(value, label) {
                var lbl = document.createElement('label');
                lbl.className = 'picker-row picker-row--campaign';
                var cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.value = value;
                cb.checked = true;
                var span = document.createElement('span');
                span.textContent = label;
                lbl.appendChild(cb);
                lbl.appendChild(span);
                return lbl;
            }
            if (window.PAGE.projectHasConcept && window.PAGE.projectHasKV) {
                pickerList.appendChild(makeCampaignRow('__concept__', 'Concept & KV'));
            } else {
                if (window.PAGE.projectHasConcept) pickerList.appendChild(makeCampaignRow('__concept__', 'Concept'));
                if (window.PAGE.projectHasKV) pickerList.appendChild(makeCampaignRow('__kv__', 'Initial KV'));
            }

            // Wire global Select / Deselect All to the campaign rows
            if (selAll) selAll.addEventListener('click', function () { pickerList.querySelectorAll('input').forEach(function (cb) { cb.checked = true; }); });
            if (deselAll) deselAll.addEventListener('click', function () { pickerList.querySelectorAll('input').forEach(function (cb) { cb.checked = false; }); });
        } else {
            // Standard brief: flat deliverable list (no customer grouping)
            buildPickerInto(pickerList, selAll, deselAll);
        }
    })();

    // ── Step 2 → 3: Submit for Internal Review ───────────────────────────────────
    // Designer confirms the deliverable selection and sends the deck to CS.
    // We collect the checked deliverable IDs and POST them along with the
    // submission ID to /submission/submit-for-review.
    var submissionSubmitForReviewBtn = document.getElementById('submissionSubmitForReviewBtn');
    if (submissionSubmitForReviewBtn) {
        submissionSubmitForReviewBtn.addEventListener('click', function () {
            var submissionId = parseInt(this.dataset.submissionId);
            var pickerList = document.getElementById('pickerList');

            // Collect checked deliverable IDs and concept/KV flags
            var checked = [];
            var includesConcept = false;
            var includesKV = false;
            if (pickerList) {
                pickerList.querySelectorAll('input[type="checkbox"]:checked').forEach(function (cb) {
                    if (cb.value === '__concept__') includesConcept = true;
                    else if (cb.value === '__kv__') includesKV = true;
                    else checked.push(parseInt(cb.value));
                });
            }
            // When merged Concept & KV row is checked (value=__concept__) and project has KV, include KV too
            if (includesConcept && window.PAGE.projectHasKV) includesKV = true;

            if (checked.length === 0 && !includesConcept && !includesKV) {
                showToast('Select at least one item to include.', 'error');
                return;
            }

            btnLoading(submissionSubmitForReviewBtn);

            // Collect Gulf POSM region + customer.
            // C&KV submissions (includesConcept/includesKV) bypass this — they have
            // no POSM country and are routed through the concept_kv phase instead.
            var posmCountry = null;
            var posmCustomerId = null;
            if (window.PAGE.posmActive && !includesConcept && !includesKV) {
                var posmRegionSel = document.getElementById('posmRegionSelect');
                var posmCustomerSel = document.getElementById('posmCustomerSelect');
                posmCountry = posmRegionSel ? (posmRegionSel.value || null) : null;
                posmCustomerId = posmCustomerSel ? (parseInt(posmCustomerSel.value) || null) : null;
                if (!posmCountry && !posmCustomerId) {
                    showToast('Select a region before submitting POSM.', 'error');
                    return;
                }
            }

            fetch('/projects/' + detailProjectId + '/submission/submit-for-review', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    submission_id: submissionId,
                    deliverable_ids: checked,
                    includes_concept: includesConcept,
                    includes_kv: includesKV,
                    posm_country: posmCountry,
                    posm_customer_id: posmCustomerId
                })
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.success) {
                        showToast(data.error || 'Could not submit for review.', 'error');
                        btnDone(submissionSubmitForReviewBtn);
                        return;
                    }
                    showToast('Submitted for internal review. CS has been notified.', 'success');
                    // Reload so the template renders State 3 (internal review) with CS buttons
                    window.location.reload();
                })
                .catch(function () {
                    showToast('Something went wrong.', 'error');
                    btnDone(submissionSubmitForReviewBtn);
                });
        });
    }

    // ── Step 3a: CS flags the deck ───────────────────────────────────────────────
    // CS clicks "Flag Issue" → flag form slides in → they write a reason →
    // "Send Flag" POSTs to /submission/flag → page reloads into State 4.
    var submissionFlagBtn = document.getElementById('submissionFlagBtn');
    var submissionFlagForm = document.getElementById('submissionFlagForm');
    var submissionFlagCancel = document.getElementById('submissionFlagCancel');

    if (submissionFlagBtn) {
        submissionFlagBtn.addEventListener('click', function () {
            submissionFlagForm.classList.remove('hidden');
            submissionFlagBtn.classList.add('hidden');
        });
    }

    if (submissionFlagCancel) {
        submissionFlagCancel.addEventListener('click', function () {
            submissionFlagForm.classList.add('hidden');
            submissionFlagBtn.classList.remove('hidden');
            document.getElementById('submissionFlagMessage').value = '';
        });
    }

    var submissionFlagConfirm = document.getElementById('submissionFlagConfirm');
    if (submissionFlagConfirm) {
        submissionFlagConfirm.addEventListener('click', function () {
            var message = document.getElementById('submissionFlagMessage').value.trim();
            if (!message) {
                showToast('Please describe the issue before flagging.', 'error');
                return;
            }

            btnLoading(submissionFlagConfirm);

            fetch('/projects/' + detailProjectId + '/submission/flag', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: message })
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.success) {
                        showToast(data.error, 'error');
                        btnDone(submissionFlagConfirm);
                        return;
                    }
                    // Reload so the flagged banner shows and designer sees "Reupload Deck"
                    window.location.reload();
                })
                .catch(function () {
                    showToast('Something went wrong.', 'error');
                    btnDone(submissionFlagConfirm);
                });
        });
    }

    // ── Step 3b: CS submits to client ────────────────────────────────────────────
    // CS clicks "Submit to Client" → all deliverables → submitted_to_client,
    // then optionally opens a mailto to draft the email.
    var submissionSubmitBtn = document.getElementById('submissionSubmitBtn');
    if (submissionSubmitBtn) {
        submissionSubmitBtn.addEventListener('click', function () {
            var projectName = this.dataset.projectName;

            btnLoading(submissionSubmitBtn);

            fetch('/projects/' + detailProjectId + '/submission/submit-to-client', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.success) {
                        showToast(data.error, 'error');
                        btnDone(submissionSubmitBtn);
                        return;
                    }

                    showToast('Project submitted to client.', 'success');

                    // Offer to open Outlook with a pre-filled subject line via custom modal.
                    var emailModal = document.getElementById('email-draft-modal');
                    var emailYes = document.getElementById('emailDraftYes');
                    var emailNo = document.getElementById('emailDraftNo');
                    if (emailModal && emailYes && emailNo) {
                        emailModal.classList.remove('hidden');
                        var subject = encodeURIComponent(data.project_name);
                        var body = encodeURIComponent('Please find attached the latest client deck for ' + data.project_name + '.\n\nBest regards,');
                        var mailto = 'mailto:' + (data.client_email || '') + '?subject=' + subject + '&body=' + body;
                        emailYes.onclick = function () {
                            emailModal.classList.add('hidden');
                            window.open(mailto);
                            window.location.reload();
                        };
                        emailNo.onclick = function () {
                            emailModal.classList.add('hidden');
                            window.location.reload();
                        };
                    } else {
                        window.location.reload();
                    }
                })
                .catch(function () {
                    showToast('Something went wrong.', 'error');
                    btnDone(submissionSubmitBtn);
                });
        });
    }

    // ── Step 5: CS sends revision request ────────────────────────────────────────
    // Shown in State 5 (submitted_to_client). CS clicks "Send for Revision" →
    // revision form slides in with a free-text field and a deliverable picker.
    // On confirm: POSTs to /send-revision → project → revision_in_queue.
    (function () {
        var sendRevisionBtn = document.getElementById('sendRevisionBtn');
        var sendRevisionForm = document.getElementById('sendRevisionForm');
        var sendRevisionCancel = document.getElementById('sendRevisionCancel');
        var sendRevisionConfirm = document.getElementById('sendRevisionConfirm');
        var revisionPickerList = document.getElementById('revisionPickerList');

        if (!sendRevisionBtn) return; // not in submitted_to_client state

        var pickerBuilt = false; // lazy-build the picker only once

        sendRevisionBtn.addEventListener('click', function () {
            sendRevisionForm.classList.remove('hidden');
            sendRevisionBtn.classList.add('hidden');

            // Build the revision picker the first time the form is opened.
            // C&CM concept/KV phase: only Concept and/or KV can be revised (deliverables
            // are not yet in play — POSM hasn't started). Standard briefs and POSM phase
            // show the full deliverable picker via buildPickerInto.
            if (!pickerBuilt && revisionPickerList) {
                if (!window.PAGE.posmActive && (window.PAGE.projectHasConcept || window.PAGE.projectHasKV)) {
                    function makeRevCampaignRow(value, label) {
                        var lbl = document.createElement('label');
                        lbl.className = 'picker-row picker-row--campaign';
                        var cb = document.createElement('input');
                        cb.type = 'checkbox';
                        cb.value = value;
                        cb.checked = true;
                        var span = document.createElement('span');
                        span.textContent = label;
                        lbl.appendChild(cb);
                        lbl.appendChild(span);
                        return lbl;
                    }
                    if (window.PAGE.projectHasConcept && window.PAGE.projectHasKV) {
                        revisionPickerList.appendChild(makeRevCampaignRow('__concept__', 'Concept & KV'));
                    } else {
                        if (window.PAGE.projectHasConcept) revisionPickerList.appendChild(makeRevCampaignRow('__concept__', 'Concept'));
                        if (window.PAGE.projectHasKV) revisionPickerList.appendChild(makeRevCampaignRow('__kv__', 'Initial KV'));
                    }
                    var revSelAll = document.getElementById('revisionPickerSelectAll');
                    var revDeselAll = document.getElementById('revisionPickerDeselectAll');
                    if (revSelAll) revSelAll.addEventListener('click', function () { revisionPickerList.querySelectorAll('input').forEach(function (cb) { cb.checked = true; }); });
                    if (revDeselAll) revDeselAll.addEventListener('click', function () { revisionPickerList.querySelectorAll('input').forEach(function (cb) { cb.checked = false; }); });
                } else if (window.PAGE.projectDeliverables) {
                    buildPickerInto(revisionPickerList,
                        document.getElementById('revisionPickerSelectAll'),
                        document.getElementById('revisionPickerDeselectAll'));
                }
                pickerBuilt = true;
            }
        });

        if (sendRevisionCancel) {
            sendRevisionCancel.addEventListener('click', function () {
                sendRevisionForm.classList.add('hidden');
                sendRevisionBtn.classList.remove('hidden');
                document.getElementById('revisionMessage').value = '';
            });
        }

        if (sendRevisionConfirm) {
            sendRevisionConfirm.addEventListener('click', function () {
                var message = document.getElementById('revisionMessage').value.trim();
                if (!message) {
                    showToast('Please describe what needs to be revised.', 'error');
                    return;
                }

                // Collect checked deliverable IDs and concept/KV flags from the revision picker
                var checked = [];
                var includesConcept = false;
                var includesKV = false;
                if (revisionPickerList) {
                    revisionPickerList.querySelectorAll('input[type="checkbox"]:checked').forEach(function (cb) {
                        if (cb.value === '__concept__') includesConcept = true;
                        else if (cb.value === '__kv__') includesKV = true;
                        else checked.push(parseInt(cb.value));
                    });
                }
                // When merged Concept & KV row is checked and project has KV, include KV too
                if (includesConcept && window.PAGE.projectHasKV) includesKV = true;
                if (checked.length === 0 && !includesConcept && !includesKV) {
                    showToast('Select at least one item to revise.', 'error');
                    return;
                }

                btnLoading(sendRevisionConfirm);

                // Collect Gulf POSM region + customer for revision
                var revPosmCountry = null;
                var revPosmCustomerId = null;
                if (window.PAGE.posmActive) {
                    var revRegionSel = document.getElementById('revPosmRegionSelect');
                    var revCustomerSel = document.getElementById('revPosmCustomerSelect');
                    revPosmCountry = revRegionSel ? (revRegionSel.value || null) : null;
                    revPosmCustomerId = revCustomerSel ? (parseInt(revCustomerSel.value) || null) : null;
                }

                fetch('/projects/' + detailProjectId + '/submission/send-revision', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: message,
                        deliverable_ids: checked,
                        includes_concept: includesConcept,
                        includes_kv: includesKV,
                        posm_country: revPosmCountry,
                        posm_customer_id: revPosmCustomerId
                    })
                })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (!data.success) {
                            showToast(data.error || 'Could not send revision.', 'error');
                            btnDone(sendRevisionConfirm);
                            return;
                        }
                        showToast('Revision sent. Designer has been notified.', 'success');
                        window.location.reload();
                    })
                    .catch(function () {
                        showToast('Something went wrong.', 'error');
                        btnDone(sendRevisionConfirm);
                    });
            });
        }
    })();

    // ── Step 6: Designer starts the revision ─────────────────────────────────────
    // Shown in State 6 (revision_in_queue). Designer clicks "Start Revision" →
    // POSTs to /start-revision → project + deliverables → revision_in_progress,
    // CS gets notified.
    var startRevisionBtn = document.getElementById('startRevisionBtn');
    if (startRevisionBtn) {
        startRevisionBtn.addEventListener('click', function () {
            btnLoading(startRevisionBtn);

            fetch('/projects/' + detailProjectId + '/submission/start-revision', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.success) {
                        showToast(data.error || 'Could not start revision.', 'error');
                        btnDone(startRevisionBtn);
                        return;
                    }
                    showToast('Revision started. CS has been notified.', 'success');
                    window.location.reload();
                })
                .catch(function () {
                    showToast('Something went wrong.', 'error');
                    btnDone(startRevisionBtn);
                });
        });
    }

// ── C&KV: Submit to Client ───────────────────────────────────────────────────
// Shown in internal_review state. Sends deck to client and moves
// concept_status → submitted_to_client. Offers email draft on success.
var ckvSubmitToClientBtn = document.getElementById('ckvSubmitToClientBtn');
if (ckvSubmitToClientBtn) {
    ckvSubmitToClientBtn.addEventListener('click', function () {
        ckvSubmitToClientBtn.disabled = true;
        ckvSubmitToClientBtn.textContent = 'Submitting...';

        fetch('/projects/' + detailProjectId + '/submission/submit-to-client', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ckv: true })  // tells the route this is C&KV, not a POSM channel
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.success) {
                    showToast(data.error || 'Could not submit.', 'error');
                    ckvSubmitToClientBtn.disabled = false;
                    ckvSubmitToClientBtn.textContent = 'Submit to Client';
                    return;
                }
                showToast('C&KV submitted to client.', 'success');
                // Offer email draft modal — same flow as standard submission
                var emailModal = document.getElementById('email-draft-modal');
                var emailYes = document.getElementById('emailDraftYes');
                var emailNo = document.getElementById('emailDraftNo');
                if (emailModal && emailYes && emailNo) {
                    emailModal.classList.remove('hidden');
                    var subject = encodeURIComponent(data.project_name);
                    var body = encodeURIComponent('Please find attached the latest Concept & KV deck for ' + data.project_name + '.\n\nBest regards,');
                    var mailto = 'mailto:' + (data.client_email || '') + '?subject=' + subject + '&body=' + body;
                    emailYes.onclick = function () { emailModal.classList.add('hidden'); window.open(mailto); window.location.reload(); };
                    emailNo.onclick = function () { emailModal.classList.add('hidden'); window.location.reload(); };
                } else {
                    window.location.reload();
                }
            })
            .catch(function () {
                showToast('Something went wrong.', 'error');
                ckvSubmitToClientBtn.disabled = false;
                ckvSubmitToClientBtn.textContent = 'Submit to Client';
            });
    });
}

// ── C&KV: Send for Revision ──────────────────────────────────────────────────
// Shown in submitted_to_client state. "Send for Revision" reveals a textarea;
// "Send Revision" POSTs the message → concept_status moves to revision_in_queue.
// Simpler than the standard revision — no deliverable picker needed (C&KV has no
// standard deliverables in the POSM sense).
(function () {
    var ckvSendRevisionBtn = document.getElementById('ckvSendRevisionBtn');
    var ckvRevisionForm = document.getElementById('ckvRevisionForm');
    var ckvRevisionCancel = document.getElementById('ckvRevisionCancel');
    var ckvRevisionConfirm = document.getElementById('ckvRevisionConfirm');

    if (!ckvSendRevisionBtn) return;  // not in submitted_to_client state

    ckvSendRevisionBtn.addEventListener('click', function () {
        // Reveal the form and hide the trigger button
        ckvRevisionForm.classList.remove('hidden');
        ckvSendRevisionBtn.classList.add('hidden');
    });

    if (ckvRevisionCancel) {
        ckvRevisionCancel.addEventListener('click', function () {
            // Restore the button and clear the textarea
            ckvRevisionForm.classList.add('hidden');
            ckvSendRevisionBtn.classList.remove('hidden');
            document.getElementById('ckvRevisionMessage').value = '';
        });
    }

    if (ckvRevisionConfirm) {
        ckvRevisionConfirm.addEventListener('click', function () {
            var message = document.getElementById('ckvRevisionMessage').value.trim();
            if (!message) {
                showToast('Please describe the revision required.', 'error');
                return;
            }
            ckvRevisionConfirm.disabled = true;
            ckvRevisionConfirm.textContent = 'Sending...';

            fetch('/projects/' + detailProjectId + '/submission/send-revision', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ckv: true, message: message })
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.success) {
                        showToast(data.error || 'Could not send revision.', 'error');
                        ckvRevisionConfirm.disabled = false;
                        ckvRevisionConfirm.textContent = 'Send Revision';
                        return;
                    }
                    showToast('Revision sent. Designer has been notified.', 'success');
                    window.location.reload();
                })
                .catch(function () {
                    showToast('Something went wrong.', 'error');
                    ckvRevisionConfirm.disabled = false;
                    ckvRevisionConfirm.textContent = 'Send Revision';
                });
        });
    }
})();

// ── C&KV: Start Revision ─────────────────────────────────────────────────────
// Shown in revision_in_queue state. Designer clicks to acknowledge the revision
// and move concept_status → revision_in_progress, signalling work has begun.
var ckvStartRevisionBtn = document.getElementById('ckvStartRevisionBtn');
if (ckvStartRevisionBtn) {
    ckvStartRevisionBtn.addEventListener('click', function () {
        ckvStartRevisionBtn.disabled = true;
        ckvStartRevisionBtn.textContent = 'Starting...';

        fetch('/projects/' + detailProjectId + '/submission/start-revision', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ckv: true })  // routes the action to the C&KV branch
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.success) {
                    showToast(data.error || 'Could not start revision.', 'error');
                    ckvStartRevisionBtn.disabled = false;
                    ckvStartRevisionBtn.textContent = 'Start Revision';
                    return;
                }
                showToast('Revision started. CS has been notified.', 'success');
                window.location.reload();
            })
            .catch(function () {
                showToast('Something went wrong.', 'error');
                ckvStartRevisionBtn.disabled = false;
                ckvStartRevisionBtn.textContent = 'Start Revision';
            });
    });
}
    // ── Start Project ─────────────────────────────────────────────────
    // Handles the one-time transition from 'briefed' to 'in_progress'.
    // Stores the project ID when the modal opens, clears it on close.

    var _startProjectId = null;

    function openStartProjectModal(projectId, team) {
        _startProjectId = projectId;
        var msg = document.getElementById('start-project-assign-msg');
        if (msg) {
            msg.textContent = team
                ? 'You will be assigned as the ' + team + ' lead designer on this project.'
                : '';
        }
        document.getElementById('start-project-modal').classList.remove('hidden');
    }

    function closeStartProjectModal() {
        document.getElementById('start-project-modal').classList.add('hidden');
        _startProjectId = null;
    }

    // start-project-confirm is wired in detail.html's _wireDetailPage so it
    // re-attaches correctly after SPA navigation.

    // ── Lead Designer Self-Assignment ────────────────────────────────────────────

    function assignLeadSelf(team, projectId) {
        fetch('/projects/' + projectId + '/assign-lead', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ team: team })
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    refreshSection(projectId, 'section-assignments');
                } else {
                    showToast(data.error || 'Could not assign lead.', 'error');
                }
            });
    }

    function showTransferForm(teamLower) {
        document.getElementById('transfer-trigger-' + teamLower).classList.add('hidden');
        document.getElementById('transfer-form-' + teamLower).classList.remove('hidden');
    }

    function cancelTransfer(teamLower) {
        document.getElementById('transfer-form-' + teamLower).classList.add('hidden');
        document.getElementById('transfer-trigger-' + teamLower).classList.remove('hidden');
    }

    function confirmTransfer(teamLower, projectId) {
        var select = document.getElementById('transfer-select-' + teamLower);
        var newDesignerId = select ? select.value : '';
        if (!newDesignerId) {
            showToast('Please select a designer to transfer to.', 'warning');
            return;
        }
        fetch('/projects/' + projectId + '/assign-lead', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ team: teamLower, new_designer_id: parseInt(newDesignerId) })
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    var pid = window.location.pathname.split('/')[2];
                    refreshSection(pid, 'section-assignments');
                } else {
                    showToast(data.error || 'Could not transfer ownership.', 'error');
                }
            });
    }

    var _takeoverTeam = null;
    var _takeoverProjectId = null;

    function openTakeoverModal(team, previousLeadName, projectId) {
        _takeoverTeam = team;
        _takeoverProjectId = projectId;
        document.getElementById('lead-takeover-body').textContent =
            'You\'ll replace ' + previousLeadName + ' as the ' + team +
            ' lead on this project. They\'ll be notified.';
        document.getElementById('lead-takeover-modal').classList.remove('hidden');
    }

    function closeTakeoverModal() {
        document.getElementById('lead-takeover-modal').classList.add('hidden');
        _takeoverTeam = null;
        _takeoverProjectId = null;
    }

    // lead-takeover-confirm is wired in detail.html's _wireDetailPage so it
    // re-attaches correctly after SPA navigation.

    // ── Remove Secondary CS Modal ─────────────────────────────────────────────────
    // Stores the form to submit on confirm; nullified on close (CLAUDE.md pattern).

    var _pendingRemoveForm = null;

    function openRemoveCSModal(form, msg) {
        _pendingRemoveForm = form;
        document.getElementById('remove-cs-body').textContent = msg;
        document.getElementById('remove-cs-modal').classList.remove('hidden');
    }

    function closeRemoveCSModal() {
        document.getElementById('remove-cs-modal').classList.add('hidden');
        _pendingRemoveForm = null;
    }


    // ── POSM Parallel Channel Submission ─────────────────────────────────────────
    // Handles the pill-tab UI for Gulf C&CM POSM projects.
    // Each channel (UAE-Customer or Country) is its own independent submission pipeline.
    // All interactions use class-based selectors + data-channel-id; no global IDs.

    // Reload the page and restore focus to the given channel pill after load
    function reloadToChannel(channelId) {
        sessionStorage.setItem('posmActiveChannel', channelId);
        window.location.reload();
    }

    // Switch the visible channel section and update pill active state
    function selectPosmChannel(channelId) {
        // Deactivate all pills
        document.querySelectorAll('.posm-channel-pill').forEach(function (btn) {
            btn.classList.remove('posm-channel-pill--active');
        });
        // Activate the clicked pill
        var activePill = document.querySelector('.posm-channel-pill[data-channel-id="' + channelId + '"]');
        if (activePill) activePill.classList.add('posm-channel-pill--active');

        // Hide all channel sections, show the selected one
        document.querySelectorAll('.posm-channel-section').forEach(function (sec) {
            sec.classList.add('hidden');
        });
        var activeSection = document.getElementById('posm-ch-' + channelId);
        if (activeSection) {
            activeSection.classList.remove('hidden');
            // Lazy-build the deliverable picker if state 2 is visible
            var pickerList = document.getElementById('ch-picker-list-' + channelId);
            if (pickerList && pickerList.children.length === 0) {
                var _cIds = (pickerList.dataset.customerIds || '').split(',').filter(Boolean).map(Number);
                buildPickerInto(pickerList, null, null, _cIds);
            }
        }
    }

    // Restore the last-active channel on page load (saved by reloadToChannel before reload)
    (function () {
        var savedId = sessionStorage.getItem('posmActiveChannel');
        if (savedId && document.getElementById('posm-ch-' + savedId)) {
            sessionStorage.removeItem('posmActiveChannel');
            selectPosmChannel(savedId);
        } else {
            // Default: build picker for the first (already-visible) channel
            var firstSection = document.querySelector('.posm-channel-section:not(.hidden)');
            if (!firstSection) return;
            var channelId = firstSection.dataset.channelId;
            var pickerList = document.getElementById('ch-picker-list-' + channelId);
            if (pickerList) {
                var _cIds = (pickerList.dataset.customerIds || '').split(',').filter(Boolean).map(Number);
                buildPickerInto(pickerList, null, null, _cIds);
            }
        }
    })();

    // ── Channel event delegation ──────────────────────────────────────────────────
    // All channel buttons use class names (.ch-upload-btn, .ch-flag-btn, etc.)
    // We delegate from the pills container downward.
    document.addEventListener('click', function (e) {
        // ── Upload button ──────────────────────────────────────────────────────────
        var uploadBtn = e.target.closest('.ch-upload-btn');
        if (uploadBtn) {
            var chId = uploadBtn.dataset.channelId;
            var fileInput = document.getElementById('ch-file-' + chId);
            if (fileInput) fileInput.click();
            return;
        }

        // ── Flag button: show form ─────────────────────────────────────────────────
        var flagBtn = e.target.closest('.ch-flag-btn');
        if (flagBtn) {
            var chId = flagBtn.dataset.channelId;
            var form = document.getElementById('ch-flag-form-' + chId);
            if (form) {
                form.classList.remove('hidden');
                flagBtn.classList.add('hidden');
            }
            return;
        }

        // ── Flag cancel ────────────────────────────────────────────────────────────
        var flagCancel = e.target.closest('.ch-flag-cancel');
        if (flagCancel) {
            var chId = flagCancel.dataset.channelId;
            var form = document.getElementById('ch-flag-form-' + chId);
            if (form) form.classList.add('hidden');
            var msg = document.getElementById('ch-flag-msg-' + chId);
            if (msg) msg.value = '';
            // Re-show the flag button
            var btn = document.querySelector('.ch-flag-btn[data-channel-id="' + chId + '"]');
            if (btn) btn.classList.remove('hidden');
            return;
        }

        // ── Flag confirm ───────────────────────────────────────────────────────────
        var flagConfirm = e.target.closest('.ch-flag-confirm');
        if (flagConfirm) {
            var chId = flagConfirm.dataset.channelId;
            var projectId = flagConfirm.dataset.projectId;
            var msg = (document.getElementById('ch-flag-msg-' + chId) || {}).value || '';
            if (!msg.trim()) { showToast('Please describe the issue before flagging.', 'error'); return; }
            btnLoading(flagConfirm);
            fetch('/projects/' + projectId + '/submission/flag', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: msg.trim(), posm_channel_id: parseInt(chId) })
            }).then(function (r) { return r.json(); }).then(function (data) {
                if (!data.success) {
                    showToast(data.error || 'Could not flag submission.', 'error');
                    btnDone(flagConfirm);
                    return;
                }
                reloadToChannel(chId);
            }).catch(function () {
                showToast('Something went wrong.', 'error');
                btnDone(flagConfirm);
            });
            return;
        }

        // ── Submit to Client ───────────────────────────────────────────────────────
        var submitClientBtn = e.target.closest('.ch-submit-client-btn');
        if (submitClientBtn) {
            var chId = submitClientBtn.dataset.channelId;
            var projectId = submitClientBtn.dataset.projectId;
            btnLoading(submitClientBtn);
            fetch('/projects/' + projectId + '/submission/submit-to-client', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ posm_channel_id: parseInt(chId) })
            }).then(function (r) { return r.json(); }).then(function (data) {
                if (!data.success) {
                    showToast(data.error || 'Could not submit to client.', 'error');
                    btnDone(submitClientBtn);
                    return;
                }
                showToast('Submitted to client.', 'success');
                reloadToChannel(chId);
            }).catch(function () {
                showToast('Something went wrong.', 'error');
                btnDone(submitClientBtn);
            });
            return;
        }

        // ── Submit for Internal Review ─────────────────────────────────────────────
        var submitReviewBtn = e.target.closest('.ch-submit-review-btn');
        if (submitReviewBtn) {
            var chId = submitReviewBtn.dataset.channelId;
            var projectId = submitReviewBtn.dataset.projectId;
            var submissionId = parseInt(submitReviewBtn.dataset.submissionId);
            // Collect checked deliverables from this channel's picker
            var pickerList = document.getElementById('ch-picker-list-' + chId);
            var deliverableIds = [];
            if (pickerList) {
                pickerList.querySelectorAll('input[type="checkbox"]:checked').forEach(function (cb) {
                    var val = cb.value;
                    if (val !== '__concept__' && val !== '__kv__') deliverableIds.push(parseInt(val));
                });
            }
            if (!deliverableIds.length) {
                showToast('Select at least one deliverable to include.', 'error');
                return;
            }
            btnLoading(submitReviewBtn);
            fetch('/projects/' + projectId + '/submission/submit-for-review', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    submission_id: submissionId,
                    deliverable_ids: deliverableIds,
                    posm_channel_id: parseInt(chId)
                })
            }).then(function (r) { return r.json(); }).then(function (data) {
                if (!data.success) {
                    showToast(data.error || 'Could not submit for review.', 'error');
                    btnDone(submitReviewBtn);
                    return;
                }
                reloadToChannel(chId);
            }).catch(function () {
                showToast('Something went wrong.', 'error');
                btnDone(submitReviewBtn);
            });
            return;
        }

        // ── Send Revision button: show form ───────────────────────────────────────
        var sendRevBtn = e.target.closest('.ch-send-revision-btn');
        if (sendRevBtn) {
            var chId = sendRevBtn.dataset.channelId;
            var form = document.getElementById('ch-rev-form-' + chId);
            if (form) {
                form.classList.remove('hidden');
                sendRevBtn.classList.add('hidden');
            }
            return;
        }

        // ── Send Revision cancel ───────────────────────────────────────────────────
        var sendRevCancel = e.target.closest('.ch-send-revision-cancel');
        if (sendRevCancel) {
            var chId = sendRevCancel.dataset.channelId;
            var form = document.getElementById('ch-rev-form-' + chId);
            if (form) form.classList.add('hidden');
            var msg = document.getElementById('ch-rev-msg-' + chId);
            if (msg) msg.value = '';
            var btn = document.querySelector('.ch-send-revision-btn[data-channel-id="' + chId + '"]');
            if (btn) btn.classList.remove('hidden');
            return;
        }

        // ── Send Revision confirm ──────────────────────────────────────────────────
        var sendRevConfirm = e.target.closest('.ch-send-revision-confirm');
        if (sendRevConfirm) {
            var chId = sendRevConfirm.dataset.channelId;
            var projectId = sendRevConfirm.dataset.projectId;
            var msgEl = document.getElementById('ch-rev-msg-' + chId);
            var message = msgEl ? msgEl.value.trim() : '';
            if (!message) { showToast('Please describe what needs to be revised.', 'error'); return; }
            btnLoading(sendRevConfirm);
            fetch('/projects/' + projectId + '/submission/send-revision', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: message, posm_channel_id: parseInt(chId) })
            }).then(function (r) { return r.json(); }).then(function (data) {
                if (!data.success) {
                    showToast(data.error || 'Could not send revision.', 'error');
                    btnDone(sendRevConfirm);
                    return;
                }
                showToast('Revision sent. Designer has been notified.', 'success');
                reloadToChannel(chId);
            }).catch(function () {
                showToast('Something went wrong.', 'error');
                btnDone(sendRevConfirm);
            });
            return;
        }

        // ── Start Revision ─────────────────────────────────────────────────────────
        var startRevBtn = e.target.closest('.ch-start-revision-btn');
        if (startRevBtn) {
            var chId = startRevBtn.dataset.channelId;
            var projectId = startRevBtn.dataset.projectId;
            btnLoading(startRevBtn);
            fetch('/projects/' + projectId + '/submission/start-revision', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ posm_channel_id: parseInt(chId) })
            }).then(function (r) { return r.json(); }).then(function (data) {
                if (!data.success) {
                    showToast(data.error || 'Could not start revision.', 'error');
                    btnDone(startRevBtn);
                    return;
                }
                showToast('Revision started. CS has been notified.', 'success');
                reloadToChannel(chId);
            }).catch(function () {
                showToast('Something went wrong.', 'error');
                btnDone(startRevBtn);
            });
            return;
        }
    });

    // ── Channel file upload ────────────────────────────────────────────────────────
    // Wire up each ch-file-input so that when a file is selected it uploads immediately
    // to /submission/upload with posm_channel_id in the form data.
    document.querySelectorAll('.ch-file-input').forEach(function (fileInput) {
        fileInput.addEventListener('change', function () {
            if (!fileInput.files || !fileInput.files.length) return;
            var chId = fileInput.dataset.channelId;
            var projectId = document.querySelector('.ch-upload-btn[data-channel-id="' + chId + '"]').dataset.projectId;
            var statusEl = document.getElementById('ch-upload-status-' + chId);

            if (statusEl) { statusEl.textContent = 'Uploading...'; }

            var formData = new FormData();
            formData.append('file', fileInput.files[0]);
            formData.append('posm_channel_id', chId);

            fetch('/projects/' + projectId + '/submission/upload', {
                method: 'POST',
                body: formData
            }).then(function (r) { return r.json(); }).then(function (data) {
                if (!data.success) {
                    if (statusEl) { statusEl.textContent = data.error || 'Upload failed.'; }
                    showToast(data.error || 'Upload failed.', 'error');
                    return;
                }
                // Reload back to this channel — server will show State 2 (picker)
                reloadToChannel(chId);
            }).catch(function () {
                if (statusEl) { statusEl.textContent = 'Upload failed.'; }
                showToast('Something went wrong during upload.', 'error');
            });

            // Clear the input so the same file can be re-selected if needed
            fileInput.value = '';
        });
    });

// ── B9: Event Delegation ──────────────────────────────────────────────────────
//
// All inline onclick=/onchange= attributes have been removed from detail.html.
// A single listener on `document` catches every click (or change) that bubbles
// up and routes it to the right handler via the element's data-action attribute.
//
// Why delegation instead of per-element addEventListener?
//   1. Survives DOM replacement — refreshSection() swaps HTML without re-wiring.
//   2. No global function leakage — handlers don't have to live on window.
//   3. Server data stays in data-* attrs where tojson can escape it safely,
//      eliminating the "quote in customer name breaks onclick string" class of bug.
//
// The handler functions (openFlagModalFromBtn, confirmCancelCustomer, etc.) are
// still defined in detail.html's inline <script> block, which loads before this
// file. Delegation calls them directly — no change to their internals required.

document.addEventListener('click', function (e) {

    // ── Flag modal: open ──────────────────────────────────────────────────────
    // All three button types (project / concept / deliverable) already carry
    // data-flag-type, data-project-id, data-context, data-deliverable-id.
    // openFlagModalFromBtn() reads those from element.dataset — no args needed.
    var flagBtn = e.target.closest('[data-action="open-flag-modal"]');
    if (flagBtn) { openFlagModalFromBtn(flagBtn); return; }

    // ── Flag modal: close (Cancel button) ────────────────────────────────────
    if (e.target.closest('[data-action="close-flag-modal"]')) { closeFlagModal(); return; }

    // ── Flag modal: close (click on backdrop) ────────────────────────────────
    // closest() matches ancestors too, so clicking *inside* the modal box would
    // also find the overlay. The extra e.target === overlay check prevents that:
    // it only fires when the click landed directly on the backdrop itself.
    var overlay = e.target.closest('[data-action="close-flag-modal-overlay"]');
    if (overlay && e.target === overlay) { closeFlagModal(); return; }

    // ── Flag modal: submit ────────────────────────────────────────────────────
    if (e.target.closest('[data-action="submit-flag"]')) { submitFlag(); return; }

    // ── Flag: resolve ─────────────────────────────────────────────────────────
    var resolveBtn = e.target.closest('[data-action="resolve-flag"]');
    if (resolveBtn) {
        resolveFlag(
            parseInt(resolveBtn.dataset.flagId),
            parseInt(resolveBtn.dataset.projectId)
        );
        return;
    }

    // ── Customer: cancel ──────────────────────────────────────────────────────
    // data-customer-name is tojson-encoded, so JSON.parse gives the raw string
    // safely regardless of what characters the name contains. This replaces the
    // old onclick="...('{{ name | e }}')" pattern that broke on names with quotes.
    var cancelBtn = e.target.closest('[data-action="cancel-customer"]');
    if (cancelBtn) {
        confirmCancelCustomer(
            parseInt(cancelBtn.dataset.customerId),
            JSON.parse(cancelBtn.dataset.customerName)
        );
        return;
    }

    // ── Customer: remove ──────────────────────────────────────────────────────
    var removeBtn = e.target.closest('[data-action="remove-customer"]');
    if (removeBtn) {
        confirmRemoveCustomer(
            parseInt(removeBtn.dataset.customerId),
            JSON.parse(removeBtn.dataset.customerName)
        );
        return;
    }

    // ── Start project modal: open ─────────────────────────────────────────────
    var startBtn = e.target.closest('[data-action="open-start-project-modal"]');
    if (startBtn) {
        openStartProjectModal(
            parseInt(startBtn.dataset.projectId),
            startBtn.dataset.team || ''
        );
        return;
    }

    // ── Start project modal: close ────────────────────────────────────────────
    if (e.target.closest('[data-action="close-start-project-modal"]')) {
        closeStartProjectModal();
        return;
    }

    // ── Lead assignment: assign self ──────────────────────────────────────────
    var assignSelfBtn = e.target.closest('[data-action="assign-lead-self"]');
    if (assignSelfBtn) {
        assignLeadSelf(assignSelfBtn.dataset.team, parseInt(assignSelfBtn.dataset.projectId));
        return;
    }

    // ── Lead assignment: show transfer form ───────────────────────────────────
    var showTransferBtn = e.target.closest('[data-action="show-transfer-form"]');
    if (showTransferBtn) { showTransferForm(showTransferBtn.dataset.team); return; }

    // ── Lead assignment: confirm transfer ─────────────────────────────────────
    var confirmTransferBtn = e.target.closest('[data-action="confirm-transfer"]');
    if (confirmTransferBtn) {
        confirmTransfer(
            confirmTransferBtn.dataset.team,
            parseInt(confirmTransferBtn.dataset.projectId)
        );
        return;
    }

    // ── Lead assignment: cancel transfer form ─────────────────────────────────
    var cancelTransferBtn = e.target.closest('[data-action="cancel-transfer"]');
    if (cancelTransferBtn) { cancelTransfer(cancelTransferBtn.dataset.team); return; }

    // ── Lead takeover modal: open ─────────────────────────────────────────────
    // data-current-owner is tojson-encoded so names with apostrophes work safely.
    var takeoverBtn = e.target.closest('[data-action="open-takeover-modal"]');
    if (takeoverBtn) {
        openTakeoverModal(
            takeoverBtn.dataset.team,
            JSON.parse(takeoverBtn.dataset.currentOwner),
            parseInt(takeoverBtn.dataset.projectId)
        );
        return;
    }

    // ── Lead takeover modal: close ────────────────────────────────────────────
    if (e.target.closest('[data-action="close-takeover-modal"]')) {
        closeTakeoverModal();
        return;
    }

    // ── POSM channel pill: C&KV ───────────────────────────────────────────────
    if (e.target.closest('[data-action="select-ckv-channel"]')) {
        selectCkvChannel();
        return;
    }

    // ── POSM channel pill: individual channel ─────────────────────────────────
    // data-channel-id is still on the element; selectPosmChannel() needs the int.
    var channelPill = e.target.closest('[data-action="select-posm-channel"]');
    if (channelPill) {
        selectPosmChannel(parseInt(channelPill.dataset.channelId));
        return;
    }

    // ── Approve Concept & KV ─────────────────────────────────────────────────
    var approveCkvBtn = e.target.closest('[data-action="approve-ckv"]');
    if (approveCkvBtn) {
        approveCKV(parseInt(approveCkvBtn.dataset.projectId));
        return;
    }

    // ── POSM submission history toggle ────────────────────────────────────────
    // data-target holds the panel ID; togglePosmHistory() reads it from the element.
    var historyToggle = e.target.closest('[data-action="toggle-posm-history"]');
    if (historyToggle) { togglePosmHistory(historyToggle); return; }

    // ── Flag history section toggle ───────────────────────────────────────────
    if (e.target.closest('[data-action="toggle-flag-history"]')) {
        toggleFlagHistory();
        return;
    }

    // ── Form submit with inline confirm ───────────────────────────────────────
    // Used for the secondary-CS remove button (type="submit"). We intercept the
    // click, ask for confirmation, then submit the parent form only if confirmed.
    // data-confirm-message is tojson-encoded so names with quotes survive.
    //
    // WHY requestSubmit() instead of dispatchEvent(new Event('submit')):
    // dispatchEvent fires the JS event but browsers do NOT submit the form as a
    // result of a synthetic event — only real user actions or form.requestSubmit()
    // trigger actual submission. requestSubmit() also fires submit listeners so any
    // other handlers get a chance to run; we fall back to form.submit() for older
    // browsers that don't support it.
    var confirmSubmitBtn = e.target.closest('[data-action="confirm-submit"]');
    if (confirmSubmitBtn) {
        e.preventDefault();
        // Plain string read — no JSON.parse. Jinja auto-escapes the name in the
        // HTML attribute, and the browser un-escapes it when we read dataset.*
        openRemoveCSModal(confirmSubmitBtn.closest('form'), confirmSubmitBtn.dataset.confirmMessage);
        return;
    }

    // ── Remove CS modal: cancel ────────────────────────────────────────────────
    if (e.target.closest('[data-action="close-remove-cs-modal"]')) {
        closeRemoveCSModal();
        return;
    }

    // ── Remove CS modal: backdrop click ───────────────────────────────────────
    var removeCsOverlay = e.target.closest('[data-action="close-remove-cs-overlay"]');
    if (removeCsOverlay && e.target === removeCsOverlay) { closeRemoveCSModal(); return; }

    // ── Remove CS modal: confirm ──────────────────────────────────────────────
    if (e.target.closest('[data-action="confirm-remove-cs"]')) {
        var pendingForm = _pendingRemoveForm;   // save first — closeRemoveCSModal nullifies the ref
        closeRemoveCSModal();
        if (pendingForm) {
            if (pendingForm.requestSubmit) { pendingForm.requestSubmit(); } else { pendingForm.submit(); }
        }
        return;
    }
});

// ── Status select: change delegation ─────────────────────────────────────────
// Covers project status, CCM deliverable status, and standard brief deliverable
// status — all three selects now carry data-action="update-status" instead of
// onchange="updateStatus(this)". updateStatus() reads dataset.url from the
// element itself, so no argument changes are needed.
document.addEventListener('change', function (e) {
    var sel = e.target.closest('select[data-action="update-status"]');
    if (sel) { updateStatus(sel); }
});

// ── Assign designer form: submit delegation ───────────────────────────────────
// Admin / team-lead assignment forms carry data-action="assign-designer-form".
// We intercept the submit, POST via fetch (sending FormData so the route's
// request.form.get() calls work unchanged), then update the DOM without a
// full-page reload.
document.addEventListener('submit', function (e) {
    var form = e.target.closest('form[data-action="assign-designer-form"]');
    if (!form) return;

    e.preventDefault(); // stop the browser from navigating away

    var projectId = form.dataset.projectId;
    var btn = form.querySelector('button[type="submit"]');
    btnLoading(btn);

    fetch(form.action, {
        method: 'POST',
        body: new FormData(form)
        // No Content-Type header — browser sets it automatically for FormData
        // so Flask receives it as request.form (multipart or urlencoded).
    })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (!data.success) {
                showToast(data.error || 'Could not assign designer.', 'error');
                btnDone(btn);
                return;
            }
            // Build a readable summary: "Alice assigned to this project."
            var names = (data.assignments || []).map(function (a) {
                return a.name + ' assigned to this project';
            });
            showToast(
                names.length ? names.join('. ') + '.' : 'Designer assigned.',
                'success'
            );
            refreshSection(projectId, 'section-assignments');
        })
        .catch(function () {
            btnDone(btn);
            showToast('Could not assign designer.', 'error');
        });
});
