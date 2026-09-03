/* Invoicing page — Days Pending threshold modal (admin/management).
   IIFE + direct init so it re-runs on SPA nav (no DOMContentLoaded gate). */
(function () {
    function init() {
        var btn = document.getElementById('cs-inv-thresholds-btn');
        var modal = document.getElementById('cs-inv-thresholds-modal');
        if (!btn || !modal) return;

        var green = document.getElementById('cs-inv-green');
        var red = document.getElementById('cs-inv-red');
        var err = document.getElementById('cs-inv-thresholds-error');
        var save = document.getElementById('cs-inv-thresholds-save');
        var cancel = document.getElementById('cs-inv-thresholds-cancel');

        function open() { err.classList.add('hidden'); modal.classList.remove('hidden'); }
        function close() { modal.classList.add('hidden'); }
        function showError(msg) { err.textContent = msg; err.classList.remove('hidden'); }

        btn.addEventListener('click', open);
        cancel.addEventListener('click', close);
        modal.addEventListener('click', function (e) { if (e.target === modal) close(); });

        save.addEventListener('click', function () {
            var payload = {
                days_green_max: parseInt(green.value, 10),
                days_red_max: parseInt(red.value, 10)
            };
            save.disabled = true;
            fetch(save.dataset.url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            }).then(function (r) {
                return r.json().then(function (d) { return { ok: r.ok, d: d }; });
            }).then(function (res) {
                if (res.ok) { window.location.reload(); }
                else { showError(res.d.error || 'Could not save.'); save.disabled = false; }
            }).catch(function () { showError('Could not save.'); save.disabled = false; });
        });
    }
    init();
})();
