// Pre-Production page. Standard init(rootEl, projectId, onChanged) /
// destroy() card shape, mounted via project_list.js's SUBTAB_LOADERS.

window.ProjectPreproductionCard = (function () {
    function init(rootEl, projectId, onChanged) {
        if (!rootEl) return null;

        function postJson(url, body) {
            return fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body || {}),
            }).then(function (r) { return r.json(); });
        }

        // ── C&CM customer scope select: shows the matching panels. ──
        var scopeSelect = rootEl.querySelector('#overlay-preprod-scope-select');
        if (scopeSelect) {
            scopeSelect.addEventListener('change', function () {
                rootEl.querySelectorAll('.overlay-preprod-panel, .overlay-preprod-attention-panel').forEach(function (panel) {
                    panel.classList.toggle('is-hidden', panel.dataset.customerPanel !== scopeSelect.value);
                });
            });
        }

        // ── Completed section collapse. The list must be the button's
        // next sibling. ──
        rootEl.querySelectorAll('.overlay-preprod-completed-toggle').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var list = btn.nextElementSibling;
                if (!list) return;
                var open = list.classList.toggle('is-hidden') === false;
                btn.setAttribute('aria-expanded', open ? 'true' : 'false');
            });
        });

        // ── Open the deliverable's NAS folder (main.js openNasLink()). ──
        rootEl.querySelectorAll('.overlay-preprod-nas-link').forEach(function (btn) {
            btn.addEventListener('click', function () { openNasLink(btn); });
        });

        // ── Stream assignment picker, one per stream, scoped to that
        // stream's team. The enclosing .overlay-preprod-stream carries
        // data-deliverable-id and data-stream. ──
        var pickerHandles = [];
        rootEl.querySelectorAll('.overlay-preprod-stream .avatar-picker').forEach(function (pickerEl) {
            var streamEl = pickerEl.closest('.overlay-preprod-stream');
            if (!streamEl) return;
            pickerHandles.push(window.AvatarPicker.init(pickerEl, function (userId) {
                postJson(`/deliverables/${streamEl.dataset.deliverableId}/preproduction/assign`, {
                    stream: streamEl.dataset.stream,
                    designer_id: userId,
                }).then(function (data) {
                    if (!data.success) { alert(data.error || 'Could not update this assignment.'); return; }
                    onChanged();
                });
            }));
        });

        // ── Mark Done (the assignee marks their upload ready). ──
        rootEl.querySelectorAll('.overlay-preprod-markdone-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var streamEl = btn.closest('.overlay-preprod-stream');
                if (!streamEl) return;
                var deliverableId = streamEl.dataset.deliverableId;
                var stream = streamEl.dataset.stream;
                if (!deliverableId || !stream) return;
                postJson(`/deliverables/${deliverableId}/preproduction/mark-done`, {
                    stream: stream,
                }).then(function (data) {
                    if (!data.success) { alert(data.error || 'Could not mark this done.'); return; }
                    onChanged();
                });
            });
        });

        // ── Approve (Project Owner signs off a stream). ──
        rootEl.querySelectorAll('.overlay-preprod-approve-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var streamEl = btn.closest('.overlay-preprod-stream');
                if (!streamEl) return;
                postJson(`/deliverables/${streamEl.dataset.deliverableId}/preproduction/approve`, {
                    stream: streamEl.dataset.stream,
                }).then(function (data) {
                    if (!data.success) { alert(data.error || 'Could not approve this stream.'); return; }
                    onChanged();
                });
            });
        });

        // ── Flag for Reupload: swaps the action buttons for a comment form.
        // Cancel assumes the actions span is the form's previous sibling
        // (_preproduction_row.html). ──
        rootEl.querySelectorAll('.overlay-preprod-flag-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var streamEl = btn.closest('.overlay-preprod-stream');
                var form = streamEl.querySelector('.overlay-preprod-flag-form');
                if (!form) return;
                form.classList.remove('is-hidden');
                btn.closest('.overlay-preprod-stream-actions').classList.add('is-hidden');
            });
        });
        rootEl.querySelectorAll('.overlay-preprod-flag-cancel').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var form = btn.closest('.overlay-preprod-flag-form');
                var actions = form.previousElementSibling;
                form.classList.add('is-hidden');
                if (actions && actions.classList.contains('overlay-preprod-stream-actions')) {
                    actions.classList.remove('is-hidden');
                }
            });
        });
        rootEl.querySelectorAll('.overlay-preprod-flag-confirm').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var form = btn.closest('.overlay-preprod-flag-form');
                var streamEl = btn.closest('.overlay-preprod-stream');
                var textarea = form.querySelector('.overlay-preprod-flag-textarea');
                var errorEl = form.querySelector('.overlay-flag-revision-error');
                var message = textarea ? textarea.value.trim() : '';

                if (!message) {
                    if (errorEl) { errorEl.textContent = 'A comment is required.'; errorEl.classList.remove('hidden'); }
                    return;
                }
                btn.disabled = true;
                postJson(`/deliverables/${streamEl.dataset.deliverableId}/preproduction/flag`, {
                    stream: streamEl.dataset.stream,
                    message: message,
                }).then(function (data) {
                    btn.disabled = false;
                    if (!data.success) {
                        if (errorEl) { errorEl.textContent = data.error || 'Could not flag this stream.'; errorEl.classList.remove('hidden'); }
                        return;
                    }
                    onChanged();
                });
            });
        });

        // ── Active / History view toggle. Flag history is fetched once,
        // then filtered client-side by the deliverable dropdown. ──
        var viewToggleBtns = rootEl.querySelectorAll('.overlay-submissions-view-toggle-btn');
        var activeView = rootEl.querySelector('#overlay-preprod-active-view');
        var historyView = rootEl.querySelector('#overlay-preprod-history-view');
        var historyFilter = rootEl.querySelector('#overlay-preprod-history-filter');
        var historyList = rootEl.querySelector('#overlay-preprod-history-list');
        var historyEvents = null;  // cached after first fetch

        function escapeHtml(str) {
            var div = document.createElement('div');
            div.textContent = str == null ? '' : String(str);
            return div.innerHTML;
        }

        function renderHistory() {
            if (!historyList) return;
            var filterId = historyFilter ? historyFilter.value : 'all';
            var events = historyEvents || [];
            if (filterId !== 'all') {
                events = events.filter(function (e) { return String(e.deliverable_id) === filterId; });
            }
            if (!events.length) {
                historyList.innerHTML = '<p class="overlay-field-empty">No flags yet.</p>';
                return;
            }
            historyList.innerHTML = events.map(function (e) {
                var when = e.created_at ? new Date(e.created_at).toLocaleString() : '';
                return '<div class="overlay-preprod-history-item">' +
                    '<div class="overlay-preprod-history-item-header">' +
                    '<strong>' + escapeHtml(e.deliverable_name) + '</strong>' +
                    '<span class="overlay-field-label">' + escapeHtml(e.stream) + '</span>' +
                    '</div>' +
                    '<p class="overlay-notes-text">' + escapeHtml(e.message) + '</p>' +
                    '<span class="overlay-preprod-history-item-meta">' + escapeHtml(e.author_name) + ' · ' + escapeHtml(when) + '</span>' +
                    '</div>';
            }).join('');
        }

        viewToggleBtns.forEach(function (btn) {
            btn.addEventListener('click', function () {
                viewToggleBtns.forEach(function (b) { b.classList.toggle('active', b === btn); });
                var showHistory = btn.dataset.view === 'history';
                if (activeView) activeView.classList.toggle('is-hidden', showHistory);
                if (historyView) historyView.classList.toggle('is-hidden', !showHistory);
                if (showHistory && historyEvents === null) {
                    fetch(`/projects/${projectId}/preproduction/events`)
                        .then(function (r) { return r.json(); })
                        .then(function (data) {
                            historyEvents = data.events || [];
                            renderHistory();
                        })
                        .catch(function () {
                            historyEvents = [];
                            if (historyList) historyList.innerHTML = '<p class="overlay-field-empty">Could not load history.</p>';
                        });
                }
            });
        });
        if (historyFilter) {
            historyFilter.addEventListener('change', renderHistory);
        }

        return {
            destroy: function () {
                pickerHandles.forEach(function (h) { if (h) h.destroy(); });
            }
        };
    }

    return { init: init };
})();
