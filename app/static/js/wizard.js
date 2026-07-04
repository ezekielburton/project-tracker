(function () {
    var overlay = document.getElementById('wizard-overlay');
    if (!overlay) return; // Wizard_completed is already true, nothing to do on this page.

    if (window.helixPolling) window.helixPolling.pause();

    var showNameStep = overlay.dataset.showNameStep === 'true';
    var steps = Array.prototype.slice.call(overlay.querySelectorAll('.wizard-step'));
    var dots = Array.prototype.slice.call(overlay.querySelectorAll('.wizard-dot'));
    var backBtn = document.getElementById('wizard-back-btn');
    var nextBtn = document.getElementById('wizard-next-btn');
    var finishBtn = document.getElementById('wizard-finish-btn');
    var firstIndex = showNameStep ? 0 : 1;
    var currentIndex = firstIndex;

    function render() {
        steps.forEach(function (step, i) {
            step.classList.toggle('hidden', i !== currentIndex);
        });
        dots.forEach(function(dot, i) {
            dot.classList.toggle('active', i === currentIndex);
        });
        backBtn.classList.toggle('hidden', currentIndex === firstIndex);
        var isLast = currentIndex === steps.length -1;
        nextBtn.classList.toggle('hidden', isLast);
        finishBtn.classList.toggle('hidden', !isLast);

    }

    backBtn.addEventListener('click', function() {
        if (currentIndex > firstIndex) {
            currentIndex--;
            render();
        }
    });

    nextBtn.addEventListener('click', function () {
        if (steps[currentIndex].dataset.wizardStep === '1') {
            var pw = document.getElementById('wizard-password').value;
            var pwConfirm = document.getElementById('wizard-password-confirm').value;
            var errorEi = document.getElementById('wizard-password-error');
            if (pw || pwConfirm) {
                if(pw !== pwConfirm) {
                errorEi.textContent = 'Passwords do not match.';
                errorEi.classList.remove('hidden');
                return;
                }
                if (pw.length < 8) {
                errorEi.textContent = 'Password must be at least 8 characters.';
                errorEi.classList.remove('hidden');
                return;
                
                }
            }
            errorEi.classList.add('hidden');
        }
        currentIndex++;
        render();     
      
    })

    //Prefill sound controls from the same server-side prefs the account page uses.
    var volumeSlider = document.getElementById('wizard-sound-volume');
    var volumeLabel = document.getElementById('wizard-sound-volume-label');
    var initialVolume = (HELIX_SOUND_PREFS.volume != null) ? Math.round(HELIX_SOUND_PREFS.volume * 100) : 100;
    volumeSlider.value = initialVolume;
    volumeLabel.textContent = initialVolume + '%';
    document.getElementById('wizard-sound-toggle').checked = HELIX_SOUND_PREFS.enabled !== false;
    volumeSlider.addEventListener('input', function () {
        volumeLabel.textContent = this.value + '%';
    });

    finishBtn.addEventListener('click', function () {
        var payload = {
            name: showNameStep ? document.getElementById('wizard-name').value : '',
            password: showNameStep ? document.getElementById('wizard-password').value : '',
            password_confirm: showNameStep ? document.getElementById('wizard-password-confirm').value : '',
            birthday: document.getElementById('wizard-birthday').value,
            favorite_food: document.getElementById('wizard-food').value,
            email_enabled: document.getElementById('wizard-email-toggle').checked,
            sound_enabled: document.getElementById('wizard-sound-toggle').checked,
            sound_volume: parseInt(volumeSlider.value, 10) / 100
        };

        finishBtn.disabled = true;

        fetch('/wizard/complete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
            .then(function (res) { return res.json(); })
            .then(function (result) {
                if (result.success) {
                    overlay.remove();
                    if (window.helixPolling) window.helixPolling.resume();
                } else {
                    finishBtn.disabled = false;
                    showToast(result.error || 'Something went wrong. Please try again.', 'error');
                }
            })
            .catch(function () {
                finishBtn.disabled = false;
                showToast('Something went wrong. Please try again.', 'error');
            });
    });

    render();
})();