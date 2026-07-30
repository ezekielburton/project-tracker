/* ── bug_reports.js ─────────────────────────────────────── */

(function () {

    var contentArea = document.getElementById('br-content-area');
    if (!contentArea) return;

    var cardList   = document.getElementById('br-card-list');
    var currentSort = 'status';  // 'status' | 'newest'
    var bugs        = typeof BUGS_DATA !== 'undefined' ? BUGS_DATA.slice() : [];

    // ── Status config ─────────────────────────────────────
    var STATUS_LABEL = {
        in_queue:        'In Queue',
        fix_in_progress: 'Fix in Progress',
        testing:         'Testing',
        resolved:        'Resolved'
    };
    var STATUS_ORDER = ['fix_in_progress', 'testing', 'in_queue', 'resolved'];

    // ── Escape HTML ───────────────────────────────────────
    function esc(str) {
        return String(str || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    // ── Build one card's HTML ─────────────────────────────
    function cardHTML(b) {
        return '<div class="fr-card" data-bug-id="' + b.id + '">' +
            '<span class="fr-card-title">' + esc(b.title) + '</span>' +
            '<div class="fr-card-footer">' +
            '<span class="br-status-pill br-status-pill--' + b.status + '">' +
                (STATUS_LABEL[b.status] || b.status) +
            '</span>' +
            '</div>' +
            '</div>';
    }

    // ── Render the card list ──────────────────────────────
    function renderCards() {
        var html = '';

        if (currentSort === 'newest') {
            var sorted = bugs.slice().sort(function (a, b) { return b.id - a.id; });
            if (!sorted.length) {
                html = '<p style="padding:1rem 1.25rem;font-size:0.85rem;color:#aaa;">No bug reports yet.</p>';
            } else {
                sorted.forEach(function (b) { html += cardHTML(b); });
            }
        } else {
            var hasAny = false;
            STATUS_ORDER.forEach(function (status) {
                var group = bugs.filter(function (b) { return b.status === status; });
                if (!group.length) return;
                hasAny = true;
                html += '<p class="fr-group-label">' + STATUS_LABEL[status] + '</p>';
                group.forEach(function (b) { html += cardHTML(b); });
            });
            if (!hasAny) {
                html = '<p style="padding:1rem 1.25rem;font-size:0.85rem;color:#aaa;">No bug reports yet.</p>';
            }
        }

        cardList.innerHTML = html;
        reMarkActive();
    }

    // ── Re-apply active class ─────────────────────────────
    var _activeId = null;
    function reMarkActive() {
        cardList.querySelectorAll('.fr-card').forEach(function (el) {
            el.classList.toggle('active', el.dataset.bugId === String(_activeId));
        });
    }

    // ── Card click ────────────────────────────────────────
    cardList.addEventListener('click', function (e) {
        var card = e.target.closest('.fr-card');
        if (!card) return;
        loadBug(parseInt(card.dataset.bugId));
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

    // ── Load bug detail ───────────────────────────────────
    function loadBug(bugId) {
        _activeId = bugId;
        reMarkActive();
        history.replaceState(null, '', '/bug-reports#br-' + bugId);

        contentArea.innerHTML = '<div class="blog-placeholder"><p style="color:#bbb;font-size:0.9rem;">Loading...</p></div>';

        fetch('/bug-reports/' + bugId, { headers: { 'X-Nav-Request': '0' } })
            .then(function (r) { return r.text(); })
            .then(function (html) {
                contentArea.innerHTML = html;
                initBugDetail(bugId);
            })
            .catch(function () {
                contentArea.innerHTML = '<div class="blog-placeholder"><p style="color:var(--rose);">Failed to load.</p></div>';
            });
    }

    // ── Auto-load from hash ───────────────────────────────
    var hash = window.location.hash;
    if (hash && hash.startsWith('#br-')) {
        loadBug(parseInt(hash.replace('#br-', '')));
    }

    // ── Expose render + remove so initBugDetail can update local array
    window._renderBugCards = renderCards;
    window._removeBug = function (id) {
        for (var i = 0; i < bugs.length; i++) {
            if (bugs[i].id === id) { bugs.splice(i, 1); break; }
        }
    };

    // ── Confirm modal ─────────────────────────────────────
    var delOverlay  = document.getElementById('br-del-overlay');
    var delMessage  = document.getElementById('br-del-message');
    var delConfirm  = document.getElementById('br-del-confirm');
    var delCancel   = document.getElementById('br-del-cancel');
    var _delCallback = null;

    window._brConfirm = function (message, onConfirm) {
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
    var overlay   = document.getElementById('br-modal-overlay');
    var modal     = document.getElementById('br-modal');
    var openBtn   = document.getElementById('br-report-btn');
    var closeBtn  = document.getElementById('br-modal-close');
    var cancelBtn = document.getElementById('br-modal-cancel');
    var submitBtn = document.getElementById('br-modal-submit');

    function openModal() {
        overlay.classList.add('active');
        modal.classList.add('active');
        document.getElementById('br-input-title').focus();
    }

    function closeModal() {
        overlay.classList.remove('active');
        modal.classList.remove('active');
    }

    if (openBtn)   openBtn.addEventListener('click', openModal);
    if (closeBtn)  closeBtn.addEventListener('click', closeModal);
    if (cancelBtn) cancelBtn.addEventListener('click', closeModal);
    overlay.addEventListener('click', closeModal);

    if (submitBtn) {
        submitBtn.addEventListener('click', function () {
            var title = document.getElementById('br-input-title').value.trim();
            var desc  = document.getElementById('br-input-description').value.trim();

            if (!title || !desc) {
                alert('Please fill in both the title and description.');
                return;
            }

            submitBtn.disabled    = true;
            submitBtn.textContent = 'Submitting...';

            fetch('/bug-reports', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: title, description: desc })
            })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    bugs.unshift(data.bug);
                    renderCards();
                    closeModal();
                    document.getElementById('br-input-title').value       = '';
                    document.getElementById('br-input-description').value = '';
                    loadBug(data.bug.id);
                } else {
                    alert(data.error || 'Submit failed.');
                }
                submitBtn.disabled    = false;
                submitBtn.textContent = 'Submit Report';
            })
            .catch(function () {
                alert('Submit failed. Please try again.');
                submitBtn.disabled    = false;
                submitBtn.textContent = 'Submit Report';
            });
        });
    }

}());


// ── Bug detail interactions ───────────────────────────────
function initBugDetail(bugId) {

    // ── Admin: status change ──────────────────────────────
    var statusSelect = document.getElementById('br-status-select');
    if (statusSelect) {
        statusSelect.addEventListener('change', function () {
            var newStatus = statusSelect.value;
            fetch('/bug-reports/' + bugId + '/status', {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: newStatus })
            })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.success) return;
                var pill   = document.getElementById('br-status-display');
                var labels = {
                    in_queue:        'In Queue',
                    fix_in_progress: 'Fix in Progress',
                    testing:         'Testing',
                    resolved:        'Resolved'
                };
                if (pill) {
                    pill.className   = 'br-status-pill br-status-pill--' + data.status;
                    pill.textContent = labels[data.status] || data.status;
                }
                // Update local data and re-render grouped list
                if (typeof BUGS_DATA !== 'undefined') {
                    BUGS_DATA.forEach(function (b) {
                        if (b.id === bugId) b.status = data.status;
                    });
                }
                if (typeof window._renderBugCards === 'function') {
                    window._renderBugCards();
                }
            });
        });
    }

    // ── Delete bug ────────────────────────────────────────
    var deleteBtn = document.getElementById('br-delete-btn');
    if (deleteBtn) {
        deleteBtn.addEventListener('click', function () {
            window._brConfirm('Delete this bug report? This cannot be undone.', function () {
                fetch('/bug-reports/' + bugId, { method: 'DELETE' })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (data.success) {
                            if (typeof window._removeBug === 'function') window._removeBug(bugId);
                            if (typeof window._renderBugCards === 'function') window._renderBugCards();
                            document.getElementById('br-content-area').innerHTML =
                                '<div class="blog-placeholder"><p style="color:#bbb;font-size:0.9rem;">Select a bug report to view details</p></div>';
                            history.replaceState(null, '', '/bug-reports');
                        }
                    });
            });
        });
    }

    // ── Comments ──────────────────────────────────────────
    var commentsSection = document.getElementById('br-comments');
    if (!commentsSection) return;

    // Reply show/hide
    commentsSection.addEventListener('click', function (e) {
        var replyBtn = e.target.closest('.br-reply-btn');
        if (!replyBtn) return;
        var id   = replyBtn.dataset.commentId;
        var form = document.getElementById('br-reply-form-' + id);
        if (!form) return;
        var visible = form.style.display !== 'none';
        form.style.display = visible ? 'none' : 'block';
        if (!visible) form.querySelector('textarea').focus();
    });

    // Reply cancel
    commentsSection.addEventListener('click', function (e) {
        var btn = e.target.closest('.br-reply-cancel');
        if (!btn) return;
        var form = btn.closest('.br-reply-form');
        if (form) { form.style.display = 'none'; form.querySelector('textarea').value = ''; }
    });

    // Reply submit
    commentsSection.addEventListener('submit', function (e) {
        var form = e.target.closest('.br-reply-form');
        if (!form) return;
        e.preventDefault();

        var commentId = form.id.replace('br-reply-form-', '');
        var textarea  = form.querySelector('textarea');
        var btn       = form.querySelector('button[type="submit"]');
        var body      = textarea.value.trim();
        if (!body) return;

        btn.disabled    = true;
        btn.textContent = 'Posting...';

        var fd = new FormData();
        fd.append('body', body);
        fd.append('parent_id', commentId);

        fetch('/bug-reports/' + bugId + '/comments', { method: 'POST', body: fd })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    var c        = data.comment;
                    var repliesEl = document.getElementById('br-replies-' + commentId);
                    if (repliesEl) {
                        var div = document.createElement('div');
                        div.className = 'blog-comment blog-comment--reply';
                        div.id = 'br-comment-' + c.id;
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
                    textarea.value     = '';
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
        var btn = e.target.closest('.br-comment-delete');
        if (!btn) return;
        var commentId = btn.dataset.commentId;
        window._brConfirm('Delete this comment?', function () {
            fetch('/bug-reports/comments/' + commentId, { method: 'DELETE' })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.success) {
                        var el = document.getElementById('br-comment-' + commentId);
                        if (el) el.remove();
                    }
                });
        });
    });

    // Top-level comment submit
    var commentForm = document.getElementById('br-comment-form');
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

            fetch('/bug-reports/' + bugId + '/comments', { method: 'POST', body: fd })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.success) {
                        var c          = data.comment;
                        var noComments = commentsSection.querySelector('.blog-no-comments');
                        if (noComments) noComments.remove();

                        var div = document.createElement('div');
                        div.className = 'blog-comment';
                        div.id        = 'br-comment-' + c.id;
                        div.innerHTML =
                            '<div class="blog-comment-meta">' +
                            '<div class="blog-comment-avatar">' + c.avatar_letter + '</div>' +
                            '<div class="blog-comment-author-info">' +
                            '<span class="blog-comment-author-name">' + c.author + '</span>' +
                            '<span class="blog-comment-date">' + c.created_at + '</span>' +
                            '</div></div>' +
                            '<p class="blog-comment-body">' + c.body + '</p>' +
                            '<button class="blog-reply-btn br-reply-btn" data-comment-id="' + c.id + '">Reply</button>' +
                            '<form class="blog-reply-form br-reply-form" id="br-reply-form-' + c.id + '" style="display:none;">' +
                            '<div class="form-group"><textarea name="body" class="form-input" rows="2" placeholder="Write a reply..."></textarea></div>' +
                            '<div class="blog-reply-actions">' +
                            '<button type="submit" class="btn btn-primary btn-sm">Post Reply</button>' +
                            '<button type="button" class="btn btn-secondary btn-sm br-reply-cancel">Cancel</button>' +
                            '</div></form>' +
                            '<div class="blog-replies" id="br-replies-' + c.id + '"></div>';

                        document.getElementById('br-comments-list').appendChild(div);
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
