// Digital Innovation Archive screen: closed projects (reopen or archive) and
// archived projects (reopen). The user's own actions reload the page; other
// users' changes arrive via a DI-wide SSE ping that re-fetches the lists.

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
            // Reload so the moved row leaves its list and the rail's project list updates.
            window.location.reload();
        })
        .catch(function () {
            window.location.reload();
        });
}


// Re-fetches _archive_lists.html and replaces #di-archive-lists. The
// fragment is its own wrapper, so the node is replaced, not its innerHTML.
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
            // Silent: the page keeps its last state.
        });
}

diWatchDashboardStream('archive', '#di-archive-lists', diRefreshArchiveLists);
