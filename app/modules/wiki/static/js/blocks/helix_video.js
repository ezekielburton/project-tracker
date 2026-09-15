/**
 * Editor.js block for wiki video: a YouTube/Vimeo link, or a self-hosted upload.
 * Uploads go to the existing /wiki/upload-video endpoint.
 */
(function () {
    'use strict';

    var ICON = '<svg width="17" height="15" viewBox="0 0 17 15" fill="none">' +
        '<rect x="1" y="2" width="15" height="11" rx="2" stroke="currentColor" stroke-width="2"/>' +
        '<path d="M7 6l4 2.5L7 11V6z" fill="currentColor"/></svg>';

    class HelixVideo {
        static get toolbox() {
            return { title: 'Video', icon: ICON };
        }

        static get sanitize() {
            return { source: false, url: false };
        }

        constructor(options) {
            var data = options.data || {};
            var config = options.config || {};
            this.uploadUrl = config.uploadUrl || '/wiki/upload-video';
            this.readOnly = !!options.readOnly;
            this.data = {
                source: data.source === 'upload' ? 'upload' : 'embed',
                url: data.url || ''
            };
        }

        render() {
            this.wrapper = document.createElement('div');
            this.wrapper.className = 'wiki-editor-video';

            this.wrapper.appendChild(this.renderModes());
            this.wrapper.appendChild(this.renderEmbedField());
            this.wrapper.appendChild(this.renderUploadField());

            this.status = document.createElement('p');
            this.status.className = 'wiki-editor-video__status';
            this.wrapper.appendChild(this.status);

            this.applyMode();
            return this.wrapper;
        }

        renderModes() {
            var self = this;
            var row = document.createElement('div');
            row.className = 'wiki-editor-video__modes';

            this.modeButtons = {};
            ['embed', 'upload'].forEach(function (mode) {
                var button = document.createElement('button');
                button.type = 'button';
                button.className = 'wiki-editor-video__mode';
                button.textContent = mode === 'embed' ? 'Link' : 'Upload';
                button.addEventListener('click', function () { self.setMode(mode); });
                self.modeButtons[mode] = button;
                row.appendChild(button);
            });

            return row;
        }

        renderEmbedField() {
            var self = this;
            this.embedInput = document.createElement('input');
            this.embedInput.type = 'url';
            this.embedInput.className = 'wiki-editor-video__input';
            this.embedInput.placeholder = 'YouTube or Vimeo link';
            this.embedInput.disabled = this.readOnly;
            this.embedInput.value = this.data.source === 'embed' ? this.data.url : '';
            this.embedInput.addEventListener('input', function () {
                self.data.url = self.embedInput.value.trim();
                self.showStatus('');
            });
            return this.embedInput;
        }

        renderUploadField() {
            var self = this;
            var holder = document.createElement('div');
            holder.className = 'wiki-editor-video__upload';

            this.fileInput = document.createElement('input');
            this.fileInput.type = 'file';
            this.fileInput.accept = 'video/mp4,video/webm';
            this.fileInput.className = 'wiki-editor-video__file';
            this.fileInput.disabled = this.readOnly;
            this.fileInput.addEventListener('change', function () {
                if (self.fileInput.files.length) { self.upload(self.fileInput.files[0]); }
            });

            holder.appendChild(this.fileInput);
            return holder;
        }

        setMode(mode) {
            this.data.source = mode;
            this.data.url = '';
            this.embedInput.value = '';
            this.fileInput.value = '';
            this.showStatus('');
            this.applyMode();
        }

        applyMode() {
            var isUpload = this.data.source === 'upload';
            this.embedInput.hidden = isUpload;
            this.fileInput.parentNode.hidden = !isUpload;
            this.modeButtons.embed.classList.toggle('is-active', !isUpload);
            this.modeButtons.upload.classList.toggle('is-active', isUpload);
            if (isUpload && this.data.url) { this.showStatus('Uploaded: ' + this.data.url.split('/').pop()); }
        }

        upload(file) {
            var self = this;
            var form = new FormData();
            form.append('file', file);
            this.showStatus('Uploading…');

            fetch(this.uploadUrl, { method: 'POST', body: form, credentials: 'same-origin' })
                .then(function (response) { return response.json(); })
                .then(function (result) {
                    if (!result.success) { throw new Error(result.error || 'Upload failed'); }
                    self.data.url = result.url;
                    self.showStatus('Uploaded: ' + result.filename);
                })
                .catch(function (error) {
                    self.data.url = '';
                    self.showStatus(error.message || 'Upload failed');
                });
        }

        showStatus(message) {
            this.status.textContent = message;
        }

        save() {
            return { source: this.data.source, url: this.data.url };
        }

        validate(data) {
            return !!data.url;
        }
    }

    window.HelixVideo = HelixVideo;
}());
