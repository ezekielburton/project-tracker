/* Close / close-out prompts on the CS table. The SPA router re-runs this on
   every visit, so init runs inline. No-ops when the modals aren't rendered
   (viewer can't close). Closing is final: both prompts confirm, then reload. */
(function () {
    // Listeners go on .cs-page, not document, so they die with the page
    // instead of stacking each visit.
    var page = document.querySelector('.cs-page');
    var closeModal = document.getElementById('cs-close-modal');
    var outModal = document.getElementById('cs-closeout-modal');
    if (!page || !closeModal || !outModal) return;

    var pending = null;  // the close URL the open prompt is acting on

    function show(el) { el.classList.remove('hidden'); }
    function hide(el) { el.classList.add('hidden'); }

    function clearError(el) { el.textContent = ''; el.classList.add('hidden'); }
    function showError(el, msg) { el.textContent = msg; el.classList.remove('hidden'); }

    function post(url, payload, errorBox, buttons) {
        buttons.forEach(function (b) { b.disabled = true; });
        fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload || {})
        }).then(function (r) {
            return r.json().then(function (d) { return { ok: r.ok, d: d }; });
        }).then(function (res) {
            if (res.ok) { window.location.reload(); return; }
            showError(errorBox, res.d.error || 'Could not close that project.');
            buttons.forEach(function (b) { b.disabled = false; });
        }).catch(function () {
            showError(errorBox, 'Could not close that project.');
            buttons.forEach(function (b) { b.disabled = false; });
        });
    }

    // ── Live project → confirm and close ──────────────────────────────
    var subject = document.getElementById('cs-close-subject');
    var closeError = document.getElementById('cs-close-error');
    var confirmBtn = document.getElementById('cs-close-confirm');
    var closeCancel = document.getElementById('cs-close-cancel');

    page.addEventListener('click', function (e) {
        var btn = e.target.closest ? e.target.closest('.cs-close-btn') : null;
        if (!btn) return;
        pending = btn.dataset.closeUrl;
        subject.textContent = btn.dataset.projectName || '';
        clearError(closeError);
        confirmBtn.disabled = false;
        show(closeModal);
    });

    closeCancel.addEventListener('click', function () { hide(closeModal); });
    closeModal.addEventListener('click', function (e) { if (e.target === closeModal) hide(closeModal); });
    confirmBtn.addEventListener('click', function () {
        post(pending, {}, closeError, [confirmBtn]);
    });

    // ── Cancelled project → two-step prompt ───────────────────────────
    var title = document.getElementById('cs-closeout-title');
    var outSubject = document.getElementById('cs-closeout-subject');
    var step1 = document.getElementById('cs-closeout-step1');
    var step2 = document.getElementById('cs-closeout-step2');
    var error1 = document.getElementById('cs-closeout-error-1');
    var error2 = document.getElementById('cs-closeout-error-2');
    var invoiceDate = document.getElementById('cs-closeout-invoice-date');
    var valueField = document.getElementById('cs-closeout-value-field');
    var valueInput = document.getElementById('cs-closeout-value');
    var outCancel = document.getElementById('cs-closeout-cancel');
    var noBtn = document.getElementById('cs-closeout-no');
    var yesBtn = document.getElementById('cs-closeout-yes');
    var backBtn = document.getElementById('cs-closeout-back');
    var notYetBtn = document.getElementById('cs-closeout-not-yet');
    var invoicedBtn = document.getElementById('cs-closeout-invoiced');

    function toStep1() {
        title.textContent = 'Does this project need invoicing?';
        step2.hidden = true;
        step1.hidden = false;
        clearError(error1);
        clearError(error2);
        [noBtn, yesBtn, backBtn, notYetBtn, invoicedBtn].forEach(function (b) { b.disabled = false; });
    }

    function toStep2() {
        title.textContent = 'Has it been invoiced?';
        step1.hidden = true;
        step2.hidden = false;
        clearError(error2);
    }

    page.addEventListener('click', function (e) {
        var btn = e.target.closest ? e.target.closest('.cs-closeout-btn') : null;
        if (!btn) return;
        pending = btn.dataset.closeUrl;
        outSubject.textContent = btn.dataset.projectName || '';
        invoiceDate.value = '';
        valueInput.value = '';
        // Only ask for a value when this project hasn't got one.
        valueField.hidden = btn.dataset.hasValue === '1';
        toStep1();
        show(outModal);
    });

    outCancel.addEventListener('click', function () { hide(outModal); });
    outModal.addEventListener('click', function (e) { if (e.target === outModal) hide(outModal); });
    yesBtn.addEventListener('click', toStep2);
    backBtn.addEventListener('click', toStep1);

    noBtn.addEventListener('click', function () {
        post(pending, { invoice_needed: false }, error1, [noBtn, yesBtn]);
    });

    /* Both step-2 answers need a project value if it has none. Returns null
       (after showing the error) when the value is required and empty. */
    function valuePayload(errorBox) {
        if (valueField.hidden) return {};
        if (!valueInput.value) {
            showError(errorBox, 'Enter the project value.');
            return null;
        }
        return { project_value: valueInput.value };
    }

    notYetBtn.addEventListener('click', function () {
        var extra = valuePayload(error2);
        if (!extra) return;
        extra.invoice_needed = true;
        post(pending, extra, error2, [backBtn, notYetBtn, invoicedBtn]);
    });

    invoicedBtn.addEventListener('click', function () {
        if (!invoiceDate.value) {
            showError(error2, 'Enter the invoice date, or choose Not yet.');
            return;
        }
        var extra = valuePayload(error2);
        if (!extra) return;
        extra.invoice_needed = true;
        extra.invoice_date = invoiceDate.value;
        post(pending, extra, error2, [backBtn, notYetBtn, invoicedBtn]);
    });
})();
