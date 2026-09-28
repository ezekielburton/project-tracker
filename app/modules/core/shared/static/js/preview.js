// preview.js — in-app file preview modal (window.openFilePreview).
// Renders a /preview route's file inline as PDF, image, video or audio.
// A JSON response means no preview (unsupported type, failed pptx
// conversion) and shows a message with a download link.

(function () {
    var modal = document.getElementById('file-preview-modal');
    var titleEl = document.getElementById('file-preview-title');
    var bodyEl = document.getElementById('file-preview-body');
    var closeBtn = document.getElementById('file-preview-close');

    // Revoked on close; blob URLs are never garbage collected on their own.
    var currentBlobUrl = null;

    function showLoading() {
        bodyEl.innerHTML = '<div class="file-preview-loading">Loading preview…</div>';
    }

    // Built with DOM nodes: the message comes from the server's JSON and the
    // URL from the caller, so neither may be parsed as HTML.
    function showFallback(message, downloadUrl) {
        var wrap = document.createElement('div');
        wrap.className = 'file-preview-fallback';
        var p = document.createElement('p');
        p.textContent = message;
        var link = document.createElement('a');
        link.href = downloadUrl;
        link.className = 'btn btn--primary';
        link.textContent = 'Download instead';
        wrap.appendChild(p);
        wrap.appendChild(link);
        bodyEl.innerHTML = '';
        bodyEl.appendChild(wrap);
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
    // fileType:    the file's extension; picks video/audio vs pdf/image
    window.openFilePreview = function (previewUrl, downloadUrl, filename, fileType) {
        titleEl.textContent = filename;
        showLoading();
        modal.classList.remove('hidden');

        // Pause live polling so it can't refresh the page mid-preview.
        if (window.helixPolling) window.helixPolling.pause();

        var MEDIA_KIND_BY_EXT = {
            mp4: 'video', webm: 'video',
            mp3: 'audio', wav: 'audio', m4a: 'audio', aac: 'audio', ogg: 'audio'
        };

        function showVideo(url) {
            bodyEl.innerHTML = '<video src="' + url + '" controls></video>';
        }

        function showAudio(url) {
            bodyEl.innerHTML = '<audio src="' + url + '" controls></audio>';
        }

        // Video/audio point straight at the route so the browser can use
        // range requests; a fetch() would download the whole file first.
        var mediaKind = MEDIA_KIND_BY_EXT[(fileType || '').toLowerCase()];
        if (mediaKind) {
            if (mediaKind === 'video') showVideo(previewUrl); else showAudio(previewUrl);
            bodyEl.querySelector('video, audio').addEventListener('error', function () {
                fetch(previewUrl)
                    .then(function (res) { return res.json(); })
                    .then(function (data) { showFallback(data.error || 'Preview unavailable.', downloadUrl); })
                    .catch(function () { showFallback('Something went wrong loading the preview.', downloadUrl); });
            });
            return;
        }

        fetch(previewUrl)
            .then(function (res) {
                var contentType = res.headers.get('Content-Type') || '';

                // JSON means "no preview, here's why"; anything else is the file.
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

    // A click on the backdrop (not the box) closes it.
    modal.addEventListener('click', function (e) {
        if (e.target === modal) closePreview();
    });
})();