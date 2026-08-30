// settings-overlay.js — Vitamin-E
// Opens auth.account's content inside a modal instead of navigating there.
// Reuses the exact fragment sidebar.js's SPA nav already gets from the
// server (X-Nav-Request), so every form and endpoint on that page keeps
// working unchanged — this only changes how it's displayed.

(function () {
    var trigger = document.getElementById('settings-dropdown-btn');
    var modal = document.getElementById('settings-modal');
    var body = document.getElementById('settings-modal-body');
    var closeBtn = document.getElementById('settings-modal-close');
    var dropdown = document.getElementById('account-dropdown');

    if (!trigger || !modal) return;

    function openSettings() {
        if (dropdown) dropdown.classList.add('hidden');
        modal.classList.remove('hidden');
        if (window.helixPolling) window.helixPolling.pause();

        fetch('/account', { headers: { 'X-Nav-Request': '1' } })
            .then(function (r) {
                if (!r.ok) throw new Error('settings-fetch-failed');
                return r.text();
            })
            .then(function (html) {
                body.innerHTML = html;
                if (window.helixExecScripts) window.helixExecScripts(body);
            })
            .catch(function () {
                body.innerHTML = '<p class="muted">Could not load settings. Please try again.</p>';
            });
    }

    function closeSettings() {
        modal.classList.add('hidden');
        body.innerHTML = ''; // so the next open re-fetches fresh instead of flashing stale content
        if (window.helixPolling) window.helixPolling.resume();
    }

    trigger.addEventListener('click', openSettings);
    closeBtn.addEventListener('click', closeSettings);
    modal.addEventListener('click', function (e) {
        if (e.target === modal) closeSettings();
    });
})();