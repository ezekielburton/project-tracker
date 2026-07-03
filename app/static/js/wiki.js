(function () {
    'use strict';

    // ── VIEWER ────────────────────────────────────────────────────────────────────

    // NOTE: contentPanel is NOT captured at module scope. The wiki page can be
    // reached via SPA navigation (sidebar.js swaps #main-content), in which case
    // the DOM is replaced but this IIFE doesn't re-run. Always look it up fresh.

    function toEmbedUrl(url) {
        if (!url) return null;
        var yt = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/)([^\&\?\/]+)/);
        if (yt) return 'https://www.youtube.com/embed/' + yt[1];
        var vi = url.match(/vimeo\.com\/(\d+)/);
        if (vi) return 'https://player.vimeo.com/video/' + vi[1];
        return null;
    }

    function loadArticle(articleId) {
        var contentPanel = document.getElementById('wiki-content-panel');
        if (!contentPanel) return;

        document.querySelectorAll('.wiki-nav-article').forEach(function (a) {
            a.classList.toggle('active', a.dataset.articleId === String(articleId));
        });

        contentPanel.innerHTML = '<p style="padding:2rem;color:var(--text-muted);">Loading…</p>';

        fetch('/wiki/article/' + articleId)
            .then(function (r) { return r.text(); })
            .then(function (html) {
                contentPanel.innerHTML = html;
                contentPanel.querySelectorAll('[data-video-url]').forEach(function (el) {
                    var embedUrl = toEmbedUrl(el.dataset.videoUrl);
                    if (embedUrl) {
                        el.innerHTML = '<iframe src="' + embedUrl + '" allowfullscreen></iframe>';
                    }
                });
            })
            .catch(function () {
                contentPanel.innerHTML = '<p style="padding:2rem;color:var(--rose);">Failed to load article.</p>';
            });

        history.replaceState(null, '', '#article-' + articleId);
    }

    // Nav clicks — delegated to document so they survive SPA navigation
    // (after sidebar.js swaps #main-content, the original <a> elements are gone
    // but the document listener stays alive)
    document.addEventListener('click', function (e) {
        var a = e.target.closest('.wiki-nav-article');
        if (!a) return;
        e.preventDefault();
        loadArticle(a.dataset.articleId);
    });

    // Auto-load: first article or hash-specified article.
    // Named function so it can be called on both initial load AND SPA navigation.
    function autoLoadWiki() {
        if (!document.getElementById('wiki-content-panel')) return; // not on wiki page
        var match = window.location.hash.match(/^#article-(\d+)$/);
        if (match) {
            loadArticle(match[1]);
        } else {
            var first = document.querySelector('.wiki-nav-article');
            if (first) loadArticle(first.dataset.articleId);
        }
    }

    autoLoadWiki();
    document.addEventListener('helix:navigated', autoLoadWiki);

    // ── Section publish + delete (dashboard) ─────────────────────────────────────

    document.querySelectorAll('.wiki-section-publish-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var sectionId = this.dataset.sectionId;
            var self = this;
            fetch('/wiki/editor/section/' + sectionId + '/toggle-publish', { method: 'POST' })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.success) {
                        self.textContent = data.is_published ? 'Unpublish' : 'Publish';
                        showToast(data.is_published ? 'Section published' : 'Section unpublished', 'success');
                    }
                })
                .catch(function () { showToast('Something went wrong', 'error'); });
        });
    });

    document.querySelectorAll('.wiki-section-delete-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var sectionId = this.dataset.sectionId;
            showConfirm(
                'Delete this section and all its articles? This cannot be undone.',
                function () {
                    fetch('/wiki/editor/section/' + sectionId + '/delete', { method: 'POST' })
                        .then(function (r) { return r.json(); })
                        .then(function (data) {
                            if (data.success) location.reload();
                        })
                        .catch(function () { showToast('Something went wrong', 'error'); });
                },
                'Delete Section'
            );
        });
    });

    // ── EDITOR ────────────────────────────────────────────────────────────────────
    var blockList = document.getElementById('wiki-block-list');
    
    var blockList = document.getElementById('wiki-block-list');
    if (!blockList) return; // not on editor page — stop here

    var blocks = [];
    var quillInstances = {};

    var BLOCK_LABELS = {
        'body': 'Paragraph',
        'richtext': 'Rich Text',
        'h3': 'Heading',
        'callout': 'Callout',
        'callout-pine': 'Callout (Green)',
        'list': 'List',
        'image': 'Image',
        'video': 'Video'
    };

    function uid() {
        return Math.random().toString(36).slice(2, 10);
    }

    function esc(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    // ── Load existing blocks (edit mode) ─────────────────────────────────────────

    (function () {
        var input = document.getElementById('wiki-sections-json');
        if (!input || !input.value || input.value === '[]') return;
        try {
            blocks = JSON.parse(input.value) || [];
            blocks.forEach(function (b) { b._id = b._id || uid(); });
        } catch (e) { blocks = []; }
        renderBlocks();
    }());

    // ── Slug auto-generate ────────────────────────────────────────────────────────

    var titleInput = document.getElementById('wiki-title');
    var slugInput = document.getElementById('wiki-slug');
    var slugEdited = !!(slugInput && slugInput.value.length > 0);

    if (titleInput && slugInput) {
        slugInput.addEventListener('input', function () { slugEdited = true; });
        titleInput.addEventListener('input', function () {
            if (!slugEdited) {
                slugInput.value = this.value.toLowerCase().trim()
                    .replace(/[^\w\s-]/g, '')
                    .replace(/[\s_]+/g, '-')
                    .replace(/-+/g, '-')
                    .replace(/^-|-$/g, '');
            }
        });
    }

    // ── Block body HTML ───────────────────────────────────────────────────────────

    function blockBodyHTML(block) {
        switch (block.type) {
            case 'body':
            case 'callout':
            case 'callout-pine':
                return '<textarea rows="3" data-field="content" placeholder="' + esc(BLOCK_LABELS[block.type]) + '…">' + esc(block.content || '') + '</textarea>';

            case 'h3':
                return '<input type="text" data-field="content" placeholder="Heading text…" value="' + esc(block.content || '') + '">';

            case 'richtext':
                return '<div class="wiki-quill-container"></div>';

            case 'list':
                var items = Array.isArray(block.items) ? block.items.join('\n') : '';
                return '<textarea rows="4" data-field="list-items" placeholder="One item per line…">' + esc(items) + '</textarea>';

            case 'image':
                return [
                    '<div style="display:flex;flex-direction:column;gap:0.5rem;">',
                    '  <div class="wiki-image-preview">' + (block.url ? '<img src="' + esc(block.url) + '" style="max-height:120px;border-radius:4px;">' : '') + '</div>',
                    '  <input type="hidden" class="wiki-image-url" value="' + esc(block.url || '') + '">',
                    '  <input type="file" class="wiki-image-file-input hidden" accept="image/*">',
                    '  <button type="button" class="btn-secondary btn-sm wiki-image-upload-btn">Upload Image</button>',
                    '  <input type="text" data-field="caption" placeholder="Caption (optional)" value="' + esc(block.caption || '') + '">',
                    '</div>'
                ].join('');

            case 'video':
                return '<input type="url" data-field="content" placeholder="YouTube or Vimeo URL…" value="' + esc(block.content || '') + '">';

            default:
                return '<textarea rows="3" data-field="content">' + esc(block.content || '') + '</textarea>';
        }
    }

    // ── Render all blocks ─────────────────────────────────────────────────────────

    function renderBlocks() {
        blockList.innerHTML = '';
        quillInstances = {};

        blocks.forEach(function (block, index) {
            var card = document.createElement('div');
            card.className = 'wiki-editor-block';
            card.dataset.blockId = block._id;

            card.innerHTML = [
                '<div class="wiki-editor-block-header">',
                '  <span class="block-type-label">' + (BLOCK_LABELS[block.type] || block.type) + '</span>',
                '  <button type="button" class="btn-icon block-move-up"' + (index === 0 ? ' disabled' : '') + ' title="Move up">↑</button>',
                '  <button type="button" class="btn-icon block-move-down"' + (index === blocks.length - 1 ? ' disabled' : '') + ' title="Move down">↓</button>',
                '  <button type="button" class="btn-icon block-delete" title="Remove" style="color:var(--rose);">✕</button>',
                '</div>',
                '<div class="wiki-editor-block-body">' + blockBodyHTML(block) + '</div>'
            ].join('');

            blockList.appendChild(card);

            // Move up
            card.querySelector('.block-move-up').addEventListener('click', function () {
                if (index === 0) return;
                syncBlocks();
                var tmp = blocks[index - 1];
                blocks[index - 1] = blocks[index];
                blocks[index] = tmp;
                renderBlocks();
            });

            // Move down
            card.querySelector('.block-move-down').addEventListener('click', function () {
                if (index === blocks.length - 1) return;
                syncBlocks();
                var tmp = blocks[index + 1];
                blocks[index + 1] = blocks[index];
                blocks[index] = tmp;
                renderBlocks();
            });

            // Delete
            card.querySelector('.block-delete').addEventListener('click', function () {
                blocks.splice(index, 1);
                renderBlocks();
            });

            // Quill for richtext
            if (block.type === 'richtext') {
                var container = card.querySelector('.wiki-quill-container');
                var q = new Quill(container, {
                    theme: 'snow',
                    modules: {
                        toolbar: [
                            ['bold', 'italic', 'underline'],
                            [{ list: 'ordered' }, { list: 'bullet' }],
                            ['clean']
                        ]
                    }
                });
                if (block.content) q.clipboard.dangerouslyPasteHTML(block.content);
                quillInstances[block._id] = q;
            }

            // Image upload
            if (block.type === 'image') {
                var uploadBtn = card.querySelector('.wiki-image-upload-btn');
                var fileInput = card.querySelector('.wiki-image-file-input');
                var preview = card.querySelector('.wiki-image-preview');
                var urlStore = card.querySelector('.wiki-image-url');

                uploadBtn.addEventListener('click', function () { fileInput.click(); });
                fileInput.addEventListener('change', function () {
                    var file = this.files[0];
                    if (!file) return;
                    uploadBtn.textContent = 'Uploading…';
                    uploadBtn.disabled = true;
                    var fd = new FormData();
                    fd.append('file', file);
                    fetch('/wiki/upload-image', { method: 'POST', body: fd })
                        .then(function (r) { return r.json(); })
                        .then(function (data) {
                            if (data.success) {
                                urlStore.value = data.url;
                                preview.innerHTML = '<img src="' + data.url + '" style="max-height:120px;border-radius:4px;">';
                            } else {
                                showToast(data.error || 'Upload failed', 'error');
                            }
                            uploadBtn.textContent = 'Upload Image';
                            uploadBtn.disabled = false;
                        })
                        .catch(function () {
                            showToast('Upload failed', 'error');
                            uploadBtn.textContent = 'Upload Image';
                            uploadBtn.disabled = false;
                        });
                });
            }
        });
    }

    // ── Sync DOM → blocks array before save or reorder ────────────────────────────

    function syncBlocks() {
        blocks.forEach(function (block) {
            var card = blockList.querySelector('[data-block-id="' + block._id + '"]');
            if (!card) return;

            if (block.type === 'richtext') {
                var q = quillInstances[block._id];
                block.content = q ? q.root.innerHTML : '';
            } else if (block.type === 'list') {
                var ta = card.querySelector('[data-field="list-items"]');
                block.items = ta ? ta.value.split('\n').map(function (s) { return s.trim(); }).filter(Boolean) : [];
            } else if (block.type === 'image') {
                block.url = card.querySelector('.wiki-image-url').value;
                block.caption = card.querySelector('[data-field="caption"]').value;
            } else {
                var field = card.querySelector('[data-field="content"]');
                if (field) block.content = field.value;
            }
        });
    }

    // ── Add block buttons ─────────────────────────────────────────────────────────

    document.querySelectorAll('.wiki-add-block-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            syncBlocks();  // ← add this line
            blocks.push({ _id: uid(), type: this.dataset.blockType, content: '', items: [] });
            renderBlocks();
            blockList.lastElementChild && blockList.lastElementChild.scrollIntoView({ behavior: 'smooth' });
        });
    });

    // ── Save form ─────────────────────────────────────────────────────────────────

    var saveForm = document.getElementById('wiki-article-form');
    if (saveForm) {
        saveForm.addEventListener('submit', function () {
            syncBlocks();
            var clean = blocks.map(function (b) {
                var copy = Object.assign({}, b);
                delete copy._id;
                return copy;
            });
            document.getElementById('wiki-sections-json').value = JSON.stringify(clean);
        });
    }

    // ── Publish toggle ────────────────────────────────────────────────────────────

    var publishBtn = document.getElementById('wiki-publish-btn');
    if (publishBtn) {
        publishBtn.addEventListener('click', function () {
            var articleId = this.dataset.articleId;
            fetch('/wiki/editor/article/' + articleId + '/toggle-publish', { method: 'POST' })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.success) {
                        publishBtn.textContent = data.is_published ? 'Unpublish' : 'Publish';
                        showToast(data.is_published ? 'Published' : 'Unpublished', 'success');
                    }
                })
                .catch(function () { showToast('Something went wrong', 'error'); });
        });
    }

    // ── Delete article ────────────────────────────────────────────────────────────

    var deleteArticleBtn = document.getElementById('wiki-delete-article-btn');
    if (deleteArticleBtn) {
        deleteArticleBtn.addEventListener('click', function () {
            var articleId = this.dataset.articleId;
            showConfirm('Delete this article? This cannot be undone.', function () {
                fetch('/wiki/editor/article/' + articleId + '/delete', { method: 'POST' })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (data.success) window.location.href = '/wiki/editor';
                    })
                    .catch(function () { showToast('Something went wrong', 'error'); });
            }, 'Delete Article');
        });
    }  

}());

