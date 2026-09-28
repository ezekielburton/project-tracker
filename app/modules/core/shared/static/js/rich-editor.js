/**
 * rich-editor.js
 * Drag-and-drop / paste image embedding for every [data-rich-editor]
 * element. Images upload at once and embed inline; click one for resize
 * handles.
 *
 * Public API (set on window):
 *   getRichContent(id)   — returns innerHTML (empty string if visually blank)
 *   clearRichContent(id) — clears the editor and resets placeholder
 *   initRichEditors()    — wires any un-wired [data-rich-editor] elements
 */
(function () {
    'use strict';

    // ── Upload helper ──────────────────────────────────────────────────────────
    function uploadImage(file, projectId, callback) {
        var fd = new FormData();
        fd.append('file', file);
        fetch('/projects/' + projectId + '/inline-image', {
            method: 'POST',
            body: fd
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    callback(null, data.url);
                } else {
                    callback(data.error || 'Upload failed');
                }
            })
            .catch(function (err) { callback(String(err)); });
    }

    // ── Insert <img> at the caret inside a contenteditable ────────────────────
    function insertImageAtCursor(editor, url) {
        editor.focus();
        var img = document.createElement('img');
        img.src = url;
        img.style.maxWidth = '100%';
        img.style.height = 'auto';

        var sel = window.getSelection();
        if (sel && sel.rangeCount) {
            var range = sel.getRangeAt(0);
            if (editor.contains(range.commonAncestorContainer)) {
                range.deleteContents();
                range.insertNode(img);
                range.setStartAfter(img);
                range.collapse(true);
                sel.removeAllRanges();
                sel.addRange(range);
            } else {
                editor.appendChild(img);
            }
        } else {
            editor.appendChild(img);
        }
        updateEmpty(editor);
    }

    // ── Empty-state tracking (drives the placeholder pseudo-element) ──────────
    function updateEmpty(editor) {
        var visiblyEmpty = editor.textContent.trim() === '' && !editor.querySelector('img');
        if (visiblyEmpty) {
            editor.setAttribute('data-empty', '');
        } else {
            editor.removeAttribute('data-empty');
        }
    }

    // ── Resize overlay ─────────────────────────────────────────────────────────
    var _overlay = null;
    var _selectedImg = null;
    var _resizing = null; // { img, dir, startX, startY, startW, startH }

    var HANDLE_DIRS = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];

    function ensureOverlay() {
        if (_overlay) return;
        _overlay = document.createElement('div');
        _overlay.className = 'img-resize-overlay';
        _overlay.style.display = 'none';
        HANDLE_DIRS.forEach(function (dir) {
            var h = document.createElement('div');
            h.className = 'img-resize-handle img-resize-handle--' + dir;
            h.dataset.dir = dir;
            h.addEventListener('mousedown', onHandleDown);
            _overlay.appendChild(h);
        });
        document.body.appendChild(_overlay);
    }

    function placeOverlay(img) {
        var r = img.getBoundingClientRect();
        _overlay.style.display = 'block';
        _overlay.style.left   = r.left + 'px';
        _overlay.style.top    = r.top  + 'px';
        _overlay.style.width  = r.width  + 'px';
        _overlay.style.height = r.height + 'px';
    }

    function showOverlay(img) {
        ensureOverlay();
        if (_selectedImg && _selectedImg !== img) {
            _selectedImg.classList.remove('re-selected');
        }
        _selectedImg = img;
        img.classList.add('re-selected');
        placeOverlay(img);
    }

    function hideOverlay() {
        if (_overlay) _overlay.style.display = 'none';
        if (_selectedImg) {
            _selectedImg.classList.remove('re-selected');
            _selectedImg = null;
        }
    }

    function onHandleDown(e) {
        e.preventDefault();
        e.stopPropagation();
        if (!_selectedImg) return;
        var r = _selectedImg.getBoundingClientRect();
        _resizing = {
            img:    _selectedImg,
            dir:    e.currentTarget.dataset.dir,
            startX: e.clientX,
            startY: e.clientY,
            startW: r.width,
            startH: r.height
        };
        document.body.classList.add('img-resize-dragging');
    }

    document.addEventListener('mousemove', function (e) {
        if (!_resizing) return;
        var dx = e.clientX - _resizing.startX;
        var dy = e.clientY - _resizing.startY;
        var dir = _resizing.dir;
        var w = _resizing.startW;
        var h = _resizing.startH;

        if (dir.indexOf('e') !== -1) w = Math.max(20, _resizing.startW + dx);
        if (dir.indexOf('w') !== -1) w = Math.max(20, _resizing.startW - dx);
        if (dir.indexOf('s') !== -1) h = Math.max(20, _resizing.startH + dy);
        if (dir.indexOf('n') !== -1) h = Math.max(20, _resizing.startH - dy);

        _resizing.img.width  = Math.round(w);
        _resizing.img.height = Math.round(h);
        placeOverlay(_resizing.img);
    });

    document.addEventListener('mouseup', function () {
        if (!_resizing) return;
        _resizing = null;
        document.body.classList.remove('img-resize-dragging');
        if (_selectedImg) placeOverlay(_selectedImg);
    });

    // Capture phase, so scrolling any container moves the overlay too.
    window.addEventListener('scroll', function () {
        if (_selectedImg) placeOverlay(_selectedImg);
    }, true);

    document.addEventListener('click', function (e) {
        if (_overlay && _overlay.contains(e.target)) return;
        if (_selectedImg && e.target === _selectedImg) return;
        hideOverlay();
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') hideOverlay();
    });

    // ── Wire up a single editor ────────────────────────────────────────────────
    function initEditor(editor) {
        if (editor._richEditorInit) return;
        editor._richEditorInit = true;

        var projectId = editor.dataset.projectId;

        updateEmpty(editor);

        editor.addEventListener('input', function () { updateEmpty(editor); });

        editor.addEventListener('click', function (e) {
            if (e.target.tagName === 'IMG') {
                showOverlay(e.target);
            } else {
                hideOverlay();
            }
        });

        editor.addEventListener('dragover', function (e) {
            var types = e.dataTransfer && e.dataTransfer.types;
            var hasFiles = types && (
                Array.prototype.indexOf.call(types, 'Files') !== -1 ||
                Array.prototype.indexOf.call(types, 'files') !== -1
            );
            if (hasFiles) {
                e.preventDefault();
                editor.classList.add('drag-over');
            }
        });
        editor.addEventListener('dragleave', function (e) {
            // Only clear if we actually left the editor (not just moved between children)
            if (!editor.contains(e.relatedTarget)) {
                editor.classList.remove('drag-over');
            }
        });
        editor.addEventListener('drop', function (e) {
            editor.classList.remove('drag-over');
            var files = e.dataTransfer && e.dataTransfer.files;
            if (!files || !files.length) return;

            var hasImage = false;
            for (var i = 0; i < files.length; i++) {
                if (files[i].type.indexOf('image/') === 0) { hasImage = true; break; }
            }
            if (!hasImage) return; // non-image drop → let browser handle normally

            e.preventDefault();
            for (var j = 0; j < files.length; j++) {
                if (files[j].type.indexOf('image/') === 0) {
                    (function (file) {
                        uploadImage(file, projectId, function (err, url) {
                            if (err) {
                                if (window.showToast) showToast('Image upload failed.', 'error');
                                return;
                            }
                            insertImageAtCursor(editor, url);
                        });
                    })(files[j]);
                }
            }
        });

        // Paste — intercept image items
        editor.addEventListener('paste', function (e) {
            var items = e.clipboardData && e.clipboardData.items;
            if (!items) return;
            var hasImage = false;
            for (var i = 0; i < items.length; i++) {
                if (items[i].type.indexOf('image/') === 0) { hasImage = true; break; }
            }
            if (!hasImage) return; // text paste → browser handles normally

            e.preventDefault();
            for (var j = 0; j < items.length; j++) {
                if (items[j].type.indexOf('image/') === 0) {
                    (function (item) {
                        var file = item.getAsFile();
                        if (!file) return;
                        uploadImage(file, projectId, function (err, url) {
                            if (err) {
                                if (window.showToast) showToast('Image upload failed.', 'error');
                                return;
                            }
                            insertImageAtCursor(editor, url);
                        });
                    })(items[j]);
                }
            }
        });
    }

    // ── Public API ─────────────────────────────────────────────────────────────

    /**
     * Returns the HTML content of the editor. Returns an empty string if the
     * editor is visually empty (only whitespace / stray <br> tags, no images).
     */
    window.getRichContent = function (id) {
        var el = document.getElementById(id);
        if (!el) return '';
        if (el.textContent.trim() === '' && !el.querySelector('img')) return '';
        return el.innerHTML;
    };

    /** Clears the editor and restores the placeholder. */
    window.clearRichContent = function (id) {
        var el = document.getElementById(id);
        if (!el) return;
        el.innerHTML = '';
        updateEmpty(el);
    };

    // ── Init all editors ───────────────────────────────────────────────────────
    window.initRichEditors = function () {
        document.querySelectorAll('[data-rich-editor]').forEach(initEditor);
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', window.initRichEditors);
    } else {
        window.initRichEditors();
    }

    // SPA swaps never refire DOMContentLoaded.
    document.addEventListener('helix:navigated', window.initRichEditors);

})();
