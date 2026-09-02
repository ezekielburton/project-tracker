// digital_innovation_board.js — Digital Innovation module, board page.
// Phase 2a: the "+ New project" modal. Phase 2b: chunk 2 added "+ New
// feature"; chunk 3 added the read-only feature detail modal; chunk 4
// makes it interactive (tick/add/delete steps, advance, close). The
// Incoming overlay (button + card modal) was added 1 Sep 2026, followed
// same-day by a live indicator on its badge — a small, scoped piece of
// the still-pending "frontend SSE wiring" chunk, built just for this
// button rather than a general board-wide live refresh.

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
            if (promoteCard) diPromoteIntakeItem(promoteCard.getAttribute('data-di-intake-id'), promoteCard.getAttribute('data-di-kind'));
            return;
        }
        var dismissBtn = e.target.closest('.di-incoming-dismiss-btn');
        if (dismissBtn) {
            var dismissCard = dismissBtn.closest('.di-incoming-card[data-di-intake-id]');
            if (dismissCard) diDismissIntakeItem(dismissCard.getAttribute('data-di-intake-id'), dismissCard.getAttribute('data-di-kind'));
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
        var closeProjectBtn = e.target.closest('.di-project-close-btn');
        if (closeProjectBtn) {
            diCloseProject(closeProjectBtn.getAttribute('data-di-project-id'));
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
        if (document.activeElement && (
            document.activeElement.id === 'di-cost-add-hours' ||
            document.activeElement.id === 'di-cost-add-amount' ||
            document.activeElement.id === 'di-cost-add-description'
        )) {
            diAddCostEntry();
        }
    });

    // Toggles the add-row's Hours+Feature vs. Amount inputs whenever the
    // cost type changes — delegated (not bound directly to
    // #di-cost-add-type) for the same reason every other listener here
    // is: this script tag re-executes on every SPA nav, so a direct
    // addEventListener on the select itself would stack a duplicate
    // listener per visit.
    document.addEventListener('change', function (e) {
        if (e.target.id === 'di-cost-add-type') {
            _diToggleCostTypeFields();
        }
    });

    // Debounced type-to-search for the link-project picker. Delegated on
    // 'input' rather than bound directly to #di-link-search-input, same
    // reasoning as the click/keydown delegation above — this script tag
    // re-executes on every SPA nav to a DI page, so a direct addEventListener
    // on the input element itself would stack a duplicate listener per visit.
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

// Last known Incoming count, tracked so a live update can tell "went up"
// (worth a pulse) from "went down" (someone else promoted/dismissed) or
// "unchanged" (an SSE ping for an unrelated DI change, e.g. a step tick —
// di_changes is a per-project doorbell, not itemized, so every ping on
// this project re-checks Incoming even when nothing there actually
// moved). Reset to null by _diSyncLiveStream on every (re)connect — see
// there for why.
var _diIncomingCount = null;

// Opens (or re-opens, on project change) ONE live connection per board
// page — read off .di-board's own data-di-project-id (present on every
// board, not just the permanent one), so this now opens for every viewer
// regardless of whether they can see the Incoming button. Originally
// scoped to just the Incoming badge (1 Sep 2026); widened 2 Sep 2026 to
// also drive the board-wide live refresh below rather than opening a
// second connection to the same route, per the plan noted when the badge
// shipped. Torn down and recreated on every SPA navigation via the
// 'helix:navigated' listener below, exactly like this script's own
// re-execution resets _diNewFeatureProjectId etc. above — except a live
// EventSource, unlike a plain var, has to be explicitly closed or it
// leaks a connection (and a server-side subscriber queue, see
// sse_relay.py) for as long as the tab stays open, even after navigating
// to a page that never touches this file again.
function _diSyncLiveStream() {
    var board = document.querySelector('.di-board[data-di-project-id]');
    var projectId = board ? board.getAttribute('data-di-project-id') : null;

    // Already watching the right thing (including "nothing to watch" on
    // a page with no DI board) — nothing to do.
    if (window._diLiveStreamProjectId === projectId) return;

    if (window._diLiveStream) {
        window._diLiveStream.close();
        window._diLiveStream = null;
    }
    window._diLiveStreamProjectId = projectId;
    _diIncomingCount = null;

    if (!projectId || typeof EventSource === 'undefined') return;

    // Seed the baseline from what the server already rendered, so the
    // very first live ping compares against the true starting count
    // rather than null (which _diUpdateIncomingBadge treats as "just
    // connected, don't pulse yet"). Only present when the Incoming
    // overlay itself is on the page (permanent board + can_edit_board).
    var cardsContainer = document.querySelector('#di-incoming-modal .di-incoming-cards');
    if (cardsContainer) {
        _diIncomingCount = cardsContainer.querySelectorAll('.di-incoming-card[data-di-intake-id]').length;
    }

    // di_changes is a plain "something changed" doorbell (see sse.py) —
    // no per-message detail, so every ping just triggers a re-fetch of
    // whatever this page shows rather than trying to parse what changed.
    var source = new EventSource('/sse/digital-innovation/' + projectId);
    source.onmessage = function () { _diHandleLivePing(); };
    window._diLiveStream = source;
}

// Fans one SSE ping out to everything on the page that needs to react.
// diRefreshBoard always runs (every viewer, on every board, cares about
// feature moves/step ticks/new or closed features); diRefreshIncomingTray
// only when the Incoming button exists (permanent board + can_edit_board
// — same gate board.html already applies to rendering it). Does NOT
// touch an open feature-detail modal even if the ping is about that very
// feature — re-rendering mid-interaction (e.g. while typing a new step)
// would stomp on unsaved input; left as a known gap, same tier as the
// FeatureRequest-SSE gap noted elsewhere in this file's history.
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

function diCloseProject(projectId) {
    fetch('/digital-innovation/projects/' + projectId + '/close', { method: 'POST' })
        .then(function (res) {
            if (!res.ok) throw new Error('request failed');
            // Full navigation, same reasoning as submitDiNewProject below:
            // a rare action, and the sidebar's project list has to reflect
            // the closed project's absence regardless of which board is
            // currently open — including the one that was just closed.
            window.location.href = '/digital-innovation/';
        })
        .catch(function () {
            window.location.reload();
        });
}

function openDiIncomingModal() {
    var modal = document.getElementById('di-incoming-modal');
    if (modal) modal.classList.remove('hidden');
}

function closeDiIncomingModal() {
    var modal = document.getElementById('di-incoming-modal');
    if (modal) modal.classList.add('hidden');
}

// kind is 'feature_request' (a live FeatureRequest card) or 'intake_item'
// (a native DiIntakeItem, the default if a card is somehow missing the
// attribute) — see board_data.py's IncomingCard and routes/intake.py's
// two separate route pairs for why these aren't the same endpoint.
function diPromoteIntakeItem(id, kind) {
    var url = kind === 'feature_request'
        ? '/digital-innovation/feature-requests/' + id + '/promote'
        : '/digital-innovation/intake/' + id + '/promote';
    _diApplyIncomingAction(fetch(url, { method: 'POST' }));
}

function diDismissIntakeItem(id, kind) {
    var url = kind === 'feature_request'
        ? '/digital-innovation/feature-requests/' + id + '/dismiss'
        : '/digital-innovation/intake/' + id + '/dismiss';
    // Unlike Promote, dismissing never touches the board itself (no new
    // feature, no column/count change) — only the tray's own contents,
    // so just refresh the card list in place rather than reloading the
    // whole page. That also means the modal stays open, so a user
    // clearing several items doesn't get kicked out after each one.
    fetch(url, { method: 'POST' })
        .then(function (res) {
            if (!res.ok) throw new Error('request failed');
            diRefreshIncomingTray();
        })
        .catch(function () {
            diRefreshIncomingTray();
        });
}

// Called on every SSE ping (see _diHandleLivePing above) — re-fetches
// the same _board_columns.html fragment board.html itself rendered on
// load (columns + closed-features strip, wrapped together in
// #di-board-body) and swaps it in wholesale, so another user's feature
// move, step tick, new feature or closed feature shows up without a
// manual reload. The subtitle's "N active features" count is derived
// client-side from the swapped-in DOM afterward rather than fetched
// separately — one fragment, one request, same "cheap enough to just
// re-render" reasoning as diRefreshIncomingTray below.
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
            // The response is itself the #di-board-body wrapper (see
            // _board_columns.html), so replace the whole node rather
            // than setting innerHTML on it — otherwise we'd end up with
            // #di-board-body nested inside #di-board-body.
            var wrapper = document.createElement('div');
            wrapper.innerHTML = html;
            var fresh = wrapper.firstElementChild;
            if (fresh) container.replaceWith(fresh);

            var subtitle = document.querySelector('.di-board-subtitle');
            if (subtitle) {
                var count = document.querySelectorAll('#di-board-body .di-card[data-feature-id]').length;
                subtitle.textContent = 'Project board \u00b7 ' + count + ' active feature' + (count !== 1 ? 's' : '');
            }
        })
        .catch(function () {
            // Same "nice-to-have on top of a working full reload"
            // reasoning as diRefreshIncomingTray's catch below — a
            // network blip just leaves the board showing its last known
            // state until the next successful ping or a manual reload.
        });
}

// Called on every SSE ping (see _diHandleLivePing above) — re-fetches
// the same _incoming_cards.html fragment board.html itself rendered on
// load, swaps it into the (possibly-hidden) overlay so it's never stale
// by the time someone opens it, and updates the trigger's badge from the
// fetched count.
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
            // Live refresh is a nice-to-have on top of the button already
            // working correctly on every full page load — if this one
            // fetch fails (a network blip), the badge just keeps showing
            // its last known count until the next successful ping or a
            // manual reload; never worth surfacing an error for.
        });
}

// Creates/updates/removes the badge to match `count`, and — only when
// the count went UP since the last check, i.e. something new actually
// arrived rather than someone else acting on an existing item — replays
// a brief pulse animation so the arrival is genuinely noticeable, not
// just a number that quietly changed.
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
        // Remove-then-reflow-then-add so the animation restarts even if
        // it's still mid-run from a previous arrival a few seconds ago —
        // just re-adding the same class name on an element that already
        // has it is a no-op in CSS, the browser needs to see it actually
        // leave and come back.
        badge.classList.remove('di-incoming-badge--pulse');
        void badge.offsetWidth;
        badge.classList.add('di-incoming-badge--pulse');
    }
}

// Only used by Promote now (Dismiss refreshes the tray in place instead,
// see diDismissIntakeItem above) — promoting adds a card to a column and
// shifts the header's "X active features" count, so a full reload is
// simpler than patching each affected piece client-side. The reload also
// naturally closes the Incoming modal, which is the desired behavior on
// Promote (Ezekiel: modal should only close when you promote something).
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

// System-project link picker — search-as-you-type against the shared
// Project table (routes/projects.py::search_projects), gated the same as
// the trigger/badge that opens this modal. Setting or clearing the link
// reloads the page on success (diSetProjectLink), same "rare mutating
// action, simpler to re-render server-side" reasoning as
// _diApplyIncomingAction above — it also naturally closes the modal.

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
            // The input may have moved on to a newer query while this
            // request was in flight — only render if it's still current.
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

// Set whenever the Cost breakdown modal is opened — add/delete both need
// the project id, same reasoning as _diCurrentFeatureId above.
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
    // No board reload on close — unlike the feature detail modal, cost
    // entries don't affect anything the board itself displays (columns,
    // counts), so there's nothing on the page behind the modal to catch
    // up on.
}

// Shared by add/delete below — same "swap the fragment on success, show
// the persistent error slot on failure" shape as
// _diApplyFeatureDetailAction, mirrored here for the cost modal.
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

// Toggles the add-row's Hours+Feature inputs vs. its Amount input to
// match the selected cost type — Dev Time is priced from hours × the
// department rate (lib/costs.py computes the amount server-side), every
// other type takes a typed-in amount instead. Delegated 'change' handler
// below calls this on every switch; the template's own initial markup
// already matches this shape for the default selection (Dev Time, the
// first <option>), so there's no need to call it again right after a
// fragment swap.
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
