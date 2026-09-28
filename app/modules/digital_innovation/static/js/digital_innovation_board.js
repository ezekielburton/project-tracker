// Digital Innovation board page: new project/feature modals, feature detail
// modal, Incoming overlay, project link picker, cost breakdown modal, and the
// live SSE refresh of the board.

// SPA nav re-runs this script on every visit, so document listeners are
// wired once behind a window flag or they would stack.
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
        // Delete is checked before the step row so it does not also toggle the tick.
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
        if (e.target.closest('.di-move-stage-btn')) {
            diMoveFeatureStage();
            return;
        }
        if (e.target.closest('.di-close-feature-btn')) {
            diCloseFeature();
            return;
        }
        if (e.target.closest('.di-reopen-feature-btn')) {
            diReopenFeature();
            return;
        }
        if (e.target.closest('#di-incoming-trigger')) {
            openDiIncomingModal();
            return;
        }
        if (e.target.closest('#di-incoming-modal-close') || e.target.id === 'di-incoming-modal') {
            closeDiIncomingModal();
            return;
        }
        var promoteBtn = e.target.closest('.di-incoming-promote-btn');
        if (promoteBtn) {
            var promoteCard = promoteBtn.closest('.di-incoming-card[data-di-intake-id]');
            if (promoteCard) diPromoteIntakeItem(promoteCard.getAttribute('data-di-intake-id'));
            return;
        }
        var dismissBtn = e.target.closest('.di-incoming-dismiss-btn');
        if (dismissBtn) {
            var dismissCard = dismissBtn.closest('.di-incoming-card[data-di-intake-id]');
            if (dismissCard) diDismissIntakeItem(dismissCard.getAttribute('data-di-intake-id'));
            return;
        }
        var trackBadge = e.target.closest('#di-track-badge');
        if (trackBadge) {
            diToggleProjectTrack(trackBadge.getAttribute('data-project-id'), trackBadge.getAttribute('data-track'));
            return;
        }
        if (e.target.closest('#di-linked-badge') || e.target.closest('#di-link-project-trigger')) {
            openDiLinkProjectModal();
            return;
        }
        if (e.target.closest('#di-link-modal-close') || e.target.id === 'di-link-project-modal') {
            closeDiLinkProjectModal();
            return;
        }
        var linkResult = e.target.closest('.di-link-result[data-project-id]');
        if (linkResult) {
            diSetProjectLink(parseInt(linkResult.getAttribute('data-project-id'), 10));
            return;
        }
        if (e.target.closest('#di-link-clear-btn')) {
            diSetProjectLink(null);
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
        if (e.target.closest('#di-cost-trigger')) {
            var costTrigger = e.target.closest('#di-cost-trigger');
            openDiCostBreakdown(costTrigger.getAttribute('data-di-project-id'));
            return;
        }
        if (e.target.closest('#di-cost-close') || e.target.id === 'di-cost-modal') {
            closeDiCostBreakdown();
            return;
        }
        if (e.target.closest('#di-cost-add-btn')) {
            diAddCostEntry();
            return;
        }
        var costDeleteBtn = e.target.closest('.di-cost-delete-btn');
        if (costDeleteBtn) {
            var costRow = costDeleteBtn.closest('tr[data-entry-id]');
            if (costRow) diDeleteCostEntry(costRow.getAttribute('data-entry-id'));
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
        if (document.activeElement && document.activeElement.id === 'di-linked-badge') {
            openDiLinkProjectModal();
        }
        if (document.activeElement && document.activeElement.id === 'di-track-badge') {
            diToggleProjectTrack(document.activeElement.getAttribute('data-project-id'), document.activeElement.getAttribute('data-track'));
        }
        if (document.activeElement && (
            document.activeElement.id === 'di-cost-add-hours' ||
            document.activeElement.id === 'di-cost-add-amount' ||
            document.activeElement.id === 'di-cost-add-description'
        )) {
            diAddCostEntry();
        }
    });

    // Swaps the cost add-row's inputs when the cost type changes.
    document.addEventListener('change', function (e) {
        if (e.target.id === 'di-cost-add-type') {
            _diToggleCostTypeFields();
        }
    });

    // Debounced search for the link-project picker.
    document.addEventListener('input', function (e) {
        if (e.target.id !== 'di-link-search-input') return;
        var query = e.target.value.trim();
        window.clearTimeout(window._diLinkSearchTimer);
        if (query.length < 2) {
            _diRenderLinkResults([], query);
            return;
        }
        window._diLinkSearchTimer = window.setTimeout(function () {
            _diFetchLinkResults(query);
        }, 250);
    });
}

// Project id for the "+ Add feature" POST, taken from the trigger's data attribute.
var _diNewFeatureProjectId = null;

// Feature open in the detail modal. Kept here so buttons inside the
// fragment need no data-feature-id, which the board-card click handler matches.
var _diCurrentFeatureId = null;

// True once an action in the open detail modal succeeds; closing then reloads the board.
var _diFeatureDetailDirty = false;

// Last known Incoming count, so a live update can pulse only when it goes up.
// Every ping re-checks Incoming, since di_changes does not say what changed.
// null means "just connected, do not pulse".
var _diIncomingCount = null;

// Keeps one EventSource open for the board's project, and closes it on
// SPA nav away. An unclosed EventSource leaks a connection and a server-side
// subscriber queue (sse_relay.py) for the life of the tab.
function _diSyncLiveStream() {
    var board = document.querySelector('.di-board[data-di-project-id]');
    var projectId = board ? board.getAttribute('data-di-project-id') : null;

    // Already watching the right project (or nothing, off the board).
    if (window._diLiveStreamProjectId === projectId) return;

    if (window._diLiveStream) {
        window._diLiveStream.close();
        window._diLiveStream = null;
    }
    window._diLiveStreamProjectId = projectId;
    _diIncomingCount = null;

    if (!projectId || typeof EventSource === 'undefined') return;

    // Seed the baseline from the server-rendered cards so the first ping
    // can pulse. The overlay only exists on the permanent board.
    var cardsContainer = document.querySelector('#di-incoming-modal .di-incoming-cards');
    if (cardsContainer) {
        _diIncomingCount = cardsContainer.querySelectorAll('.di-incoming-card[data-di-intake-id]').length;
    }

    // Pings carry no detail (sse.py), so each one just re-fetches the page's fragments.
    var source = new EventSource('/sse/digital-innovation/' + projectId);
    source.onmessage = function () { _diHandleLivePing(); };
    window._diLiveStream = source;
}

// Refreshes the board, plus the Incoming tray when its button is on the page.
// An open feature detail modal is left alone so typed input is not lost.
function _diHandleLivePing() {
    diRefreshBoard();
    if (document.getElementById('di-incoming-trigger')) {
        diRefreshIncomingTray();
    }
}

_diSyncLiveStream();

if (!window._diLiveStreamNavWired) {
    window._diLiveStreamNavWired = true;
    document.addEventListener('helix:navigated', _diSyncLiveStream);
}

function openDiIncomingModal() {
    var modal = document.getElementById('di-incoming-modal');
    if (modal) modal.classList.remove('hidden');
}

function closeDiIncomingModal() {
    var modal = document.getElementById('di-incoming-modal');
    if (modal) modal.classList.add('hidden');
}

// id is a FeatureRequest's id (routes/intake.py).
function diPromoteIntakeItem(id) {
    _diApplyIncomingAction(fetch('/digital-innovation/feature-requests/' + id + '/promote', { method: 'POST' }));
}

function diDismissIntakeItem(id) {
    var url = '/digital-innovation/feature-requests/' + id + '/dismiss';
    // Dismiss does not change the board, so only the tray refreshes and
    // the modal stays open for clearing several items.
    fetch(url, { method: 'POST' })
        .then(function (res) {
            if (!res.ok) throw new Error('request failed');
            diRefreshIncomingTray();
        })
        .catch(function () {
            diRefreshIncomingTray();
        });
}

// Scroll regions inside #di-board-body whose position survives a refresh.
var _DI_BOARD_SCROLLERS = '.di-columns, .di-column-cards, .di-closed-strip-list';

// Re-fetches _board_columns.html and swaps #di-board-body, then recounts
// the subtitle's "N active features" from the new cards. The closed strip's
// open state and scroll positions carry over, or every ping would reset them.
function diRefreshBoard() {
    var container = document.getElementById('di-board-body');
    var board = document.querySelector('.di-board[data-di-project-id]');
    if (!container || !board) return;
    var projectId = board.getAttribute('data-di-project-id');
    if (!projectId) return;

    fetch('/digital-innovation/' + projectId + '/board/columns')
        .then(function (res) {
            if (!res.ok) throw new Error('failed to refresh board');
            return res.text();
        })
        .then(function (html) {
            // The fragment is itself #di-board-body, so replace the node;
            // innerHTML would nest it inside itself.
            var wrapper = document.createElement('div');
            wrapper.innerHTML = html;
            var fresh = wrapper.firstElementChild;
            if (fresh) {
                var current = document.getElementById('di-board-body') || container;
                var oldStrip = current.querySelector('.di-closed-strip');
                // Read before the swap: a detached node reports scroll 0.
                var positions = Array.prototype.map.call(
                    current.querySelectorAll(_DI_BOARD_SCROLLERS),
                    function (el) { return [el.scrollTop, el.scrollLeft]; }
                );
                var freshStrip = fresh.querySelector('.di-closed-strip');
                if (oldStrip && freshStrip) freshStrip.open = oldStrip.open;
                current.replaceWith(fresh);
                // After the swap: a node must be in the page to take a scroll position.
                var freshScrollers = fresh.querySelectorAll(_DI_BOARD_SCROLLERS);
                if (freshScrollers.length === positions.length) {
                    for (var i = 0; i < positions.length; i++) {
                        freshScrollers[i].scrollTop = positions[i][0];
                        freshScrollers[i].scrollLeft = positions[i][1];
                    }
                }
            }

            var subtitle = document.querySelector('.di-board-subtitle');
            if (subtitle) {
                var count = document.querySelectorAll('#di-board-body .di-card[data-feature-id]').length;
                subtitle.textContent = 'Project board \u00b7 ' + count + ' active feature' + (count !== 1 ? 's' : '');
            }
        })
        .catch(function () {
            // Silent: the board keeps its last state until the next ping.
        });
}

// Re-fetches _incoming_cards.html into the (possibly hidden) overlay and
// updates the trigger's badge from the new count.
function diRefreshIncomingTray() {
    var trigger = document.getElementById('di-incoming-trigger');
    var cardsContainer = document.querySelector('#di-incoming-modal .di-incoming-cards');
    if (!trigger || !cardsContainer) return;
    var projectId = trigger.getAttribute('data-di-project-id');
    if (!projectId) return;

    fetch('/digital-innovation/' + projectId + '/intake/cards')
        .then(function (res) {
            if (!res.ok) throw new Error('failed to refresh Incoming items');
            return res.text();
        })
        .then(function (html) {
            cardsContainer.innerHTML = html;
            var count = cardsContainer.querySelectorAll('.di-incoming-card[data-di-intake-id]').length;
            _diUpdateIncomingBadge(trigger, count);
        })
        .catch(function () {
            // Silent: the badge keeps its last count until the next ping.
        });
}

// Creates, updates or removes the badge to match count, and pulses it
// only when the count went up.
function _diUpdateIncomingBadge(trigger, count) {
    var badge = trigger.querySelector('.di-incoming-badge');
    var isNewArrival = _diIncomingCount !== null && count > _diIncomingCount;
    _diIncomingCount = count;

    if (count > 0) {
        if (!badge) {
            badge = document.createElement('span');
            badge.className = 'di-incoming-badge';
            trigger.appendChild(badge);
        }
        badge.textContent = String(count);
    } else if (badge) {
        badge.remove();
        badge = null;
    }

    if (isNewArrival && badge) {
        // Remove, force a reflow, re-add: restarts the animation if it is still running.
        badge.classList.remove('di-incoming-badge--pulse');
        void badge.offsetWidth;
        badge.classList.add('di-incoming-badge--pulse');
    }
}

// Promote only: reloads so the new card and count show, which also closes the modal.
function _diApplyIncomingAction(fetchPromise) {
    fetchPromise
        .then(function (res) {
            if (!res.ok) throw new Error('request failed');
            window.location.reload();
        })
        .catch(function () {
            window.location.reload();
        });
}

// Flips the board's Internal/External track, then reloads: the track changes
// stage labels in several places. The badge flips straight away and flips
// back with an error toast if the save fails.
function diToggleProjectTrack(projectId, currentTrack) {
    if (!projectId) return;
    var badge = document.getElementById('di-track-badge');
    // Ignore repeat clicks while a save is in flight.
    if (badge && badge.getAttribute('aria-busy') === 'true') return;
    var nextTrack = currentTrack === 'external' ? 'internal' : 'external';
    var oldLabel = badge ? badge.textContent : '';
    if (badge) {
        badge.setAttribute('aria-busy', 'true');
        badge.setAttribute('data-track', nextTrack);
        badge.textContent = nextTrack === 'external' ? 'External' : 'Internal';
    }

    fetch('/digital-innovation/projects/' + projectId + '/track', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ track: nextTrack }),
    })
        .then(function (res) {
            if (!res.ok) throw new Error('request failed');
            window.location.reload();
        })
        .catch(function () {
            if (badge) {
                badge.removeAttribute('aria-busy');
                badge.setAttribute('data-track', currentTrack);
                badge.textContent = oldLabel;
            }
            if (typeof showToast === 'function') showToast('Could not change the track — try again.', 'error');
        });
}

function openDiLinkProjectModal() {
    var modal = document.getElementById('di-link-project-modal');
    if (!modal) return;
    modal.classList.remove('hidden');
    var input = document.getElementById('di-link-search-input');
    if (input) { input.value = ''; input.focus(); }
    _diRenderLinkResults([], '');
}

function closeDiLinkProjectModal() {
    var modal = document.getElementById('di-link-project-modal');
    if (modal) modal.classList.add('hidden');
}

function _diFetchLinkResults(query) {
    fetch('/digital-innovation/projects/search?q=' + encodeURIComponent(query))
        .then(function (res) {
            if (!res.ok) throw new Error('search failed');
            return res.json();
        })
        .then(function (results) {
            // Drop stale responses if the user has typed on since.
            var input = document.getElementById('di-link-search-input');
            if (input && input.value.trim() === query) {
                _diRenderLinkResults(results, query);
            }
        })
        .catch(function () {
            _diRenderLinkResults([], query, true);
        });
}

function _diRenderLinkResults(results, query, failed) {
    var container = document.getElementById('di-link-results');
    if (!container) return;
    container.innerHTML = '';

    if (failed) {
        var errorMsg = document.createElement('p');
        errorMsg.className = 'di-link-results-empty';
        errorMsg.textContent = 'Search failed — try again.';
        container.appendChild(errorMsg);
        return;
    }
    if (query.length < 2) {
        var hint = document.createElement('p');
        hint.className = 'di-link-results-empty';
        hint.textContent = 'Type at least 2 characters to search.';
        container.appendChild(hint);
        return;
    }
    if (results.length === 0) {
        var empty = document.createElement('p');
        empty.className = 'di-link-results-empty';
        empty.textContent = 'No matching projects.';
        container.appendChild(empty);
        return;
    }

    results.forEach(function (project) {
        var row = document.createElement('div');
        row.className = 'di-link-result';
        row.setAttribute('data-project-id', project.id);
        var name = document.createElement('span');
        name.className = 'di-link-result-name';
        name.textContent = project.name;
        row.appendChild(name);
        if (project.client) {
            var client = document.createElement('span');
            client.className = 'di-link-result-client';
            client.textContent = project.client;
            row.appendChild(client);
        }
        container.appendChild(row);
    });
}

// projectId is null to clear the link (di-link-clear-btn).
function diSetProjectLink(projectId) {
    var modal = document.getElementById('di-link-project-modal');
    var diProjectId = modal ? modal.getAttribute('data-di-project-id') : null;
    if (!diProjectId) return;

    fetch('/digital-innovation/projects/' + diProjectId + '/link', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ linked_project_id: projectId }),
    })
        .then(function (res) {
            if (!res.ok) throw new Error('request failed');
            window.location.reload();
        })
        .catch(function () {
            window.location.reload();
        });
}

function openDiNewProjectModal() {
    var modal = document.getElementById('di-new-project-modal');
    if (!modal) return;
    modal.classList.remove('hidden');
    var input = document.getElementById('di-new-project-name');
    if (input) { input.value = ''; input.focus(); }
    var track = document.getElementById('di-new-project-track');
    if (track) track.value = 'internal';
    var error = document.getElementById('di-new-project-error');
    if (error) error.classList.add('hidden');
}

function closeDiNewProjectModal() {
    var modal = document.getElementById('di-new-project-modal');
    if (modal) modal.classList.add('hidden');
}

function submitDiNewProject() {
    var input = document.getElementById('di-new-project-name');
    var trackSelect = document.getElementById('di-new-project-track');
    var error = document.getElementById('di-new-project-error');
    var name = input ? input.value.trim() : '';
    var track = trackSelect ? trackSelect.value : 'internal';

    if (!name) {
        if (error) { error.textContent = 'Name is required.'; error.classList.remove('hidden'); }
        return;
    }

    fetch('/digital-innovation/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name, track: track }),
    })
        .then(function (res) { return res.json().then(function (data) { return { ok: res.ok, data: data }; }); })
        .then(function (result) {
            if (!result.ok) {
                var message = (result.data && result.data.error) || 'Could not create the project.';
                if (error) { error.textContent = message; error.classList.remove('hidden'); }
                return;
            }
            // Full navigation so the rail's project list includes the new project.
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
    var stage = document.getElementById('di-new-feature-stage');
    if (stage) stage.selectedIndex = 0;
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
    var stageSelect = document.getElementById('di-new-feature-stage');
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
        body: JSON.stringify({
            name: name,
            projected_date: dateInput ? dateInput.value : '',
            starting_stage: stageSelect ? stageSelect.value : '',
        }),
    })
        .then(function (res) { return res.json().then(function (data) { return { ok: res.ok, data: data }; }); })
        .then(function (result) {
            if (!result.ok) {
                var message = (result.data && result.data.error) || 'Could not create the feature.';
                if (error) { error.textContent = message; error.classList.remove('hidden'); }
                return;
            }
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
        // Something changed in the modal; reload so columns and counts catch up.
        window.location.reload();
    }
}

// Runs a step/move/close request: on success swaps the returned fragment
// into the modal body, on failure shows the error. The error slot sits
// outside #di-feature-detail-body so the swap does not wipe it.
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

function diMoveFeatureStage() {
    if (!_diCurrentFeatureId) return;
    var select = document.getElementById('di-stage-picker-select');
    var stage = select ? select.value : '';
    if (!stage) return;
    // Any stage, either direction; the server (step_engine.move_to_stage) validates it.
    _diApplyFeatureDetailAction(fetch('/digital-innovation/features/' + _diCurrentFeatureId + '/move', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stage: stage }),
    }));
}

function diCloseFeature() {
    if (!_diCurrentFeatureId) return;
    _diApplyFeatureDetailAction(fetch('/digital-innovation/features/' + _diCurrentFeatureId + '/close', {
        method: 'POST',
    }));
}

function diReopenFeature() {
    if (!_diCurrentFeatureId) return;
    _diApplyFeatureDetailAction(fetch('/digital-innovation/features/' + _diCurrentFeatureId + '/reopen', {
        method: 'POST',
    }));
}

// Project open in the cost breakdown modal, for add/delete.
var _diCurrentCostProjectId = null;

function openDiCostBreakdown(projectId) {
    var modal = document.getElementById('di-cost-modal');
    var body = document.getElementById('di-cost-body');
    var error = document.getElementById('di-cost-error');
    if (!modal || !body) return;
    _diCurrentCostProjectId = projectId;
    if (error) error.classList.add('hidden');
    body.innerHTML = '<p class="di-feature-detail-loading">Loading…</p>';
    modal.classList.remove('hidden');

    fetch('/digital-innovation/' + projectId + '/costs')
        .then(function (res) {
            if (!res.ok) throw new Error('failed to load cost breakdown for project ' + projectId);
            return res.text();
        })
        .then(function (html) { body.innerHTML = html; })
        .catch(function () {
            body.innerHTML = '<p class="di-feature-detail-loading">Could not load the cost breakdown — try again.</p>';
        });
}

function closeDiCostBreakdown() {
    var modal = document.getElementById('di-cost-modal');
    if (modal) modal.classList.add('hidden');
    // No reload: cost entries do not show on the board.
}

// Cost modal version of _diApplyFeatureDetailAction.
function _diApplyCostBreakdownAction(fetchPromise) {
    var body = document.getElementById('di-cost-body');
    var error = document.getElementById('di-cost-error');

    fetchPromise
        .then(function (res) {
            if (res.ok) {
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

// Dev Time shows Feature + Hours (priced server-side at the department rate);
// other types show Amount. The fragment's markup already starts in the Dev
// Time shape, so this is not needed after a swap.
function _diToggleCostTypeFields() {
    var typeSelect = document.getElementById('di-cost-add-type');
    var featureSelect = document.getElementById('di-cost-add-feature');
    var hoursInput = document.getElementById('di-cost-add-hours');
    var amountInput = document.getElementById('di-cost-add-amount');
    if (!typeSelect) return;
    var isDevTime = typeSelect.value === 'dev_time';
    if (featureSelect) featureSelect.classList.toggle('hidden', !isDevTime);
    if (hoursInput) hoursInput.classList.toggle('hidden', !isDevTime);
    if (amountInput) amountInput.classList.toggle('hidden', isDevTime);
}

function diAddCostEntry() {
    if (!_diCurrentCostProjectId) return;

    var typeSelect = document.getElementById('di-cost-add-type');
    var dateInput = document.getElementById('di-cost-add-date');
    var descriptionInput = document.getElementById('di-cost-add-description');
    var featureSelect = document.getElementById('di-cost-add-feature');
    var hoursInput = document.getElementById('di-cost-add-hours');
    var amountInput = document.getElementById('di-cost-add-amount');

    var costType = typeSelect ? typeSelect.value : '';
    var payload = {
        date: dateInput ? dateInput.value : '',
        type: costType,
        description: descriptionInput ? descriptionInput.value.trim() : '',
    };
    if (costType === 'dev_time') {
        payload.feature_id = featureSelect ? featureSelect.value : '';
        payload.hours = hoursInput ? hoursInput.value : '';
    } else {
        payload.amount = amountInput ? amountInput.value : '';
    }

    _diApplyCostBreakdownAction(fetch('/digital-innovation/' + _diCurrentCostProjectId + '/costs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    }));
}

function diDeleteCostEntry(entryId) {
    _diApplyCostBreakdownAction(fetch('/digital-innovation/costs/' + entryId, { method: 'DELETE' }));
}
