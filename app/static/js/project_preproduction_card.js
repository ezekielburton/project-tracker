// app/static/js/project_preproduction_card.js
//
// Design > Pre-Production sub-tab. Same init(rootEl, projectId, onChanged)
// / destroy() shape every other sub-tab card module uses (see
// project_details_card.js) so project_list.js's SUBTAB_LOADERS registry
// can mount/unmount it identically to the others.

window.ProjectPreproductionCard = (function () {
    function init(rootEl, projectId, onChanged) {
        if (!rootEl) return null;
        var pickerHandles = [];

        function postJson(url, body) {
            return fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body || {}),
            }).then(function (r) { return r.json(); });
        }

        // ── C&CM customer scope select — same panel-switch pattern as
        // Deliverables/Submissions (project_deliverables_card.js). ──
        var scopeSelect = rootEl.querySelector('#overlay-preprod-scope-select');
        if (scopeSelect) {
            scopeSelect.addEventListener('change', function () {
                rootEl.querySelectorAll('.overlay-preprod-panel').forEach(function (panel) {
                    panel.classList.toggle('is-hidden', panel.dataset.customerPanel !== scopeSelect.value);
                });
            });
        }

        // ── Completed section collapse (same recipe as .overlay-inc-toggle
        // — button.nextElementSibling is the list it reveals). ──
        rootEl.querySelectorAll('.overlay-preprod-completed-toggle').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var list = btn.nextElementSibling;
                if (!list) return;
                var open = list.classList.toggle('is-hidden') === false;
                btn.setAttribute('aria-expanded', open ? 'true' : 'false');
            });
        });

        // ── Stream assignment / transfer — one AvatarPicker per stream. ──
        rootEl.querySelectorAll('.overlay-preprod-stream .avatar-picker').forEach(function (pickerEl) {
            pickerHandles.push(window.AvatarPicker.init(pickerEl, function (userId) {
                var streamEl = pickerEl.closest('.overlay-preprod-stream');
                if (!streamEl) return;
                postJson(`/deliverables/${streamEl.dataset.deliverableId}/preproduction/assign`, {
                    stream: streamEl.dataset.stream,
                    designer_id: userId,
                }).then(function (data) {
                    if (!data.success) { alert(data.error || 'Could not assign.'); return; }
                    onChanged();
                });
            }));
        });

        // ── Mark Done (the assignee marking their own upload ready). ──
        rootEl.querySelectorAll('.overlay-preprod-markdone-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var streamEl = btn.closest('.overlay-preprod-stream');
                if (!streamEl) return;
                postJson(`/deliverables/${streamEl.dataset.deliverableId}/preproduction/mark-done`, {
                    stream: streamEl.dataset.stream,
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

        // ── Flag for Reupload — opens a comment form, same show/hide
        // pattern as Mark Approved / Request Client Revision. ──
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

        // ── Flag/comment history panel — fetched once on first open, then
        // filtered client-side by the deliverable dropdown (no re-fetch per
        // filter change — the whole project's history is small enough to
        // hold in memory at once). ──
        var historyToggle = rootEl.querySelector('#overlay-preprod-history-toggle');
        var historyPanel = rootEl.querySelector('#overlay-preprod-history-panel');
        var historyFilter = rootEl.querySelector('#overlay-preprod-history-filter');
        var historyList = rootEl.querySelector('#overlay-preprod-history-list');
        var historyEvents = null;  // cached after first fetch

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
                    '<strong>' + e.deliverable_name + '</strong>' +
                    '<span class="overlay-field-label">' + e.stream + '</span>' +
                    '</div>' +
                    '<p class="overlay-notes-text">' + e.message + '</p>' +
                    '<span class="overlay-preprod-history-item-meta">' + e.author_name + ' · ' + when + '</span>' +
                    '</div>';
            }).join('');
        }

        if (historyToggle && historyPanel) {
            historyToggle.addEventListener('click', function () {
                var opening = historyPanel.classList.contains('is-hidden');
                historyPanel.classList.toggle('is-hidden');
                if (opening && historyEvents === null) {
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
        }
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
