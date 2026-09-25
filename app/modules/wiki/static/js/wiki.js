(function () {
    'use strict';

    function loadArticle(articleId) {
        // Looked up per call: an SPA swap replaces the panel without re-running this file.
        var contentPanel = document.getElementById('wiki-content-panel');
        if (!contentPanel) return;

        document.querySelectorAll('.wiki-nav-article').forEach(function (a) {
            a.classList.toggle('active', a.dataset.articleId === String(articleId));
        });

        contentPanel.innerHTML = '<p style="padding:2rem;color:var(--text-muted);">Loading…</p>';

        fetch('/wiki/article/' + articleId)
            .then(function (r) { return r.text(); })
            .then(function (html) { contentPanel.innerHTML = html; })
            .catch(function () {
                contentPanel.innerHTML = '<p style="padding:2rem;color:var(--rose);">Failed to load article.</p>';
            });

        history.replaceState(null, '', '#article-' + articleId);
    }

    // Delegated to document so the binding outlives an SPA swap.
    document.addEventListener('click', function (e) {
        var a = e.target.closest('.wiki-nav-article');
        if (!a) return;
        e.preventDefault();
        loadArticle(a.dataset.articleId);
    });

    function autoLoadWiki() {
        if (!document.getElementById('wiki-content-panel')) return;
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
