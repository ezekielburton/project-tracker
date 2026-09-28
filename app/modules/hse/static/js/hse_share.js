// The "Email this report" dialog (templates/hse/_share_dialog.html), on My
// performance and on the printable reports. Posts the picked people and the
// note as JSON to the form's action. Document listeners are guarded so SPA
// re-runs never stack a second set.
(function () {
    if (window.hseShareWired) return;
    window.hseShareWired = true;

    function message(form, text, ok) {
        var slot = form.querySelector('.hse-share-msg');
        slot.textContent = text;
        slot.classList.toggle('is-ok', Boolean(ok));
        slot.hidden = false;
    }

    document.addEventListener('click', function (e) {
        var dialog = document.getElementById('hse-share');
        if (!dialog) return;
        if (e.target.closest('[data-share-open]')) {
            e.preventDefault();
            var form = dialog.querySelector('form');
            form.reset();
            form.querySelector('.hse-share-msg').hidden = true;
            form.querySelector('[data-share-send]').hidden = false;
            form.querySelector('[data-share-cancel]').textContent = 'Cancel';
            dialog.showModal();
        } else if (e.target.closest('[data-share-cancel]')) {
            dialog.close();
        }
    });

    document.addEventListener('submit', function (e) {
        var form = e.target.closest('.hse-share-form');
        if (!form) return;
        e.preventDefault();
        var send = form.querySelector('[data-share-send]');
        var to = Array.prototype.map.call(
            form.querySelectorAll('input[name="to"]:checked'),
            function (input) { return Number(input.value); });
        send.disabled = true;
        fetch(form.getAttribute('action'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ to: to, note: form.querySelector('textarea').value })
        }).then(function (res) {
            return res.json().then(function (body) { return { ok: res.ok, body: body }; });
        }).then(function (result) {
            send.disabled = false;
            if (!result.ok) {
                message(form, result.body.error || 'Could not send.', false);
                return;
            }
            var text = 'Sent to ' + result.body.sent.join(', ') + '.';
            // In the app a toast confirms it; the printable reports have no
            // toasts, so the dialog says so and offers Close.
            if (window.showToast) {
                form.closest('dialog').close();
                window.showToast(text, 'success');
            } else {
                message(form, text, true);
                send.hidden = true;
                form.querySelector('[data-share-cancel]').textContent = 'Close';
            }
        }).catch(function () {
            send.disabled = false;
            message(form, 'Could not reach the server.', false);
        });
    });
})();
