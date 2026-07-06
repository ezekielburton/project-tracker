// preview.js — in-app file preview modal.
// Opens a modal, fetches a file from one of the /preview routes (reference
// files or submission decks), and renders it inline as a PDF or image.
// If the route responds with JSON instead of a file (unsupported file type,
// or a pptx that failed to convert), shows a fallback message with a
// download link instead of a broken viewer.

(function () {
    var modal = document.getElementById('file-preview-modal');
    var titleEl = document.getElementById('file-preview-title');
    var bodyEl = document.getElementById('file-preview-body');
    var closeBtn = document.getElementById('file-preview-close');

    // Tracks the current blob URL so we can free it on close — blob URLs
    // are never automatically garbage collected, so without this, opening
    // many previews in one session would slowly leak memory.
    var currentBlobUrl = null;

    function showLoading() {
        bodyEl.innerHTML = '<div class="file-preview-loading">Loading preview…</div>';
    }

    function showFallback(message, downloadUrl) {
        bodyEl.innerHTML =
            '<div class="file-preview-fallback">' +
            '<p>' + message + '</p>' +
            '<a href="' + downloadUrl + '" class="btn btn--primary">Download instead</a>' +
            '</div>';
    }

    function showPdf(blobUrl) {
        bodyEl.innerHTML = '<iframe src="' + blobUrl + '"></iframe>';
    }

    function showImage(blobUrl) {
        bodyEl.innerHTML = '<img src="' + blobUrl + '">';
    }

    // previewUrl:  the /preview route to fetch from
    // downloadUrl: the matching /download route — used as the fallback link
    // filename:    shown in the modal header
    window.openFilePreview = function (previewUrl, downloadUrl, filename) {
        titleEl.textContent = filename;
        showLoading();
        modal.classList.remove('hidden');

        // Same convention every other modal in the app follows — without
        // this, live polling could reload the page out from under someone
        // mid-preview.
        if (window.helixPolling) window.helixPolling.pause();

        fetch(previewUrl)
            .then(function (res) {
                var contentType = res.headers.get('Content-Type') || '';

                // Our preview routes return real JSON (not a file) when
                // something's gone wrong — wrong file type, or a pptx that
                // failed to convert. Checking content-type up front lets us
                // tell "here's your file" apart from "here's why there
                // isn't one," without guessing from the HTTP status alone.
                if (contentType.indexOf('application/json') !== -1) {
                    return res.json().then(function (data) {
                        showFallback(data.error || 'Preview unavailable.', downloadUrl);
                    });
                }

                return res.blob().then(function (blob) {
                    currentBlobUrl = URL.createObjectURL(blob);
                    if (contentType.indexOf('image/') === 0) {
                        showImage(currentBlobUrl);
                    } else {
                        showPdf(currentBlobUrl);
                    }
                });
            })
            .catch(function () {
                showFallback('Something went wrong loading the preview.', downloadUrl);
            });
    };

    function closePreview() {
        modal.classList.add('hidden');
        bodyEl.innerHTML = '';

        if (currentBlobUrl) {
            URL.revokeObjectURL(currentBlobUrl);
            currentBlobUrl = null;
        }

        if (window.helixPolling) window.helixPolling.resume();
    }

    closeBtn.addEventListener('click', closePreview);

    // Clicking the dark backdrop (not the box itself) also closes it —
    // same pattern the quick-add modal already uses elsewhere in the app.
    modal.addEventListener('click', function (e) {
        if (e.target === modal) closePreview();
    });

    // Rather than hand-edit the ~30 near-identical reference-file blocks
    // scattered across detail.html, find every existing Download link on
    // the page and inject a matching Preview button next to it. Runs once
    // on load, and again after SPA navigation (same event polling.js
    // already listens for), so it stays correct without upkeep.
    function injectPreviewButtons() {
        document.querySelectorAll('.reference-file-actions a.btn-secondary').forEach(function (link) {
            var href = link.getAttribute('href');
            if (!href || link.dataset.previewAdded) return;

            // Only the two routes we've actually built a /preview
            // counterpart for. "Extra" submission files use a different
            // route we haven't wired up yet — leave those Download-only.
            var isReferenceFile = href.indexOf('/projects/files/') !== -1;
            var isSubmissionDeck = href.indexOf('/projects/submission/') !== -1 &&
                href.indexOf('/projects/submission/file/') === -1;
            if (!isReferenceFile && !isSubmissionDeck) return;

            var previewUrl = href.replace('/download', '/preview');
            var item = link.closest('.reference-file-item');
            var filenameEl = item ? item.querySelector('.reference-file-name') : null;
            var filename = filenameEl ? filenameEl.textContent.trim() : 'file';

            var previewBtn = document.createElement('button');
            previewBtn.type = 'button';
            previewBtn.className = 'btn-secondary btn-sm';
            previewBtn.textContent = 'Preview';
            previewBtn.addEventListener('click', function () {
                openFilePreview(previewUrl, href, filename);
            });

            link.parentNode.insertBefore(previewBtn, link);
            link.dataset.previewAdded = 'true';  // marks it done, in case this ever runs twice
        });
    }

    document.addEventListener('DOMContentLoaded', injectPreviewButtons);
    document.addEventListener('helix:navigated', injectPreviewButtons);
})();