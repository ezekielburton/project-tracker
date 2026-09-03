/* ── Blog JS ─────────────────────────────────────────── */

// ── Post list: load post on click / hash on load ──────
(function () {
    var contentArea = document.getElementById('blog-content-area');
    if (!contentArea) return;

    var listPanel = document.getElementById('blog-post-list');
    var _savedList = null;   // stores original post-list HTML before first swap

    // ── Restore post list, clear content ────────────────
    function goBack() {
        history.replaceState(null, '', '/blog');

        listPanel.classList.add('fading');
        contentArea.classList.add('fading');

        setTimeout(function () {
            listPanel.innerHTML = _savedList;
            listPanel.classList.remove('fading');

            contentArea.innerHTML =
                '<div class="blog-placeholder" id="blog-placeholder">' +
                '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none"' +
                ' stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"' +
                ' style="color:#ccc;margin-bottom:1rem;">' +
                '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>' +
                '<polyline points="14 2 14 8 20 8"/>' +
                '<line x1="16" y1="13" x2="8" y2="13"/>' +
                '<line x1="16" y1="17" x2="8" y2="17"/>' +
                '</svg><p style="color:#bbb;font-size:0.9rem;">Select a post to read</p></div>';
            contentArea.classList.remove('fading');
        }, 180);
    }

    // ── Load a post ──────────────────────────────────────
    function loadPost(postId, updateHash) {
        if (updateHash !== false) {
            history.replaceState(null, '', '/blog#post-' + postId);
        }

        // Capture the post list before first swap
        if (!_savedList) {
            _savedList = listPanel.innerHTML;
        }

        // Mark active item if list is currently showing
        listPanel.querySelectorAll('.blog-post-item').forEach(function (el) {
            el.classList.toggle('active', el.dataset.postId === String(postId));
        });

        contentArea.innerHTML = '<div class="blog-placeholder"><p style="color:#bbb;font-size:0.9rem;">Loading...</p></div>';

        fetch('/blog/post/' + postId, { headers: { 'X-Nav-Request': '0' } })
            .then(function (r) { return r.text(); })
            .then(function (html) {
                contentArea.innerHTML = html;

                // Pull nav items out of the hidden div and remove it from the article
                var navData = document.getElementById('blog-nav-data');
                var navInner = navData ? navData.innerHTML : '';
                if (navData) navData.remove();

                // Fade-swap the left panel to the "In This Post" nav
                listPanel.classList.add('fading');
                setTimeout(function () {
                    listPanel.innerHTML =
                        '<button class="blog-back-btn" id="blog-back-btn">← Posts</button>' +
                        '<p class="blog-list-label" style="margin-top:1.25rem;">IN THIS POST</p>' +
                        navInner;
                    listPanel.classList.remove('fading');

                    document.getElementById('blog-back-btn').addEventListener('click', goBack);

                    // Init scrollspy & interactions — nav items are now in the DOM
                    initPostContent(postId);
                }, 180);
            })
            .catch(function () {
                contentArea.innerHTML = '<div class="blog-placeholder"><p style="color:var(--rose);">Failed to load post.</p></div>';
            });
    }

    listPanel.addEventListener('click', function (e) {
        var item = e.target.closest('.blog-post-item');
        if (!item) return;
        e.preventDefault();
        loadPost(item.dataset.postId);
    });

    var hash = window.location.hash;
    if (hash && hash.startsWith('#post-')) {
        loadPost(hash.replace('#post-', ''));
    }
}());

// ── Post content: scrollspy, comments, admin buttons ──
function initPostContent(postId) {

    // Scrollspy
    var scrollArea = document.getElementById('blog-scroll-area');
    var navItems = document.querySelectorAll('.blog-nav-item');
    var sections = document.querySelectorAll('.blog-section');

    if (scrollArea && sections.length) {
        function getActive() {
            var containerTop = scrollArea.getBoundingClientRect().top;
            var active = sections[0];
            sections.forEach(function (s) {
                if (s.getBoundingClientRect().top - containerTop <= 60) active = s;
            });
            return active.id;
        }

        function updateNav() {
            var id = getActive();
            navItems.forEach(function (item) {
                item.classList.toggle('active', item.dataset.target === id);
            });
        }

        scrollArea.addEventListener('scroll', updateNav);
        updateNav();

        navItems.forEach(function (item) {
            item.addEventListener('click', function (e) {
                e.preventDefault();
                var target = document.getElementById(item.dataset.target);
                if (target) {
                    var containerTop = scrollArea.getBoundingClientRect().top;
                    var targetTop = target.getBoundingClientRect().top - containerTop;
                    scrollArea.scrollBy({ top: targetTop - 24, behavior: 'smooth' });
                }
            });
        });
    }

    // Publish toggle — updates button + post list item without refresh
    var publishBtn = document.querySelector('.blog-publish-btn');
    if (publishBtn) {
        publishBtn.addEventListener('click', function () {
            fetch('/blog/posts/' + postId + '/publish', { method: 'POST' })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.success) return;

                    // Update the button text
                    publishBtn.textContent = data.is_published ? 'Unpublish' : 'Publish';

                    // Update the post list item on the left
                    var listItem = document.querySelector('.blog-post-item[data-post-id="' + postId + '"]');
                    if (listItem) {
                        var dateEl = listItem.querySelector('.blog-post-item-date');
                        if (data.is_published) {
                            listItem.classList.remove('blog-post-item--draft');
                            if (dateEl) dateEl.innerHTML = data.published_date;
                        } else {
                            listItem.classList.add('blog-post-item--draft');
                            if (dateEl) dateEl.innerHTML = '<em>Draft</em>';
                        }
                    }
                });
        });
    }

    // Delete post
    var deletePostBtn = document.querySelector('.blog-delete-post-btn');
    if (deletePostBtn) {
        deletePostBtn.addEventListener('click', function () {
            if (!confirm('Delete this post? This cannot be undone.')) return;
            fetch('/blog/posts/' + postId, { method: 'DELETE' })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.success) window.location.href = '/blog';
                });
        });
    }

    // Delete comment
    document.getElementById('blog-comments').addEventListener('click', function (e) {
        var btn = e.target.closest('.blog-comment-delete');
        if (!btn) return;
        if (!confirm('Delete this comment?')) return;
        var commentId = btn.dataset.commentId;
        fetch('/blog/comments/' + commentId, { method: 'DELETE' })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    document.getElementById('comment-' + commentId).remove();
                }
            });
    });

    // Reply buttons — show/hide inline reply form
    document.getElementById('blog-comments').addEventListener('click', function (e) {
        var replyBtn = e.target.closest('.blog-reply-btn');
        if (!replyBtn) return;
        var commentId = replyBtn.dataset.commentId;
        var form = document.getElementById('reply-form-' + commentId);
        if (!form) return;
        var isVisible = form.style.display !== 'none';
        form.style.display = isVisible ? 'none' : 'block';
        if (!isVisible) form.querySelector('textarea').focus();
    });

    // Cancel reply
    document.getElementById('blog-comments').addEventListener('click', function (e) {
        var cancelBtn = e.target.closest('.blog-reply-cancel');
        if (!cancelBtn) return;
        var form = cancelBtn.closest('.blog-reply-form');
        if (form) {
            form.style.display = 'none';
            form.querySelector('textarea').value = '';
        }
    });

    // Submit reply
    document.getElementById('blog-comments').addEventListener('submit', function (e) {
        var form = e.target.closest('.blog-reply-form');
        if (!form) return;
        e.preventDefault();

        var commentId = form.id.replace('reply-form-', '');
        var textarea = form.querySelector('textarea');
        var submitBtn = form.querySelector('button[type="submit"]');
        var body = textarea.value.trim();
        if (!body) return;

        submitBtn.disabled = true;
        submitBtn.textContent = 'Posting...';

        var formData = new FormData();
        formData.append('body', body);
        formData.append('parent_id', commentId);

        fetch('/blog/post/' + postId + '/comments', { method: 'POST', body: formData })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    var c = data.comment;
                    var repliesEl = document.getElementById('replies-' + commentId);
                    if (repliesEl) {
                        var div = document.createElement('div');
                        div.className = 'blog-comment blog-comment--reply';
                        div.id = 'comment-' + c.id;
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
                submitBtn.disabled = false;
                submitBtn.textContent = 'Post Reply';
            })
            .catch(function () {
                submitBtn.disabled = false;
                submitBtn.textContent = 'Post Reply';
            });
    });

    // Post top-level comment
    var commentForm = document.getElementById('comment-form');
    if (commentForm) {
        commentForm.addEventListener('submit', function (e) {
            e.preventDefault();
            var body = commentForm.querySelector('textarea[name="body"]');
            var btn = commentForm.querySelector('button[type="submit"]');
            var formData = new FormData();
            formData.append('body', body.value.trim());

            btn.disabled = true;
            btn.textContent = 'Posting...';

            fetch('/blog/post/' + postId + '/comments', { method: 'POST', body: formData })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.success) {
                        var c = data.comment;
                        var noComments = document.querySelector('.blog-no-comments');
                        if (noComments) noComments.remove();

                        var div = document.createElement('div');
                        div.className = 'blog-comment';
                        div.id = 'comment-' + c.id;
                        div.innerHTML =
                            '<div class="blog-comment-meta">' +
                            '<div class="blog-comment-avatar">' + c.avatar_letter + '</div>' +
                            '<div class="blog-comment-author-info">' +
                            '<span class="blog-comment-author-name">' + c.author + '</span>' +
                            '<span class="blog-comment-date">' + c.created_at + '</span>' +
                            '</div></div>' +
                            '<p class="blog-comment-body">' + c.body + '</p>' +
                            '<button class="blog-reply-btn" data-comment-id="' + c.id + '">Reply</button>' +
                            '<form class="blog-reply-form" id="reply-form-' + c.id + '" style="display:none;">' +
                            '<div class="form-group"><textarea name="body" class="form-input" rows="2" placeholder="Write a reply..."></textarea></div>' +
                            '<div class="blog-reply-actions">' +
                            '<button type="submit" class="btn btn-primary btn-sm">Post Reply</button>' +
                            '<button type="button" class="btn btn-secondary btn-sm blog-reply-cancel">Cancel</button>' +
                            '</div></form>' +
                            '<div class="blog-replies" id="replies-' + c.id + '"></div>';

                        document.getElementById('comments-list').appendChild(div);
                        body.value = '';
                    }
                    btn.disabled = false;
                    btn.textContent = 'Post Comment';
                })
                .catch(function () {
                    btn.disabled = false;
                    btn.textContent = 'Post Comment';
                });
        });
    }
}

// ── Editor ───────────────────────────────────────────
(function () {
    var sectionsContainer = document.getElementById('sections-container');
    if (!sectionsContainer) return;

    var sections = [];

    try {
        var raw = typeof EDIT_POST_DATA === 'string' ? JSON.parse(EDIT_POST_DATA) : EDIT_POST_DATA;
        sections = Array.isArray(raw) ? raw : [];
    } catch (e) { sections = []; }

    // Auto-resize a textarea to fit its content
    function autoResize(el) {
        el.style.height = 'auto';
        el.style.height = el.scrollHeight + 'px';
    }

    function applyAutoResize() {
        sectionsContainer.querySelectorAll('.block-input').forEach(function (el) {
            autoResize(el);
        });
    }

    // ── Render ──────────────────────────────────────
    function render() {
        sectionsContainer.innerHTML = '';
        sections.forEach(function (section, si) {
            var div = document.createElement('div');
            div.className = 'blog-editor-section';
            div.dataset.index = si;

            var blocksHtml = section.blocks.map(function (block, bi) {
                return renderBlock(block, si, bi);
            }).join('');

            div.innerHTML =
                '<div class="blog-editor-section-header">' +
                '<span class="blog-editor-section-num">' + section.number + '</span>' +
                '<input type="text" value="' + escAttr(section.title) + '" ' +
                'placeholder="Section title" data-si="' + si + '" class="section-title-input">' +
                '<button class="blog-block-btn blog-block-btn--danger section-delete-btn" data-si="' + si + '">✕</button>' +
                '</div>' +
                '<div class="blog-editor-section-body" id="section-body-' + si + '">' +
                blocksHtml +
                '</div>' +
                '<div class="blog-section-actions">' +
                '<button class="blog-block-btn add-block-btn" data-si="' + si + '">+ Add Block</button>' +
                (si > 0 ? '<button class="blog-block-btn section-up-btn" data-si="' + si + '">↑ Move Up</button>' : '') +
                (si < sections.length - 1 ? '<button class="blog-block-btn section-down-btn" data-si="' + si + '">↓ Move Down</button>' : '') +
                '</div>';

            sectionsContainer.appendChild(div);
        });

        applyAutoResize();
    }

    function renderBlock(block, si, bi) {
        var label = { body: 'Paragraph', callout: 'Callout', 'callout-pine': 'Callout (green)', h3: 'Sub-heading', list: 'List', image: 'Image', video: 'Video' }[block.type] || block.type;
        var inputHtml = '';

        if (block.type === 'list') {
            inputHtml = '<textarea rows="4" data-si="' + si + '" data-bi="' + bi + '" ' +
                'class="block-input" placeholder="One item per line">' +
                escText((block.items || []).join('\n')) + '</textarea>';
        } else if (block.type === 'image' || block.type === 'video') {
            var isVideo = block.type === 'video';
            var previewHtml = block.url
                ? (isVideo
                    ? '<video src="' + escAttr(block.url) + '" controls></video>'
                    : '<img src="' + escAttr(block.url) + '" alt="">')
                : '';
            inputHtml =
                '<div class="blog-media-block" data-si="' + si + '" data-bi="' + bi + '">' +
                '<div class="blog-media-preview">' + previewHtml + '</div>' +
                '<input type="file" class="blog-media-file-input hidden" accept="' +
                (isVideo ? '.mp4,.webm' : '.png,.jpg,.jpeg,.gif,.webp') + '">' +
                '<button type="button" class="blog-block-btn blog-media-upload-btn">' +
                (block.url ? 'Replace ' : 'Upload ') + label + '</button>' +
                '<input type="text" data-si="' + si + '" data-bi="' + bi + '" ' +
                'class="block-input blog-media-caption" placeholder="Caption (optional)" ' +
                'value="' + escAttr(block.text || '') + '">' +
                '</div>';
        } else {
            inputHtml = '<textarea rows="3" data-si="' + si + '" data-bi="' + bi + '" ' +
                'class="block-input" placeholder="' + label + '...">' +
                escText(block.text || '') + '</textarea>';
        }

        return '<div class="blog-editor-block" data-si="' + si + '" data-bi="' + bi + '">' +
            '<div class="blog-editor-block-type">' + label + '</div>' +
            inputHtml +
            '<div class="blog-editor-block-actions">' +
            (bi > 0 ? '<button class="blog-block-btn block-up-btn" data-si="' + si + '" data-bi="' + bi + '">↑</button>' : '') +
            (bi < sections[si].blocks.length - 1 ? '<button class="blog-block-btn block-down-btn" data-si="' + si + '" data-bi="' + bi + '">↓</button>' : '') +
            '<button class="blog-block-btn blog-block-btn--danger block-delete-btn" data-si="' + si + '" data-bi="' + bi + '">Remove</button>' +
            '</div>' +
            '</div>';
    }

    // ── Block type picker ────────────────────────────
    var menu = document.getElementById('block-type-menu');
    var activeSi = null;

    sectionsContainer.addEventListener('click', function (e) {
        var addBtn = e.target.closest('.add-block-btn');
        if (addBtn) {
            activeSi = parseInt(addBtn.dataset.si);
            var rect = addBtn.getBoundingClientRect();
            menu.style.top = (rect.bottom + 6) + 'px';
            menu.style.left = rect.left + 'px';
            menu.style.display = 'flex';
            return;
        }

        var delSec = e.target.closest('.section-delete-btn');
        if (delSec) {
            if (!confirm('Remove this section?')) return;
            sections.splice(parseInt(delSec.dataset.si), 1);
            renumber();
            render();
            return;
        }

        var upSec = e.target.closest('.section-up-btn');
        if (upSec) {
            var i = parseInt(upSec.dataset.si);
            var tmp = sections[i]; sections[i] = sections[i - 1]; sections[i - 1] = tmp;
            render(); return;
        }

        var downSec = e.target.closest('.section-down-btn');
        if (downSec) {
            var i = parseInt(downSec.dataset.si);
            var tmp = sections[i]; sections[i] = sections[i + 1]; sections[i + 1] = tmp;
            render(); return;
        }

        var delBlock = e.target.closest('.block-delete-btn');
        if (delBlock) {
            var si = parseInt(delBlock.dataset.si), bi = parseInt(delBlock.dataset.bi);
            sections[si].blocks.splice(bi, 1);
            render(); return;
        }

        var upBlock = e.target.closest('.block-up-btn');
        if (upBlock) {
            var si = parseInt(upBlock.dataset.si), bi = parseInt(upBlock.dataset.bi);
            var tmp = sections[si].blocks[bi]; sections[si].blocks[bi] = sections[si].blocks[bi - 1]; sections[si].blocks[bi - 1] = tmp;
            render(); return;
        }

        var downBlock = e.target.closest('.block-down-btn');
        if (downBlock) {
            var si = parseInt(downBlock.dataset.si), bi = parseInt(downBlock.dataset.bi);
            var tmp = sections[si].blocks[bi]; sections[si].blocks[bi] = sections[si].blocks[bi + 1]; sections[si].blocks[bi + 1] = tmp;
            render(); return;
        }

        var mediaUploadBtn = e.target.closest('.blog-media-upload-btn');
        if (mediaUploadBtn) {
            mediaUploadBtn.closest('.blog-media-block').querySelector('.blog-media-file-input').click();
            return;
        }
    });

    // ── Media upload (image/video blocks) ────────────
    sectionsContainer.addEventListener('change', function (e) {
        if (!e.target.classList.contains('blog-media-file-input')) return;
        var file = e.target.files[0];
        if (!file) return;

        var block = e.target.closest('.blog-media-block');
        var si = parseInt(block.dataset.si), bi = parseInt(block.dataset.bi);
        var btn = block.querySelector('.blog-media-upload-btn');
        var originalLabel = btn.textContent;
        btn.textContent = 'Uploading…';
        btn.disabled = true;

        var fd = new FormData();
        fd.append('file', file);
        fetch('/blog/upload-media', { method: 'POST', body: fd })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    sections[si].blocks[bi].url = data.url;
                    render();
                } else {
                    showToast(data.error || 'Upload failed', 'error');
                    btn.textContent = originalLabel;
                    btn.disabled = false;
                }
            })
            .catch(function () {
                showToast('Upload failed', 'error');
                btn.textContent = originalLabel;
                btn.disabled = false;
            });
    });

    menu.addEventListener('click', function (e) {
        var btn = e.target.closest('button');
        if (!btn || activeSi === null) return;
        var type = btn.dataset.type;
        var block;
        if (type === 'list') {
            block = { type: 'list', items: [] };
        } else if (type === 'image' || type === 'video') {
            block = { type: type, url: '', text: '' };
        } else {
            block = { type: type.replace('-pine', ''), text: '', color: type === 'callout-pine' ? 'pine' : undefined };
            if (type === 'callout-pine') block.type = 'callout';
        }
        sections[activeSi].blocks.push(block);
        menu.style.display = 'none';
        activeSi = null;
        render();
    });

    document.addEventListener('click', function (e) {
        if (!menu.contains(e.target) && !e.target.closest('.add-block-btn')) {
            menu.style.display = 'none';
        }
    });

    // ── Live sync + auto-resize on input ────────────
    sectionsContainer.addEventListener('input', function (e) {
        if (e.target.classList.contains('section-title-input')) {
            var si = parseInt(e.target.dataset.si);
            sections[si].title = e.target.value;
            sections[si].anchor = e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
        }
        if (e.target.classList.contains('block-input')) {
            var si = parseInt(e.target.dataset.si), bi = parseInt(e.target.dataset.bi);
            if (sections[si].blocks[bi].type === 'list') {
                sections[si].blocks[bi].items = e.target.value.split('\n').filter(function (l) { return l.trim(); });
            } else {
                sections[si].blocks[bi].text = e.target.value;
            }
            autoResize(e.target);
        }
    });

    // ── Add section ──────────────────────────────────
    document.getElementById('add-section-btn').addEventListener('click', function () {
        sections.push({ anchor: 'section-' + (sections.length + 1), number: '', title: '', blocks: [] });
        renumber();
        render();
        sectionsContainer.lastElementChild.querySelector('.section-title-input').focus();
    });

    function renumber() {
        sections.forEach(function (s, i) {
            s.number = String(i + 1).padStart(2, '0');
        });
    }

    // ── Collect & save ───────────────────────────────
    function collectData() {
        var sendEmailEl = document.getElementById('send-email-toggle');
        return {
            title: document.getElementById('post-title').value.trim(),
            version_tag: document.getElementById('post-version-tag').value.trim(),
            sections: sections,
            send_email: sendEmailEl ? sendEmailEl.checked : false
        };
    }

    function save(andPublish) {
        var data = collectData();
        if (!data.title) { alert('Please add a post title.'); return; }

        var isEdit = typeof EDIT_POST_ID === 'number';
        var url = isEdit ? '/blog/posts/' + EDIT_POST_ID : '/blog/posts';
        var method = isEdit ? 'PUT' : 'POST';

        fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        })
            .then(function (r) { return r.json(); })
            .then(function (res) {
                if (!res.success) { showToast('Save failed.', 'error'); return; }
                var postId = isEdit ? EDIT_POST_ID : res.post_id;
                if (andPublish) {
                    fetch('/blog/posts/' + postId + '/publish', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ send_email: data.send_email })
                    })
                        .then(function (r) { return r.json(); })
                        .then(function () { window.location.href = '/blog#post-' + postId; })
                        .catch(function () { showToast('Post saved but could not publish. Try again.', 'error'); });
                } else {
                    window.location.href = '/blog#post-' + postId;
                }
            })
            .catch(function () { showToast('Could not save post. Check your connection.', 'error'); });
    }

    document.getElementById('save-draft-btn').addEventListener('click', function () { save(false); });
    document.getElementById('save-publish-btn').addEventListener('click', function () { save(true); });

    // ── Helpers ──────────────────────────────────────
    function escAttr(str) {
        return String(str || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
    }
    function escText(str) {
        return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;');
    }

    renumber();
    render();
}());