// Profile page edit controls: avatar/banner (via HelixAvatarCropper, which
// owns the crop modal and upload), the Edit Details modal, and inline bio.
// Depends on: avatar-cropper.js and the #avatar-file-input/#banner-file-input
// from base.html; showToast()/btnLoading()/btnDone() from main.js.
// Edit controls render only on your own profile, so each section below
// skips itself when its elements are absent.

(function () {
    var editAvatarBtn = document.getElementById('edit-avatar-btn');
    var editBannerBtn = document.getElementById('edit-banner-btn');
    var avatarFileInput = document.getElementById('avatar-file-input');
    var bannerFileInput = document.getElementById('banner-file-input');

    if (editAvatarBtn && avatarFileInput) {
        editAvatarBtn.addEventListener('click', function () {
            avatarFileInput.click();
        });
        // Reload so the new image shows everywhere it appears.
        HelixAvatarCropper.wireFileInput(avatarFileInput, 'avatar', function () {
            window.location.reload();
        });
    }
    if (editBannerBtn && bannerFileInput) {
        editBannerBtn.addEventListener('click', function () {
            bannerFileInput.click();
        });
        HelixAvatarCropper.wireFileInput(bannerFileInput, 'banner', function () {
            window.location.reload();
        });
    }

    // ── Edit Details modal ──────────────────────────────────────────────────
    // Role and Fun Title inputs are display-only; neither is sent.
    var editDetailsBtn = document.getElementById('edit-details-btn');
    var editDetailsModal = document.getElementById('edit-details-modal');
    var editDetailsCancelBtn = document.getElementById('edit-details-cancel-btn');
    var editDetailsSaveBtn = document.getElementById('edit-details-save-btn');

    if (editDetailsBtn && editDetailsModal) {
        // Pause polling so a background reload can't wipe the form mid-edit.
        editDetailsBtn.addEventListener('click', function () {
            editDetailsModal.classList.remove('hidden');
            if (window.helixPolling) window.helixPolling.pause();
        });

        // Cancel button and backdrop click.
        var closeEditDetailsModal = function () {
            editDetailsModal.classList.add('hidden');
            if (window.helixPolling) window.helixPolling.resume();
        };

        editDetailsCancelBtn.addEventListener('click', closeEditDetailsModal);
        editDetailsModal.addEventListener('click', function (e) {
            if (e.target === editDetailsModal) closeEditDetailsModal();
        });

        editDetailsSaveBtn.addEventListener('click', function () {
            var name = document.getElementById('edit-details-name').value.trim();
            var food = document.getElementById('edit-details-food').value.trim();
            // 'yyyy-mm-dd', or '' when cleared.
            var birthday = document.getElementById('edit-details-birthday').value;

            if (!name) {
                showToast('Name cannot be empty.', 'error');
                return;
            }

            btnLoading(editDetailsSaveBtn);
            fetch('/profile/details', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                // null clears the birthday.
                body: JSON.stringify({ name: name, favorite_food: food, birthday: birthday || null })
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    btnDone(editDetailsSaveBtn);
                    if (!data.success) {
                        showToast(data.error || 'Could not save details.', 'error');
                        return;
                    }
                    // Reload so the name updates in the sidebar too.
                    window.location.reload();
                })
                .catch(function () {
                    btnDone(editDetailsSaveBtn);
                    showToast('Could not save details.', 'error');
                });
        });
    }

    // ── Inline Bio editing ──────────────────────────────────────────────────
    // Bio appears only here, so a save patches the DOM with no reload.
    var editBioBtn = document.getElementById('edit-bio-btn');
    var bioText = document.getElementById('profile-bio-text');
    var bioEditWrap = document.getElementById('profile-bio-edit-wrap');
    var bioTextarea = document.getElementById('profile-bio-textarea');
    var bioCancelBtn = document.getElementById('bio-cancel-btn');
    var bioSaveBtn = document.getElementById('bio-save-btn');

    if (!editBioBtn || !bioEditWrap) return;

    editBioBtn.addEventListener('click', function () {
        bioText.classList.add('hidden');
        bioEditWrap.classList.remove('hidden');
        bioTextarea.focus();
        if (window.helixPolling) window.helixPolling.pause();
    });

    function closeBioEdit() {
        bioEditWrap.classList.add('hidden');
        bioText.classList.remove('hidden');
        if (window.helixPolling) window.helixPolling.resume();
    }

    bioCancelBtn.addEventListener('click', function () {
        // Restore the last saved value from data-raw.
        bioTextarea.value = bioText.dataset.raw || '';
        closeBioEdit();
    });

    bioSaveBtn.addEventListener('click', function () {
        var newBio = bioTextarea.value.trim();

        btnLoading(bioSaveBtn);
        fetch('/profile/bio', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ bio: newBio })
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                btnDone(bioSaveBtn);
                if (!data.success) {
                    showToast(data.error || 'Could not save bio.', 'error');
                    return;
                }
                // Keep data-raw in sync so a later Cancel restores this value.
                bioText.textContent = newBio || 'No bio yet.';
                bioText.dataset.raw = newBio;
                closeBioEdit();
            })
            .catch(function () {
                btnDone(bioSaveBtn);
                showToast('Could not save bio.', 'error');
            });
    });
})();