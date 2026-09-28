// Chat tray — the conversation list, and the thread pane that reuses the
// overlay's chat panel (ProjectChatPanel). Registers with HelixTrays and
// loads once from base.html, outside #main-content, so SPA nav never re-runs it.
(function () {
    if (!window.HelixTrays) return;

    var conversations = [];
    var selectedId = null;
    var panel = null;      // the live ProjectChatPanel instance, if a thread is open
    var listEl = null;
    var chatEl = null;
    var headEl = null;
    var searchTerm = '';

    var PIN_ICON = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="17" x2="12" y2="22"/><path d="M5 17h14l-1.7-3.4a2 2 0 0 1-.2-.9V4H6.9v8.7a2 2 0 0 1-.2.9z"/></svg>';
    var CLOSE_ICON = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/></svg>';

    function fetchJson(url, options) {
        return fetch(url, options).then(function (r) { return r.json(); });
    }

    function timeLabel(iso) {
        if (!iso) return '';
        var at = new Date(iso);
        var now = new Date();
        var sameDay = at.toDateString() === now.toDateString();
        if (sameDay) {
            return at.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }
        var yesterday = new Date(now);
        yesterday.setDate(now.getDate() - 1);
        if (at.toDateString() === yesterday.toDateString()) return 'Yest';
        if (now - at < 7 * 24 * 3600 * 1000) return at.toLocaleDateString([], { weekday: 'short' });
        return at.toLocaleDateString([], { day: 'numeric', month: 'short' });
    }

    function loadConversations() {
        return fetchJson('/chat-tray/conversations').then(function (data) {
            conversations = (data && data.conversations) || [];
            window.HelixTrays.setUnread('chat', (data && data.unread_total) || 0);
            renderList();
        }).catch(function () { /* offline or logged out — leave the list as it was */ });
    }

    function matchesSearch(row) {
        if (!searchTerm) return true;
        return (row.name || '').toLowerCase().indexOf(searchTerm) !== -1;
    }

    function renderList() {
        if (!listEl) return;
        listEl.innerHTML = '';
        var rows = conversations.filter(matchesSearch);
        if (!rows.length) {
            var empty = document.createElement('p');
            empty.className = 'chat-tray__empty';
            empty.textContent = searchTerm ? 'No projects match.' : 'No conversations yet.';
            listEl.appendChild(empty);
            return;
        }
        rows.forEach(function (row) {
            var el = document.createElement('div');
            el.className = 'chat-tray__conv'
                + (row.project_id === selectedId ? ' is-selected' : '')
                + (row.pinned ? ' is-pinned' : '');
            el.setAttribute('role', 'button');
            el.setAttribute('tabindex', '0');
            el.dataset.projectId = row.project_id;

            var last = row.last_message;
            var snippet = last ? (last.author ? last.author + ': ' : '') + (last.text || '') : 'No messages yet';
            var bubble = row.unread > 0
                ? '<span class="chat-tray__unread">' + (row.unread > 99 ? '99+' : row.unread) + '</span>'
                : '';

            el.innerHTML =
                '<span class="chat-tray__avatar"></span>' +
                '<span class="chat-tray__conv-mid">' +
                '<span class="chat-tray__conv-name"></span>' +
                '<span class="chat-tray__conv-snippet"></span>' +
                '</span>' +
                '<span class="chat-tray__conv-right">' +
                '<span class="chat-tray__time"></span>' + bubble +
                '</span>' +
                '<span class="chat-tray__conv-actions">' +
                '<button type="button" class="chat-tray__act" data-act="pin" title="' +
                (row.pinned ? 'Unpin' : 'Pin to top') + '" aria-label="' +
                (row.pinned ? 'Unpin' : 'Pin to top') + '">' + PIN_ICON + '</button>' +
                '<button type="button" class="chat-tray__act" data-act="hide" title="Remove from list" aria-label="Remove from list">' +
                CLOSE_ICON + '</button>' +
                '</span>';

            el.querySelector('.chat-tray__avatar').textContent = row.initials;
            el.querySelector('.chat-tray__conv-name').textContent = row.name;
            el.querySelector('.chat-tray__conv-snippet').textContent = snippet;
            el.querySelector('.chat-tray__time').textContent = last ? timeLabel(last.at) : '';

            el.addEventListener('click', function () { selectProject(row.project_id); });
            el.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    selectProject(row.project_id);
                }
            });
            el.querySelectorAll('.chat-tray__act').forEach(function (btn) {
                btn.addEventListener('click', function (e) {
                    // The row itself opens the thread; these must not.
                    e.stopPropagation();
                    if (btn.dataset.act === 'pin') togglePin(row);
                    else hideConversation(row);
                });
            });

            listEl.appendChild(el);
        });
    }

    function togglePin(row) {
        fetchJson('/chat-tray/projects/' + row.project_id + '/pin', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pinned: !row.pinned })
        }).then(loadConversations);
    }

    function hideConversation(row) {
        fetch('/chat-tray/projects/' + row.project_id, { method: 'DELETE' })
            .then(function () {
                if (selectedId === row.project_id) {
                    selectedId = null;
                    if (panel && panel.destroy) panel.destroy();
                    panel = null;
                    if (headEl) headEl.innerHTML = '';
                    if (chatEl) chatEl.innerHTML = '<p class="chat-tray__empty">Pick a project to open its chat.</p>';
                }
                loadConversations();
                if (window.showToast) window.showToast('Removed — it comes back if someone posts.', 'success');
            });
    }

    function selectProject(projectId) {
        selectedId = projectId;
        renderList();

        var row = conversations.filter(function (c) { return c.project_id === projectId; })[0];
        renderThreadHead(row);

        if (panel && panel.destroy) panel.destroy();
        panel = null;
        chatEl.innerHTML = '<p class="chat-tray__empty">Loading…</p>';

        fetch('/chat-tray/projects/' + projectId + '/thread')
            .then(function (r) {
                if (!r.ok) throw new Error('forbidden');
                return r.text();
            })
            .then(function (html) {
                chatEl.innerHTML = html;
                panel = window.ProjectChatPanel.init(chatEl, projectId);
                // Reading clears the watermark server-side; refresh so the row
                // and launcher bubbles clear with it.
                loadConversations();
            })
            .catch(function () {
                chatEl.innerHTML = '<p class="chat-tray__empty">Could not open this conversation.</p>';
            });
    }

    function renderThreadHead(row) {
        if (!headEl) return;
        headEl.innerHTML = '';
        if (!row) return;

        var avatar = document.createElement('span');
        avatar.className = 'chat-tray__avatar chat-tray__avatar--sm';
        avatar.textContent = row.initials;

        var meta = document.createElement('span');
        meta.className = 'chat-tray__thread-meta';
        var name = document.createElement('span');
        name.className = 'chat-tray__thread-name';
        name.textContent = row.name;
        var sub = document.createElement('span');
        sub.className = 'chat-tray__thread-sub';
        sub.textContent = row.job_number ? 'JOB #' + row.job_number : '';
        meta.appendChild(name);
        meta.appendChild(sub);

        var open = document.createElement('a');
        open.className = 'chat-tray__open';
        open.href = '/projects-new/?view=all&project=' + row.project_id;
        open.textContent = 'Open project';

        headEl.appendChild(avatar);
        headEl.appendChild(meta);
        headEl.appendChild(open);
    }

    function openAddPicker() {
        fetchJson('/chat-tray/addable').then(function (data) {
            var listed = {};
            conversations.forEach(function (c) { listed[c.project_id] = true; });
            var options = ((data && data.projects) || []).filter(function (p) { return !listed[p.project_id]; });
            renderAddPicker(options);
        });
    }

    function renderAddPicker(options) {
        var existing = document.getElementById('chat-tray-add-picker');
        if (existing) existing.remove();
        if (!options.length) {
            if (window.showToast) window.showToast('Every project you are on is already listed.', 'success');
            return;
        }
        var picker = document.createElement('div');
        picker.className = 'chat-tray__picker';
        picker.id = 'chat-tray-add-picker';
        options.forEach(function (p) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'chat-tray__picker-item';
            btn.textContent = p.name;
            btn.addEventListener('click', function () {
                fetchJson('/chat-tray/projects', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ project_id: p.project_id })
                }).then(function () {
                    picker.remove();
                    loadConversations().then(function () { selectProject(p.project_id); });
                });
            });
            picker.appendChild(btn);
        });
        document.getElementById('chat-tray-panes').appendChild(picker);
    }

    function buildPanes(body, actions) {
        body.innerHTML =
            '<div class="chat-tray" id="chat-tray-panes">' +
            '<div class="chat-tray__list-pane">' +
            '<div class="chat-tray__search"><input type="text" class="form-input" id="chat-tray-search" placeholder="Search projects…"></div>' +
            '<div class="chat-tray__list" id="chat-tray-list"></div>' +
            '</div>' +
            '<div class="chat-tray__thread">' +
            '<div class="chat-tray__thread-head" id="chat-tray-thread-head"></div>' +
            '<div class="project-overlay-chat-content" id="chat-tray-chat">' +
            '<p class="chat-tray__empty">Pick a project to open its chat.</p>' +
            '</div>' +
            '</div>' +
            '</div>';

        listEl = document.getElementById('chat-tray-list');
        chatEl = document.getElementById('chat-tray-chat');
        headEl = document.getElementById('chat-tray-thread-head');

        var addBtn = document.createElement('button');
        addBtn.type = 'button';
        addBtn.className = 'chat-tray__add';
        addBtn.textContent = '+ Add Chat';
        addBtn.addEventListener('click', openAddPicker);
        actions.appendChild(addBtn);

        var search = document.getElementById('chat-tray-search');
        search.addEventListener('input', function () {
            searchTerm = this.value.trim().toLowerCase();
            renderList();
        });

        renderList();
        loadConversations().then(function () {
            if (selectedId) selectProject(selectedId);
        });
    }

    function teardown() {
        if (panel && panel.destroy) panel.destroy();
        panel = null;
        listEl = chatEl = headEl = null;
    }

    window.HelixTrays.register('chat', {
        onOpen: buildPanes,
        onClose: teardown,
        onSignal: loadConversations
    });

    // Any project change pings /sse/dashboard. This is its own connection,
    // so the unread bubble stays live on every page, tray open or not.
    if (typeof EventSource !== 'undefined') {
        var stream = new EventSource('/sse/dashboard');
        stream.onmessage = function () {
            loadConversations();
            if (panel && panel.liveRefresh) panel.liveRefresh();
        };
    }

    loadConversations();
})();
