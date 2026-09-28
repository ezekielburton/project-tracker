// settings-overlay.js — shows the /account page inside a modal.
// Fetches it with X-Nav-Request, the same stripped fragment SPA nav gets,
// and re-runs its scripts with sidebar.js's helixExecScripts.

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
                // The fragment repeats the shell's crop modal, file pickers and
                // cropper script; the page already has them, so drop the copies.
                body.querySelectorAll('#crop-modal, #avatar-file-input, #banner-file-input, script[src*="avatar-cropper.js"]')
                    .forEach(function (el) { el.remove(); });
                if (window.helixExecScripts) window.helixExecScripts(body);
            })
            .catch(function () {
                body.innerHTML = '<p class="muted">Could not load settings. Please try again.</p>';
            });
    }

    function closeSettings() {
        modal.classList.add('hidden');
        body.innerHTML = ''; // next open starts blank, with no stale flash
        if (window.helixPolling) window.helixPolling.resume();
    }

    trigger.addEventListener('click', openSettings);
    closeBtn.addEventListener('click', closeSettings);
    modal.addEventListener('click', function (e) {
        if (e.target === modal) closeSettings();
    });
})();