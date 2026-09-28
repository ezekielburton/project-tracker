// Digital Innovation Settings screen: saves the Dev Time rate and currency as
// JSON to /digital-innovation/settings. A 400 carries `errors` (field ->
// message), shown under each field; success shows a toast.

if (!window._diSettingsDispatcherWired) {
    window._diSettingsDispatcherWired = true;

    // Delegated on document: SPA nav re-runs this script and swaps the form.
    document.addEventListener('submit', function (e) {
        if (!e.target.closest('#di-settings-form')) return;
        e.preventDefault();
        submitDiSettingsForm();
    });

    document.addEventListener('input', function (e) {
        var input = e.target.closest('#di-settings-form input[name]');
        if (input) _diShowSettingsError(input.name, '');
    });
}

function _diShowSettingsError(field, message) {
    var el = document.querySelector('[data-di-settings-error="' + field + '"]');
    if (!el) return;
    el.textContent = message;
    el.classList.toggle('hidden', !message);
}

function submitDiSettingsForm() {
    var rateInput = document.getElementById('di-settings-rate');
    var currencyInput = document.getElementById('di-settings-currency');
    var saveBtn = document.getElementById('di-settings-save');
    if (!rateInput || !currencyInput) return;

    _diShowSettingsError('dev_hourly_rate', '');
    _diShowSettingsError('currency', '');
    if (saveBtn) saveBtn.disabled = true;

    fetch('/digital-innovation/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            dev_hourly_rate: rateInput.value.trim(),
            currency: currencyInput.value,
        }),
    })
        .then(function (res) { return res.json().then(function (data) { return { ok: res.ok, data: data }; }); })
        .then(function (result) {
            if (result.ok) {
                rateInput.value = Number(result.data.dev_hourly_rate).toFixed(2);
                currencyInput.value = result.data.currency;
                if (typeof showToast === 'function') showToast('Settings saved.', 'success');
                return;
            }
            var errors = (result.data && result.data.errors) || {};
            Object.keys(errors).forEach(function (field) { _diShowSettingsError(field, errors[field]); });
            if (!Object.keys(errors).length && typeof showToast === 'function') {
                showToast((result.data && result.data.error) || 'Could not save settings — try again.', 'error');
            }
        })
        .catch(function () {
            if (typeof showToast === 'function') showToast('Could not save settings — try again.', 'error');
        })
        .then(function () {
            if (saveBtn) saveBtn.disabled = false;
        });
}
