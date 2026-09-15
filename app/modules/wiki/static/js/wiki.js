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

