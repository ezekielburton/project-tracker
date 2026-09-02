// digital_innovation_archive.js — Digital Innovation module, the Archive
// screen: closed and archived projects, each reopenable, closed ones
// also archivable one step further. Same "reload after a mutating
// action" approach digital_innovation_board.js uses for new project/
// feature creation — these actions are rare, and there's no fragment
// worth swapping for a list this short.

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
