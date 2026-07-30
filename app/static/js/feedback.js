/* ── feedback.js — Feature Requests ────────────────────── */

(function () {

    var contentArea = document.getElementById('fr-content-area');
    if (!contentArea) return;

    var cardList    = document.getElementById('fr-card-list');
    var currentSort = 'status';  // 'status' | 'popular'
    var features    = typeof FEATURES_DATA !== 'undefined' ? FEATURES_DATA.slice() : [];

    // ── Status config ─────────────────────────────────────
    var STATUS_LABEL = {
        testing:     'Testing',
        in_progress: 'In Progress',
        requested:   'Requested',
        implemented: 'Implemented'
    };
    var STATUS_ORDER = ['testing', 'in_progress', 'requested', 'implemented'];

    // ── Escape HTML for injecting user content ────────────
    function esc(str) {
        return String(str || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    // ── Build one card's HTML ─────────────────────────────
    function cardHTML(f) {
        return '<div class="fr-card" data-feature-id="' + f.id + '">' +
            '<span class="fr-card-title">' + esc(f.title) + '</span>' +
            '<div class="fr-card-footer">' +
            '<span class="fr-card-upvotes">▲ ' + f.upvote_count + '</span>' +
            '<span class="fr-status-pill fr-status-pill--' + f.status + '">' +
                (STATUS_LABEL[f.status] || f.status) +
            '</span>' +
            '</div>' +
            '</div>';
    }

    // ── Render the card list ──────────────────────────────
    function renderCards() {
        var html = '';

        if (currentSort === 'popular') {
            var sorted = features.slice().sort(function (a, b) {
                return b.upvote_count - a.upvote_count;
            });
            if (!sorted.length) {
                html = '<p style="padding:1rem 1.25rem;font-size:0.85rem;color:#aaa;">No feature requests yet.</p>';
            } else {
                sorted.forEach(function (f) { html += cardHTML(f); });
            }
        } else {
            // Group by status in priority order
            var hasAny = false;
            STATUS_ORDER.forEach(function (status) {
                var group = features.filter(function (f) { return f.status === status; });
                if (!group.length) return;
                hasAny = true;
                html += '<p class="fr-group-label">' + STATUS_LABEL[status] + '</p>';
                group.forEach(function (f) { html += cardHTML(f); });
            });
            if (!hasAny) {
                html = '<p style="padding:1rem 1.25rem;font-size:0.85rem;color:#aaa;">No feature requests yet.</p>';
            }
        }

        cardList.innerHTML = html;
        reMarkActive();
    }

    // ── Re-apply active class after re-render ─────────────
    var _activeId = null;
    function reMarkActive() {
        cardList.querySelectorAll('.fr-card').forEach(function (el) {
            el.classList.toggle('active', el.dataset.featureId === String(_activeId));
        });
    }

    // ── Card click (event delegation) ────────────────────
    cardList.addEventListener('click', function (e) {
        var card = e.target.closest('.fr-card');
        if (!card) return;
        loadFeature(parseInt(card.dataset.featureId));
    });

    // ── Sort toggle ───────────────────────────────────────
    document.querySelectorAll('.fr-sort-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            document.querySelectorAll('.fr-sort-btn').forEach(function (b) {
                b.classList.remove('active');
            });
            btn.classList.add('active');
            currentSort = btn.dataset.sort;
            renderCards();
        });
    });

    // ── Load feature detail ───────────────────────────────
    function loadFeature(featureId) {
        _activeId = featureId;
        reMarkActive();
        history.replaceState(null, '', '/feature-requests#fr-' + featureId);

        contentArea.innerHTML = '<div class="blog-placeholder"><p style="color:#bbb;font-size:0.9rem;">Loading...</p></div>';

        fetch('/feature-requests/' + featureId, { headers: { 'X-Nav-Request': '0' } })
            .then(function (r) { return r.text(); })
            .then(function (html) {
                contentArea.innerHTML = html;
                initFeatureDetail(featureId);
            })
            .catch(function () {
                contentArea.innerHTML = '<div class="blog-placeholder"><p style="color:var(--rose);">Failed to load.</p></div>';
            });
    }

    // ── Auto-load from hash ───────────────────────────────
    var hash = window.location.hash;
    if (hash && hash.startsWith('#fr-')) {
        loadFeature(parseInt(hash.replace('#fr-', '')));
    }

    // ── Expose render + remove so initFeatureDetail can update local array
    window._renderFeatureCards = renderCards;
    window._removeFeature = function (id) {
        for (var i = 0; i < features.length; i++) {
            if (features[i].id === id) { features.splice(i, 1); break; }
        }
    };

    // ── Confirm modal ─────────────────────────────────────
    var delOverlay  = document.getElementById('fr-del-overlay');
    var delMessage  = document.getElementById('fr-del-message');
    var delConfirm  = document.getElementById('fr-del-confirm');
    var delCancel   = document.getElementById('fr-del-cancel');
    var _delCallback = null;

    window._frConfirm = function (message, onConfirm) {
        delMessage.textContent = message;
        _delCallback = onConfirm;
        delOverlay.classList.add('active');
    };

    function closeDelModal() {
        delOverlay.classList.remove('active');
        _delCallback = null;
    }

    delCancel.addEventListener('click', closeDelModal);
    delOverlay.addEventListener('click', function (e) {
        if (e.target === delOverlay) closeDelModal();
    });
    delConfirm.addEventListener('click', function () {
        var fn = _delCallback;
        closeDelModal();
        if (fn) fn();
    });

    // ── Initial render ────────────────────────────────────
    renderCards();

    // ── Modal ─────────────────────────────────────────────
    var overlay  = document.getElementById('fr-modal-overlay');
    var modal    = document.getElementById('fr-modal');
    var openBtn  = document.getElementById('fr-request-btn');
    var closeBtn = document.getElementById('fr-modal-close');
    var cancelBtn = document.getElementById('fr-modal-cancel');
    var submitBtn = document.getElementById('fr-modal-submit');

    function openModal() {
        overlay.classList.add('active');
        modal.classList.add('active');
        document.getElementById('fr-input-title').focus();
    }

    function closeModal() {
        overlay.classList.remove('active');
        modal.classList.remove('active');
    }

    if (openBtn) openBtn.addEventListener('click', openModal);
    if (closeBtn) closeBtn.addEventListener('click', closeModal);
    if (cancelBtn) cancelBtn.addEventListener('click', closeModal);
    overlay.addEventListener('click', closeModal);

    if (submitBtn) {
        submitBtn.addEventListener('click', function () {
            var title = document.getElementById('fr-input-title').value.trim();
            var desc  = document.getElementById('fr-input-description').value.trim();

            if (!title || !desc) {
                alert('Please fill in both the title and description.');
                return;
            }

            submitBtn.disabled = true;
            submitBtn.textContent = 'Submitting...';

            fetch('/feature-requests', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: title, description: desc })
            })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    // Add to local data and re-render list
                    features.unshift(data.feature);
                    renderCards();
                    closeModal();
                    // Clear form
                    document.getElementById('fr-input-title').value = '';
                    document.getElementById('fr-input-description').value = '';
                    // Auto-load the new feature
                    loadFeature(data.feature.id);
                } else {
                    alert(data.error || 'Submit failed.');
                }
                submitBtn.disabled = false;
                submitBtn.textContent = 'Submit Request';
            })
            .catch(function () {
                alert('Submit failed. Please try again.');
                submitBtn.disabled = false;
                submitBtn.textContent = 'Submit Request';
            });
        });
    }

}());


// ── Feature detail interactions ───────────────────────────
function initFeatureDetail(featureId) {

    // ── Upvote toggle ────────────────────────────────────
    var upvoteBtn = document.getElementById('fr-upvote-btn');
    if (upvoteBtn) {
        upvoteBtn.addEventListener('click', function () {
            fetch('/feature-requests/' + featureId + '/upvote', { method: 'POST' })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.success) return;
                    var countEl = document.getElementById('fr-upvote-count');
                    var labelEl = document.getElementById('fr-upvote-label');
                    var svgPath = upvoteBtn.querySelector('polyline');

                    if (data.voted) {
                        upvoteBtn.classList.add('fr-upvote-btn--voted');
                        if (labelEl) labelEl.textContent = 'Upvoted';
                        if (svgPath) svgPath.closest('svg').setAttribute('fill', 'currentColor');
                    } else {
                        upvoteBtn.classList.remove('fr-upvote-btn--voted');
                        if (labelEl) labelEl.textContent = 'Upvote';
                        if (svgPath) svgPath.closest('svg').setAttribute('fill', 'none');
                    }
                    if (countEl) countEl.textContent = data.count;

                    // Update local data and re-render so popular sort re-orders
                    if (typeof FEATURES_DATA !== 'undefined') {
                        FEATURES_DATA.forEach(function (f) {
                            if (f.id === featureId) f.upvote_count = data.count;
                        });
                    }
                    if (typeof window._renderFeatureCards === 'function') {
                        window._renderFeatureCards();
                    }
                });
        });
    }

    // ── Admin: status change ──────────────────────────────
    var statusSelect = document.getElementById('fr-status-select');
    if (statusSelect) {
        statusSelect.addEventListener('change', function () {
            var newStatus = statusSelect.value;
            fetch('/feature-requests/' + featureId + '/status', {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: newStatus })
            })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.success) return;
                // Update pill in detail view
                var pill = document.getElementById('fr-status-display');
                var labels = { requested: 'Requested', in_progress: 'In Progress', testing: 'Testing', implemented: 'Implemented' };
                if (pill) {
                    pill.className = 'fr-status-pill fr-status-pill--' + data.status;
                    pill.textContent = labels[data.status] || data.status;
                }
                // Update local data and re-render grouped list
                if (typeof FEATURES_DATA !== 'undefined') {
                    FEATURES_DATA.forEach(function (f) {
                        if (f.id === featureId) f.status = data.status;
                    });
                }
                if (typeof window._renderFeatureCards === 'function') {
                    window._renderFeatureCards();
                }
            });
        });
    }

    // ── Admin: delete feature ─────────────────────────────
    var deleteBtn = document.getElementById('fr-delete-btn');
    if (deleteBtn) {
        deleteBtn.addEventListener('click', function () {
            window._frConfirm('Delete this feature request? This cannot be undone.', function () {
                fetch('/feature-requests/' + featureId, { method: 'DELETE' })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (data.success) {
                            if (typeof window._removeFeature === 'function') window._removeFeature(featureId);
                            if (typeof window._renderFeatureCards === 'function') window._renderFeatureCards();
                            document.getElementById('fr-content-area').innerHTML =
                                '<div class="blog-placeholder"><p style="color:#bbb;font-size:0.9rem;">Select a feature to view details</p></div>';
                            history.replaceState(null, '', '/feature-requests');
                        }
                    });
            });
        });
    }

    // ── Comments ──────────────────────────────────────────
    var commentsSection = document.getElementById('fr-comments');
    if (!commentsSection) return;

    // Reply show/hide
    commentsSection.addEventListener('click', function (e) {
        var replyBtn = e.target.closest('.fr-reply-btn');
        if (!replyBtn) return;
        var id   = replyBtn.dataset.commentId;
        var form = document.getElementById('fr-reply-form-' + id);
        if (!form) return;
        var visible = form.style.display !== 'none';
        form.style.display = visible ? 'none' : 'block';
        if (!visible) form.querySelector('textarea').focus();
    });

    // Reply cancel
    commentsSection.addEventListener('click', function (e) {
        var cancelBtn = e.target.closest('.fr-reply-cancel');
        if (!cancelBtn) return;
        var form = cancelBtn.closest('.fr-reply-form');
        if (form) {
            form.style.display = 'none';
            form.querySelector('textarea').value = '';
        }
    });

    // Reply submit
    commentsSection.addEventListener('submit', function (e) {
        var form = e.target.closest('.fr-reply-form');
        if (!form) return;
        e.preventDefault();

        var commentId = form.id.replace('fr-reply-form-', '');
        var textarea  = form.querySelector('textarea');
        var btn       = form.querySelector('button[type="submit"]');
        var body      = textarea.value.trim();
        if (!body) return;

        btn.disabled    = true;
        btn.textContent = 'Posting...';

        var fd = new FormData();
        fd.append('body', body);
        fd.append('parent_id', commentId);

        fetch('/feature-requests/' + featureId + '/comments', { method: 'POST', body: fd })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    var c = data.comment;
                    var repliesEl = document.getElementById('fr-replies-' + commentId);
                    if (repliesEl) {
                        var div = document.createElement('div');
                        div.className = 'blog-comment blog-comment--reply';
                        div.id = 'fr-comment-' + c.id;
                        div.innerHTML =
                            '<div class="blog-comment-meta">' +
                            '<div class="blog-comment-avatar">' + c.avatar_letter + '</div>' +
                            '<div class="blog-comment-author-info">' +
                            '<span class="blog-comment-author-name">' + c.author + '</span>' +
                            '<span class="blog-comment-date">' + c.created_at + '</span>' +
                            '</div></div>' +
                            '<p class="blog-comment-body">' + c.body + '</p>';
                        repliesEl.appendChild(div);
                    }
                    textarea.value = '';
                    form.style.display = 'none';
                }
                btn.disabled    = false;
                btn.textContent = 'Post Reply';
            })
            .catch(function () {
                btn.disabled    = false;
                btn.textContent = 'Post Reply';
            });
    });

    // Delete comment
    commentsSection.addEventListener('click', function (e) {
        var btn = e.target.closest('.fr-comment-delete');
        if (!btn) return;
        var commentId = btn.dataset.commentId;
        window._frConfirm('Delete this comment?', function () {
            fetch('/feature-requests/comments/' + commentId, { method: 'DELETE' })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.success) {
                        var el = document.getElementById('fr-comment-' + commentId);
                        if (el) el.remove();
                    }
                });
        });
    });

    // Top-level comment submit
    var commentForm = document.getElementById('fr-comment-form');
    if (commentForm) {
        commentForm.addEventListener('submit', function (e) {
            e.preventDefault();
            var textarea = commentForm.querySelector('textarea[name="body"]');
            var btn      = commentForm.querySelector('button[type="submit"]');
            var body     = textarea.value.trim();
            if (!body) return;

            btn.disabled    = true;
            btn.textContent = 'Posting...';

            var fd = new FormData();
            fd.append('body', body);

            fetch('/feature-requests/' + featureId + '/comments', { method: 'POST', body: fd })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.success) {
                        var c = data.comment;
                        var noComments = commentsSection.querySelector('.blog-no-comments');
                        if (noComments) noComments.remove();

                        var div = document.createElement('div');
                        div.className = 'blog-comment';
                        div.id = 'fr-comment-' + c.id;
                        div.innerHTML =
                            '<div class="blog-comment-meta">' +
                            '<div class="blog-comment-avatar">' + c.avatar_letter + '</div>' +
                            '<div class="blog-comment-author-info">' +
                            '<span class="blog-comment-author-name">' + c.author + '</span>' +
                            '<span class="blog-comment-date">' + c.created_at + '</span>' +
                            '</div></div>' +
                            '<p class="blog-comment-body">' + c.body + '</p>' +
                            '<button class="blog-reply-btn fr-reply-btn" data-comment-id="' + c.id + '">Reply</button>' +
                            '<form class="blog-reply-form fr-reply-form" id="fr-reply-form-' + c.id + '" style="display:none;">' +
                            '<div class="form-group"><textarea name="body" class="form-input" rows="2" placeholder="Write a reply..."></textarea></div>' +
                            '<div class="blog-reply-actions">' +
                            '<button type="submit" class="btn btn-primary btn-sm">Post Reply</button>' +
                            '<button type="button" class="btn btn-secondary btn-sm fr-reply-cancel">Cancel</button>' +
                            '</div></form>' +
                            '<div class="blog-replies" id="fr-replies-' + c.id + '"></div>';

                        document.getElementById('fr-comments-list').appendChild(div);
                        textarea.value = '';
                    }
                    btn.disabled    = false;
                    btn.textContent = 'Post Comment';
                })
                .catch(function () {
                    btn.disabled    = false;
                    btn.textContent = 'Post Comment';
                });
        });
    }
}
