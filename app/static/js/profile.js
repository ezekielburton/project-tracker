// profile.js — Vitamin-E
// Drives the avatar/banner picker + Cropper.js crop-and-zoom popup, and the
// upload of the resulting cropped+compressed image.
// Depends on: showToast(), btnLoading(), btnDone() from main.js. Loaded after
// Cropper.js and after the page HTML (script tag sits at the bottom of profile.html).

(function () {
    var editAvatarBtn = document.getElementById('edit-avatar-btn');
    var editBannerBtn = document.getElementById('edit-banner-btn');
    var avatarFileInput = document.getElementById('avatar-file-input');
    var bannerFileInput = document.getElementById('banner-file-input');

    var cropModal = document.getElementById('crop-modal');
    var cropModalTitle = document.getElementById('crop-modal-title');
    var cropImage = document.getElementById('crop-image');
    var cropContainer = cropImage.parentElement;
    var cropZoomSlider = document.getElementById('crop-zoom-slider');
    var cropCancelBtn = document.getElementById('crop-cancel-btn');
    var cropSaveBtn = document.getElementById('crop-save-btn');

    var cropper = null;
    var currentMode = null; // 'avatar' or 'banner'

    // Per-mode settings: aspect ratio for the crop box, and the fixed pixel
    // size we export to (also crops AND resizes/compresses spatially in one step).
    var MODE_CONFIG = {
        avatar: { aspectRatio: 1, outputWidth: 512, outputHeight: 512, title: 'Adjust Photo' },
        banner: { aspectRatio: 4, outputWidth: 1584, outputHeight: 396, title: 'Adjust Banner' }
    };

    function openCropModal(dataUrl, mode) {
        currentMode = mode;
        var config = MODE_CONFIG[mode];

        var cropSizeHint = document.getElementById('crop-size-hint');
        cropSizeHint.textContent = 'Saved at ' + config.outputWidth + '×' + config.outputHeight + 'px';
        cropSizeHint.classList.remove('crop-size-hint--warning');

        cropModalTitle.textContent = config.title;
        cropImage.src = dataUrl;
        cropModal.classList.remove('hidden');

        // Circular crop preview only makes sense for the avatar — toggled via
        // a CSS class rather than inline styles, see profile.css.
        cropContainer.classList.toggle('crop-container--circle', mode === 'avatar');

        // Pause the 1s dashboard polling while this modal is open — same rule
        // CLAUDE.md documents for any modal requiring input before a server action.
        if (window.helixPolling) window.helixPolling.pause();

        // Cropper.js needs the <img> to have already loaded its new src before
        // it can read natural dimensions — destroy any previous instance first.
        if (cropper) {
            cropper.destroy();
            cropper = null;
        }

        cropImage.onload = function () {
            // Warn if the source photo is smaller than our target output — cropping
            // can't add detail that isn't there, so this would upscale and look soft.
            // This has to run here, inside onload, since naturalWidth/Height are
            // only known once the image has actually finished loading.
            if (cropImage.naturalWidth < config.outputWidth || cropImage.naturalHeight < config.outputHeight) {
                cropSizeHint.textContent = 'This photo is smaller than ' + config.outputWidth + '×' + config.outputHeight +
                    'px \u2014 it may look blurry once saved.';
                cropSizeHint.classList.add('crop-size-hint--warning');
            }

            cropper = new Cropper(cropImage, {
                aspectRatio: config.aspectRatio,
                viewMode: 1,
                dragMode: 'move',
                background: false,
                autoCropArea: 1,
                guides: false,
                center: false,
                highlight: false,
                cropBoxResizable: false,
                cropBoxMovable: false,
                toggleDragModeOnDblclick: false
            });
            cropZoomSlider.value = 0;
        };
    }

    function closeCropModal() {
        cropModal.classList.add('hidden');
        if (cropper) {
            cropper.destroy();
            cropper = null;
        }
        avatarFileInput.value = '';
        banannerFileInputReset();
        if (window.helixPolling) window.helixPolling.resume();
    }

    // Separate helper only so a typo in one spot doesn't silently break both —
    // resets whichever file input was actually used, so re-selecting the same
    // file later still fires a 'change' event.
    function banannerFileInputReset() {
        bannerFileInput.value = '';
    }

    // ── Trigger file pickers from the pencil icons ──────────────────────────
    editAvatarBtn.addEventListener('click', function () {
        avatarFileInput.click();
    });
    editBannerBtn.addEventListener('click', function () {
        bannerFileInput.click();
    });

    function handleFileSelected(input, mode) {
        input.addEventListener('change', function () {
            var file = this.files[0];
            if (!file) return;

            var reader = new FileReader();
            reader.onload = function (e) {
                openCropModal(e.target.result, mode);
            };
            reader.readAsDataURL(file);
        });
    }
    handleFileSelected(avatarFileInput, 'avatar');
    handleFileSelected(bannerFileInput, 'banner');

    // ── Zoom slider ──────────────────────────────────────────────────────────
    // Cropper's zoomTo() takes an absolute ratio (1 = image at natural size
    // relative to the crop box), not a percentage — map the 0-100 slider onto
    // a 0.1-2.0 range, which covers "zoomed out" to "zoomed in" for most photos.
    cropZoomSlider.addEventListener('input', function () {
        if (!cropper) return;
        var ratio = 0.1 + (parseInt(this.value, 10) / 100) * 1.9;
        cropper.zoomTo(ratio);
    });

    // ── Cancel / close on backdrop click ────────────────────────────────────
    cropCancelBtn.addEventListener('click', closeCropModal);
    cropModal.addEventListener('click', function (e) {
        if (e.target === cropModal) closeCropModal();
    });

    // ── Save: export the cropped canvas, compress to JPEG, upload ──────────
    cropSaveBtn.addEventListener('click', function () {
        if (!cropper) return;
        var config = MODE_CONFIG[currentMode];

        var canvas = cropper.getCroppedCanvas({
            width: config.outputWidth,
            height: config.outputHeight
        });

        btnLoading(cropSaveBtn);

        // toBlob's quality argument (0.85) is where the actual compression
        // happens — this is a JPEG regardless of what format was uploaded.
        canvas.toBlob(function (blob) {
            var formData = new FormData();
            formData.append('file', blob, currentMode + '.jpg');

            fetch('/profile/' + currentMode, { method: 'POST', body: formData })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    btnDone(cropSaveBtn);
                    if (!data.success) {
                        showToast(data.error || 'Upload failed.', 'error');
                        return;
                    }
                    closeCropModal();
                    // Simplest correct way to reflect the new image everywhere
                    // it appears (this page, and eventually project tables) —
                    // a full reload rather than patching the DOM in place.
                    // Uploads are infrequent enough that this tradeoff is fine.
                    window.location.reload();
                })
                .catch(function () {
                    btnDone(cropSaveBtn);
                    showToast('Upload failed.', 'error');
                });
        }, 'image/jpeg', 0.85);
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