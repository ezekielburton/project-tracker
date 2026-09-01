// digital_innovation_board.js — Digital Innovation module, board page.
// Phase 2a: the "+ New project" modal. Phase 2b: chunk 2 added "+ New
// feature"; chunk 3 added the read-only feature detail modal; chunk 4
// makes it interactive (tick/add/delete steps, advance, close). The
// Incoming tray is still ahead.

// Guard against re-registering this listener every time the SPA nav
// re-executes this script (sidebar.js's execScripts() genuinely re-runs
// external <script> tags on every navigation to this page) — same pattern
// as file-templates.js. Without this, document (which is never destroyed)
// would accumulate one extra click listener per visit.
if (!window._diDispatcherWired) {
    window._diDispatcherWired = true;

    document.addEventListener('click', function (e) {
        // Cards on the board and rows in the closed-features strip both
        // carry data-feature-id and open the same detail modal.
        var featureTrigger = e.target.closest('[data-feature-id]');
        if (featureTrigger) {
            openDiFeatureDetail(featureTrigger.getAttribute('data-feature-id'));
            return;
        }
        if (e.target.closest('#di-feature-detail-close') || e.target.id === 'di-feature-detail-modal') {
            closeDiFeatureDetail();
            return;
        }
        // Step rows: click anywhere on the row to tick/untick, except the
        // delete button — that's checked first so it doesn't also toggle
        // the tick underneath it.
        var deleteBtn = e.target.closest('.di-step-delete');
        if (deleteBtn) {
            var stepToDelete = deleteBtn.closest('.di-step[data-step-id]');
            if (stepToDelete) diDeleteStep(stepToDelete.getAttribute('data-step-id'));
            return;
        }
        var stepRow = e.target.closest('.di-step[data-step-id]');
        if (stepRow) {
            var nowDone = stepRow.getAttribute('data-step-done') !== 'true';
            diTickStep(stepRow.getAttribute('data-step-id'), nowDone);
            return;
        }
        if (e.target.closest('#di-step-add-btn')) {
            diAddStep();
            return;
        }
        if (e.target.closest('.di-advance-feature-btn')) {
            diAdvanceFeature();
            return;
        }
        if (e.target.closest('.di-close-feature-btn')) {
            diCloseFeature();
            return;
        }
        if (e.target.closest('#di-new-project-trigger')) {
            openDiNewProjectModal();
            return;
        }
        if (e.target.closest('#di-new-project-cancel') || e.target.id === 'di-new-project-modal') {
            closeDiNewProjectModal();
            return;
        }
        if (e.target.closest('#di-new-project-save')) {
            submitDiNewProject();
            return;
        }
        if (e.target.closest('#di-add-feature-trigger')) {
            openDiNewFeatureModal(e.target.closest('#di-add-feature-trigger'));
            return;
        }
        if (e.target.closest('#di-new-feature-cancel') || e.target.id === 'di-new-feature-modal') {
            closeDiNewFeatureModal();
            return;
        }
        if (e.target.closest('#di-new-feature-save')) {
            submitDiNewFeature();
            return;
        }
    });

    document.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter') return;
        if (document.activeElement && document.activeElement.id === 'di-new-project-name') {
            submitDiNewProject();
        }
        if (document.activeElement && document.activeElement.id === 'di-new-feature-name') {
            submitDiNewFeature();
        }
        if (document.activeElement && (document.activeElement.id === 'di-step-add-title' || document.activeElement.id === 'di-step-add-details')) {
            diAddStep();
        }
    });
}

// Set when the "+ Add feature" trigger is clicked (it carries the current
// board's project id via a data attribute) — read back on submit so the
// POST goes to the right project.
var _diNewFeatureProjectId = null;

// Set whenever the feature detail modal is opened — every step/advance/
// close action needs the feature id, and reading it off the currently
// open feature avoids sprinkling data-feature-id across buttons inside
// the fragment (which would collide with the board-card click delegation
// above, since that matches on the same attribute).
var _diCurrentFeatureId = null;

// True once any mutating action inside the open modal has succeeded —
// closing the modal then does a full reload so the board reflects the
// change, same "reload rather than hand-patch the DOM" approach already
// used for new project/feature creation.
var _diFeatureDetailDirty = false;

function openDiNewProjectModal() {
    var modal = document.getElementById('di-new-project-modal');
    if (!modal) return;
    modal.classList.remove('hidden');
    var input = document.getElementById('di-new-project-name');
    if (input) { input.value = ''; input.focus(); }
    var error = document.getElementById('di-new-project-error');
    if (error) error.classList.add('hidden');
}

function closeDiNewProjectModal() {
    var modal = document.getElementById('di-new-project-modal');
    if (modal) modal.classList.add('hidden');
}

function submitDiNewProject() {
    var input = document.getElementById('di-new-project-name');
    var error = document.getElementById('di-new-project-error');
    var name = input ? input.value.trim() : '';

    if (!name) {
        if (error) { error.textContent = 'Name is required.'; error.classList.remove('hidden'); }
        return;
    }

    fetch('/digital-innovation/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name }),
    })
        .then(function (res) { return res.json().then(function (data) { return { ok: res.ok, data: data }; }); })
        .then(function (result) {
            if (!result.ok) {
                var message = (result.data && result.data.error) || 'Could not create the project.';
                if (error) { error.textContent = message; error.classList.remove('hidden'); }
                return;
            }
            // Full navigation (not SPA nav) — simplest way to land on the new
            // board with a correct sidebar + column state, and this action is
            // rare enough that the reload cost doesn't matter.
            window.location.href = '/digital-innovation/' + result.data.id;
        })
        .catch(function () {
            if (error) { error.textContent = 'Something went wrong — try again.'; error.classList.remove('hidden'); }
        });
}


function openDiNewFeatureModal(trigger) {
    var modal = document.getElementById('di-new-feature-modal');
    if (!modal) return;
    _diNewFeatureProjectId = trigger.getAttribute('data-di-project-id');
    modal.classList.remove('hidden');
    var input = document.getElementById('di-new-feature-name');
    if (input) { input.value = ''; input.focus(); }
    var date = document.getElementById('di-new-feature-date');
    if (date) date.value = '';
    var error = document.getElementById('di-new-feature-error');
    if (error) error.classList.add('hidden');
}

function closeDiNewFeatureModal() {
    var modal = document.getElementById('di-new-feature-modal');
    if (modal) modal.classList.add('hidden');
}

function submitDiNewFeature() {
    var input = document.getElementById('di-new-feature-name');
    var dateInput = document.getElementById('di-new-feature-date');
    var error = document.getElementById('di-new-feature-error');
    var name = input ? input.value.trim() : '';

    if (!name) {
        if (error) { error.textContent = 'Name is required.'; error.classList.remove('hidden'); }
        return;
    }
    if (!_diNewFeatureProjectId) return;

    fetch('/digital-innovation/' + _diNewFeatureProjectId + '/features', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name, projected_date: dateInput ? dateInput.value : '' }),
    })
        .then(function (res) { return res.json().then(function (data) { return { ok: res.ok, data: data }; }); })
        .then(function (result) {
            if (!result.ok) {
                var message = (result.data && result.data.error) || 'Could not create the feature.';
                if (error) { error.textContent = message; error.classList.remove('hidden'); }
                return;
            }
            // Same reasoning as new-project creation: reload to land in a
            // correct, consistent column state rather than hand-patching
            // the DOM. Live SSE refresh is a later phase.
            window.location.reload();
        })
        .catch(function () {
            if (error) { error.textContent = 'Something went wrong — try again.'; error.classList.remove('hidden'); }
        });
}


function openDiFeatureDetail(featureId) {
    var modal = document.getElementById('di-feature-detail-modal');
    var body = document.getElementById('di-feature-detail-body');
    var error = document.getElementById('di-feature-detail-error');
    if (!modal || !body) return;
    _diCurrentFeatureId = featureId;
    _diFeatureDetailDirty = false;
    if (error) error.classList.add('hidden');
    body.innerHTML = '<p class="di-feature-detail-loading">Loading…</p>';
    modal.classList.remove('hidden');

    fetch('/digital-innovation/features/' + featureId)
        .then(function (res) {
            if (!res.ok) throw new Error('failed to load feature ' + featureId);
            return res.text();
        })
        .then(function (html) { body.innerHTML = html; })
        .catch(function () {
            body.innerHTML = '<p class="di-feature-detail-loading">Could not load this feature — try again.</p>';
        });
}

function closeDiFeatureDetail() {
    var modal = document.getElementById('di-feature-detail-modal');
    if (modal) modal.classList.add('hidden');
    if (_diFeatureDetailDirty) {
        // A tick/add/delete/advance/close happened while the modal was
        // open — reload so the board's columns and counts catch up,
        // rather than hand-patching every place a feature's state shows.
        window.location.reload();
    }
}

// Shared by every step/advance/close action below: POSTs or DELETEs,
// swaps the returned fragment into the modal body on success, or shows
// the returned error message in the persistent error slot on failure.
// That slot lives outside #di-feature-detail-body specifically so it
// survives the innerHTML swap on the next successful action.
function _diApplyFeatureDetailAction(fetchPromise) {
    var body = document.getElementById('di-feature-detail-body');
    var error = document.getElementById('di-feature-detail-error');

    fetchPromise
        .then(function (res) {
            if (res.ok) {
                _diFeatureDetailDirty = true;
                if (error) error.classList.add('hidden');
                return res.text().then(function (html) { if (body) body.innerHTML = html; });
            }
            return res.json().catch(function () { return {}; }).then(function (data) {
                var message = (data && data.error) || 'Something went wrong — try again.';
                if (error) { error.textContent = message; error.classList.remove('hidden'); }
            });
        })
        .catch(function () {
            if (error) { error.textContent = 'Something went wrong — try again.'; error.classList.remove('hidden'); }
        });
}

function diTickStep(stepId, done) {
    _diApplyFeatureDetailAction(fetch('/digital-innovation/steps/' + stepId + '/tick', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ done: done }),
    }));
}

function diDeleteStep(stepId) {
    _diApplyFeatureDetailAction(fetch('/digital-innovation/steps/' + stepId, { method: 'DELETE' }));
}

function diAddStep() {
    var titleInput = document.getElementById('di-step-add-title');
    var detailsInput = document.getElementById('di-step-add-details');
    var title = titleInput ? titleInput.value.trim() : '';
    var details = detailsInput ? detailsInput.value.trim() : '';
    if (!title || !_diCurrentFeatureId) return;

    _diApplyFeatureDetailAction(fetch('/digital-innovation/features/' + _diCurrentFeatureId + '/steps', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: title, details: details }),
    }));
}

function diAdvanceFeature() {
    if (!_diCurrentFeatureId) return;
    _diApplyFeatureDetailAction(fetch('/digital-innovation/features/' + _diCurrentFeatureId + '/advance', {
        method: 'POST',
    }));
}

function diCloseFeature() {
    if (!_diCurrentFeatureId) return;
    _diApplyFeatureDetailAction(fetch('/digital-innovation/features/' + _diCurrentFeatureId + '/close', {
        method: 'POST',
    }));
}
