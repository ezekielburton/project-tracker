/**
 * Editor buttons shared by the dashboard and the article editor:
 * section publish and delete, and article delete.
 */
(function () {
    'use strict';

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
