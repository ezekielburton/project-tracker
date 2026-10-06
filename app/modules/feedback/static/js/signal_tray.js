// Signal tray: compact Bug Report and Feature Request boards, plus the Friction
// Log chat. Registers with HelixTrays and loads once, outside #main-content,
// so SPA nav never re-runs it.
//
// Opening a row injects the feedback module's detail fragment
// (_bug_content.html / _feature_content.html) and wires it here.
(function () {
    if (!window.HelixTrays) return;

    var ICONS = {
        bug: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="8" y="6" width="8" height="12" rx="4"/><path d="m19 7-3 2"/><path d="m5 7 3 2"/><path d="m19 17-3-2"/><path d="m5 17 3-2"/><path d="M20 12h-4"/><path d="M4 12h4"/></svg>',
        feature: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M9 21h6"/><path d="M12 2a7 7 0 0 1 7 7c0 2.38-1.19 4.47-3 5.74V17a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 0 1 7-7z"/></svg>',
        friction: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 4v16h16"/><path d="M4 14l4-4 4 3 6-7"/></svg>',
        comment: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
        up: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><polyline points="18 15 12 9 6 15"/></svg>',
        plus: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>',
        back: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><polyline points="15 18 9 12 15 6"/></svg>',
        trash: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/></svg>'
    };

    var TABS = [
        { key: 'bug', label: 'Bug Report' },
        { key: 'feature', label: 'Feature Request' },
        { key: 'friction', label: 'Friction Log' }
    ];

    // Endpoints and DOM id prefix per board, so one set of handlers serves both.
    var BOARDS = {
        bug: {
            list: '/signal/bugs',
            item: function (id) { return '/bug-reports/' + id; },
            submit: '/bug-reports',
            comments: function (id) { return '/bug-reports/' + id + '/comments'; },
            comment: function (id) { return '/bug-reports/comments/' + id; },
            prefix: 'br',
            newLabel: 'Report a bug'
        },
        feature: {
            list: '/signal/features',
            item: function (id) { return '/feature-requests/' + id; },
            submit: '/feature-requests',
            comments: function (id) { return '/feature-requests/' + id + '/comments'; },
            comment: function (id) { return '/feature-requests/comments/' + id; },
            prefix: 'fr',
            newLabel: 'New request'
        }
    };

    // Every selector this tray binds on the detail fragments.
    // test_signal_tray_contract.py parses this literal and checks the templates
    // still carry each one; keep it plain JSON-like (see that test).
    var FRAGMENT_CONTRACT = {
        '_bug_content.html': [
            '#br-status-select', '#br-delete-btn', '#br-comment-form',
            '#br-reply-form-', '.br-reply-btn', '.br-reply-cancel',
            '.br-comment-delete', '.br-reply-form'
        ],
        '_feature_content.html': [
            '#fr-status-select', '#fr-delete-btn', '#fr-comment-form',
            '#fr-upvote-btn', '#fr-reply-form-', '.fr-reply-btn',
            '.fr-reply-cancel', '.fr-comment-delete', '.fr-reply-form'
        ]
    };

    // Finished items are hidden from "All" until their own chip is picked;
    // that chip still shows the real count.
    var HIDDEN_UNLESS_PICKED = { feature: 'implemented' };

    var activeTab = 'bug';
    var activeStatus = 'all';
    var boardEl = null;
    var tabsEl = null;
    var severities = [];
    // { key, id } from a notification link, opened by the next buildPanes.
    var linkedItem = null;

    function fetchJson(url, options) {
        return fetch(url, options).then(function (r) { return r.json(); });
    }

    function dateLabel(iso) {
        if (!iso) return '';
        return new Date(iso).toLocaleDateString([], { day: 'numeric', month: 'short' });
    }

    function toast(message, kind) {
        if (window.showToast) window.showToast(message, kind || 'success');
    }

    // The server sends naive UTC; marking it as UTC shows the reader's local time.
    function timeLabel(iso) {
        if (!iso) return '';
        var when = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + 'Z');
        return when.toLocaleDateString([], { weekday: 'short' }) + ' '
            + when.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    // ── Shell ────────────────────────────────────────────

    function buildPanes(body) {
        body.innerHTML =
            '<div class="signal-tray">' +
            '<div class="signal-tray__tabs" id="signal-tabs"></div>' +
            '<div class="signal-tray__body" id="signal-board"></div>' +
            '</div>';

        tabsEl = document.getElementById('signal-tabs');
        boardEl = document.getElementById('signal-board');

        var linked = linkedItem;
        linkedItem = null;
        if (linked) activeTab = linked.key;

        if (linked && linked.id) {
            renderTabs();
            openItem(linked.key, linked.id);
        } else {
            openTab(activeTab);
        }

        // Opening the tray is what clears its bubble.
        fetch('/signal/seen', { method: 'POST' })
            .then(function () { window.HelixTrays.setUnread('signal', 0); });
    }

    function renderTabs() {
        tabsEl.innerHTML = '';
        TABS.forEach(function (tab) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'signal-tray__tab' + (tab.key === activeTab ? ' is-active' : '');
            btn.innerHTML = ICONS[tab.key] + '<span>' + tab.label + '</span>';
            btn.addEventListener('click', function () { openTab(tab.key); });
            tabsEl.appendChild(btn);
        });
    }

    function openTab(key) {
        if (!boardEl) return;  // tray closed while a request was in flight
        activeTab = key;
        activeStatus = 'all';
        renderTabs();
        if (key === 'friction') {
            openFriction();
            startLive();
        } else {
            leaveFriction();
            loadBoard(key);
        }
    }

    // The Friction tab reloads when anyone posts or deletes, while it is showing.
    function startLive() {
        if (!window.helixPolling) return;
        window.helixPolling.startFrictionStream(function () {
            if (friction) loadFriction();
        });
    }

    function leaveFriction() {
        if (window.helixPolling) window.helixPolling.stopFrictionStream();
        friction = null;
        if (boardEl) boardEl.classList.remove('is-chat');
    }

    // ── The two boards ───────────────────────────────────

    function loadBoard(key) {
        // onClose nulls boardEl and a reopen builds a new one; a reply for
        // the old one must not render.
        var target = boardEl;
        target.innerHTML = '<p class="signal-tray__empty">Loading…</p>';
        fetchJson(BOARDS[key].list).then(function (data) {
            if (boardEl !== target) return;
            if (data.severities) severities = data.severities;
            renderBoard(key, data);
        }).catch(function () {
            if (boardEl === target) target.innerHTML = '<p class="signal-tray__empty">Could not load this board.</p>';
        });
    }

    function renderBoard(key, data) {
        if (activeTab !== key) return;
        var board = BOARDS[key];
        boardEl.innerHTML = '';

        var toolbar = document.createElement('div');
        toolbar.className = 'signal-tray__toolbar';

        var hidden = HIDDEN_UNLESS_PICKED[key];
        var visible = data.rows.filter(function (row) { return row.status !== hidden; });

        var chips = [{ key: 'all', label: 'All', count: visible.length }]
            .concat(data.counts.by_status);
        chips.forEach(function (chip) {
            var el = document.createElement('button');
            el.type = 'button';
            el.className = 'signal-tray__chip' + (chip.key === activeStatus ? ' is-active' : '');
            el.innerHTML = chip.label + ' <span class="signal-tray__chip-n">' + chip.count + '</span>';
            el.addEventListener('click', function () {
                activeStatus = chip.key;
                renderBoard(key, data);
            });
            toolbar.appendChild(el);
        });

        var spacer = document.createElement('span');
        spacer.className = 'signal-tray__spacer';
        toolbar.appendChild(spacer);

        var newBtn = document.createElement('button');
        newBtn.type = 'button';
        newBtn.className = 'signal-tray__new';
        newBtn.innerHTML = ICONS.plus + board.newLabel;
        newBtn.addEventListener('click', function () { renderNewForm(key); });
        toolbar.appendChild(newBtn);

        boardEl.appendChild(toolbar);

        var list = document.createElement('div');
        list.className = 'signal-tray__list';
        var rows = activeStatus === 'all'
            ? visible
            : data.rows.filter(function (row) { return row.status === activeStatus; });

        if (!rows.length) {
            list.innerHTML = '<p class="signal-tray__empty">Nothing here.</p>';
        } else {
            rows.forEach(function (row) { list.appendChild(renderRow(key, row)); });
        }
        boardEl.appendChild(list);
    }

    function renderRow(key, row) {
        var el = document.createElement('div');
        el.className = 'signal-tray__row';
        el.setAttribute('role', 'button');
        el.setAttribute('tabindex', '0');

        var lead = document.createElement('span');
        if (key === 'bug') {
            lead.className = 'signal-tray__sev' + (row.severity ? ' is-' + row.severity : '');
            lead.textContent = row.severity_label || '—';
        } else {
            lead.className = 'signal-tray__vote' + (row.voted ? ' is-voted' : '');
            lead.innerHTML = ICONS.up + '<span>' + row.upvotes + '</span>';
            lead.addEventListener('click', function (e) {
                e.stopPropagation();
                fetch('/feature-requests/' + row.id + '/upvote', { method: 'POST' })
                    .then(function () { loadBoard('feature'); });
            });
        }
        el.appendChild(lead);

        var mid = document.createElement('div');
        mid.className = 'signal-tray__row-mid';
        var title = document.createElement('div');
        title.className = 'signal-tray__row-title';
        title.textContent = row.title;
        var meta = document.createElement('div');
        meta.className = 'signal-tray__row-meta';
        meta.textContent = row.author + ' · ' + dateLabel(row.created_at)
            + (row.di_state ? ' · ' + diLabel(row.di_state) : '');
        mid.appendChild(title);
        mid.appendChild(meta);
        el.appendChild(mid);

        var right = document.createElement('div');
        right.className = 'signal-tray__row-right';
        right.innerHTML =
            '<span class="signal-tray__pill is-' + row.status + '">' + row.status_label + '</span>' +
            '<span class="signal-tray__comments">' + ICONS.comment + row.comments + '</span>';
        el.appendChild(right);

        el.addEventListener('click', function () { openItem(key, row.id); });
        el.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                openItem(key, row.id);
            }
        });
        return el;
    }

    // Only the states DI records; there is no link to a shipped version.
    function diLabel(state) {
        if (state === 'queued') return 'DI: queued';
        if (state === 'declined') return 'DI: declined';
        return 'DI: picked up';
    }

    // ── One item's detail — the feedback module's own fragment ──

    function openItem(key, id) {
        if (!boardEl) return;
        var board = BOARDS[key];
        var target = boardEl;  // see loadBoard
        target.innerHTML = '<p class="signal-tray__empty">Loading…</p>';

        fetch(board.item(id))
            .then(function (r) {
                if (!r.ok) throw new Error('item fetch failed');
                return r.text();
            })
            .then(function (html) {
                if (boardEl !== target) return;
                boardEl.innerHTML = '';

                var back = document.createElement('button');
                back.type = 'button';
                back.className = 'signal-tray__back';
                back.innerHTML = ICONS.back + 'Back to the board';
                back.addEventListener('click', function () { openTab(key); });
                boardEl.appendChild(back);

                var wrap = document.createElement('div');
                wrap.className = 'signal-tray__detail';
                wrap.innerHTML = html;
                boardEl.appendChild(wrap);

                wireDetail(key, id, wrap);
            })
            .catch(function () {
                if (boardEl === target) target.innerHTML = '<p class="signal-tray__empty">Could not open this item.</p>';
            });
    }

    function wireDetail(key, id, wrap) {
        var board = BOARDS[key];
        var p = board.prefix;

        var statusSelect = wrap.querySelector('#' + p + '-status-select');
        if (statusSelect) {
            statusSelect.addEventListener('change', function () {
                fetchJson(board.item(id) + '/status', {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ status: statusSelect.value })
                }).then(function (data) {
                    if (data.success) { toast('Status updated.'); openItem(key, id); }
                    else toast(data.error || 'Could not update the status.', 'error');
                });
            });
        }

        var deleteBtn = wrap.querySelector('#' + p + '-delete-btn');
        if (deleteBtn) {
            deleteBtn.addEventListener('click', function () {
                window.showConfirm('Delete this ' + (key === 'bug' ? 'bug report' : 'feature request')
                    + '? This cannot be undone.', function () {
                    fetch(board.item(id), { method: 'DELETE' })
                        .then(function (r) { return r.json(); })
                        .then(function (data) {
                            if (data.success) { toast('Deleted.'); openTab(key); }
                            else toast(data.error || 'Could not delete this.', 'error');
                        });
                });
            });
        }

        var upvoteBtn = wrap.querySelector('#fr-upvote-btn');
        if (upvoteBtn) {
            upvoteBtn.addEventListener('click', function () {
                fetch('/feature-requests/' + id + '/upvote', { method: 'POST' })
                    .then(function () { openItem(key, id); });
            });
        }

        var commentForm = wrap.querySelector('#' + p + '-comment-form');
        if (commentForm) {
            commentForm.addEventListener('submit', function (e) {
                e.preventDefault();
                postComment(key, id, new FormData(commentForm));
            });
        }

        // Delegated on the wrapper; openItem builds a fresh wrapper each time,
        // so listeners never stack.
        wrap.addEventListener('click', function (e) {
            var replyBtn = e.target.closest('.' + p + '-reply-btn');
            if (replyBtn) {
                var form = wrap.querySelector('#' + p + '-reply-form-' + replyBtn.dataset.commentId);
                if (form) form.style.display = form.style.display === 'none' ? '' : 'none';
                return;
            }
            var cancel = e.target.closest('.' + p + '-reply-cancel');
            if (cancel) {
                var parent = cancel.closest('form');
                if (parent) parent.style.display = 'none';
                return;
            }
            var del = e.target.closest('.' + p + '-comment-delete');
            if (del) {
                window.showConfirm('Delete this comment?', function () {
                    fetch(board.comment(del.dataset.commentId), { method: 'DELETE' })
                        .then(function () { openItem(key, id); });
                });
            }
        });

        wrap.querySelectorAll('.' + p + '-reply-form').forEach(function (form) {
            form.addEventListener('submit', function (e) {
                e.preventDefault();
                var data = new FormData(form);
                data.append('parent_id', form.id.replace(p + '-reply-form-', ''));
                postComment(key, id, data);
            });
        });
    }

    function postComment(key, id, formData) {
        // The comment endpoints take form data, not JSON.
        fetch(BOARDS[key].comments(id), { method: 'POST', body: formData })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) openItem(key, id);
                else toast(data.error || 'Could not post that.', 'error');
            });
    }

    // ── Submitting a new item ────────────────────────────

    function renderNewForm(key) {
        var board = BOARDS[key];
        boardEl.innerHTML = '';

        var back = document.createElement('button');
        back.type = 'button';
        back.className = 'signal-tray__back';
        back.innerHTML = ICONS.back + 'Back to the board';
        back.addEventListener('click', function () { openTab(key); });
        boardEl.appendChild(back);

        var form = document.createElement('form');
        form.className = 'signal-tray__form';
        form.innerHTML =
            '<label class="signal-tray__label">Title</label>' +
            '<input type="text" class="form-input" name="title" required>' +
            (key === 'bug' ? '<label class="signal-tray__label">Severity</label>' +
                '<select class="form-input" name="severity">' +
                '<option value="">Not set</option>' +
                severities.map(function (s) {
                    return '<option value="' + s.key + '">' + s.label + '</option>';
                }).join('') +
                '</select>' : '') +
            '<label class="signal-tray__label">Description</label>' +
            '<textarea class="form-input" name="description" rows="5" required></textarea>' +
            '<div class="add-user-actions"><button type="submit" class="btn-primary">' +
            board.newLabel + '</button></div>';

        form.addEventListener('submit', function (e) {
            e.preventDefault();
            var payload = {
                title: form.title.value.trim(),
                description: form.description.value.trim()
            };
            if (key === 'bug') payload.severity = form.severity.value || null;

            fetchJson(board.submit, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            }).then(function (data) {
                if (data.success) { toast('Submitted.'); openTab(key); }
                else toast(data.error || 'Could not submit that.', 'error');
            });
        });

        boardEl.appendChild(form);
    }

    // ── Friction Log ─────────────────────────────────────
    // A chat: the list scrolls, the composer stays pinned below it, and a live
    // reload redraws only the list so a half-typed post survives.

    // { log, form, first } while the Friction tab is showing; null otherwise.
    var friction = null;

    function openFriction() {
        boardEl.innerHTML = '';
        boardEl.classList.add('is-chat');

        var intro = document.createElement('p');
        intro.className = 'signal-tray__intro';
        intro.textContent = 'Annoyances only — bugs and ideas have their own tabs.';
        boardEl.appendChild(intro);

        var log = document.createElement('div');
        log.className = 'signal-tray__log';
        log.innerHTML = '<p class="signal-tray__empty">Loading…</p>';
        boardEl.appendChild(log);

        var form = document.createElement('form');
        form.className = 'signal-tray__composer';
        form.innerHTML =
            '<textarea class="form-input" name="body" rows="2" placeholder="What\'s annoying you?"'
            + ' aria-label="New friction post"></textarea>'
            + '<button type="submit" class="btn-primary">Post</button>';
        boardEl.appendChild(form);

        friction = { log: log, form: form, first: true };
        wireComposer(form);
        loadFriction();
    }

    // opts.toBottom: jump to the newest post (after your own post).
    function loadFriction(opts) {
        var view = friction;
        fetchJson('/signal/friction').then(function (data) {
            if (friction === view) renderFrictionLog(data, opts || {});
        }).catch(function () {
            if (friction === view && view.first) {
                view.log.innerHTML = '<p class="signal-tray__empty">Could not load the Friction Log.</p>';
            }
        });
    }

    function isNearBottom(el) {
        return el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    }

    function renderFrictionLog(data, opts) {
        var log = friction.log;
        var stick = friction.first || opts.toBottom || isNearBottom(log);
        var kept = log.scrollTop;
        friction.first = false;
        friction.form.body.maxLength = data.max_length;

        log.innerHTML = '';
        if (!data.weeks.length) {
            log.innerHTML = '<p class="signal-tray__empty">Nothing logged yet.</p>';
            return;
        }

        data.weeks.forEach(function (week) {
            var head = document.createElement('div');
            head.className = 'signal-tray__week';
            head.innerHTML = '<span>Week of ' + dateLabel(week.week_start) + '</span>'
                + '<span class="signal-tray__week-line"></span>'
                + (week.week_start === data.current_week
                    ? '<span class="signal-tray__week-tag">Review Fri</span>' : '');
            log.appendChild(head);
            week.entries.forEach(function (entry) { log.appendChild(renderFrictionEntry(entry)); });
        });

        log.scrollTop = stick ? log.scrollHeight : kept;
    }

    function renderFrictionEntry(entry) {
        var el = document.createElement('div');
        el.className = 'signal-tray__entry';

        var head = document.createElement('div');
        head.className = 'signal-tray__entry-head';

        var who = document.createElement('span');
        who.className = 'signal-tray__entry-who';
        who.textContent = entry.author + (entry.department ? ' · ' + entry.department : '');
        head.appendChild(who);

        var when = document.createElement('span');
        when.className = 'signal-tray__entry-when';
        when.textContent = timeLabel(entry.created_at);
        head.appendChild(when);

        if (entry.can_delete) {
            var del = document.createElement('button');
            del.type = 'button';
            del.className = 'signal-tray__entry-delete';
            del.title = 'Delete post';
            del.setAttribute('aria-label', 'Delete post');
            del.innerHTML = ICONS.trash;
            del.addEventListener('click', function () { deleteFriction(entry.id); });
            head.appendChild(del);
        }
        el.appendChild(head);

        var body = document.createElement('p');
        body.className = 'signal-tray__entry-body';
        body.textContent = entry.body;
        el.appendChild(body);
        return el;
    }

    function wireComposer(form) {
        var input = form.body;
        var button = form.querySelector('button');

        function send() {
            var body = input.value.trim();
            if (!body || button.disabled) return;
            button.disabled = true;
            fetchJson('/signal/friction', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ body: body })
            }).then(function (result) {
                button.disabled = false;
                if (result.success) {
                    input.value = '';
                    if (friction) loadFriction({ toBottom: true });
                } else {
                    toast(result.error || 'Could not post that.', 'error');
                }
            }).catch(function () {
                button.disabled = false;
                toast('Could not post that.', 'error');
            });
        }

        // Enter sends, Shift+Enter inserts a newline, as in project chat.
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
                e.preventDefault();
                send();
            }
        });
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            send();
        });
    }

    function deleteFriction(id) {
        window.showConfirm('Delete this post?', function () {
            fetchJson('/signal/friction/' + id, { method: 'DELETE' }).then(function (result) {
                if (!result.success) toast(result.error || 'Could not delete that.', 'error');
                else if (friction) loadFriction();
            }).catch(function () { toast('Could not delete that.', 'error'); });
        });
    }

    // ── Registration and the launcher bubble ─────────────

    function loadUnread() {
        fetchJson('/signal/unread')
            .then(function (data) { window.HelixTrays.setUnread('signal', (data && data.unread) || 0); })
            .catch(function () { /* offline or logged out — leave the bubble alone */ });
    }

    // A notification links to ?signal=feature:12 (or bug:12). Older links
    // redirect to ?signal=feature with the id left in the #fr-12 fragment.
    function readLinkedItem() {
        var params = new URLSearchParams(window.location.search);
        var raw = params.get('signal');
        if (!raw) return null;
        var parts = raw.split(':');
        var board = BOARDS[parts[0]];
        if (!board) return null;
        var id = parseInt(parts[1], 10) || null;
        var hash = window.location.hash.match(/^#(fr|br)-(\d+)$/);
        if (!id && hash && hash[1] === board.prefix) id = parseInt(hash[2], 10);

        // Drop the param so a reload does not reopen the item.
        params.delete('signal');
        var query = params.toString();
        history.replaceState(history.state, '',
            window.location.pathname + (query ? '?' + query : '') + (hash ? '' : window.location.hash));
        return { key: parts[0], id: id };
    }

    // Set before register: a tray restored open on load builds its panes there.
    linkedItem = readLinkedItem();

    window.HelixTrays.register('signal', {
        onOpen: buildPanes,
        onClose: function () { leaveFriction(); boardEl = tabsEl = null; },
        onSignal: loadUnread
    });

    if (linkedItem) window.HelixTrays.open('signal');

    loadUnread();

    window.SignalTrayFragmentContract = FRAGMENT_CONTRACT;
})();
