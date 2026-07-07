// profile.js — Vitamin-E
// Wires the profile page's avatar/banner pickers into the shared
// HelixAvatarCropper module (avatar-cropper.js) — that module owns the
// crop modal, Cropper.js wiring, and upload; this file only tells it which
// inputs to watch and what to do once each upload succeeds.
// Depends on: HelixAvatarCropper (avatar-cropper.js, loaded before this
// file), showToast()/btnLoading()/btnDone() from main.js.

(function () {
    var editAvatarBtn = document.getElementById('edit-avatar-btn');
    var editBannerBtn = document.getElementById('edit-banner-btn');
    var avatarFileInput = document.getElementById('avatar-file-input');
    var bannerFileInput = document.getElementById('banner-file-input');

    editAvatarBtn.addEventListener('click', function () {
        avatarFileInput.click();
    });
    editBannerBtn.addEventListener('click', function () {
        bannerFileInput.click();
    });

    // Same "reload the whole page" behavior as before extraction — simplest
    // correct way to reflect the new image everywhere it appears (this page,
    // and eventually project tables). Uploads are infrequent enough that
    // this tradeoff is fine.
    HelixAvatarCropper.wireFileInput(avatarFileInput, 'avatar', function () {
        window.location.reload();
    });
    HelixAvatarCropper.wireFileInput(bannerFileInput, 'banner', function () {
        window.location.reload();
    });

    // ── Edit Details modal (Phase 4) ────────────────────────────────────────
    // One popup edits name, favorite_food, and birthday together. Role and
    // Fun Title are shown in this same popup as disabled inputs (see the
    // template) purely for context — this JS never reads their values, and
    // the backend route never accepts them either, so there's no path here
    // that could change a user's permissions.
    var editDetailsBtn = document.getElementById('edit-details-btn');
    var editDetailsModal = document.getElementById('edit-details-modal');
    var editDetailsCancelBtn = document.getElementById('edit-details-cancel-btn');
    var editDetailsSaveBtn = document.getElementById('edit-details-save-btn');

    // Open the popup — same "pause polling while a modal needs input" rule
    // used for the crop modal above, so a background poll can't reload the
    // page out from under someone mid-edit.
    editDetailsBtn.addEventListener('click', function () {
        editDetailsModal.classList.remove('hidden');
        if (window.helixPolling) window.helixPolling.pause();
    });

    // Shared close logic for both the Cancel button and clicking the dark
    // backdrop outside the modal box.
    function closeEditDetailsModal() {
        editDetailsModal.classList.add('hidden');
        if (window.helixPolling) window.helixPolling.resume();
    }

    editDetailsCancelBtn.addEventListener('click', closeEditDetailsModal);
    editDetailsModal.addEventListener('click', function (e) {
        // Only close if the click landed on the overlay itself, not on the
        // modal box or anything inside it (e.g. clicking a form field).
        if (e.target === editDetailsModal) closeEditDetailsModal();
    });

    editDetailsSaveBtn.addEventListener('click', function () {
        var name = document.getElementById('edit-details-name').value.trim();
        var food = document.getElementById('edit-details-food').value.trim();
        // <input type="date"> gives us 'yyyy-mm-dd' directly, or '' if cleared —
        // exactly the format the backend's datetime.strptime() call expects.
        var birthday = document.getElementById('edit-details-birthday').value;

        // Mirror the backend's "name required" check here too, so the user
        // gets instant feedback without waiting on a round-trip to the server
        // just to be told the same thing.
        if (!name) {
            showToast('Name cannot be empty.', 'error');
            return;
        }

        btnLoading(editDetailsSaveBtn);
        fetch('/profile/details', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            // Send birthday as null (not '') when empty, matching how the
            // backend distinguishes "clear this field" from "not provided".
            body: JSON.stringify({ name: name, favorite_food: food, birthday: birthday || null })
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                btnDone(editDetailsSaveBtn);
                if (!data.success) {
                    showToast(data.error || 'Could not save details.', 'error');
                    return;
                }
                // A name change needs to show up in the sidebar dropdown too,
                // not just this page — reload rather than patching multiple
                // spots in the DOM, same tradeoff as the avatar/banner saves.
                window.location.reload();
            })
            .catch(function () {
                btnDone(editDetailsSaveBtn);
                showToast('Could not save details.', 'error');
            });
    });

    // ── Inline Bio editing (Phase 5) ────────────────────────────────────────
    // Unlike name/avatar/banner, bio only ever appears in this one spot on
    // the page (not the sidebar dropdown too), so on save we patch the DOM
    // directly instead of doing a full reload — a nicer, faster save for
    // something people might edit and re-edit a few times in a row.
    var editBioBtn = document.getElementById('edit-bio-btn');
    var bioText = document.getElementById('profile-bio-text');
    var bioEditWrap = document.getElementById('profile-bio-edit-wrap');
    var bioTextarea = document.getElementById('profile-bio-textarea');
    var bioCancelBtn = document.getElementById('bio-cancel-btn');
    var bioSaveBtn = document.getElementById('bio-save-btn');

    editBioBtn.addEventListener('click', function () {
        // Swap the static <p> for the textarea and focus it immediately.
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
        // Reset the textarea back to the last SAVED value (data-raw, set in
        // the template and kept in sync below on every successful save) —
        // discards any unsaved typing before closing.
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
                // Patch the visible text and its data-raw cache together so
                // a later Cancel (without a page reload in between) restores
                // the correct value rather than a stale one.
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