// app/static/js/project_preproduction_card.js
//
// Design > Pre-Production sub-tab. Same init(rootEl, projectId, onChanged)
// / destroy() shape every other sub-tab card module uses (see
// project_details_card.js) so project_list.js's SUBTAB_LOADERS registry
// can mount/unmount it identically to the others.

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

        // ── C&CM customer scope select — same panel-switch pattern as
        // Deliverables/Submissions (project_deliverables_card.js). ──
        var scopeSelect = rootEl.querySelector('#overlay-preprod-scope-select');
        if (scopeSelect) {
            scopeSelect.addEventListener('change', function () {
                rootEl.querySelectorAll('.overlay-preprod-panel, .overlay-preprod-attention-panel').forEach(function (panel) {
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

        // ── Open this deliverable's folder (Synology Drive, M10 NAS
        // migration, 21 Aug 2026) — click-triggered, see main.js's
        // openNasLink(). ──
        rootEl.querySelectorAll('.overlay-preprod-nas-link').forEach(function (btn) {
            btn.addEventListener('click', function () { openNasLink(btn); });
        });

        // ── Stream Assignment picker (21 Aug 2026, per Ezekiel; folded into
        // every stream's own box 23 Aug 2026) — every stream (2D/3D/
        // Technical alike) now gets an interactive picker, scoped to that
        // stream's own team (see _preproduction_row.html). Same
        // AvatarPicker.init(el, onSelect) recipe as the Design Leads
        // per-team picker in project_details_card.js — the containing
        // .overlay-preprod-stream carries both data-deliverable-id and
        // data-stream already, so both come straight off the same element
        // the picker lives in. ──
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

        // ── Mark Done (the assignee marking their own upload ready). Every
        // stream lives inside a .overlay-preprod-stream card again (21 Aug
        // 2026, per Ezekiel — the idle-stream quick-action extraction was
        // reverted), so this just reads deliverable-id/stream off the
        // containing card, same as Approve/Flag below. ──
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

        // ── Active / History view toggle — swaps the whole view, same
        // pattern as Submissions' Current/History toggle, not a reveal-a-
        // panel-underneath button. Flag history is fetched once on first
        // switch into it, then filtered client-side by the deliverable
        // dropdown (no re-fetch per filter change). ──
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
