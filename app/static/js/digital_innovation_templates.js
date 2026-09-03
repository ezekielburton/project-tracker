// digital_innovation_templates.js — Digital Innovation module, the
// admin-only Edit Templates screen. Same "fetch an HTML fragment and
// swap it in" pattern as digital_innovation_board.js's feature detail
// modal: every add/edit/delete/move POSTs or DELETEs, then swaps the
// returned fragment into #di-templates-body. As of 3 Sep 2026 that
// swap also happens on a DI-wide live SSE ping (another admin's own
// add/edit/delete/move) — safe to always auto-apply (Ezekiel's explicit
// choice) because the add/edit modal (#di-template-step-modal) lives
// OUTSIDE #di-templates-body entirely, so refreshing the list behind it
// never touches whatever's currently typed into an open modal. See
// digital_innovation_live.js for the shared connection-watching helper
// this calls into.

if (!window._diTemplatesDispatcherWired) {
    window._diTemplatesDispatcherWired = true;

    document.addEventListener('click', function (e) {
        var addBtn = e.target.closest('.di-template-add-btn');
        if (addBtn) {
            openDiTemplateStepModal({ stage: addBtn.getAttribute('data-stage') });
            return;
        }
        var editBtn = e.target.closest('.di-template-edit-btn');
        if (editBtn) {
            var editRow = editBtn.closest('.di-template-step[data-step-id]');
            if (editRow) {
                openDiTemplateStepModal({
                    stepId: editRow.getAttribute('data-step-id'),
                    title: editRow.getAttribute('data-title'),
                    details: editRow.getAttribute('data-details'),
                });
            }
            return;
        }
        var deleteBtn = e.target.closest('.di-template-delete-btn');
        if (deleteBtn) {
            var deleteRow = deleteBtn.closest('.di-template-step[data-step-id]');
            if (deleteRow) diDeleteTemplateStep(deleteRow.getAttribute('data-step-id'));
            return;
        }
        var moveBtn = e.target.closest('.di-template-move-btn');
        if (moveBtn && !moveBtn.disabled) {
            var moveRow = moveBtn.closest('.di-template-step[data-step-id]');
            if (moveRow) diMoveTemplateStep(moveRow.getAttribute('data-step-id'), moveBtn.getAttribute('data-direction'));
            return;
        }
        if (e.target.closest('#di-template-step-cancel') || e.target.id === 'di-template-step-modal') {
            closeDiTemplateStepModal();
            return;
        }
        if (e.target.closest('#di-template-step-save')) {
            submitDiTemplateStepModal();
            return;
        }
    });

    document.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter') return;
        if (document.activeElement && (document.activeElement.id === 'di-template-step-title' || document.activeElement.id === 'di-template-step-details')) {
            submitDiTemplateStepModal();
        }
    });
}

// Set by openDiTemplateStepModal(): null stepId means "adding a new step
// to _diTemplateModalStage"; a stepId means "editing that existing step"
// (its stage never changes, so the stage isn't needed once editing).
var _diTemplateModalStepId = null;
var _diTemplateModalStage = null;

function openDiTemplateStepModal(opts) {
    var modal = document.getElementById('di-template-step-modal');
    var modalTitle = document.getElementById('di-template-step-modal-title');
    var titleInput = document.getElementById('di-template-step-title');
    var detailsInput = document.getElementById('di-template-step-details');
    var error = document.getElementById('di-template-step-error');
    if (!modal) return;

    _diTemplateModalStepId = opts.stepId || null;
    _diTemplateModalStage = opts.stage || null;

    if (modalTitle) modalTitle.textContent = _diTemplateModalStepId ? 'Edit step' : 'Add step';
    if (titleInput) titleInput.value = opts.title || '';
    if (detailsInput) detailsInput.value = opts.details || '';
    if (error) error.classList.add('hidden');

    modal.classList.remove('hidden');
    if (titleInput) titleInput.focus();
}

function closeDiTemplateStepModal() {
    var modal = document.getElementById('di-template-step-modal');
    if (modal) modal.classList.add('hidden');
}

function submitDiTemplateStepModal() {
    var titleInput = document.getElementById('di-template-step-title');
    var detailsInput = document.getElementById('di-template-step-details');
    var error = document.getElementById('di-template-step-error');
    var title = titleInput ? titleInput.value.trim() : '';
    var details = detailsInput ? detailsInput.value.trim() : '';

    if (!title) {
        if (error) { error.textContent = 'Title is required.'; error.classList.remove('hidden'); }
        return;
    }

    var url = _diTemplateModalStepId
        ? '/digital-innovation/template-steps/' + _diTemplateModalStepId
        : '/digital-innovation/templates/' + _diTemplateModalStage + '/steps';

    fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: title, details: details }),
    })
        .then(function (res) { return res.text().then(function (text) { return { ok: res.ok, text: text }; }); })
        .then(function (result) {
            if (result.ok) {
                var body = document.getElementById('di-templates-body');
                if (body) body.innerHTML = result.text;
                closeDiTemplateStepModal();
                return;
            }
            var message = 'Something went wrong — try again.';
            try {
                var data = JSON.parse(result.text);
                if (data && data.error) message = data.error;
            } catch (e) { /* leave the generic message */ }
            if (error) { error.textContent = message; error.classList.remove('hidden'); }
        })
        .catch(function () {
            if (error) { error.textContent = 'Something went wrong — try again.'; error.classList.remove('hidden'); }
        });
}

function diDeleteTemplateStep(stepId) {
    _diApplyTemplatesBodyAction(fetch('/digital-innovation/template-steps/' + stepId, { method: 'DELETE' }));
}

function diMoveTemplateStep(stepId, direction) {
    _diApplyTemplatesBodyAction(fetch('/digital-innovation/template-steps/' + stepId + '/move', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ direction: direction }),
    }));
}

function _diApplyTemplatesBodyAction(fetchPromise) {
    var body = document.getElementById('di-templates-body');
    fetchPromise
        .then(function (res) {
            if (!res.ok) throw new Error('request failed');
            return res.text();
        })
        .then(function (html) { if (body) body.innerHTML = html; })
        .catch(function () {
            // Delete/move failures are rare (a 404 on an already-removed
            // row, two admins editing at once) — reload rather than leave
            // the screen showing stale state silently.
            window.location.reload();
        });
}


// Re-fetches _templates_body.html fresh and swaps it into
// #di-templates-body — same innerHTML-swap _diApplyTemplatesBodyAction
// already uses for every mutating action above, not a whole-node
// replaceWith, since (unlike _board_columns.html/_archive_lists.html)
// this fragment was never self-wrapping to begin with — #di-templates-
// body is templates.html's own wrapper, not part of the fragment.
function diRefreshTemplatesBody() {
    var body = document.getElementById('di-templates-body');
    if (!body) return;

    fetch('/digital-innovation/templates/body')
        .then(function (res) {
            if (!res.ok) throw new Error('failed to refresh templates body');
            return res.text();
        })
        .then(function (html) { body.innerHTML = html; })
        .catch(function () {
            // A failed live refresh isn't worth surfacing to the user —
            // the page just stays showing what it last successfully
            // loaded, same as if the ping had never arrived.
        });
}

diWatchDashboardStream('templates', '#di-templates-body', diRefreshTemplatesBody);
