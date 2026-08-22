// app/static/js/project_chat_panel.js
// Persistent chat drawer controller — messages, replies, pins, attachments,
// reactions, emoji picker, and @-mentions. Wires #project-overlay-chat-content.

window.ProjectChatPanel = (function () {

    function init(contentEl, projectId) {

        // Lives outside wire()/reload() so a refresh doesn't drop it.
        var replyState = null; // { noteId, author, text } | null

        // blob is the upload payload (client-compressed for images); previewUrl
        // is an object URL for the preview bar, revoked when replaced/cleared.
        var stagedAttachment = null; // { blob, filename, type, previewUrl } | null

        // mentionableUsers: this project's roster, fetched once per drawer-open.
        // mentionQuery: the in-progress "@word" being typed.
        var mentionableUsers = []; // [{id, name}]
        var mentionedUsers = [];   // [{id, name}]
        var mentionQuery = null;   // { start, query } | null

        var CHAT_VIDEO_MAX_BYTES = 16 * 1024 * 1024;
        var CHAT_VIDEO_EXTENSIONS = ['mp4', 'mov', 'webm', 'm4v'];
        var CHAT_IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif', 'webp'];

        function postJson(url, body) {
            return fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body || {}),
            }).then((res) => res.json().then((data) => ({ ok: res.ok, data })));
        }

        function escapeHtml(str) {
            const div = document.createElement('div');
            div.textContent = str == null ? '' : String(str);
            return div.innerHTML;
        }

        function fetchMentionableUsers() {
            fetch(`/projects/${projectId}/overlay/chat/mentionable`)
                .then((res) => res.json())
                .then((data) => { if (data && data.users) mentionableUsers = data.users; })
                .catch(() => {});
        }

        function scrollToBottom() {
            const thread = contentEl.querySelector('#overlay-chat-thread');
            if (thread) thread.scrollTop = thread.scrollHeight;
        }

        // Clones the bubble text and strips the floated timestamp span, so
        // Copy/Reply get the message text alone. Falls back to a Photo/Video
        // placeholder for a caption-less attachment.
        function getMessageText(messageEl) {
            const textEl = messageEl.querySelector('.overlay-chat-bubble-text');
            if (textEl) {
                const clone = textEl.cloneNode(true);
                const ts = clone.querySelector('.overlay-chat-timestamp');
                if (ts) ts.remove();
                const text = clone.textContent.trim();
                if (text) return text;
            }
            if (messageEl.querySelector('.overlay-chat-attachment-image')) return '📷 Photo';
            if (messageEl.querySelector('.overlay-chat-attachment-video')) return '🎥 Video';
            return '';
        }

        function closeAllPopups() {
            contentEl.querySelectorAll('.overlay-chat-menu').forEach((el) => el.classList.add('hidden'));
            contentEl.querySelectorAll('.overlay-chat-react-popover').forEach((el) => el.classList.add('hidden'));
            contentEl.querySelectorAll('.overlay-chat-pinned-menu').forEach((el) => el.classList.add('hidden'));
            contentEl.querySelectorAll('.overlay-chat-emoji-picker').forEach((el) => el.classList.add('hidden'));
            contentEl.querySelectorAll('.overlay-chat-mention-picker').forEach((el) => el.classList.add('hidden'));
        }

        // Server enforces one pin per project — a new pin replaces the old one.
        function togglePin(noteId) {
            postJson(`/projects/${projectId}/overlay/notes/${noteId}/pin`, {}).then(({ ok, data }) => {
                if (!ok || !data.success) {
                    if (window.showToast) window.showToast((data && data.error) || 'Could not update pin.', 'error');
                    return;
                }
                reload();
            });
        }

        // Shared by the quick-react popover and reaction chips; re-picking removes it.
        function toggleReaction(noteId, emoji) {
            postJson(`/projects/notes/${noteId}/react`, { emoji: emoji }).then(({ ok, data }) => {
                if (!ok || !data.success) {
                    if (window.showToast) window.showToast((data && data.error) || 'Could not update reaction.', 'error');
                    return;
                }
                reload();
            });
        }

        function renderReplyPreview() {
            const bar = contentEl.querySelector('#overlay-chat-reply-preview');
            if (!bar) return;
            if (!replyState) {
                bar.classList.add('hidden');
                return;
            }
            const authorEl = contentEl.querySelector('#overlay-chat-reply-preview-author');
            const textEl = contentEl.querySelector('#overlay-chat-reply-preview-text');
            if (authorEl) authorEl.textContent = replyState.author;
            if (textEl) textEl.textContent = replyState.text;
            bar.classList.remove('hidden');
        }

        function setReply(noteId, author, text) {
            replyState = { noteId: noteId, author: author, text: text };
            renderReplyPreview();
            const input = contentEl.querySelector('#overlay-chat-input');
            if (input) input.focus();
        }

        function clearReply() {
            replyState = null;
            renderReplyPreview();
        }

        // Checks the text before the cursor for an in-progress "@word" and
        // re-filters mentionableUsers by it.
        function updateMentionPicker() {
            const input = contentEl.querySelector('#overlay-chat-input');
            const picker = contentEl.querySelector('#overlay-chat-mention-picker');
            if (!input || !picker) return;
            const cursor = input.selectionStart != null ? input.selectionStart : input.value.length;
            const uptoCursor = input.value.slice(0, cursor);
            const match = uptoCursor.match(/(?:^|\s)@([^\s@]*)$/);
            if (!match) {
                mentionQuery = null;
                picker.classList.add('hidden');
                return;
            }
            const query = match[1];
            mentionQuery = { start: cursor - query.length - 1, query: query };
            const filtered = mentionableUsers.filter((u) =>
                u.name.toLowerCase().indexOf(query.toLowerCase()) !== -1
            );
            if (!filtered.length) {
                picker.classList.add('hidden');
                return;
            }
            picker.innerHTML = filtered.map((u) =>
                `<button type="button" class="overlay-chat-mention-option" data-user-id="${u.id}" data-user-name="${escapeHtml(u.name)}">${escapeHtml(u.name)}</button>`
            ).join('');
            picker.classList.remove('hidden');
        }

        // Replaces the in-progress "@word" with "@Name " and records the pick.
        function insertMention(userId, name) {
            const input = contentEl.querySelector('#overlay-chat-input');
            const picker = contentEl.querySelector('#overlay-chat-mention-picker');
            if (!input || !mentionQuery) return;
            const cursor = input.selectionStart != null ? input.selectionStart : input.value.length;
            const before = input.value.slice(0, mentionQuery.start);
            const after = input.value.slice(cursor);
            const insertText = `@${name} `;
            input.value = before + insertText + after;
            const newCursor = before.length + insertText.length;
            input.selectionStart = input.selectionEnd = newCursor;
            input.focus();
            input.style.height = 'auto';
            input.style.height = input.scrollHeight + 'px';
            if (picker) picker.classList.add('hidden');
            mentionQuery = null;
            if (!mentionedUsers.some((u) => u.id === userId)) mentionedUsers.push({ id: userId, name: name });
        }

        function extOf(filename) {
            var parts = String(filename || '').split('.');
            return parts.length > 1 ? parts.pop().toLowerCase() : '';
        }

        // Resizes to a 1600px longest edge and re-encodes as JPEG.
        // GIFs skip this entirely (see handleFileSelected) — re-encoding flattens animation.
        function compressImage(file) {
            return new Promise((resolve, reject) => {
                const img = new Image();
                const objectUrl = URL.createObjectURL(file);
                img.onload = () => {
                    URL.revokeObjectURL(objectUrl);
                    const MAX_DIM = 1600;
                    let width = img.naturalWidth, height = img.naturalHeight;
                    if (width > MAX_DIM || height > MAX_DIM) {
                        if (width > height) {
                            height = Math.round(height * (MAX_DIM / width));
                            width = MAX_DIM;
                        } else {
                            width = Math.round(width * (MAX_DIM / height));
                            height = MAX_DIM;
                        }
                    }
                    const canvas = document.createElement('canvas');
                    canvas.width = width;
                    canvas.height = height;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0, width, height);
                    canvas.toBlob((blob) => {
                        if (blob) resolve(blob); else reject(new Error('canvas.toBlob returned null'));
                    }, 'image/jpeg', 0.82);
                };
                img.onerror = () => { URL.revokeObjectURL(objectUrl); reject(new Error('Could not load image')); };
                img.src = objectUrl;
            });
        }

        function renderStagedAttachment() {
            const bar = contentEl.querySelector('#overlay-chat-staged-attachment');
            if (!bar) return;
            if (!stagedAttachment) {
                bar.classList.add('hidden');
                return;
            }
            const previewEl = contentEl.querySelector('#overlay-chat-staged-attachment-preview');
            const nameEl = contentEl.querySelector('#overlay-chat-staged-attachment-name');
            if (previewEl) {
                previewEl.innerHTML = '';
                if (stagedAttachment.type === 'image') {
                    const img = document.createElement('img');
                    img.src = stagedAttachment.previewUrl;
                    previewEl.appendChild(img);
                } else {
                    previewEl.textContent = '🎥';
                }
            }
            if (nameEl) nameEl.textContent = stagedAttachment.filename;
            bar.classList.remove('hidden');
        }

        function stageAttachment(blob, filename, type) {
            if (stagedAttachment && stagedAttachment.previewUrl) URL.revokeObjectURL(stagedAttachment.previewUrl);
            stagedAttachment = { blob: blob, filename: filename, type: type, previewUrl: URL.createObjectURL(blob) };
            renderStagedAttachment();
        }

        function clearStagedAttachment() {
            if (stagedAttachment && stagedAttachment.previewUrl) URL.revokeObjectURL(stagedAttachment.previewUrl);
            stagedAttachment = null;
            renderStagedAttachment();
            const fileInput = contentEl.querySelector('#overlay-chat-file-input');
            if (fileInput) fileInput.value = '';
        }

        function handleFileSelected(file) {
            const ext = extOf(file.name);
            const errorEl = contentEl.querySelector('#overlay-chat-error');
            if (errorEl) errorEl.classList.add('hidden');

            if (CHAT_VIDEO_EXTENSIONS.indexOf(ext) !== -1) {
                if (file.size > CHAT_VIDEO_MAX_BYTES) {
                    if (window.showToast) window.showToast('Video is too large (max 16MB).', 'error');
                    return;
                }
                stageAttachment(file, file.name, 'video');
                return;
            }

            if (CHAT_IMAGE_EXTENSIONS.indexOf(ext) !== -1) {
                if (ext === 'gif') {
                    stageAttachment(file, file.name, 'image');
                    return;
                }
                compressImage(file).then((blob) => {
                    const compressedName = file.name.replace(/\.[^.]+$/, '') + '.jpg';
                    stageAttachment(blob, compressedName, 'image');
                }).catch(() => {
                    // Compression failed — fall back to the original; server still caps size.
                    stageAttachment(file, file.name, 'image');
                });
                return;
            }

            if (window.showToast) window.showToast('That file type is not supported here.', 'error');
        }

        function isNearBottom(thread) {
            if (!thread) return true;
            return thread.scrollHeight - thread.scrollTop - thread.clientHeight < 80;
        }

        // Full-fragment refetch on every send/delete/pin/live update. {live: true}
        // (someone else's action) preserves your draft and only auto-scrolls if
        // you were already near the bottom.
        function reload(afterReload, opts) {
            var isLive = !!(opts && opts.live);
            var threadBefore = contentEl.querySelector('#overlay-chat-thread');
            var wasNearBottom = isNearBottom(threadBefore);
            var inputBefore = contentEl.querySelector('#overlay-chat-input');
            var draftText = (isLive && inputBefore) ? inputBefore.value : '';

            return fetch(`/projects/${projectId}/overlay/chat`)
                .then((res) => res.text())
                .then((html) => {
                    contentEl.innerHTML = html;
                    wire();
                    renderReplyPreview();
                    renderStagedAttachment();
                    if (draftText) {
                        const freshInput = contentEl.querySelector('#overlay-chat-input');
                        if (freshInput) {
                            freshInput.value = draftText;
                            freshInput.style.height = 'auto';
                            freshInput.style.height = freshInput.scrollHeight + 'px';
                        }
                    }
                    if (!isLive || wasNearBottom) scrollToBottom();
                    if (afterReload) afterReload();
                });
        }

        function sendMessage() {
            const input = contentEl.querySelector('#overlay-chat-input');
            const sendBtn = contentEl.querySelector('#overlay-chat-send-btn');
            const errorEl = contentEl.querySelector('#overlay-chat-error');
            const body = input ? input.value.trim() : '';
            if (!body && !stagedAttachment) return;

            if (sendBtn) sendBtn.disabled = true;
            if (errorEl) errorEl.classList.add('hidden');

            // Only send mentions whose "@Name" text is still actually in the message.
            const activeMentionIds = mentionedUsers
                .filter((u) => body.indexOf(`@${u.name}`) !== -1)
                .map((u) => u.id);

            // Attachment present — post multipart/form-data instead of JSON.
            // No Content-Type header — the browser sets the multipart boundary itself.
            let request;
            if (stagedAttachment) {
                const formData = new FormData();
                formData.append('body', body);
                if (replyState) formData.append('reply_to_id', replyState.noteId);
                // FormData can't carry a real array — JSON-encode it instead.
                if (activeMentionIds.length) formData.append('mentioned_ids', JSON.stringify(activeMentionIds));
                formData.append('file', stagedAttachment.blob, stagedAttachment.filename);
                request = fetch(`/projects/${projectId}/overlay/notes/create`, { method: 'POST', body: formData })
                    .then((res) => res.json().then((data) => ({ ok: res.ok, data })));
            } else {
                const payload = { body: body };
                if (replyState) payload.reply_to_id = replyState.noteId;
                if (activeMentionIds.length) payload.mentioned_ids = activeMentionIds;
                request = postJson(`/projects/${projectId}/overlay/notes/create`, payload);
            }

            request.then(({ ok, data }) => {
                if (sendBtn) sendBtn.disabled = false;
                if (!ok || !data.success) {
                    if (errorEl) { errorEl.textContent = (data && data.error) || 'Could not send this message.'; errorEl.classList.remove('hidden'); }
                    return;
                }
                clearReply();
                clearStagedAttachment();
                mentionedUsers = [];
                reload(() => {
                    const freshInput = contentEl.querySelector('#overlay-chat-input');
                    if (freshInput) freshInput.focus();
                });
            });
        }

        function jumpToMessage(noteId) {
            const target = contentEl.querySelector(`.overlay-chat-message[data-note-id="${noteId}"]`);
            if (!target) return;
            target.scrollIntoView({ behavior: 'smooth', block: 'center' });
            target.classList.add('overlay-chat-message--flash');
            setTimeout(() => target.classList.remove('overlay-chat-message--flash'), 1600);
        }

        function handleMenuAction(action, noteId, messageEl) {
            closeAllPopups();
            if (action === 'copy') {
                const text = getMessageText(messageEl);
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(text).then(() => {
                        if (window.showToast) window.showToast('Message copied', 'success');
                    }).catch(() => {
                        if (window.showToast) window.showToast('Could not copy message.', 'error');
                    });
                }
                return;
            }
            if (action === 'reply') {
                const authorEl = messageEl.querySelector('.overlay-chat-author');
                const author = messageEl.classList.contains('overlay-chat-message--own')
                    ? 'You' : (authorEl ? authorEl.textContent : '');
                setReply(noteId, author, getMessageText(messageEl));
                return;
            }
            if (action === 'react') {
                const popover = messageEl.querySelector('.overlay-chat-react-popover');
                if (popover) popover.classList.remove('hidden');
                return;
            }
            if (action === 'pin') {
                togglePin(noteId);
                return;
            }
            if (action === 'delete') {
                window.showConfirm('Delete this message?', () => {
                    postJson(`/projects/${projectId}/overlay/notes/${noteId}/delete`, {}).then(({ ok, data }) => {
                        if (!ok || !data.success) {
                            if (window.showToast) window.showToast((data && data.error) || 'Could not delete this message.', 'error');
                            return;
                        }
                        reload();
                    });
                });
            }
        }

        function wire() {
            const sendBtn = contentEl.querySelector('#overlay-chat-send-btn');
            const input = contentEl.querySelector('#overlay-chat-input');

            if (sendBtn) sendBtn.addEventListener('click', sendMessage);

            if (input) {
                // Enter sends, Shift+Enter inserts a newline.
                input.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        sendMessage();
                    }
                });
                // Auto-grow with typed content up to the CSS max-height.
                input.addEventListener('input', () => {
                    input.style.height = 'auto';
                    input.style.height = input.scrollHeight + 'px';
                    updateMentionPicker();
                });
                // Not 'click' too — that bubbles to contentEl's closeAllPopups and would re-hide it.
                input.addEventListener('keyup', updateMentionPicker);
            }

            const replyClose = contentEl.querySelector('#overlay-chat-reply-preview-close');
            if (replyClose) replyClose.addEventListener('click', clearReply);

            const attachBtn = contentEl.querySelector('#overlay-chat-attach-btn');
            const fileInput = contentEl.querySelector('#overlay-chat-file-input');
            if (attachBtn && fileInput) {
                attachBtn.addEventListener('click', () => fileInput.click());
                fileInput.addEventListener('change', () => {
                    if (fileInput.files && fileInput.files[0]) handleFileSelected(fileInput.files[0]);
                });
            }

            const stagedRemoveBtn = contentEl.querySelector('#overlay-chat-staged-attachment-remove');
            if (stagedRemoveBtn) stagedRemoveBtn.addEventListener('click', clearStagedAttachment);

            contentEl.querySelectorAll('.overlay-chat-pinned-item').forEach((item) => {
                item.addEventListener('click', () => jumpToMessage(item.getAttribute('data-jump-to')));
            });

            // Opens a one-item Unpin menu; stopPropagation avoids the click-to-jump listener above.
            contentEl.querySelectorAll('.overlay-chat-pinned-menu-btn').forEach((btn) => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const menu = btn.nextElementSibling;
                    const willOpen = menu && menu.classList.contains('hidden');
                    closeAllPopups();
                    if (willOpen) menu.classList.remove('hidden');
                });
            });

            contentEl.querySelectorAll('.overlay-chat-pinned-menu .overlay-chat-menu-item').forEach((btn) => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    closeAllPopups();
                    togglePin(btn.getAttribute('data-note-id'));
                });
            });

            // Hover toolbar: smiley opens the quick-react popover, chevron opens the dropdown.
            contentEl.querySelectorAll('.overlay-chat-react-btn').forEach((btn) => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const messageEl = btn.closest('.overlay-chat-message');
                    const popover = messageEl ? messageEl.querySelector('.overlay-chat-react-popover') : null;
                    const willOpen = popover && popover.classList.contains('hidden');
                    closeAllPopups();
                    if (willOpen) popover.classList.remove('hidden');
                });
            });

            contentEl.querySelectorAll('.overlay-chat-menu-btn').forEach((btn) => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const messageEl = btn.closest('.overlay-chat-message');
                    const menu = messageEl ? messageEl.querySelector('.overlay-chat-menu') : null;
                    const willOpen = menu && menu.classList.contains('hidden');
                    closeAllPopups();
                    if (willOpen) menu.classList.remove('hidden');
                });
            });

            contentEl.querySelectorAll('.overlay-chat-menu-item').forEach((btn) => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const noteId = btn.getAttribute('data-note-id');
                    const action = btn.getAttribute('data-action');
                    const messageEl = btn.closest('.overlay-chat-message');
                    if (messageEl) handleMenuAction(action, noteId, messageEl);
                });
            });

            // Quick-react emoji buttons — post the reaction and reload.
            contentEl.querySelectorAll('.overlay-chat-react-option').forEach((btn) => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    closeAllPopups();
                    toggleReaction(btn.getAttribute('data-note-id'), btn.getAttribute('data-emoji'));
                });
            });

            // Reaction chips — clicking one toggles your own reaction with that emoji.
            contentEl.querySelectorAll('button.overlay-chat-reaction-chip').forEach((chip) => {
                chip.addEventListener('click', (e) => {
                    e.stopPropagation();
                    closeAllPopups();
                    toggleReaction(chip.getAttribute('data-note-id'), chip.getAttribute('data-emoji'));
                });
            });

            // Composer emoji picker trigger.
            const emojiTrigger = contentEl.querySelector('#overlay-chat-emoji-trigger');
            const emojiPicker = contentEl.querySelector('#overlay-chat-emoji-picker');
            if (emojiTrigger && emojiPicker) {
                emojiTrigger.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const willOpen = emojiPicker.classList.contains('hidden');
                    closeAllPopups();
                    if (willOpen) emojiPicker.classList.remove('hidden');
                });
                // Stop clicks inside from bubbling to the outside-click listener below.
                emojiPicker.addEventListener('click', (e) => e.stopPropagation());
            }

            // Category tabs just scroll the grid to that section.
            contentEl.querySelectorAll('.overlay-chat-emoji-tab').forEach((tab) => {
                tab.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const targetId = tab.getAttribute('data-target');
                    const section = targetId ? contentEl.querySelector(`#${targetId}`) : null;
                    if (section) section.scrollIntoView({ block: 'start' });
                });
            });

            // Inserts the emoji at the cursor and leaves the picker open for multi-select.
            contentEl.querySelectorAll('.overlay-chat-emoji-option').forEach((btn) => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const emoji = btn.getAttribute('data-emoji');
                    const input = contentEl.querySelector('#overlay-chat-input');
                    if (!input || !emoji) return;
                    const start = input.selectionStart != null ? input.selectionStart : input.value.length;
                    const end = input.selectionEnd != null ? input.selectionEnd : input.value.length;
                    input.value = input.value.slice(0, start) + emoji + input.value.slice(end);
                    const cursor = start + emoji.length;
                    input.selectionStart = input.selectionEnd = cursor;
                    input.focus();
                    // Re-trigger auto-grow — setting .value doesn't fire 'input' on its own.
                    input.style.height = 'auto';
                    input.style.height = input.scrollHeight + 'px';
                });
            });

            // @-mention picker — delegated listener since its contents rebuild every keystroke.
            const mentionPicker = contentEl.querySelector('#overlay-chat-mention-picker');
            if (mentionPicker) {
                mentionPicker.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const btn = e.target.closest('.overlay-chat-mention-option');
                    if (!btn) return;
                    insertMention(parseInt(btn.getAttribute('data-user-id'), 10), btn.getAttribute('data-user-name'));
                });
            }
        }

        // Outside-click closes any open dropdown/popover — added once, not in wire().
        contentEl.addEventListener('click', closeAllPopups);

        wire();
        scrollToBottom();
        // Composer only renders for can_manage_notes viewers — skip the fetch otherwise.
        if (contentEl.querySelector('#overlay-chat-input')) fetchMentionableUsers();

        return {
            // Nothing to tear down; contentEl is discarded when the overlay closes.
            destroy: function () { },
            // SSE hook — project_list.js calls this on a live update; {live: true}
            // preserves the draft and scroll position.
            liveRefresh: function () { return reload(null, { live: true }); }
        };
    }

    return { init: init };
})();
