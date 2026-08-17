// detail.js — Vitamin-E
// Project detail page: post-redirect toast, expandable rows, status dropdowns,
// submission flow, C&KV, POSM channels, start project, lead designer, channel uploads.
// Depends on: showToast(), showConfirm() — defined in main.js.
//             openApprovalModal() — defined in detail.html inline script block.
// Loaded after main.js.

// ── Expandable rows ───────────────────────────────────────────────────────────
// Delegated to document so it survives SPA navigation (sidebar.js replaces
// innerHTML; direct element listeners on querySelectorAll results are lost).
// _expandRowsWired prevents stacking a duplicate listener on re-navigation.
if (!window._expandRowsWired) {
    window._expandRowsWired = true;
    document.addEventListener('click', function (e) {
        if (e.target.closest('a, button, select')) return;
        var row = e.target.closest('tr[data-expand]');
        if (!row || row.dataset.href) return;
        var expandRow = row.nextElementSibling;
        if (!expandRow || !expandRow.classList.contains('expansion-row')) return;
        expandRow.classList.toggle('hidden');
        var icon = row.querySelector('.chevron-icon');
        if (icon) icon.classList.toggle('rotated');
    });
}

// ── Deliverable image click-to-maximize preview ──────────────────────────────
// Shows a full-viewport overlay when clicking a .deliverable-row-thumb image.
// Click the backdrop, or press Escape, to close.
(function () {
    if (window._delivImgOverlayWired) return;
    window._delivImgOverlayWired = true;

    var overlay = document.createElement('div');
    overlay.id = 'deliv-img-overlay';
    overlay.innerHTML = '<div class="deliv-img-backdrop"></div>' +
        '<img class="deliv-img-large" src="" alt="">';
    document.body.appendChild(overlay);

    var large = overlay.querySelector('.deliv-img-large');

    function show(src, alt) {
        large.src = src;
        large.alt = alt || '';
        overlay.classList.add('visible');
    }

    function hide() {
        overlay.classList.remove('visible');
        large.src = '';
    }

    document.addEventListener('click', function (e) {
        var thumb = e.target.closest('.deliverable-row-thumb');
        if (thumb) { show(thumb.src, thumb.alt); return; }
        if (overlay.classList.contains('visible') && e.target !== large) hide();
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') hide();
    });
}());

// ── "Download All" zip download ───────────────────────────────────────────────
function triggerZipDownload(btn) {
    var url = btn.dataset.zipBuildUrl;
    var originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Zipping...';
    fetch(url)
        .then(function (r) { return r.json(); })
        .then(function (data) {
            btn.disabled = false;
            btn.textContent = originalText;
            if (!data.success) { showToast(data.error || 'Could not build zip.', 'error'); return; }
            window.location = data.download_url;
        })
        .catch(function () {
            btn.disabled = false;
            btn.textContent = originalText;
            showToast('Could not build zip.', 'error');
        });
}

// ── Status dropdowns ──────────────────────────────────────────────────────────
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
            if (data.error) { showToast(data.error, 'error'); }
            else { applyStatusClass(select, status); showToast('Status updated', 'success'); }
        })
        .catch(function () { showToast('Something went wrong', 'error'); });
}

function applyStatusClass(select, status) {
    var classes = [
        's-briefed', 's-in_queue', 's-in_progress', 's-submitted',
        's-internal_review', 's-internal_revision', 's-submitted_to_client',
        's-revision_in_queue', 's-revision_in_progress', 's-approved', 's-on_hold',
        's-awaiting_posm_details'
    ];
    select.classList.remove.apply(select.classList, classes);
    select.classList.add('s-' + status);
}

// ── Flag revision ─────────────────────────────────────────────────────────────
function flagRevision(deliverableId, projectId) {
    var url = '/projects/' + projectId + '/deliverable/' + deliverableId + '/flag-revision';
    fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' } })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.error) {
                showToast(data.error, 'error');
            } else {
                showToast('Deliverable flagged for revision', 'warning');
                var btn = document.querySelector('[onclick="flagRevision(' + deliverableId + ', ' + projectId + ')"]');
                if (btn) {
                    var badge = document.createElement('span');
                    badge.className = 'revision-flagged-badge';
                    badge.textContent = '⚑ Flagged';
                    btn.replaceWith(badge);
                }
                var row = document.querySelector('[data-url*="/deliverable/' + deliverableId + '/set-status"]');
                if (row) { row.value = 'revision_in_queue'; applyStatusClass(row, 'revision_in_queue'); }
            }
        })
        .catch(function () { showToast('Something went wrong', 'error'); });
}

// ── NAS deep-link opener ───────────────────────────────────────────────────────
function openNasLink(btn) {
    var url = btn.dataset.url;
    var originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Opening…';
    fetch(url)
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.success) { window.open(data.url, '_blank'); }
            else { showToast('Could not open NAS folder: ' + (data.error || 'Unknown error'), 'error'); }
        })
        .catch(function () { showToast('Could not reach the NAS. Are you on the network?', 'error'); })
        .finally(function () { btn.disabled = false; btn.textContent = originalText; });
}

// ── Shared deliverable picker builder ────────────────────────────────────────
// Used by both the submission picker (State 2) and the revision picker (State 5).
function buildPickerInto(containerEl, globalSelectEl, globalDeselectEl, filterCustomerIds) {
    if (!containerEl || !window.PAGE.projectDeliverables) return;

    var deliverables = window.PAGE.projectDeliverables;
    deliverables = deliverables.filter(function (d) { return d.status !== 'approved'; });

    if (filterCustomerIds && filterCustomerIds.length > 0) {
        var _idSet = {};
        filterCustomerIds.forEach(function (id) { _idSet[id] = true; });
        deliverables = deliverables.filter(function (d) { return d.customer_id && _idSet[d.customer_id]; });
    }

    function makeRow(d) {
        var label = document.createElement('label');
        label.className = 'deliverable-tag';
        var cb = document.createElement('input');
        cb.type = 'checkbox'; cb.value = d.id; cb.checked = true;
        cb.dataset.deliverableId = d.id;
        var span = document.createElement('span');
        span.textContent = d.name;
        label.appendChild(cb); label.appendChild(span);
        return label;
    }

    var isCCM = deliverables.some(function (d) { return d.customer_name; });

    if (isCCM) {
        var groups = {}, order = [];
        deliverables.forEach(function (d) {
            var key = d.customer_id || '__none__';
            if (!groups[key]) { groups[key] = { name: d.customer_name || 'Other', items: [] }; order.push(key); }
            groups[key].items.push(d);
        });
        order.forEach(function (key) {
            var g = groups[key];
            var wrap = document.createElement('div');
            wrap.style.cssText = 'border:1px solid var(--border);border-radius:6px;padding:0.65rem 0.75rem;margin-bottom:0.5rem;';
            var header = document.createElement('div');
            header.style.cssText = 'font-size:0.7rem;font-weight:700;letter-spacing:0.06em;color:var(--tangerine);text-transform:uppercase;margin-bottom:0.4rem;';
            header.textContent = g.name;
            wrap.appendChild(header);
            var actions = document.createElement('div');
            actions.style.cssText = 'display:flex;gap:0.4rem;margin-bottom:0.4rem;';
            var selAll = document.createElement('button'); selAll.type = 'button'; selAll.className = 'btn-secondary btn-sm'; selAll.textContent = 'Select All';
            var deselAll = document.createElement('button'); deselAll.type = 'button'; deselAll.className = 'btn-secondary btn-sm'; deselAll.textContent = 'Deselect All';
            selAll.addEventListener('click', function () { wrap.querySelectorAll('input[type="checkbox"]').forEach(function (cb) { cb.checked = true; }); });
            deselAll.addEventListener('click', function () { wrap.querySelectorAll('input[type="checkbox"]').forEach(function (cb) { cb.checked = false; }); });
            actions.appendChild(selAll); actions.appendChild(deselAll);
            wrap.appendChild(actions);
            g.items.forEach(function (d) { wrap.appendChild(makeRow(d)); });
            containerEl.appendChild(wrap);
        });
    } else {
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

// Shared campaign row builder for Concept & KV pickers.
function makeCampaignRow(value, label) {
    var lbl = document.createElement('label');
    lbl.className = 'deliverable-tag deliverable-tag--campaign';
    var cb = document.createElement('input');
    cb.type = 'checkbox'; cb.value = value; cb.checked = true;
    var span = document.createElement('span');
    span.textContent = label;
    lbl.appendChild(cb); lbl.appendChild(span);
    return lbl;
}

// ── Start Project modal ───────────────────────────────────────────────────────
var _startProjectId = null;

function openStartProjectModal(projectId, team) {
    _startProjectId = projectId;
    var msg = document.getElementById('start-project-assign-msg');
    if (msg) {
        msg.textContent = team ? 'You will be assigned as the ' + team + ' lead designer on this project.' : '';
    }
    document.getElementById('start-project-modal').classList.remove('hidden');
    if (window.helixPolling) window.helixPolling.pause();
}

function closeStartProjectModal() {
    document.getElementById('start-project-modal').classList.add('hidden');
    _startProjectId = null;
    if (window.helixPolling) window.helixPolling.resume();
}

// start-project-confirm is wired in detail.html's _wireDetailPage so it
// re-attaches correctly after SPA navigation.

// ── Lead Designer Self-Assignment ─────────────────────────────────────────────
function assignLeadSelf(team, projectId) {
    fetch('/projects/' + projectId + '/assign-lead', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ team: team })
    })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.success) { refreshSection(projectId, 'section-assignments'); }
            else { showToast(data.error || 'Could not assign lead.', 'error'); }
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

function confirmTransfer(team, projectId) {
    var select = document.getElementById('transfer-select-' + team.toLowerCase());
    var newDesignerId = select ? select.value : '';
    if (!newDesignerId) { showToast('Please select a designer to transfer to.', 'warning'); return; }
    fetch('/projects/' + projectId + '/assign-lead', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ team: team, new_designer_id: parseInt(newDesignerId) })
    })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.success) { var pid = window.location.pathname.split('/')[2]; refreshSection(pid, 'section-assignments'); }
            else { showToast(data.error || 'Could not transfer ownership.', 'error'); }
        });
}

var _takeoverTeam = null;
var _takeoverProjectId = null;

function openTakeoverModal(team, previousLeadName, projectId) {
    _takeoverTeam = team;
    _takeoverProjectId = projectId;
    document.getElementById('lead-takeover-body').textContent =
        'You\'ll replace ' + previousLeadName + ' as the ' + team + ' lead on this project. They\'ll be notified.';
    document.getElementById('lead-takeover-modal').classList.remove('hidden');
    if (window.helixPolling) window.helixPolling.pause();
}

function closeTakeoverModal() {
    document.getElementById('lead-takeover-modal').classList.add('hidden');
    _takeoverTeam = null; _takeoverProjectId = null;
    if (window.helixPolling) window.helixPolling.resume();
}

// lead-takeover-confirm is wired in detail.html's _wireDetailPage so it
// re-attaches correctly after SPA navigation.

// ── Remove Secondary CS Modal ─────────────────────────────────────────────────
var _pendingRemoveForm = null;

function openRemoveCSModal(form, msg) {
    _pendingRemoveForm = form;
    document.getElementById('remove-cs-body').textContent = msg;
    document.getElementById('remove-cs-modal').classList.remove('hidden');
    if (window.helixPolling) window.helixPolling.pause();
}

function closeRemoveCSModal() {
    document.getElementById('remove-cs-modal').classList.add('hidden');
    _pendingRemoveForm = null;
    if (window.helixPolling) window.helixPolling.resume();
}

// ── POSM channel helpers ──────────────────────────────────────────────────────
function reloadToChannel(channelId) {
    sessionStorage.setItem('posmActiveChannel', channelId);
    window.location.reload();
}

function selectPosmChannel(channelId) {
    document.querySelectorAll('.posm-channel-pill').forEach(function (btn) {
        btn.classList.remove('posm-channel-pill--active');
    });
    var activePill = document.querySelector('.posm-channel-pill[data-channel-id="' + channelId + '"]');
    if (activePill) activePill.classList.add('posm-channel-pill--active');

    document.querySelectorAll('.posm-channel-section').forEach(function (sec) { sec.classList.add('hidden'); });
    var activeSection = document.getElementById('posm-ch-' + channelId);
    if (activeSection) {
        activeSection.classList.remove('hidden');
        var pickerList = document.getElementById('ch-picker-list-' + channelId);
        if (pickerList && pickerList.children.length === 0) {
            var _cIds = (pickerList.dataset.customerIds || '').split(',').filter(Boolean).map(Number);
            buildPickerInto(pickerList, null, null, _cIds);
        }
    }
}

// ── Submission deck upload: delegated ────────────────────────────────────────
// Handles the "Upload Client Deck" / "Reupload Deck" button (id=submissionUploadBtn)
// and the corresponding hidden file input (id=submissionFileInput).
// Kept at module scope so it survives SPA navigation without needing _initDetailPage.
document.addEventListener('click', function (e) {
    if (e.target.closest('#submissionUploadBtn')) {
        var fi = document.getElementById('submissionFileInput');
        if (fi) fi.click();
    }
});

document.addEventListener('change', function (e) {
    if (e.target.id !== 'submissionFileInput') return;
    var file = e.target.files[0];
    if (!file) return;

    var statusEl = document.getElementById('submissionUploadStatus');
    if (statusEl) statusEl.textContent = 'Uploading...';

    var projectId = parseInt(window.location.pathname.split('/')[2]);
    var formData = new FormData();
    formData.append('file', file);

    // Read POSM channel ID if this upload is for a specific channel (ch-file-input path
    // handles that separately; this handler is for the main submissionFileInput only).
    fetch('/projects/' + projectId + '/submission/upload', { method: 'POST', body: formData })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (!data.success) {
                if (statusEl) statusEl.textContent = 'Error: ' + data.error;
                return;
            }
            window.location.reload();
        })
        .catch(function () {
            if (statusEl) statusEl.textContent = 'Upload failed.';
        });

    e.target.value = ''; // reset so the same file can be re-selected
});

// ── Channel event delegation ──────────────────────────────────────────────────
document.addEventListener('click', function (e) {
    var uploadBtn = e.target.closest('.ch-upload-btn');
    if (uploadBtn) {
        var chId = uploadBtn.dataset.channelId;
        var fileInput = document.getElementById('ch-file-' + chId);
        if (fileInput) fileInput.click();
        return;
    }

    var flagBtn = e.target.closest('.ch-flag-btn');
    if (flagBtn) {
        var chId = flagBtn.dataset.channelId;
        var form = document.getElementById('ch-flag-form-' + chId);
        if (form) { form.classList.remove('hidden'); flagBtn.classList.add('hidden'); }
        return;
    }

    var flagCancel = e.target.closest('.ch-flag-cancel');
    if (flagCancel) {
        var chId = flagCancel.dataset.channelId;
        var form = document.getElementById('ch-flag-form-' + chId);
        if (form) form.classList.add('hidden');
        clearRichContent('ch-flag-msg-' + chId);
        var btn = document.querySelector('.ch-flag-btn[data-channel-id="' + chId + '"]');
        if (btn) btn.classList.remove('hidden');
        return;
    }

    var flagConfirm = e.target.closest('.ch-flag-confirm');
    if (flagConfirm) {
        var chId = flagConfirm.dataset.channelId;
        var projectId = flagConfirm.dataset.projectId;
        var msg = getRichContent('ch-flag-msg-' + chId);
        if (!msg) { showToast('Please describe the issue before flagging.', 'error'); return; }
        btnLoading(flagConfirm);
        fetch('/projects/' + projectId + '/submission/flag', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: msg, posm_channel_id: parseInt(chId) })
        }).then(function (r) { return r.json(); }).then(function (data) {
            if (!data.success) { showToast(data.error || 'Could not flag submission.', 'error'); btnDone(flagConfirm); return; }
            reloadToChannel(chId);
        }).catch(function () { showToast('Something went wrong.', 'error'); btnDone(flagConfirm); });
        return;
    }

    var submitClientBtn = e.target.closest('.ch-submit-client-btn');
    if (submitClientBtn) {
        var chId = submitClientBtn.dataset.channelId;
        var projectId = submitClientBtn.dataset.projectId;
        btnLoading(submitClientBtn);
        fetch('/projects/' + projectId + '/submission/submit-to-client', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ posm_channel_id: parseInt(chId) })
        }).then(function (r) { return r.json(); }).then(function (data) {
            if (!data.success) { showToast(data.error || 'Could not submit to client.', 'error'); btnDone(submitClientBtn); return; }
            showToast('Submitted to client.', 'success');
            reloadToChannel(chId);
        }).catch(function () { showToast('Something went wrong.', 'error'); btnDone(submitClientBtn); });
        return;
    }

    var submitReviewBtn = e.target.closest('.ch-submit-review-btn');
    if (submitReviewBtn) {
        var chId = submitReviewBtn.dataset.channelId;
        var projectId = submitReviewBtn.dataset.projectId;
        var submissionId = parseInt(submitReviewBtn.dataset.submissionId);
        var pickerList = document.getElementById('ch-picker-list-' + chId);
        var deliverableIds = [];
        if (pickerList) {
            pickerList.querySelectorAll('input[type="checkbox"]:checked').forEach(function (cb) {
                var val = cb.value;
                if (val !== '__concept__' && val !== '__kv__') deliverableIds.push(parseInt(val));
            });
        }
        if (!deliverableIds.length) { showToast('Select at least one deliverable to include.', 'error'); return; }
        btnLoading(submitReviewBtn);
        fetch('/projects/' + projectId + '/submission/submit-for-review', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ submission_id: submissionId, deliverable_ids: deliverableIds, posm_channel_id: parseInt(chId) })
        }).then(function (r) { return r.json(); }).then(function (data) {
            if (!data.success) { showToast(data.error || 'Could not submit for review.', 'error'); btnDone(submitReviewBtn); return; }
            reloadToChannel(chId);
        }).catch(function () { showToast('Something went wrong.', 'error'); btnDone(submitReviewBtn); });
        return;
    }

    var sendRevBtn = e.target.closest('.ch-send-revision-btn');
    if (sendRevBtn) {
        var chId = sendRevBtn.dataset.channelId;
        var form = document.getElementById('ch-rev-form-' + chId);
        if (form) { form.classList.remove('hidden'); sendRevBtn.classList.add('hidden'); }
        return;
    }

    var sendRevCancel = e.target.closest('.ch-send-revision-cancel');
    if (sendRevCancel) {
        var chId = sendRevCancel.dataset.channelId;
        var form = document.getElementById('ch-rev-form-' + chId);
        if (form) form.classList.add('hidden');
        clearRichContent('ch-rev-msg-' + chId);
        var btn = document.querySelector('.ch-send-revision-btn[data-channel-id="' + chId + '"]');
        if (btn) btn.classList.remove('hidden');
        return;
    }

    var sendRevConfirm = e.target.closest('.ch-send-revision-confirm');
    if (sendRevConfirm) {
        var chId = sendRevConfirm.dataset.channelId;
        var projectId = sendRevConfirm.dataset.projectId;
        var message = getRichContent('ch-rev-msg-' + chId);
        if (!message) { showToast('Please describe what needs to be revised.', 'error'); return; }
        btnLoading(sendRevConfirm);
        fetch('/projects/' + projectId + '/submission/send-revision', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message, posm_channel_id: parseInt(chId) })
        }).then(function (r) { return r.json(); }).then(function (data) {
            if (!data.success) { showToast(data.error || 'Could not send revision.', 'error'); btnDone(sendRevConfirm); return; }
            showToast('Revision sent. Designer has been notified.', 'success');
            reloadToChannel(chId);
        }).catch(function () { showToast('Something went wrong.', 'error'); btnDone(sendRevConfirm); });
        return;
    }

    var startRevBtn = e.target.closest('.ch-start-revision-btn');
    if (startRevBtn) {
        var chId = startRevBtn.dataset.channelId;
        var projectId = startRevBtn.dataset.projectId;
        btnLoading(startRevBtn);
        fetch('/projects/' + projectId + '/submission/start-revision', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ posm_channel_id: parseInt(chId) })
        }).then(function (r) { return r.json(); }).then(function (data) {
            if (!data.success) { showToast(data.error || 'Could not start revision.', 'error'); btnDone(startRevBtn); return; }
            showToast('Revision started. CS has been notified.', 'success');
            reloadToChannel(chId);
        }).catch(function () { showToast('Something went wrong.', 'error'); btnDone(startRevBtn); });
        return;
    }
});

// ── Submission flag delegation ────────────────────────────────────────────────
// These buttons share IDs across the C&KV and standard-brief blocks, so
// getElementById always returns whichever appears first in the DOM — not
// necessarily the one the user clicked. Delegation + DOM traversal avoids
// that entirely and survives SPA navigation without re-wiring.
document.addEventListener('click', function (e) {
    // Open the flag form
    var flagBtn = e.target.closest('[id="submissionFlagBtn"]');
    if (flagBtn) {
        // Form is the next sibling of flagBtn's parent flex row
        var form = flagBtn.parentElement && flagBtn.parentElement.nextElementSibling;
        if (form && form.id === 'submissionFlagForm') {
            form.classList.remove('hidden');
            flagBtn.classList.add('hidden');
        }
        return;
    }

    // Cancel — close the form and restore the trigger button
    var flagCancel = e.target.closest('[id="submissionFlagCancel"]');
    if (flagCancel) {
        var form = flagCancel.closest('[id="submissionFlagForm"]');
        if (form) {
            form.classList.add('hidden');
            var prevRow = form.previousElementSibling;
            if (prevRow) {
                var btn = prevRow.querySelector('[id="submissionFlagBtn"]');
                if (btn) btn.classList.remove('hidden');
            }
            // Clear the rich editor that belongs to THIS form
            var msgEl = form.querySelector('[data-rich-editor]');
            if (msgEl) { msgEl.innerHTML = ''; msgEl.dispatchEvent(new Event('input')); }
        }
        return;
    }

    // Confirm — POST the flag
    var flagConfirm = e.target.closest('[id="submissionFlagConfirm"]');
    if (flagConfirm) {
        var form = flagConfirm.closest('[id="submissionFlagForm"]');
        var msgEl = form ? form.querySelector('[data-rich-editor]') : null;
        var message = msgEl && (msgEl.textContent.trim() !== '' || msgEl.querySelector('img'))
            ? msgEl.innerHTML : '';
        if (!message) { showToast('Please describe the issue before flagging.', 'error'); return; }
        var projectId = flagConfirm.dataset.projectId;
        btnLoading(flagConfirm);
        fetch('/projects/' + projectId + '/submission/flag', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message })
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.success) { showToast(data.error, 'error'); btnDone(flagConfirm); return; }
                window.location.reload();
            })
            .catch(function () { showToast('Something went wrong.', 'error'); btnDone(flagConfirm); });
        return;
    }
});

// ── Reference file delete delegation ─────────────────────────────────────────
document.addEventListener('click', function (e) {
    var btn = e.target.closest('.reference-file-delete-btn');
    if (!btn) return;
    var fileId = btn.dataset.fileId;
    var row = btn.closest('.reference-file-item');
    var filename = row ? (row.querySelector('.reference-file-name') || {}).textContent : 'this file';
    showConfirm('Remove "' + filename + '"? This cannot be undone.', function () {
        btnLoading(btn);
        fetch('/projects/files/' + fileId + '/delete', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.success) { showToast(data.error || 'Could not delete file.', 'error'); btnDone(btn); return; }
                if (row) row.remove();
                showToast('File removed.', 'success');
            })
            .catch(function () { showToast('Something went wrong.', 'error'); btnDone(btn); });
    }, 'Remove File');
});

// ── _initDetailPage ───────────────────────────────────────────────────────────
// All DOM wiring that targets elements in the current detail page lives here.
// Called once on initial full-page load and again on every helix:navigated
// event (SPA navigation), so buttons always point at the live DOM.
function _initDetailPage() {
    var detailProjectId = parseInt(window.location.pathname.split('/')[2]);
    if (!detailProjectId) return;

    // ── Post-redirect Toast ───────────────────────────────────────────────────
    var urlParams = new URLSearchParams(window.location.search);
    var toastMsg = urlParams.get('toast');
    if (toastMsg) { showToast(decodeURIComponent(toastMsg), 'success'); }

    // ── Status dropdowns: apply initial CSS class ─────────────────────────────
    document.querySelectorAll('.status-select').forEach(function (select) {
        applyStatusClass(select, select.value);
    });

    // ── Step 2: Deliverable picker (submission) ───────────────────────────────
    // C&CM projects render TWO pickers (id="pickerList"): one for the C&KV
    // deck (data-ckv="true") and one for the standard brief. Initialise each
    // picker according to its type using querySelectorAll so both get built.
    (function () {
        document.querySelectorAll('[id="pickerList"]').forEach(function (pickerList) {
            var pickerDiv = pickerList.closest('.submission-picker');
            var selAll   = pickerDiv ? pickerDiv.querySelector('[id="pickerSelectAll"]')   : null;
            var deselAll = pickerDiv ? pickerDiv.querySelector('[id="pickerDeselectAll"]') : null;

            if (pickerList.dataset.ckv) {
                // C&KV picker — add concept/KV option rows only
                if (window.PAGE.projectHasConcept && window.PAGE.projectHasKV) {
                    pickerList.appendChild(makeCampaignRow('__concept__', 'Concept & KV'));
                } else {
                    if (window.PAGE.projectHasConcept) pickerList.appendChild(makeCampaignRow('__concept__', 'Concept'));
                    if (window.PAGE.projectHasKV)      pickerList.appendChild(makeCampaignRow('__kv__', 'Initial KV'));
                }
                if (selAll)   selAll.addEventListener('click',   function () { pickerList.querySelectorAll('input').forEach(function (cb) { cb.checked = true;  }); });
                if (deselAll) deselAll.addEventListener('click', function () { pickerList.querySelectorAll('input').forEach(function (cb) { cb.checked = false; }); });
            } else {
                // Standard brief picker — populated from window.PAGE.projectDeliverables
                buildPickerInto(pickerList, selAll, deselAll);
            }
        });
    })();

    // ── Step 2 → 3: Submit for Internal Review ────────────────────────────────
    // querySelectorAll: C&CM projects render submissionSubmitForReviewBtn twice.
    // pickerList lookup uses DOM traversal (previousElementSibling) so each
    // button reads its own adjacent picker, not always the first in the DOM.
    document.querySelectorAll('[id="submissionSubmitForReviewBtn"]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var self = this;
            var submissionId = parseInt(self.dataset.submissionId);
            // The .submission-picker div immediately precedes the flex row that
            // holds the submit button — so parentElement.previousElementSibling
            // gives the correct picker for this specific section.
            var pickerSection = self.parentElement && self.parentElement.previousElementSibling;
            var pickerList = pickerSection && pickerSection.querySelector('[id="pickerList"]');
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
            if (includesConcept && window.PAGE.projectHasKV) includesKV = true;
            if (checked.length === 0 && !includesConcept && !includesKV) {
                showToast('Select at least one item to include.', 'error'); return;
            }
            btnLoading(self);

            var posmCountry = null;
            var posmCustomerId = null;
            if (window.PAGE.posmActive && !includesConcept && !includesKV) {
                var posmRegionSel = document.getElementById('posmRegionSelect');
                var posmCustomerSel = document.getElementById('posmCustomerSelect');
                posmCountry = posmRegionSel ? (posmRegionSel.value || null) : null;
                posmCustomerId = posmCustomerSel ? (parseInt(posmCustomerSel.value) || null) : null;
                if (!posmCountry && !posmCustomerId) {
                    showToast('Select a region before submitting POSM.', 'error'); return;
                }
            }

            fetch('/projects/' + detailProjectId + '/submission/submit-for-review', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    submission_id: submissionId, deliverable_ids: checked,
                    includes_concept: includesConcept, includes_kv: includesKV,
                    posm_country: posmCountry, posm_customer_id: posmCustomerId
                })
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.success) { showToast(data.error || 'Could not submit for review.', 'error'); btnDone(self); return; }
                    showToast('Submitted for internal review. CS has been notified.', 'success');
                    window.location.reload();
                })
                .catch(function () { showToast('Something went wrong.', 'error'); btnDone(self); });
        });
    });

    // ── Step 3a: CS flags the deck — handled by module-scope delegation above ──

    // ── Step 3b: CS submits to client ─────────────────────────────────────────
    var submissionSubmitBtn = document.getElementById('submissionSubmitBtn');
    if (submissionSubmitBtn) {
        submissionSubmitBtn.addEventListener('click', function () {
            btnLoading(submissionSubmitBtn);
            fetch('/projects/' + detailProjectId + '/submission/submit-to-client', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.success) { showToast(data.error, 'error'); btnDone(submissionSubmitBtn); return; }
                    showToast('Project submitted to client.', 'success');
                    var emailModal = document.getElementById('email-draft-modal');
                    var emailYes = document.getElementById('emailDraftYes');
                    var emailNo = document.getElementById('emailDraftNo');
                    if (emailModal && emailYes && emailNo) {
                        emailModal.classList.remove('hidden');
                        var subject = encodeURIComponent(data.project_name);
                        var body = encodeURIComponent('Please find attached the latest client deck for ' + data.project_name + '.\n\nBest regards,');
                        var mailto = 'mailto:' + (data.client_email || '') + '?subject=' + subject + '&body=' + body;
                        emailYes.onclick = function () { emailModal.classList.add('hidden'); window.open(mailto); window.location.reload(); };
                        emailNo.onclick = function () { emailModal.classList.add('hidden'); window.location.reload(); };
                    } else {
                        window.location.reload();
                    }
                })
                .catch(function () { showToast('Something went wrong.', 'error'); btnDone(submissionSubmitBtn); });
        });
    }

    // ── Step 5: CS sends revision request ─────────────────────────────────────
    (function () {
        var sendRevisionBtn = document.getElementById('sendRevisionBtn');
        var sendRevisionForm = document.getElementById('sendRevisionForm');
        var sendRevisionCancel = document.getElementById('sendRevisionCancel');
        var sendRevisionConfirm = document.getElementById('sendRevisionConfirm');
        var revisionPickerList = document.getElementById('revisionPickerList');
        var submissionApprovalSection = document.getElementById('submissionApprovalSection');

        if (!sendRevisionBtn) return;
        var pickerBuilt = false;

        sendRevisionBtn.addEventListener('click', function () {
            sendRevisionForm.classList.remove('hidden');
            if (submissionApprovalSection) submissionApprovalSection.classList.add('hidden');

            if (!pickerBuilt && revisionPickerList) {
                if (!window.PAGE.posmActive && (window.PAGE.projectHasConcept || window.PAGE.projectHasKV)) {
                    if (window.PAGE.projectHasConcept && window.PAGE.projectHasKV) {
                        revisionPickerList.appendChild(makeCampaignRow('__concept__', 'Concept & KV'));
                    } else {
                        if (window.PAGE.projectHasConcept) revisionPickerList.appendChild(makeCampaignRow('__concept__', 'Concept'));
                        if (window.PAGE.projectHasKV) revisionPickerList.appendChild(makeCampaignRow('__kv__', 'Initial KV'));
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
                if (submissionApprovalSection) submissionApprovalSection.classList.remove('hidden');
                clearRichContent('revisionMessage');
            });
        }

        if (sendRevisionConfirm) {
            sendRevisionConfirm.addEventListener('click', function () {
                var message = getRichContent('revisionMessage');
                if (!message) { showToast('Please describe what needs to be revised.', 'error'); return; }

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
                if (includesConcept && window.PAGE.projectHasKV) includesKV = true;
                if (checked.length === 0 && !includesConcept && !includesKV) {
                    showToast('Select at least one item to revise.', 'error'); return;
                }
                btnLoading(sendRevisionConfirm);

                var revPosmCountry = null;
                var revPosmCustomerId = null;
                if (window.PAGE.posmActive) {
                    var revRegionSel = document.getElementById('revPosmRegionSelect');
                    var revCustomerSel = document.getElementById('revPosmCustomerSelect');
                    revPosmCountry = revRegionSel ? (revRegionSel.value || null) : null;
                    revPosmCustomerId = revCustomerSel ? (parseInt(revCustomerSel.value) || null) : null;
                }

                fetch('/projects/' + detailProjectId + '/submission/send-revision', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: message, deliverable_ids: checked,
                        includes_concept: includesConcept, includes_kv: includesKV,
                        posm_country: revPosmCountry, posm_customer_id: revPosmCustomerId
                    })
                })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (!data.success) { showToast(data.error || 'Could not send revision.', 'error'); btnDone(sendRevisionConfirm); return; }
                        showToast('Revision sent. Designer has been notified.', 'success');
                        window.location.reload();
                    })
                    .catch(function () { showToast('Something went wrong.', 'error'); btnDone(sendRevisionConfirm); });
            });
        }
    })();

    // ── Step 6: Designer starts the revision ──────────────────────────────────
    var startRevisionBtn = document.getElementById('startRevisionBtn');
    if (startRevisionBtn) {
        startRevisionBtn.addEventListener('click', function () {
            btnLoading(startRevisionBtn);
            fetch('/projects/' + detailProjectId + '/submission/start-revision', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.success) { showToast(data.error || 'Could not start revision.', 'error'); btnDone(startRevisionBtn); return; }
                    showToast('Revision started. CS has been notified.', 'success');
                    window.location.reload();
                })
                .catch(function () { showToast('Something went wrong.', 'error'); btnDone(startRevisionBtn); });
        });
    }

    // ── C&KV: Submit to Client ────────────────────────────────────────────────
    var ckvSubmitToClientBtn = document.getElementById('ckvSubmitToClientBtn');
    if (ckvSubmitToClientBtn) {
        ckvSubmitToClientBtn.addEventListener('click', function () {
            ckvSubmitToClientBtn.disabled = true;
            ckvSubmitToClientBtn.textContent = 'Submitting...';
            fetch('/projects/' + detailProjectId + '/submission/submit-to-client', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ckv: true })
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.success) {
                        showToast(data.error || 'Could not submit.', 'error');
                        ckvSubmitToClientBtn.disabled = false; ckvSubmitToClientBtn.textContent = 'Submit to Client'; return;
                    }
                    showToast('C&KV submitted to client.', 'success');
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
                    ckvSubmitToClientBtn.disabled = false; ckvSubmitToClientBtn.textContent = 'Submit to Client';
                });
        });
    }

    // ── C&KV: Send for Revision ───────────────────────────────────────────────
    (function () {
        var ckvSendRevisionBtn = document.getElementById('ckvSendRevisionBtn');
        var ckvRevisionForm = document.getElementById('ckvRevisionForm');
        var ckvRevisionCancel = document.getElementById('ckvRevisionCancel');
        var ckvRevisionConfirm = document.getElementById('ckvRevisionConfirm');

        if (!ckvSendRevisionBtn) return;

        ckvSendRevisionBtn.addEventListener('click', function () {
            ckvRevisionForm.classList.remove('hidden');
            ckvSendRevisionBtn.classList.add('hidden');
        });

        if (ckvRevisionCancel) {
            ckvRevisionCancel.addEventListener('click', function () {
                ckvRevisionForm.classList.add('hidden');
                ckvSendRevisionBtn.classList.remove('hidden');
                clearRichContent('ckvRevisionMessage');
            });
        }

        if (ckvRevisionConfirm) {
            ckvRevisionConfirm.addEventListener('click', function () {
                var message = getRichContent('ckvRevisionMessage');
                if (!message) { showToast('Please describe the revision required.', 'error'); return; }
                ckvRevisionConfirm.disabled = true;
                ckvRevisionConfirm.textContent = 'Sending...';
                fetch('/projects/' + detailProjectId + '/submission/send-revision', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ckv: true, message: message })
                })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (!data.success) {
                            showToast(data.error || 'Could not send revision.', 'error');
                            ckvRevisionConfirm.disabled = false; ckvRevisionConfirm.textContent = 'Send Revision'; return;
                        }
                        showToast('Revision sent. Designer has been notified.', 'success');
                        window.location.reload();
                    })
                    .catch(function () {
                        showToast('Something went wrong.', 'error');
                        ckvRevisionConfirm.disabled = false; ckvRevisionConfirm.textContent = 'Send Revision';
                    });
            });
        }
    })();

    // ── C&KV: Start Revision ──────────────────────────────────────────────────
    var ckvStartRevisionBtn = document.getElementById('ckvStartRevisionBtn');
    if (ckvStartRevisionBtn) {
        ckvStartRevisionBtn.addEventListener('click', function () {
            ckvStartRevisionBtn.disabled = true;
            ckvStartRevisionBtn.textContent = 'Starting...';
            fetch('/projects/' + detailProjectId + '/submission/start-revision', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ckv: true })
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.success) {
                        showToast(data.error || 'Could not start revision.', 'error');
                        ckvStartRevisionBtn.disabled = false; ckvStartRevisionBtn.textContent = 'Start Revision'; return;
                    }
                    showToast('Revision started. CS has been notified.', 'success');
                    window.location.reload();
                })
                .catch(function () {
                    showToast('Something went wrong.', 'error');
                    ckvStartRevisionBtn.disabled = false; ckvStartRevisionBtn.textContent = 'Start Revision';
                });
        });
    }

    // ── POSM: restore last-active channel on page load ────────────────────────
    (function () {
        var savedId = sessionStorage.getItem('posmActiveChannel');
        if (savedId && document.getElementById('posm-ch-' + savedId)) {
            sessionStorage.removeItem('posmActiveChannel');
            selectPosmChannel(savedId);
        } else {
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

    // ── Channel file upload ───────────────────────────────────────────────────
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
            fetch('/projects/' + projectId + '/submission/upload', { method: 'POST', body: formData })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.success) {
                        if (statusEl) { statusEl.textContent = data.error || 'Upload failed.'; }
                        showToast(data.error || 'Upload failed.', 'error'); return;
                    }
                    reloadToChannel(chId);
                })
                .catch(function () {
                    if (statusEl) { statusEl.textContent = 'Upload failed.'; }
                    showToast('Something went wrong during upload.', 'error');
                });
            fileInput.value = '';
        });
    });
}

// ── B9: Event Delegation ──────────────────────────────────────────────────────
//
// All inline onclick=/onchange= attributes have been removed from detail.html.
// A single listener on `document` catches every click that bubbles up and
// routes it to the right handler via the element's data-action attribute.
// Survives DOM replacement — refreshSection() swaps HTML without re-wiring.

document.addEventListener('click', function (e) {

    var flagBtn = e.target.closest('[data-action="open-flag-modal"]');
    if (flagBtn) { openFlagModalFromBtn(flagBtn); return; }

    if (e.target.closest('[data-action="close-flag-modal"]')) { closeFlagModal(); return; }

    var overlay = e.target.closest('[data-action="close-flag-modal-overlay"]');
    if (overlay && e.target === overlay) { closeFlagModal(); return; }

    if (e.target.closest('[data-action="submit-flag"]')) { submitFlag(); return; }

    var resolveBtn = e.target.closest('[data-action="resolve-flag"]');
    if (resolveBtn) { resolveFlag(parseInt(resolveBtn.dataset.flagId), parseInt(resolveBtn.dataset.projectId)); return; }

    var cancelBtn = e.target.closest('[data-action="cancel-customer"]');
    if (cancelBtn) { confirmCancelCustomer(parseInt(cancelBtn.dataset.customerId), JSON.parse(cancelBtn.dataset.customerName)); return; }

    var removeBtn = e.target.closest('[data-action="remove-customer"]');
    if (removeBtn) { confirmRemoveCustomer(parseInt(removeBtn.dataset.customerId), JSON.parse(removeBtn.dataset.customerName)); return; }

    var startBtn = e.target.closest('[data-action="open-start-project-modal"]');
    if (startBtn) { openStartProjectModal(parseInt(startBtn.dataset.projectId), startBtn.dataset.team || ''); return; }

    if (e.target.closest('[data-action="close-start-project-modal"]')) { closeStartProjectModal(); return; }

    var assignSelfBtn = e.target.closest('[data-action="assign-lead-self"]');
    if (assignSelfBtn) { assignLeadSelf(assignSelfBtn.dataset.team, parseInt(assignSelfBtn.dataset.projectId)); return; }

    var showTransferBtn = e.target.closest('[data-action="show-transfer-form"]');
    if (showTransferBtn) { showTransferForm(showTransferBtn.dataset.team); return; }

    var confirmTransferBtn = e.target.closest('[data-action="confirm-transfer"]');
    if (confirmTransferBtn) { confirmTransfer(confirmTransferBtn.dataset.team, parseInt(confirmTransferBtn.dataset.projectId)); return; }

    var cancelTransferBtn = e.target.closest('[data-action="cancel-transfer"]');
    if (cancelTransferBtn) { cancelTransfer(cancelTransferBtn.dataset.team); return; }

    var takeoverBtn = e.target.closest('[data-action="open-takeover-modal"]');
    if (takeoverBtn) { openTakeoverModal(takeoverBtn.dataset.team, takeoverBtn.dataset.currentOwner, parseInt(takeoverBtn.dataset.projectId)); return; }

    if (e.target.closest('[data-action="close-takeover-modal"]')) { closeTakeoverModal(); return; }

    if (e.target.closest('[data-action="select-ckv-channel"]')) { selectCkvChannel(); return; }

    var channelPill = e.target.closest('[data-action="select-posm-channel"]');
    if (channelPill) { selectPosmChannel(parseInt(channelPill.dataset.channelId)); return; }

    var approveCkvBtn = e.target.closest('[data-action="approve-ckv"]');
    if (approveCkvBtn) { approveCKV(parseInt(approveCkvBtn.dataset.projectId)); return; }

    if (e.target.closest('[data-action="close-posm-prompt-overlay"]') &&
        e.target === e.target.closest('[data-action="close-posm-prompt-overlay"]')) {
        closePosmPromptModal(); return;
    }
    if (e.target.closest('[data-action="posm-prompt-add"]')) { sendPosmPromptResponse('add_posm'); return; }
    if (e.target.closest('[data-action="posm-prompt-pause"]')) { sendPosmPromptResponse('pause'); return; }
    if (e.target.closest('[data-action="posm-prompt-approve"]')) { sendPosmPromptResponse('approve'); return; }
    if (e.target.closest('[data-action="posm-prompt-cancel"]')) { closePosmPromptModal(); window.location.reload(); return; }

    var unapproveKvBtn = e.target.closest('[data-action="unapprove-ckv"]');
    if (unapproveKvBtn) {
        var projectId = unapproveKvBtn.dataset.projectId;
        openApprovalModal(
            'Reverse C&KV Approval?',
            'This will move Concept & KV back to Submitted to Client. If the project was fully approved it will also be unlocked. The CS lead will be notified.',
            function () {
                fetch('/projects/' + projectId + '/unapprove-ckv', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' }
                })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (data.success) { showToast('C&KV approval reversed', 'warning'); setTimeout(function () { location.reload(); }, 800); }
                        else { showToast(data.error || 'Something went wrong', 'error'); }
                    })
                    .catch(function () { showToast('Something went wrong', 'error'); });
            }
        );
        return;
    }

    var unapproveChBtn = e.target.closest('[data-action="unapprove-channel"]');
    if (unapproveChBtn) {
        var channelId = unapproveChBtn.dataset.channelId;
        var projectId = unapproveChBtn.dataset.projectId;
        var label = unapproveChBtn.dataset.label || 'this channel';
        openApprovalModal(
            'Reverse Channel Approval?',
            'This will move "' + label + '" back to Submitted to Client and reset its deliverables. If the project was fully approved it will also be unlocked. The CS lead will be notified.',
            function () {
                fetch('/projects/' + projectId + '/unapprove-channel/' + channelId, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' }
                })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (data.success) { showToast('Channel approval reversed', 'warning'); setTimeout(function () { location.reload(); }, 800); }
                        else { showToast(data.error || 'Something went wrong', 'error'); }
                    })
                    .catch(function () { showToast('Something went wrong', 'error'); });
            }
        );
        return;
    }

    var historyToggle = e.target.closest('[data-action="toggle-posm-history"]');
    if (historyToggle) { togglePosmHistory(historyToggle); return; }

    var resetPillBtn = e.target.closest('[data-action="open-pill-reset-modal"]');
    if (resetPillBtn) { openPillResetModal(resetPillBtn); return; }

    if (e.target.closest('[data-action="close-pill-reset-modal"]')) { closePillResetModal(); return; }

    var pillResetOverlay = e.target.closest('[data-action="close-pill-reset-overlay"]');
    if (pillResetOverlay && e.target === pillResetOverlay) { closePillResetModal(); return; }

    var downloadAllBtn = e.target.closest('[data-action="download-all-zip"]');
    if (downloadAllBtn) { triggerZipDownload(downloadAllBtn); return; }

    var customerToggle = e.target.closest('[data-action="toggle-customer-block"]');
    if (customerToggle) { toggleCustomerBlock(customerToggle); return; }

    if (e.target.closest('[data-action="toggle-flag-history"]')) { toggleFlagHistory(); return; }

    // ── Form submit with inline confirm ───────────────────────────────────────
    // WHY requestSubmit() instead of dispatchEvent(new Event('submit')):
    // dispatchEvent fires the JS event but browsers do NOT submit the form —
    // only real user actions or form.requestSubmit() trigger actual submission.
    var confirmSubmitBtn = e.target.closest('[data-action="confirm-submit"]');
    if (confirmSubmitBtn) {
        e.preventDefault();
        openRemoveCSModal(confirmSubmitBtn.closest('form'), confirmSubmitBtn.dataset.confirmMessage);
        return;
    }

    if (e.target.closest('[data-action="close-remove-cs-modal"]')) { closeRemoveCSModal(); return; }

    var removeCsOverlay = e.target.closest('[data-action="close-remove-cs-overlay"]');
    if (removeCsOverlay && e.target === removeCsOverlay) { closeRemoveCSModal(); return; }

    if (e.target.closest('[data-action="confirm-remove-cs"]')) {
        var pendingForm = _pendingRemoveForm;
        closeRemoveCSModal();
        if (pendingForm) {
            if (pendingForm.requestSubmit) { pendingForm.requestSubmit(); } else { pendingForm.submit(); }
        }
        return;
    }

    var attachBtn = e.target.closest('[data-action="attach-extra-file"]');
    if (attachBtn) {
        var inputId = attachBtn.dataset.inputId;
        var fileInput = document.getElementById(inputId);
        if (fileInput) fileInput.click();
        return;
    }

    var delFileBtn = e.target.closest('[data-action="delete-extra-file"]');
    if (delFileBtn) {
        var fileId = parseInt(delFileBtn.dataset.fileId);
        if (!confirm('Delete this attached file?')) return;
        fetch('/projects/submission/file/' + fileId, { method: 'DELETE' })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    var row = document.querySelector('.submission-extra-file[data-file-id="' + fileId + '"]');
                    if (row) row.remove();
                    showToast('File deleted', 'success');
                } else {
                    showToast(data.error || 'Something went wrong', 'error');
                }
            })
            .catch(function () { showToast('Something went wrong', 'error'); });
        return;
    }
});

// ── Extra file attachment: change delegation ──────────────────────────────────
document.addEventListener('change', function (e) {
    var input = e.target;
    if (!input || input.type !== 'file') return;
    if (!input.id || !input.id.startsWith('extraFileInput')) return;

    var file = input.files[0];
    if (!file) return;

    var attachBtn = document.querySelector('[data-action="attach-extra-file"][data-input-id="' + input.id + '"]');
    var statusEl = attachBtn ? attachBtn.parentElement.querySelector('.reference-file-upload-status') : null;
    var submissionId = attachBtn ? parseInt(attachBtn.dataset.submissionId) : null;
    if (!submissionId) return;

    if (statusEl) statusEl.textContent = 'Uploading…';

    var formData = new FormData();
    formData.append('file', file);

    // Read project ID directly from the URL so this module-scope handler
    // always sees the current page's ID regardless of SPA navigation.
    var currentProjectId = parseInt(window.location.pathname.split('/')[2]);

    fetch('/projects/' + currentProjectId + '/submission/' + submissionId + '/add-file', {
        method: 'POST', body: formData
    })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (!data.success) {
                if (statusEl) statusEl.textContent = 'Error: ' + (data.error || 'failed');
                return;
            }
            if (statusEl) statusEl.textContent = '';
            var ef = data.file;
            var row = document.createElement('div');
            row.className = 'reference-file-item submission-extra-file';
            row.dataset.fileId = ef.id;
            row.innerHTML =
                '<span class="reference-file-icon">📎</span>' +
                '<span class="reference-file-name">' + ef.original_filename + '</span>' +
                '<span class="reference-file-meta">' + ef.uploaded_by + '</span>' +
                '<div class="reference-file-actions">' +
                    '<a href="/projects/submission/file/' + ef.id + '/download" class="btn-secondary btn-sm">Download</a>' +
                    '<button type="button" class="btn-danger btn-sm" data-action="delete-extra-file" data-file-id="' + ef.id + '">✕</button>' +
                '</div>';
            if (attachBtn && attachBtn.parentElement) {
                attachBtn.parentElement.parentElement.insertBefore(row, attachBtn.parentElement);
            }
            input.value = '';
            showToast('File attached', 'success');
        })
        .catch(function () { if (statusEl) statusEl.textContent = 'Upload failed.'; });
});

// ── Status select: change delegation ─────────────────────────────────────────
document.addEventListener('change', function (e) {
    var sel = e.target.closest('select[data-action="update-status"]');
    if (sel) { updateStatus(sel); }
});

// ── Assign designer form: submit delegation ───────────────────────────────────
document.addEventListener('submit', function (e) {
    var form = e.target.closest('form[data-action="assign-designer-form"]');
    if (!form) return;
    e.preventDefault();

    var projectId = form.dataset.projectId;
    var btn = form.querySelector('button[type="submit"]');
    btnLoading(btn);

    fetch(form.action, { method: 'POST', body: new FormData(form) })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (!data.success) { showToast(data.error || 'Could not assign designer.', 'error'); btnDone(btn); return; }
            var names = (data.assignments || []).map(function (a) { return a.name + ' assigned to this project'; });
            showToast(names.length ? names.join('. ') + '.' : 'Designer assigned.', 'success');
            refreshSection(projectId, 'section-assignments');
        })
        .catch(function () { btnDone(btn); showToast('Could not assign designer.', 'error'); });
});

// ── Pill revert / reset modal (admin / cs) ────────────────────────────────────

var _pillResetContext = null;

function openPillResetModal(btn) {
    var action = btn.dataset.pillAction || 'reset';  // 'revert' or 'reset'
    _pillResetContext = {
        action:         action,
        pillType:       btn.dataset.pillType,
        pillLabel:      btn.dataset.pillLabel || 'this pill',
        posmCountry:    btn.dataset.posmCountry  || null,
        posmCustomerId: btn.dataset.posmCustomerId || null,
        projectId:      parseInt(window.location.pathname.split('/')[2])
    };

    var isRevert = action === 'revert';

    // Title
    var title = document.getElementById('pillResetModalTitle');
    if (title) title.textContent = isRevert ? 'Revert Pill' : 'Reset Pill';

    // Description
    var desc = document.getElementById('pillResetModalDesc');
    if (desc) {
        desc.textContent = isRevert
            ? 'Revert "' + _pillResetContext.pillLabel + '" — keeps the initial submission file and sets the pill back to internal review (revision 0). All later submissions and client revision rounds will be deleted.'
            : 'Reset "' + _pillResetContext.pillLabel + '" — permanently deletes all submission files and revision history, resetting the pill to the "not started" state.';
    }

    // Revision input is only relevant for a full reset
    var revRow = document.getElementById('pillResetRevRow');
    if (revRow) revRow.style.display = isRevert ? 'none' : '';
    var revInput = document.getElementById('pillResetRevInput');
    if (revInput) revInput.value = 0;

    // Warning
    var warning = document.getElementById('pillResetWarning');
    if (warning) {
        warning.textContent = isRevert
            ? '⚠ This permanently deletes all submissions after the first one, and all revision records. It cannot be undone.'
            : '⚠ This permanently deletes all submission files and revision history for this pill. It cannot be undone.';
    }

    // Confirm button label
    var oldBtn = document.getElementById('pillResetConfirmBtn');
    if (oldBtn) {
        oldBtn.textContent = isRevert ? '↩ Revert Pill' : '↺ Reset Pill';
        // Replace the button node to strip any stale listeners
        var newBtn = oldBtn.cloneNode(true);
        oldBtn.parentNode.replaceChild(newBtn, oldBtn);
        newBtn.addEventListener('click', submitPillReset);
    }

    var modal = document.getElementById('pillResetModal');
    if (modal) {
        modal.classList.remove('hidden');
        if (window.helixPolling) window.helixPolling.pause();
    }
}

function closePillResetModal() {
    var modal = document.getElementById('pillResetModal');
    if (modal) modal.classList.add('hidden');
    _pillResetContext = null;
    if (window.helixPolling) window.helixPolling.resume();
}

function submitPillReset() {
    if (!_pillResetContext) return;
    var isRevert = _pillResetContext.action === 'revert';
    var revInput = document.getElementById('pillResetRevInput');
    var targetRevision = (revInput && !isRevert) ? Math.max(0, parseInt(revInput.value, 10) || 0) : 0;
    var confirmBtn = document.getElementById('pillResetConfirmBtn');
    if (confirmBtn) {
        confirmBtn.disabled = true;
        confirmBtn.textContent = isRevert ? 'Reverting…' : 'Resetting…';
    }

    var body = {
        action:          _pillResetContext.action,
        pill_type:       _pillResetContext.pillType,
        target_revision: targetRevision
    };
    if (_pillResetContext.posmCountry)    body.posm_country     = _pillResetContext.posmCountry;
    if (_pillResetContext.posmCustomerId) body.posm_customer_id = parseInt(_pillResetContext.posmCustomerId, 10);

    fetch('/projects/' + _pillResetContext.projectId + '/reset-pill', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(body)
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
        if (data.success) {
            closePillResetModal();
            showToast(isRevert ? 'Pill reverted to initial submission' : ('Pill reset to revision ' + targetRevision), 'warning');
            setTimeout(function () { location.reload(); }, 800);
        } else {
            showToast(data.error || (isRevert ? 'Revert failed' : 'Reset failed'), 'error');
            if (confirmBtn) {
                confirmBtn.disabled = false;
                confirmBtn.textContent = isRevert ? '↩ Revert Pill' : '↺ Reset Pill';
            }
        }
    })
    .catch(function () {
        showToast('Something went wrong', 'error');
        if (confirmBtn) {
            confirmBtn.disabled = false;
            confirmBtn.textContent = isRevert ? '↩ Revert Pill' : '↺ Reset Pill';
        }
    });
}

// ── Bootstrap ─────────────────────────────────────────────────────────────────
// Wire direct-listener buttons on the current page, and re-wire after every
// SPA navigation (sidebar.js dispatches helix:navigated once the new page
// content is in the DOM).
_initDetailPage();
document.addEventListener('helix:navigated', _initDetailPage);
