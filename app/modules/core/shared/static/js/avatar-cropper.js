// avatar-cropper.js — shared "pick a photo, crop it, upload it" flow on
// Cropper.js (profile page, wizard, admin panel).
//
// Included inside #main-content in base.html, right after
// partials/avatar_crop_modal.html and before {% block content %}, so it
// re-runs on every SPA swap. Needs that modal markup in the DOM, which the
// partial only renders for logged-in users; without it HelixAvatarCropper
// is null. Uses showToast()/btnLoading()/
// btnDone() from main.js, inside handlers only.
//
// Public API: HelixAvatarCropper.wireFileInput(inputEl, mode, onSuccess, options)
//   inputEl:   the <input type="file"> to watch
//   mode:      'avatar' or 'banner' — controls aspect ratio, output size,
//              and modal title
//   onSuccess: called with the parsed JSON response after a successful upload
//   options:   optional { uploadUrl }: a string, or a function resolved on
//              each open (admin panel, per-user target). Default /profile/<mode>.

window.HelixAvatarCropper = (function () {
    var cropModal = document.getElementById('crop-modal');
    var cropModalTitle = document.getElementById('crop-modal-title');
    var cropImage = document.getElementById('crop-image');
    // Logged-out pages (login, register) render no modal: nothing to wire.
    if (!cropModal || !cropImage) return null;
    var cropContainer = cropImage.parentElement;
    var cropZoomSlider = document.getElementById('crop-zoom-slider');
    var cropSizeHint = document.getElementById('crop-size-hint');
    var cropCancelBtn = document.getElementById('crop-cancel-btn');
    var cropSaveBtn = document.getElementById('crop-save-btn');

    var cropper = null;
    var currentMode = null;
    var currentInput = null;     // the file input that opened the modal; cleared on close
    var currentOnSuccess = null;
    var currentUploadUrl = null;

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
        currentUploadUrl = null;
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

            fetch(currentUploadUrl, { method: 'POST', body: formData })
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

    function wireFileInput(input, mode, onSuccess, options) {
        options = options || {};
        input.addEventListener('change', function () {
            var file = this.files[0];
            if (!file) return;

            currentInput = input;
            currentOnSuccess = onSuccess;
            var uu = options.uploadUrl;
            currentUploadUrl = (typeof uu === 'function') ? uu() : (uu || ('/profile/' + mode));

            var reader = new FileReader();
            reader.onload = function (e) { openCropModal(e.target.result, mode); };
            reader.readAsDataURL(file);
        });
    }

    return { wireFileInput: wireFileInput };
})();