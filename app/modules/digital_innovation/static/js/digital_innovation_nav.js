// Digital Innovation: routes DI's own links (rail project list, Performance
// tabs and period arrows) through window.navigateTo for SPA nav. The rail's
// shared items are handled by module_rail.js. Falls back to a full load if
// navigateTo is missing. Export is not a navigation, so it is left out.
// Also owns the rail's project Close button, since the rail is on every
// DI screen and this is the one script they all load.
(function () {
    var NAV_SELECTOR = '.di-project-item, .di-perf-tab, .di-perf-nav-arrow';

    // SPA nav re-runs this script; wire the document listener once.
    if (window._diNavDispatcherWired) return;
    window._diNavDispatcherWired = true;

    function go(url, push) {
        if (window.navigateTo) {
            window.navigateTo(url, push);
        } else {
            window.location.href = url;
        }
    }

    // Closing the board on screen lands on the permanent board, replacing
    // the history entry so Back does not return to the closed board's 404.
    // Anywhere else, the current screen re-renders so the rail (and the
    // Archive list) pick up the change.
    function closeProject(projectId) {
        fetch('/digital-innovation/projects/' + projectId + '/close', { method: 'POST' })
            .then(function (res) {
                if (!res.ok) throw new Error('request failed');
                var board = document.querySelector('.di-board[data-di-project-id]');
                if (board && board.getAttribute('data-di-project-id') === String(projectId)) {
                    history.replaceState(history.state, '', '/digital-innovation');
                    go('/digital-innovation', false);
                } else {
                    go(window.location.pathname + window.location.search, false);
                }
            })
            .catch(function () {
                if (typeof showToast === 'function') showToast('Could not close the project — try again.', 'error');
            });
    }

    document.addEventListener('click', function (e) {
        var closeBtn = e.target.closest('.di-project-close-btn');
        if (closeBtn) {
            closeProject(closeBtn.getAttribute('data-di-project-id'));
            return;
        }
        var item = e.target.closest(NAV_SELECTOR);
        if (!item) return;
        // Modified and non-left clicks keep the browser's new tab/window behaviour.
        if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        var url = item.getAttribute('href');
        if (!url) return;
        e.preventDefault();
        go(url);
    });
})();
