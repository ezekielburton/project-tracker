// digital_innovation_archive.js — Digital Innovation module, the Archive
// screen: closed and archived projects, each reopenable, closed ones
// also archivable one step further. Reopen/Archive themselves still do a
// full reload — these actions are rare, at most a handful of rows, and
// the acting user already sees the result immediately either way, so
// re-rendering the whole screen server-side stays simpler than
// hand-patching the DOM for THAT case. What's new (3 Sep 2026) is a live
// refresh for the OTHER case — someone ELSE closing/archiving/reopening
// a project while this screen is just sitting open — via a DI-wide SSE
// ping; see digital_innovation_live.js for the shared connection-
// watching helper this calls into.

if (!window._diArchiveDispatcherWired) {
    window._diArchiveDispatcherWired = true;

    document.addEventListener('click', function (e) {
        var reopenBtn = e.target.closest('.di-archive-reopen-btn');
        if (reopenBtn) {
            var reopenRow = reopenBtn.closest('.di-archive-row[data-di-project-id]');
            if (reopenRow) diReopenProject(reopenRow.getAttribute('data-di-project-id'));
            return;
        }
        var archiveBtn = e.target.closest('.di-archive-archive-btn');
        if (archiveBtn) {
            var archiveRow = archiveBtn.closest('.di-archive-row[data-di-project-id]');
            if (archiveRow) diArchiveProject(archiveRow.getAttribute('data-di-project-id'));
            return;
        }
    });
}

function diReopenProject(projectId) {
    _diApplyArchiveAction(fetch('/digital-innovation/projects/' + projectId + '/reopen', { method: 'POST' }));
}

function diArchiveProject(projectId) {
    _diApplyArchiveAction(fetch('/digital-innovation/projects/' + projectId + '/archive', { method: 'POST' }));
}

function _diApplyArchiveAction(fetchPromise) {
    fetchPromise
        .then(function (res) {
            if (!res.ok) throw new Error('request failed');
            // Full reload — the row that moved needs to leave this list (or,
            // for reopen, leave the page entirely), and there are at most a
            // handful of rows here, so re-rendering the whole screen
            // server-side is simpler than hand-patching the DOM.
            window.location.reload();
        })
        .catch(function () {
            window.location.reload();
        });
}


// Re-fetches _archive_lists.html fresh and swaps #di-archive-lists
// wholesale — same "replace the whole wrapper node" reasoning
// digital_innovation_board.js's diRefreshBoard and this module's own
// diRefreshPerformanceTable use.
function diRefreshArchiveLists() {
    var container = document.getElementById('di-archive-lists');
    if (!container) return;

    fetch('/digital-innovation/archive/lists')
        .then(function (res) {
            if (!res.ok) throw new Error('failed to refresh archive lists');
            return res.text();
        })
        .then(function (html) {
            var wrapper = document.createElement('div');
            wrapper.innerHTML = html;
            var fresh = wrapper.firstElementChild;
            if (fresh) container.replaceWith(fresh);
        })
        .catch(function () {
            // A failed live refresh isn't worth surfacing to the user —
            // the page just stays showing what it last successfully
            // loaded, same as if the ping had never arrived.
        });
}

diWatchDashboardStream('archive', '#di-archive-lists', diRefreshArchiveLists);
