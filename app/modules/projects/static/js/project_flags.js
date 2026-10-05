// Flag create/reply/resolve/history for the overlay. Details and
// Deliverables render .overlay-flag-section blocks (_flag_project_panel.html)
// and call init() once per sub-tab load; it wires every section it finds.
window.ProjectFlags = (function () {
    function init(rootEl, projectId, onChanged) {
        if (!rootEl) return null;

        function postJson(url, body, onSuccess, onError) {
            fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.success) { if (onError) onError(data.error); return; }
                    if (onSuccess) onSuccess(data);
                })
                .catch(function () { if (onError) onError('Something went wrong. Please try again.'); });
        }

        function escapeHtml(s) {
            var div = document.createElement('div');
            div.textContent = s == null ? '' : String(s);
            return div.innerHTML;
        }

        // Renders a History item. Keep in sync with _flag_card.html.
        function renderFlagCard(flag) {
            var typeLabels = { project: 'Project', deliverable: 'Deliverable', concept: 'Concept', kv: 'KV' };
            var html = '<div class="overlay-flag-card' + (flag.is_resolved ? ' is-resolved' : '') + '" data-flag-id="' + flag.id + '">';
            html += '<div class="overlay-flag-card-header">';
            html += '<span class="overlay-flag-type-badge">' + (typeLabels[flag.flag_type] || flag.flag_type) + '</span>';
            if (flag.deliverable_name) html += '<span class="overlay-flag-subject">' + escapeHtml(flag.deliverable_name) + '</span>';
            var when = flag.created_at ? new Date(flag.created_at).toLocaleString() : '';
            html += '<span class="overlay-flag-meta">Raised by ' + escapeHtml(flag.created_by_name) + ' · ' + when + '</span>';
            if (flag.is_resolved) {
                var resolvedWhen = flag.resolved_at ? new Date(flag.resolved_at).toLocaleDateString() : '';
                html += '<span class="overlay-flag-resolved-badge">✓ Resolved by ' + escapeHtml(flag.resolved_by_name) + ' · ' + resolvedWhen + '</span>';
            } else if (flag.can_resolve) {
                html += '<button type="button" class="overlay-file-action-btn overlay-file-action-btn--primary overlay-flag-resolve-btn" data-flag-id="' + flag.id + '">Mark Resolved</button>';
            }
            html += '</div><div class="overlay-flag-thread">';
            (flag.messages || []).forEach(function (m) {
                var mWhen = m.created_at ? new Date(m.created_at).toLocaleString() : '';
                html += '<div class="overlay-flag-message"><div class="overlay-flag-message-header">' +
                    '<span class="overlay-flag-message-author">' + escapeHtml(m.author_name) + '</span>' +
                    '<span class="overlay-flag-message-time">' + mWhen + '</span></div>' +
                    '<p class="overlay-flag-message-text">' + escapeHtml(m.message) + '</p></div>';
            });
            html += '</div></div>';
            return html;
        }

        // Wires resolve buttons; called again after each History render.
        // data-flag-wired stops double-binding.
        function wireFlagCardActions(container) {
            container.querySelectorAll('.overlay-flag-resolve-btn').forEach(function (btn) {
                if (btn.dataset.flagWired) return;
                btn.dataset.flagWired = '1';
                btn.addEventListener('click', function () {
                    var go = function () {
                        postJson(`/projects/${projectId}/overlay/flags/${btn.dataset.flagId}/resolve`, {}, function () {
                            if (onChanged) onChanged();
                        }, function (err) { alert(err || 'Could not resolve this flag.'); });
                    };
                    window.showConfirm('Mark this flag as resolved?', go);
                });
            });
        }

        rootEl.querySelectorAll('.overlay-flag-reply-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var card = btn.closest('.overlay-flag-card');
                var input = card ? card.querySelector('.overlay-flag-reply-input') : null;
                var message = input ? input.value.trim() : '';
                if (!message) return;
                btn.disabled = true;
                postJson(`/projects/${projectId}/overlay/flags/${btn.dataset.flagId}/reply`, { message: message }, function () {
                    if (onChanged) onChanged();
                }, function (err) {
                    btn.disabled = false;
                    alert(err || 'Could not send reply.');
                });
            });
        });
        wireFlagCardActions(rootEl);

        // ── Each section: a Flag History toggle (history fetched once,
        // on first open) and, for deliverable scope, a compose form. ──
        rootEl.querySelectorAll('.overlay-flag-section').forEach(function (section) {
            var scope = section.dataset.flagScope;
            var customerId = section.dataset.customerId || null;
            var historyList = section.querySelector('.overlay-flag-history-list');
            var historyLoaded = false;

            function fetchHistory() {
                historyLoaded = true;
                var url = `/projects/${projectId}/overlay/flags/history?scope=${scope}`;
                if (customerId) url += `&customer_id=${customerId}`;
                fetch(url)
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        var flags = data.flags || [];
                        if (!historyList) return;
                        if (!flags.length) {
                            historyList.innerHTML = '<p class="overlay-field-empty">No flags yet.</p>';
                            return;
                        }
                        historyList.innerHTML = flags.map(renderFlagCard).join('');
                        wireFlagCardActions(historyList);
                    })
                    .catch(function () {
                        historyLoaded = false;
                        if (historyList) historyList.innerHTML = '<p class="overlay-field-empty">Could not load history.</p>';
                    });
            }

            var historyBtn = section.querySelector('.overlay-flag-history-toggle-btn');
            var historyPanel = section.querySelector('.overlay-flag-view');
            if (historyBtn && historyPanel) {
                historyBtn.addEventListener('click', function () {
                    var willShow = historyPanel.classList.contains('is-hidden');
                    historyPanel.classList.toggle('is-hidden', !willShow);
                    historyBtn.classList.toggle('active', willShow);
                    if (willShow && !historyLoaded) fetchHistory();
                });
            }

            // ── Raise a flag. Only deliverable-scope sections have a
            // compose form; project flags are raised from the sidebar
            // (project_list.js). ──
            var composeForm = section.querySelector('.overlay-flag-compose-form');
            var composeInput = section.querySelector('.overlay-flag-compose-input');
            var composeError = section.querySelector('.overlay-flag-revision-error');
            var composeTarget = section.querySelector('.overlay-flag-compose-target');
            var composeConfirm = section.querySelector('.overlay-flag-compose-confirm');
            var composeCancel = section.querySelector('.overlay-flag-compose-cancel');
            var targetDeliverableId = null;

            function openCompose() {
                if (!composeForm) return;
                composeForm.classList.remove('is-hidden');
                if (composeInput) { composeInput.value = ''; composeInput.focus(); }
                if (composeError) composeError.classList.add('hidden');
            }
            function closeCompose() {
                if (!composeForm) return;
                composeForm.classList.add('is-hidden');
                targetDeliverableId = null;
                if (composeTarget) composeTarget.classList.add('is-hidden');
            }

            // Deliverable scope: this customer's ⚑ row triggers open THIS
            // section's compose form. The flag panel is a sibling of the
            // rows, not an ancestor, so match by customer id. Standard has
            // one section, so it searches the whole sub-tab.
            if (scope === 'deliverable') {
                var panel = customerId
                    ? (rootEl.querySelector(`.overlay-deliverables-panel[data-customer-panel="${customerId}"]`) || rootEl)
                    : rootEl;
                panel.querySelectorAll('.overlay-flag-row-trigger').forEach(function (trigger) {
                    if (trigger.dataset.flagWired) return;
                    trigger.dataset.flagWired = '1';
                    trigger.addEventListener('click', function () {
                        targetDeliverableId = trigger.dataset.deliverableId;
                        if (composeTarget) {
                            composeTarget.textContent = 'Flagging: ' + trigger.dataset.deliverableName;
                            composeTarget.classList.remove('is-hidden');
                        }
                        openCompose();
                    });
                });
            }

            if (composeCancel) composeCancel.addEventListener('click', closeCompose);
            if (composeConfirm) {
                composeConfirm.addEventListener('click', function () {
                    var message = composeInput ? composeInput.value.trim() : '';
                    if (!message) {
                        if (composeError) { composeError.textContent = 'A message is required.'; composeError.classList.remove('hidden'); }
                        return;
                    }
                    if (scope === 'deliverable' && !targetDeliverableId) {
                        if (composeError) { composeError.textContent = 'Flag a deliverable first (⚑)'; composeError.classList.remove('hidden'); }
                        return;
                    }
                    composeConfirm.disabled = true;
                    if (composeError) composeError.classList.add('hidden');
                    postJson(`/projects/${projectId}/overlay/flags/create`, {
                        flag_type: scope === 'deliverable' ? 'deliverable' : 'project',
                        deliverable_id: scope === 'deliverable' ? targetDeliverableId : null,
                        message: message,
                    }, function () {
                        composeConfirm.disabled = false;
                        closeCompose();
                        if (onChanged) onChanged();
                    }, function (err) {
                        composeConfirm.disabled = false;
                        if (composeError) { composeError.textContent = err || 'Could not raise this flag.'; composeError.classList.remove('hidden'); }
                    });
                });
            }
        });

        return { destroy: function () { } };
    }

    return { init: init };
})();
