// app/static/js/project_chat_panel.js
//
// Persistent chat drawer controller (M10 chat redesign) — the project-
// level chat thread that replaced the old Notes card. Lives in its own
// module rather than project_notes_card.js (which still owns the Site
// Visits form) because the drawer's lifecycle is independent of whichever
// rail tab happens to be showing underneath it: project_overlay.js opens/
// closes the drawer itself, project_list.js's loadChatDrawer() lazy-fetches
// this module's content on first open, and this module only ever wires
// whatever's inside #project-overlay-chat-content.
//
// Message-interactions adjustment (21 Aug 2026): hover a message to reveal
// a react-smiley + chevron. The chevron opens a Copy/Reply/React/Pin/
// Delete dropdown (Delete only rendered server-side when the 5-minute
// self-delete window still applies); the smiley jumps straight to the
// quick-react popover.
//
// Phase 3 — attachments (21 Aug 2026): the attach button stages one image
// or video before send (client-compressed for images, hard-capped at
// 16MB with no compression for video), shown in a preview bar above the
// composer until Send or the bar's own remove button clears it.
//
// Phase 4 — emoji picker + real reactions (21 Aug 2026): the quick-react
// popover's emoji buttons and a message's own reaction chips now both
// POST to the real reactions backend (toggleReaction()) instead of the
// earlier no-op provision. The composer also gets its own multi-category
// emoji picker (#overlay-chat-emoji-picker) — picking an emoji inserts it
// at the cursor and deliberately leaves the picker open for multi-select.
//
// Phase 5 — mentions (21 Aug 2026): typing "@" in the composer opens
// #overlay-chat-mention-picker, filtered from this project's roster
// (fetched once per drawer-open from /overlay/chat/mentionable — CS
// lead, secondary CS, project owner, assigned designers). Picking someone
// inserts "@Name " and queues them for a notification on send; sendMessage
// only actually includes a mention whose "@Name" text is still literally
// in the composer at send time (see its activeMentionIds filter).



window.ProjectChatPanel = (function () {

    function init(contentEl, projectId) {

        // Reply-in-progress state — lives outside wire()/reload() so it
        // survives a full-fragment refresh (e.g. a reload triggered by
        // someone else's message shouldn't silently drop what you were
        // replying to). Cleared explicitly on send or via the preview
        // bar's close button.
        var replyState = null; // { noteId, author, text } | null

        // Attachment-in-progress state (Phase 3, 21 Aug 2026) — same
        // lives-outside-wire()/reload() treatment as replyState, so a
        // live update arriving while you're mid-attach doesn't drop the
        // photo/video you already picked. blob is what actually gets
        // uploaded (for images, the CLIENT-COMPRESSED result, not the
        // original file — see compressImage()); previewUrl is an object
        // URL for the staged-attachment bar's thumbnail, revoked whenever
        // it's replaced or cleared so these don't leak across a long
        // session.
        var stagedAttachment = null; // { blob, filename, type, previewUrl } | null

        // @-mentions (Phase 5, 21 Aug 2026). mentionableUsers is this
        // project's roster — fetched once below, right after wire() runs
        // the first time, and reused for every "@" typed during this
        // drawer-open (doesn't change often enough mid-session to justify
        // re-fetching per keystroke). mentionedUsers accumulates whoever
        // was actually picked from the dropdown; sendMessage() re-checks
        // each one's "@Name" text is still literally present in the
        // composer before including it, so deleting a mention after
        // inserting it silently drops the notification too — no separate
        // "remove mention" affordance needed. mentionQuery tracks the
        // in-progress "@word" being typed (its start index in the
        // textarea's value, and the query text after the "@") so a picker
        // click knows exactly what substring to replace.
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
                .catch(() => { /* mention picker just won't find anyone — not fatal */ });
        }

        function scrollToBottom() {
            const thread = contentEl.querySelector('#overlay-chat-thread');
            if (thread) thread.scrollTop = thread.scrollHeight;
        }

        // Bubble text carries its timestamp as a floated child span (the
        // "time in the bottom-right corner of the bubble" CSS trick) — Copy
        // and Reply both need the message text alone, so this clones the
        // node and strips the timestamp before reading textContent rather
        // than duplicating the raw note body into a data-attribute.
        //
        // A caption-less attachment has no .overlay-chat-bubble-text at all
        // (see _overlay_chat.html) — falls back to the same placeholder
        // text ProjectNote.display_text() renders server-side for the
        // quote block, so Reply's live preview bar matches what actually
        // gets stored/rendered once the reply is sent.
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

        // Shared by the per-message dropdown's Pin/Unpin item and the
        // pinned strip's own chevron menu — the server enforces one pin
        // per project (a new pin silently replaces the old one), so this
        // is always just "toggle this note's flag and reload."
        function togglePin(noteId) {
            postJson(`/projects/${projectId}/overlay/notes/${noteId}/pin`, {}).then(({ ok, data }) => {
                if (!ok || !data.success) {
                    if (window.showToast) window.showToast((data && data.error) || 'Could not update pin.', 'error');
                    return;
                }
                reload();
            });
        }

        // Real reactions backend (Phase 4, 21 Aug 2026) — shared by the
        // quick-react popover's emoji buttons and a reaction chip's own
        // click (re-clicking a chip you already reacted with removes it,
        // same toggle semantics the server enforces via the unique
        // (note_id, user_id) constraint — see toggle_reaction()).
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

        // Re-checks the text immediately before the cursor for an
        // in-progress "@word" — matches only when the "@" is at the very
        // start of the composer or preceded by whitespace (so an email
        // address or "user@host" typed mid-sentence doesn't pop this
        // open), and re-filters mentionableUsers by that word. Called on
        // every keystroke/click/cursor-move in the textarea; cheap enough
        // (a handful of names, one regex) not to worry about debouncing.
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

        // Replaces the in-progress "@word" (tracked by mentionQuery) with
        // "@Name " and records the pick — deliberately does NOT close the
        // rest of the composer or clear replyState/stagedAttachment, this
        // is purely a text-insertion + bookkeeping step.
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

        // Client-side image compression (Ezekiel, 21 Aug 2026: "Images get
        // compressed") — resizes to a 1600px longest edge and re-encodes
        // as JPEG, same "hand-roll it with canvas" approach this codebase
        // already uses for avatars (Cropper.js), just without a cropping
        // UI here. GIFs are deliberately routed around this entirely (see
        // handleFileSelected) — canvas re-encoding flattens an animated
        // GIF to its first frame.
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
                    // Compression failed (corrupt file, browser quirk) —
                    // fall back to the original rather than blocking the
                    // send entirely; the server's own size cap still applies.
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

        // Full-fragment refetch on every send/delete/pin/SSE-triggered live
        // update — same tradeoff every other overlay section already makes
        // (project_notes_card.js's own reload()): the routes only hand back
        // ids/flags, not formatted bubble markup, so re-fetching the
        // rendered thread avoids duplicating that formatting (day labels,
        // Dubai-local times, own-vs-other bubble side, reply quotes, pinned
        // strip) in JS.
        //
        // {live: true} (SSE-triggered, someone ELSE's action) is gentler
        // than the plain reload send/delete/pin already use for your own
        // actions: it carries your in-progress draft text across the DOM
        // swap instead of silently discarding it, and only auto-scrolls to
        // the new bottom if you were already reading near the bottom —
        // scrolled up through history, an incoming message doesn't yank you
        // back down, same as WhatsApp/Slack.
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

            // Only send mentions whose "@Name" text is STILL actually in
            // the message — if it got deleted/edited out after picking it
            // from the dropdown, don't notify someone about a mention that
            // no longer exists in what's being sent (Phase 5, 21 Aug 2026).
            const activeMentionIds = mentionedUsers
                .filter((u) => body.indexOf(`@${u.name}`) !== -1)
                .map((u) => u.id);

            // Attachment present — post multipart/form-data instead of JSON
            // (matches the branch create_note() checks server-side: `if
            // upload and upload.filename` reads request.files, otherwise it
            // reads request.get_json()). No Content-Type header set here on
            // purpose — the browser fills in the multipart boundary itself;
            // setting it manually breaks the boundary and the upload.
            let request;
            if (stagedAttachment) {
                const formData = new FormData();
                formData.append('body', body);
                if (replyState) formData.append('reply_to_id', replyState.noteId);
                // FormData can't carry a real array — JSON-encode it, same
                // as create_note() already expects for this multipart path.
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
                // Enter sends, Shift+Enter inserts a newline — standard
                // chat-app convention (WhatsApp/Messenger/Slack all do this).
                input.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        sendMessage();
                    }
                });
                // Auto-grow with typed content up to the CSS max-height —
                // plain textarea resize, no library, same "hand-roll it"
                // call this codebase already made for the date-range picker.
                input.addEventListener('input', () => {
                    input.style.height = 'auto';
                    input.style.height = input.scrollHeight + 'px';
                    updateMentionPicker();
                });
                // keyup (not click) so arrow-key cursor movement within an
                // in-progress "@word" re-filters correctly — deliberately
                // NOT wired on 'click' too: a raw mouse click bubbles up to
                // contentEl's own click listener (closeAllPopups, since the
                // mention picker is in its hidden-list for consistency with
                // every other popover here), which would immediately hide
                // whatever this handler just showed. Typing is the primary
                // way this picker opens anyway.
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

            // Pinned strip's own chevron — opens a one-item Unpin menu.
            // Both handlers stopPropagation so they don't also trigger the
            // pinned-item's own click-to-jump listener above (the menu and
            // its button live nested inside that same element).
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

            // Hover toolbar: smiley opens the quick-react popover directly,
            // chevron opens the Copy/Reply/React/Pin/Delete dropdown — same
            // per-item open/close-on-outside-click convention as project_
            // list.js's saved-view "⋯" menu (stopPropagation on the toggle,
            // one document-level listener closes everything else).
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

            // Quick-react emoji buttons — real backend now (Phase 4, 21 Aug
            // 2026): posts the reaction and reloads. The provision from the
            // message-interactions pass just opened/closed this popover;
            // this is what actually makes a click count.
            contentEl.querySelectorAll('.overlay-chat-react-option').forEach((btn) => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    closeAllPopups();
                    toggleReaction(btn.getAttribute('data-note-id'), btn.getAttribute('data-emoji'));
                });
            });

            // Reaction chips under a bubble — clicking one toggles YOUR OWN
            // reaction with that emoji (not "add another"), same semantics
            // as picking it from the popover. Only rendered as a <button>
            // (vs. a read-only <span>) for people who can chat here — see
            // _overlay_chat.html.
            contentEl.querySelectorAll('button.overlay-chat-reaction-chip').forEach((chip) => {
                chip.addEventListener('click', (e) => {
                    e.stopPropagation();
                    closeAllPopups();
                    toggleReaction(chip.getAttribute('data-note-id'), chip.getAttribute('data-emoji'));
                });
            });

            // Composer emoji picker trigger — same open/close-on-outside-
            // click convention as every other popover in this file.
            const emojiTrigger = contentEl.querySelector('#overlay-chat-emoji-trigger');
            const emojiPicker = contentEl.querySelector('#overlay-chat-emoji-picker');
            if (emojiTrigger && emojiPicker) {
                emojiTrigger.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const willOpen = emojiPicker.classList.contains('hidden');
                    closeAllPopups();
                    if (willOpen) emojiPicker.classList.remove('hidden');
                });
                // Keep clicks inside the picker itself from bubbling to the
                // document-level outside-click listener below, which would
                // otherwise close the picker on every category-tab click.
                emojiPicker.addEventListener('click', (e) => e.stopPropagation());
            }

            // Category tabs just scroll the grid to that section — no
            // separate "active tab" state to track, same lightweight
            // approach as a simple in-page anchor jump.
            contentEl.querySelectorAll('.overlay-chat-emoji-tab').forEach((tab) => {
                tab.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const targetId = tab.getAttribute('data-target');
                    const section = targetId ? contentEl.querySelector(`#${targetId}`) : null;
                    if (section) section.scrollIntoView({ block: 'start' });
                });
            });

            // Picking an emoji inserts it into the composer at the cursor
            // and DELIBERATELY LEAVES THE PICKER OPEN — multi-select-
            // friendly (WhatsApp/Slack both keep the picker open across
            // consecutive picks), unlike the quick-react popover which
            // closes immediately because that's a one-shot per message.
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
                    // Re-trigger auto-grow (mirrors the plain typing 'input'
                    // handler above) since setting .value programmatically
                    // doesn't fire that event on its own.
                    input.style.height = 'auto';
                    input.style.height = input.scrollHeight + 'px';
                });
            });

            // @-mention picker (Phase 5, 21 Aug 2026) — its contents are
            // rebuilt from scratch on every keystroke (updateMentionPicker),
            // so this is a single delegated listener on the container
            // rather than per-option binding. stopPropagation keeps the
            // click from also bubbling to contentEl's outside-click
            // listener, which would otherwise re-hide it a tick after
            // insertMention() already did.
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

        // Outside-click closes any open dropdown/popover — added once here
        // (not inside wire(), which reruns on every reload) so a reload
        // never stacks a second document-level-style listener. contentEl
        // itself is stable across reload() calls (only its innerHTML is
        // replaced), and gets discarded for free when the overlay closes.
        contentEl.addEventListener('click', closeAllPopups);

        wire();
        scrollToBottom();
        // Composer (and so the mention picker) only renders for
        // can_manage_notes viewers — skip the fetch entirely for a read-
        // only viewer rather than firing a request that'll just 403.
        if (contentEl.querySelector('#overlay-chat-input')) fetchMentionableUsers();

        return {
            // Nothing to explicitly tear down — the one listener this
            // module owns lives on contentEl, which is discarded along
            // with the rest of the overlay's DOM on close. Kept as a real
            // function (not omitted) so project_list.js's
            // closeProjectOverlay() can call it unconditionally, same
            // shape as every other card module's handle.
            destroy: function () { },
            // SSE hook (Phase 2, 21 Aug 2026) — project_list.js's live-
            // update stream calls this when the drawer is open and some
            // OTHER change touched this project (a message from someone
            // else, a pin/unpin, a delete). {live: true} is what makes
            // reload() preserve your draft and respect your scroll
            // position instead of the more aggressive always-scroll-and-
            // discard behaviour your own send/delete/pin actions want.
            liveRefresh: function () { return reload(null, { live: true }); }
        };
    }

    return { init: init };
})();
