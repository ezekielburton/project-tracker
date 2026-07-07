// avatar-cropper.js — Vitamin-E
// Shared Cropper.js wiring for any "pick a photo, crop it, upload it" flow.
// Extracted from profile.js so the wizard's photo step can reuse the exact
// same crop-and-upload mechanics instead of duplicating them.
//
// Loaded before {% block content %} in base.html, so it runs before any
// page-specific script (like profile.js) that depends on it. Needs the
// crop-modal markup from partials/avatar_crop_modal.html already in the DOM
// (also included right before this script tag) and showToast()/btnLoading()/
// btnDone() from main.js (called later, inside event handlers, by which
// point main.js has always finished loading).
//
// Public API: HelixAvatarCropper.wireFileInput(inputEl, mode, onSuccess)
//   inputEl:   the <input type="file"> to watch
//   mode:      'avatar' or 'banner' — controls aspect ratio, output size,
//              modal title, and which endpoint (/profile/<mode>) it posts to
//   onSuccess: called with the parsed JSON response after a successful
//              upload — the caller decides what happens next (profile.js
//              reloads the page; the wizard just updates its own preview)

window.HelixAvatarCropper = (function () {
    var cropModal = document.getElementById('crop-modal');
    var cropModalTitle = document.getElementById('crop-modal-title');
    var cropImage = document.getElementById('crop-image');
    var cropContainer = cropImage.parentElement;
    var cropZoomSlider = document.getElementById('crop-zoom-slider');
    var cropSizeHint = document.getElementById('crop-size-hint');
    var cropCancelBtn = document.getElementById('crop-cancel-btn');
    var cropSaveBtn = document.getElementById('crop-save-btn');

    var cropper = null;
    var currentMode = null;
    var currentInput = null;     // whichever file input triggered this open — reset on close
    var currentOnSuccess = null; // this open's caller-supplied callback

    var MODE_CONFIG = {
        avatar: { aspectRatio: 1, outputWidth: 512, outputHeight: 512, title: 'Adjust Photo' },
        banner: { aspectRatio: 4, outputWidth: 1584, outputHeight: 396, title: 'Adjust Banner' }
    };

    function openCropModal(dataUrl, mode) {
        currentMode = mode;
        var config = MODE_CONFIG[mode];

        cropSizeHint.textContent = 'Saved at ' + config.outputWidth + '×' + config.outputHeight + 'px';
        cropSizeHint.classList.remove('crop-size-hint--warning');

        cropModalTitle.textContent = config.title;
        cropImage.src = dataUrl;
        cropModal.classList.remove('hidden');
        cropContainer.classList.toggle('crop-container--circle', mode === 'avatar');

        if (window.helixPolling) window.helixPolling.pause();

        if (cropper) {
            cropper.destroy();
            cropper = null;
        }

        cropImage.onload = function () {
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
        if (currentInput) currentInput.value = '';
        if (window.helixPolling) window.helixPolling.resume();
    }

    cropZoomSlider.addEventListener('input', function () {
        if (!cropper) return;
        var ratio = 0.1 + (parseInt(this.value, 10) / 100) * 1.9;
        cropper.zoomTo(ratio);
    });

    cropCancelBtn.addEventListener('click', closeCropModal);
    cropModal.addEventListener('click', function (e) {
        if (e.target === cropModal) closeCropModal();
    });

    cropSaveBtn.addEventListener('click', function () {
        if (!cropper) return;
        var config = MODE_CONFIG[currentMode];
        var canvas = cropper.getCroppedCanvas({ width: config.outputWidth, height: config.outputHeight });

        btnLoading(cropSaveBtn);

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
                    if (currentOnSuccess) currentOnSuccess(data);
                })
                .catch(function () {
                    btnDone(cropSaveBtn);
                    showToast('Upload failed.', 'error');
                });
        }, 'image/jpeg', 0.85);
    });

    function wireFileInput(input, mode, onSuccess) {
        input.addEventListener('change', function () {
            var file = this.files[0];
            if (!file) return;

            currentInput = input;
            currentOnSuccess = onSuccess;

            var reader = new FileReader();
            reader.onload = function (e) { openCropModal(e.target.result, mode); };
            reader.readAsDataURL(file);
        });
    }

    return { wireFileInput: wireFileInput };
})();