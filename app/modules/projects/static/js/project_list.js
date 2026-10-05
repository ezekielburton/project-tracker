// app/modules/projects/static/js/project_list.js
//
// Projects list page: the project overlay (open/close, sidebar content,
// live updates), the create-project entry, soft navigation for tabs/filters/
// sort/group, client-side search, live table refresh, and the date picker.
// Row clicks use one delegated listener on the table.

(() => {
    // ---- Project overlay: open/close + URL state ----
    // Addressable via ?project=<id> so links, refresh and back/forward work.
    // Declared above the `if (!table) return` guard so the overlay still
    // opens on an empty-state page.

    const overlayMount = document.getElementById('project-overlay-mount');
    let activeOverlay = null;
    let activeSubTabCard = null;   // card module for the page currently showing (Details, Deliverables, ...)
    let activeOverlayEdit = null;  // Details edit-mode handle; reset (not destroyed) on every page switch
    let activeChatPanel = null;    // chat drawer controller, independent of activeSubTabCard

    // ---- Project overlay: remember last page ----
    // Per-project localStorage, written on every sidebar click so a refresh
    // or browser-back reopens the same page.
    function lastViewKey(projectId) {
        return 'overlay-last-view-' + projectId;
    }

    function saveLastView(projectId, section, subTab) {
        try {
            localStorage.setItem(lastViewKey(projectId), JSON.stringify({ section: section, subTab: subTab }));
        } catch (e) {
            // localStorage unavailable (private browsing, quota): opens on Details.
        }
    }

    function getLastView(projectId) {
        try {
            return JSON.parse(localStorage.getItem(lastViewKey(projectId)) || 'null');
        } catch (e) {
            return null;
        }
    }

    // The SPA router re-runs this file on every visit, and window/document
    // listeners outlive the page, so each run swaps out the previous run's copy.
    function bindGlobal(target, type, key, handler) {
        const handlers = window.__projectListGlobalHandlers || (window.__projectListGlobalHandlers = {});
        if (handlers[key]) target.removeEventListener(type, handlers[key]);
        handlers[key] = handler;
        target.addEventListener(type, handler);
    }

    // Content loaders for the Design pages, keyed by the sidebar button's
    // data-sub-tab value. A key with no entry here loads nothing.
    const SUBTAB_LOADERS = {
        details: {
            url: (projectId) => `/projects/${projectId}/overlay/details`,
            module: () => window.ProjectDetailsCard,
        },
        deliverables: {
            url: (projectId) => `/projects/${projectId}/overlay/deliverables`,
            module: () => window.ProjectDeliverablesCard,
        },
        submissions: {
            url: (projectId) => `/projects/${projectId}/overlay/submissions`,
            module: () => window.ProjectSubmissionsCard,
        },
        // Hyphenated to match data-sub-tab in _overlay.html, which is used as the key.
        'pre-production': {
            url: (projectId) => `/projects/${projectId}/overlay/preproduction`,
            module: () => window.ProjectPreproductionCard,
        },
    };

    // The page the overlay is showing, by the same rules openProjectOverlay
    // restores with: nothing saved, or a page that no longer exists, is Details.
    function shownPage(projectId) {
        const lastView = getLastView(projectId);
        if (lastView && lastView.section === 'notes') return 'notes';
        if (lastView && lastView.section === 'design' && lastView.subTab && SUBTAB_LOADERS[lastView.subTab]) {
            return lastView.subTab;
        }
        return 'details';
    }

    // Unsaved-edit guard, passed to ProjectOverlay.init as onBeforeNavigate.
    // Calls proceed() straight away, or after the user confirms discarding edits.
    function guardUnsavedEdit(proceed) {
        if (activeOverlayEdit && activeOverlayEdit.isEditing() && activeOverlayEdit.hasUnsavedChanges()) {
            window.showConfirm(
                'You have unsaved changes on Details. Discard them?',
                proceed,
                'Discard unsaved changes?'
            );
            return;
        }
        proceed();
    }

    function loadSubTabContent(projectId, subTabKey) {
        const loader = SUBTAB_LOADERS[subTabKey];
        if (!loader) return;

        const contentEl = document.getElementById('project-overlay-content');
        if (!contentEl) return;

        // A page switch replaces the edited DOM, so reset edit mode now or the
        // header stays stuck on Save/Cancel. The unsaved-changes confirm
        // happens earlier, in guardUnsavedEdit.
        if (activeOverlayEdit) {
            activeOverlayEdit.exitEditMode();
        }

        // The header's Edit button is for Details only; Deliverables has its own edit mode.
        const overlayHeader = document.getElementById('project-overlay-header');
        if (overlayHeader) {
            const editBtn = overlayHeader.querySelector('#project-overlay-edit-btn');
            if (editBtn) editBtn.classList.toggle('is-hidden', subTabKey !== 'details');
        }

        fetch(loader.url(projectId))
            .then((res) => res.text())
            .then((html) => {
                if (activeSubTabCard) {
                    activeSubTabCard.destroy();
                    activeSubTabCard = null;
                }
                contentEl.innerHTML = html;
                const CardModule = loader.module();
                if (CardModule) {
                    activeSubTabCard = CardModule.init(contentEl, projectId, function () {
                        loadSubTabContent(projectId, subTabKey);
                    });
                }
            });
    }
    
    function loadNotesSection(projectId) {
        const contentEl = document.getElementById('project-overlay-content');
        if (!contentEl) return;

        if (activeOverlayEdit) activeOverlayEdit.exitEditMode();
        if (activeSubTabCard) {
            activeSubTabCard.destroy();
            activeSubTabCard = null;
        }

        // Edit button is for Details only.
        const overlayHeader = document.getElementById('project-overlay-header');
        if (overlayHeader) {
            const editBtn = overlayHeader.querySelector('#project-overlay-edit-btn');
            if (editBtn) editBtn.classList.add('is-hidden');
        }

        fetch(`/projects/${projectId}/overlay/notes`)
            .then((res) => res.text())
            .then((html) => {
                contentEl.innerHTML = html;
                if (window.ProjectNotesCard) {
                    activeSubTabCard = window.ProjectNotesCard.init(contentEl, projectId);
                }
            });
    }

    // Chat drawer content lives in its own container, untouched by page
    // switches. Called once, on the drawer's first open (onChatOpened);
    // later refreshes go through the panel's own reload/liveRefresh.
    function loadChatDrawer(projectId) {
        const contentEl = document.getElementById('project-overlay-chat-content');
        if (!contentEl) return;

        fetch(`/projects/${projectId}/overlay/chat`)
            .then((res) => res.text())
            .then((html) => {
                contentEl.innerHTML = html;
                if (window.ProjectChatPanel) {
                    activeChatPanel = window.ProjectChatPanel.init(contentEl, projectId);
                }
            });
    }

    // Sidebar actions (Flag Issue, Hold/Resume, Cancel/Reactivate, folder,
    // edit access). Wired once per overlay open, since the sidebar persists
    // across page switches. Each button pair is rendered in both states and
    // toggled on success, with no sidebar refetch.
    function wireProjectLifecycleActions(sidebarEl, projectId) {
        if (!sidebarEl) return;

        function postJson(url, body, onSuccess, onError) {
            fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) })
                .then((r) => r.json())
                .then((data) => {
                    if (!data.success) { if (onError) onError(data.error); return; }
                    if (onSuccess) onSuccess();
                })
                .catch(() => { if (onError) onError('Something went wrong. Please try again.'); });
        }

        // Details is the only page showing status/flags, so refresh it if it is open.
        function refreshDetailsIfActive() {
            if (shownPage(projectId) === 'details') {
                loadSubTabContent(projectId, 'details');
            }
        }

        // ── Flag Issue (project-level): raise only. Reply/resolve live on
        // Details (project_flags.js). ──
        const flagBtn = sidebarEl.querySelector('#overlay-flag-issue-btn');
        const flagForm = sidebarEl.querySelector('#overlay-flag-issue-form');
        const flagMessageInput = sidebarEl.querySelector('#overlay-flag-issue-message');
        const flagErrorEl = sidebarEl.querySelector('#overlay-flag-issue-error');
        const flagConfirmBtn = sidebarEl.querySelector('#overlay-flag-issue-confirm');
        const flagCancelBtn = sidebarEl.querySelector('#overlay-flag-issue-cancel');

        if (flagBtn && flagForm) {
            flagBtn.addEventListener('click', () => {
                flagBtn.classList.add('is-hidden');
                flagForm.classList.remove('is-hidden');
                if (flagMessageInput) flagMessageInput.focus();
            });
        }
        if (flagCancelBtn) {
            flagCancelBtn.addEventListener('click', () => {
                flagForm.classList.add('is-hidden');
                if (flagBtn) flagBtn.classList.remove('is-hidden');
                if (flagErrorEl) flagErrorEl.classList.add('hidden');
            });
        }
        if (flagConfirmBtn) {
            flagConfirmBtn.addEventListener('click', () => {
                const message = flagMessageInput ? flagMessageInput.value.trim() : '';
                if (!message) {
                    if (flagErrorEl) { flagErrorEl.textContent = 'A message is required.'; flagErrorEl.classList.remove('hidden'); }
                    return;
                }
                flagConfirmBtn.disabled = true;
                if (flagErrorEl) flagErrorEl.classList.add('hidden');
                postJson(`/projects/${projectId}/overlay/flags/create`, { flag_type: 'project', message: message }, () => {
                    flagConfirmBtn.disabled = false;
                    if (flagMessageInput) flagMessageInput.value = '';
                    flagForm.classList.add('is-hidden');
                    if (flagBtn) flagBtn.classList.remove('is-hidden');
                    refreshDetailsIfActive();
                }, (err) => {
                    flagConfirmBtn.disabled = false;
                    if (flagErrorEl) { flagErrorEl.textContent = err || 'Could not raise this flag.'; flagErrorEl.classList.remove('hidden'); }
                });
            });
        }

        const holdBtn = sidebarEl.querySelector('#overlay-hold-project-btn');
        const resumeBtn = sidebarEl.querySelector('#overlay-resume-project-btn');
        if (holdBtn) {
            holdBtn.addEventListener('click', () => {
                const go = () => postJson(`/projects/${projectId}/overlay/toggle-hold`, {}, () => {
                    holdBtn.classList.add('is-hidden');
                    if (resumeBtn) resumeBtn.classList.remove('is-hidden');
                    refreshDetailsIfActive();
                }, (err) => alert(err || 'Could not put this project on hold.'));
                window.showConfirm('Put this project on hold?', go);
            });
        }
        if (resumeBtn) {
            resumeBtn.addEventListener('click', () => {
                postJson(`/projects/${projectId}/overlay/toggle-hold`, {}, () => {
                    resumeBtn.classList.add('is-hidden');
                    if (holdBtn) holdBtn.classList.remove('is-hidden');
                    refreshDetailsIfActive();
                }, (err) => alert(err || 'Could not resume this project.'));
            });
        }

        // Open Project Folder (Synology Drive), see main.js's openNasLink().
        const openFolderBtn = sidebarEl.querySelector('#overlay-open-folder-btn');
        if (openFolderBtn) {
            openFolderBtn.addEventListener('click', () => openNasLink(openFolderBtn));
        }

        // Request Editing Access: no confirm (not destructive). Flips to the
        // disabled "pending" state in place on success.
        const editAccessBtn = sidebarEl.querySelector('#overlay-request-edit-access-btn');
        if (editAccessBtn) {
            editAccessBtn.addEventListener('click', () => {
                editAccessBtn.disabled = true;
                postJson(`/projects/${projectId}/request-edit-access`, {}, () => {
                    editAccessBtn.dataset.state = 'pending';
                    editAccessBtn.textContent = 'Editing Access Requested';
                }, (err) => {
                    editAccessBtn.disabled = false;
                    alert(err || 'Could not request editing access.');
                });
            });
        }

        const cancelBtn = sidebarEl.querySelector('#overlay-cancel-project-btn');
        const uncancelBtn = sidebarEl.querySelector('#overlay-uncancel-project-btn');
        const cancelForm = sidebarEl.querySelector('#overlay-cancel-project-form');
        const cancelReasonInput = sidebarEl.querySelector('#overlay-cancel-project-reason');
        const cancelErrorEl = sidebarEl.querySelector('#overlay-cancel-project-error');
        const cancelConfirmBtn = sidebarEl.querySelector('#overlay-cancel-project-confirm');
        const cancelCancelBtn = sidebarEl.querySelector('#overlay-cancel-project-cancel');

        if (cancelBtn && cancelForm) {
            cancelBtn.addEventListener('click', () => {
                cancelBtn.classList.add('is-hidden');
                cancelForm.classList.remove('is-hidden');
            });
        }
        if (cancelCancelBtn) {
            cancelCancelBtn.addEventListener('click', () => {
                cancelForm.classList.add('is-hidden');
                if (cancelBtn) cancelBtn.classList.remove('is-hidden');
                if (cancelErrorEl) cancelErrorEl.classList.add('hidden');
            });
        }
        if (cancelConfirmBtn) {
            cancelConfirmBtn.addEventListener('click', () => {
                const reason = cancelReasonInput ? cancelReasonInput.value.trim() : '';
                if (!reason) {
                    if (cancelErrorEl) { cancelErrorEl.textContent = 'A reason is required.'; cancelErrorEl.classList.remove('hidden'); }
                    return;
                }
                // A reason alone doesn't stop a stray click, so confirm too.
                window.showConfirm('Cancel this project? This freezes it for invoicing until reactivated.', () => {
                    cancelConfirmBtn.disabled = true;
                    if (cancelErrorEl) cancelErrorEl.classList.add('hidden');
                    postJson(`/projects/${projectId}/overlay/cancel`, { reason: reason }, () => {
                        cancelConfirmBtn.disabled = false;
                        cancelForm.classList.add('is-hidden');
                        cancelBtn.classList.add('is-hidden');
                        if (uncancelBtn) uncancelBtn.classList.remove('is-hidden');
                        refreshDetailsIfActive();
                    }, (err) => {
                        cancelConfirmBtn.disabled = false;
                        if (cancelErrorEl) { cancelErrorEl.textContent = err || 'Could not cancel this project.'; cancelErrorEl.classList.remove('hidden'); }
                    });
                }, 'Cancel Project');
            });
        }
        if (uncancelBtn) {
            uncancelBtn.addEventListener('click', () => {
                postJson(`/projects/${projectId}/overlay/uncancel`, {}, () => {
                    uncancelBtn.classList.add('is-hidden');
                    if (cancelBtn) cancelBtn.classList.remove('is-hidden');
                    refreshDetailsIfActive();
                }, (err) => alert(err || 'Could not reactivate this project.'));
            });
        }
    }

    function openProjectOverlay(projectId, pushHistory = true, openChat = false) {
        fetch(`/projects/${projectId}/overlay`)
            .then((res) => res.text())
            .then((html) => {
                overlayMount.innerHTML = html;
                const contentEl = document.getElementById('project-overlay-content');

                activeOverlay = window.ProjectOverlay.init(
                    closeProjectOverlay,
                    function (subTabKey) {
                        saveLastView(projectId, 'design', subTabKey);
                        loadSubTabContent(projectId, subTabKey);
                    },
                    // A section button was clicked. Site Visits is the only
                    // one; the Design pages go through the sub-tab callback above.
                    function (sectionKey) {
                        saveLastView(projectId, sectionKey, null);
                        if (sectionKey === 'notes') {
                            loadNotesSection(projectId);
                        }
                    },
                    guardUnsavedEdit,
                    // onChatOpened: fires on the drawer's first open only.
                    function () {
                        loadChatDrawer(projectId);
                    }
                );

                // ?chat=1 deep link (chat-mention notifications): open the drawer now.
                if (openChat && activeOverlay) {
                    activeOverlay.openChat();
                }

                // The header persists across page switches, so edit mode is
                // initialised once per overlay open.
                const overlayHeader = document.getElementById('project-overlay-header');
                if (overlayHeader && window.ProjectOverlayEdit) {
                    activeOverlayEdit = window.ProjectOverlayEdit.init(overlayHeader, contentEl, projectId, function () {
                        loadSubTabContent(projectId, 'details');
                    });
                }

                // Sidebar actions also persist, so wire them once here.
                const sidebarEl = document.getElementById('project-overlay-sidebar');
                wireProjectLifecycleActions(sidebarEl, projectId);

                // SSE live updates for this project (see live_events.py's
                // _PROJECT_ID_GETTERS). The page refresh is skipped while this
                // viewer is editing so it can't wipe their fields; the
                // concurrent-edit check catches conflicts at Save.
                if (window.helixPolling) {
                    window.helixPolling.startOverlayStream(projectId, function () {
                        // Chat drawer refreshes regardless of the page underneath.
                        if (activeChatPanel && activeOverlay && activeOverlay.isChatOpen && activeOverlay.isChatOpen()) {
                            activeChatPanel.liveRefresh();
                        }

                        if (activeOverlayEdit && activeOverlayEdit.isEditing()) return;
                        const page = shownPage(projectId);
                        if (page === 'notes') {
                            loadNotesSection(projectId);
                        } else {
                            loadSubTabContent(projectId, page);
                        }
                    });
                }

                const lastView = getLastView(projectId);
                if (lastView && lastView.section === 'design' && lastView.subTab && lastView.subTab !== 'details' && SUBTAB_LOADERS[lastView.subTab]) {
                    // Remembered a Design page other than Details: fetch it and sync the sidebar.
                    activeOverlay.restoreView('design', lastView.subTab);
                    loadSubTabContent(projectId, lastView.subTab);
                } else if (lastView && lastView.section === 'notes') {
                    activeOverlay.restoreView('notes', null);
                    loadNotesSection(projectId);
                } else {
                    // Nothing remembered, Details, or a section that no longer
                    // exists — show the Details content already in the page.
                    activeSubTabCard = window.ProjectDetailsCard.init(contentEl, projectId, function () {
                        loadSubTabContent(projectId, 'details');
                    });
                }

                if (pushHistory) {
                    const params = new URLSearchParams(window.location.search);
                    params.set('project', projectId);
                    history.pushState({ projectId }, '', `${window.location.pathname}?${params.toString()}`);
                }
            });
    }

    // Create-mode overlay has its own open/close: its shell
    // (_overlay_create.html) has no sidebar pages, SSE stream or edit
    // header, which openProjectOverlay expects.
    function openCreateShellForDraft(projectId) {
        return fetch(`/projects/${projectId}/overlay/create`)
            .then((res) => res.text())
            .then((html) => {
                overlayMount.innerHTML = html;
                if (window.ProjectOverlayCreate) {
                    // onFinalized: after Confirm, open the new project in the full overlay.
                    window.ProjectOverlayCreate.init(projectId, closeNewProjectOverlay, openProjectOverlay);
                }
            });
    }

    function startFreshDraft() {
        fetch('/projects/overlay/new', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        })
            .then((res) => res.json())
            .then((data) => {
                if (!data.success) {
                    alert(data.error || 'Could not start a new project.');
                    return;
                }
                return openCreateShellForDraft(data.project_id);
            })
            .catch(() => alert('Could not start a new project.'));
    }

    // Drafts picker: "+ New Project" shows this when open drafts exist (own,
    // or anyone's for admin/management). Appended to body, not overlayMount,
    // because it exists before any create-mode shell is loaded.
    function openDraftsPicker(html) {
        const wrapper = document.createElement('div');
        wrapper.innerHTML = html;
        const modal = wrapper.firstElementChild;
        document.body.appendChild(modal);
        if (window.helixPolling) window.helixPolling.pause();

        function closeModal() {
            modal.remove();
            if (window.helixPolling) window.helixPolling.resume();
        }

        modal.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });

        const cancelBtn = document.getElementById('overlay-create-drafts-cancel');
        if (cancelBtn) cancelBtn.addEventListener('click', closeModal);

        const startNewBtn = document.getElementById('overlay-create-drafts-start-new');
        if (startNewBtn) {
            startNewBtn.addEventListener('click', () => {
                closeModal();
                startFreshDraft();
            });
        }

        modal.querySelectorAll('.overlay-create-draft-resume').forEach((btn) => {
            btn.addEventListener('click', () => {
                const draftId = btn.getAttribute('data-draft-id');
                closeModal();
                openCreateShellForDraft(draftId);
            });
        });

        modal.querySelectorAll('.overlay-create-draft-delete').forEach((btn) => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                window.showConfirm('Delete this draft? This cannot be undone.', () => {
                    const draftId = btn.getAttribute('data-draft-id');
                    btn.disabled = true;
                    fetch(`/projects/${draftId}/draft`, { method: 'DELETE' })
                        .then((res) => res.json())
                        .then((result) => {
                            if (!result.success) {
                                btn.disabled = false;
                                alert(result.error || 'Could not delete this draft.');
                                return;
                            }
                            const row = modal.querySelector(`.overlay-create-draft-row[data-draft-id="${draftId}"]`);
                            if (row) row.remove();
                            if (!modal.querySelector('.overlay-create-draft-row')) {
                                // Last draft deleted: keep the picker open with
                                // just Cancel / Start New.
                                const list = modal.querySelector('.overlay-create-drafts-list');
                                if (list) list.remove();
                                const intro = modal.querySelector('.overlay-submit-summary-intro');
                                if (intro) intro.textContent = 'No drafts left';
                            }
                        })
                        .catch(() => {
                            btn.disabled = false;
                            alert('Could not delete this draft.');
                        });
                });
            });
        });
    }

    function openNewProjectOverlay() {
        fetch('/projects/overlay/drafts')
            .then((res) => res.json())
            .then((data) => {
                if (data.has_drafts) {
                    openDraftsPicker(data.html);
                } else {
                    startFreshDraft();
                }
            })
            .catch(() => startFreshDraft());
    }

    function closeNewProjectOverlay() {
        overlayMount.innerHTML = '';
    }

    function closeProjectOverlay(pushHistory = true) {
        if (activeOverlay) {
            activeOverlay.destroy();
            activeOverlay = null;
        }
        if (activeSubTabCard) {
            activeSubTabCard.destroy();
            activeSubTabCard = null;
        }
        if (activeChatPanel) {
            activeChatPanel.destroy();
            activeChatPanel = null;
        }
        activeOverlayEdit = null;
        if (window.helixPolling) window.helixPolling.stopOverlayStream();
        overlayMount.innerHTML = '';

        if (pushHistory) {
            const params = new URLSearchParams(window.location.search);
            params.delete('project');
            const query = params.toString();
            history.pushState({}, '', `${window.location.pathname}${query ? '?' + query : ''}`);
        }
    }

    // Back/Forward: re-derive overlay state from the URL, since the user may
    // jump several steps at once.
    bindGlobal(window, 'popstate', 'popstate', () => {
        if (!overlayMount || !overlayMount.isConnected) return;
        // Back to another page: the router swaps it in; just drop the overlay
        // (and its SSE stream) without syncing this page's state.
        if (!window.location.pathname.startsWith('/projects-new')) {
            if (activeOverlay) closeProjectOverlay(false);
            return;
        }
        const params = new URLSearchParams(window.location.search);
        const projectId = params.get('project');
        if (projectId) {
            openProjectOverlay(projectId, false);
        } else {
            closeProjectOverlay(false);
        }
        // Soft-nav changes are history entries too, so re-sync tabs, panels
        // and table. No pushState: the browser already moved.
        syncPageStateFromLocation(window.location.pathname + window.location.search, {
            onDone: (finalQuery, failed) => {
                if (!failed && finalQuery && finalQuery !== window.location.search) {
                    history.replaceState({ softNav: true }, '', `${window.location.pathname}${finalQuery}`);
                }
            },
        });
    });

    // Direct load with ?project=<id> (and optional &chat=1). Every inbound
    // project link (notifications, achievements, escalations) relies on this.
    (function autoOpenFromUrl() {
        const params = new URLSearchParams(window.location.search);
        const projectId = params.get('project');
        const openChat = params.get('chat') === '1';
        if (projectId) openProjectOverlay(projectId, false, openChat);
    })();

    // ---- Row expansion + row-click-to-open ----

    const table = document.querySelector('.project-table');

    // ---- Soft navigation: tabs / filters / sort / group / show-cancelled ----
    // These controls fetch /projects-new/page-state and patch the DOM
    // instead of reloading the page.
    //
    // #filter-panel, #sort-panel and .tab-strip only ever get their
    // innerHTML replaced, never the elements, so the delegated listeners
    // bound on them keep working without re-binding.
    const tabStrip = document.querySelector('.tab-strip');

    // Outer-scope lookups for applyPageState(). The same names are declared
    // again inside the `if (filterToggle && filterPanel)` block below; those
    // block-scoped consts are invisible here, so do not remove these.
    const sortToggle = document.getElementById('sort-toggle');
    const sortPanel = document.getElementById('sort-panel');
    const showCancelledToggle = document.getElementById('show-cancelled-toggle');
    const saveNewViewBtn = document.getElementById('save-new-view-btn');
    const toolbarSearch = document.getElementById('toolbar-search');
    const searchClear = document.getElementById('search-clear');

    // Fresh loads render the active tab from the user's saved view but leave
    // ?view off the URL, so the toolbar handlers (search/filter/sort) would
    // fall back to 'my'. Stamp the real current tab into the URL once on load.
    (function ensureViewInUrl() {
        const params = new URLSearchParams(window.location.search);
        if (!params.get('view')) {
            const page = document.querySelector('.project-list-page');
            const v = page && page.dataset.currentView;
            if (v) {
                params.set('view', v);
                history.replaceState(history.state, '', window.location.pathname + '?' + params.toString());
            }
        }
    })();

    // Renumber visible rows in one grid container so hidden rows leave no
    // gap (rows are pinned to grid rows via --row-num; header stays at 1).
    function renumberContainer(container, needle) {
        const rows = container.querySelectorAll(':scope > .project-row--link');
        let n = 2;
        let visible = 0;
        rows.forEach((row) => {
            const match = !needle || (row.dataset.search || '').includes(needle);
            row.hidden = !match;

            // Each project owns two grid rows (itself + its expand panel), so step by 2.
            const panel = row.nextElementSibling;
            const hasPanel = panel && panel.classList.contains('project-expand-container');

            if (match) {
                row.style.setProperty('--row-num', n);
                if (hasPanel) panel.style.gridRow = n + 1;
                n += 2;
                visible += 1;
            } else if (hasPanel) {
                // Filtered out — collapse its panel so it can't linger open.
                panel.hidden = true;
                const toggle = row.querySelector('.project-expand-toggle');
                if (toggle) toggle.setAttribute('aria-expanded', 'false');
            }
        });
        return visible;
    }

    // Client-side search over the rows on screen (project name + job number).
    // Re-run after any table re-render so it stays applied.
    function applyClientSearch() {
        if (!toolbarSearch || !table) return;
        const needle = (toolbarSearch.value || '').trim().toLowerCase();
        if (searchClear) searchClear.hidden = !toolbarSearch.value;
        const grouped = table.classList.contains('project-table--grouped');
        const containers = grouped ? table.querySelectorAll('.project-group-table') : [table];
        let total = 0;
        containers.forEach((c) => {
            const visible = renumberContainer(c, needle);
            total += visible;
            if (grouped) {
                const group = c.closest('.project-group');
                if (group) group.hidden = visible === 0;
                const countEl = group && group.querySelector('.project-group-count');
                if (countEl) countEl.textContent = visible;
            }
        });
        let empty = table.querySelector('.project-search-empty');
        if (needle && total === 0) {
            if (!empty) {
                empty = document.createElement('p');
                empty.className = 'project-list-empty project-search-empty';
                empty.textContent = 'No projects match your search.';
                table.appendChild(empty);
            }
            empty.hidden = false;
        } else if (empty) {
            empty.hidden = true;
        }
    }

    function toPageStateUrl(url) {
        const qIndex = url.indexOf('?');
        const query = qIndex >= 0 ? url.slice(qIndex + 1) : '';
        return '/projects-new/page-state' + (query ? '?' + query : '');
    }

    function applyPageState(data) {
        // A column drag holds references to the header cells, so skip the
        // table update mid-drag; the next soft-nav or SSE ping catches up.
        if (!isColumnDragInProgress()) {
            table.innerHTML = data.table_html;
            table.classList.toggle('project-table--grouped', !!data.groups);
            table.dataset.tableKey = data.table_key;
            window.__savedTableLayout = data.saved_layout;
            window.__savedDeliverableTableLayout = data.saved_deliverable_layout;
            window.__currentBaseView = data.current_base_view;
            if (window.helixRebindProjectTableColumns) {
                window.helixRebindProjectTableColumns();
            }
        }

        if (tabStrip) tabStrip.innerHTML = data.tab_strip_html;
        if (filterPanel) filterPanel.innerHTML = data.filter_panel_html;
        if (sortPanel) sortPanel.innerHTML = data.sort_panel_html;

        if (filterToggle) {
            filterToggle.classList.toggle('is-active', !!data.active_filter_count);
            filterToggle.textContent = 'Filter' + (data.active_filter_count ? ' / ' + data.active_filter_count : '');
        }
        if (sortToggle) {
            sortToggle.classList.toggle('is-active', !!data.sort_badge_count);
            sortToggle.textContent = 'Sort' + (data.sort_badge_count ? ' / ' + data.sort_badge_count : '');
        }
        if (showCancelledToggle) {
            showCancelledToggle.classList.toggle('is-active', !!data.show_cancelled);
        }
        if (saveNewViewBtn) {
            saveNewViewBtn.hidden = !data.is_dirty;
        }
        // Keep the typed search and re-apply it to the new rows.
        applyClientSearch();
    }

    // Only the latest request may touch the DOM, so fast clicks can't apply stale data.
    let pageStateRequestId = 0;

    function syncPageStateFromLocation(url, { onDone } = {}) {
        const requestId = ++pageStateRequestId;
        fetch(toPageStateUrl(url))
            .then((res) => {
                if (!res.ok) throw new Error('page-state fetch failed: ' + res.status);
                // res.url is the URL after any redirect (a saved view replaying
                // its filters, see page_state() in project_list.py); the
                // address bar should show that query.
                const finalQuery = new URL(res.url, window.location.origin).search;
                return res.json().then((data) => ({ data, finalQuery }));
            })
            .then(({ data, finalQuery }) => {
                if (requestId !== pageStateRequestId) return;
                applyPageState(data);
                if (onDone) onDone(finalQuery, false);
            })
            .catch((err) => {
                if (requestId !== pageStateRequestId) return;
                // Also catches errors thrown in applyPageState(). The caller
                // falls back to a full reload, which hides the cause, so log it.
                console.error('page-state sync failed, falling back to a full navigation:', err);
                if (onDone) onDone(null, true);
            });
    }

    function softNavigate(url) {
        // Push history first; replaceState fixes it if a saved-view redirect
        // resolved to a different query.
        history.pushState({ softNav: true }, '', url);
        syncPageStateFromLocation(url, {
            onDone: (finalQuery, failed) => {
                if (failed) {
                    // Fall back to a real navigation so the click isn't lost.
                    window.location.href = url;
                    return;
                }
                if (finalQuery && finalQuery !== window.location.search) {
                    history.replaceState({ softNav: true }, '', `${window.location.pathname}${finalQuery}`);
                }
            },
        });
    }

    if (!table) return;

    // ---- Live table refresh (SSE) ----
    // polling.js calls window.helixRefreshProjectTable(projectId) on every
    // /sse/dashboard ping while .project-list-page is on screen.
    //   - Row already showing: fetch just that row and swap its content in
    //     place (a 204 means it left the view, so remove it). Its open
    //     expand panel is untouched.
    //   - Otherwise (no projectId, or a new row): re-fetch the whole view.
    // A single-row update never moves a row or fixes a group count; the
    // next full refresh does.
    //
    // Only #project-table's innerHTML is replaced, never the element:
    // project_list_layout.js keeps column CSS variables on it and the row
    // click delegation is bound to it. Header-cell listeners do not survive,
    // so window.helixRebindProjectTableColumns must run after a swap.
    function isColumnDragInProgress() {
        return document.body.classList.contains('is-resizing-column') ||
            document.body.classList.contains('is-reordering-column');
    }

    function refreshOneRow(projectId, existingRow) {
        fetch('/projects-new/table-rows/' + projectId + window.location.search)
            .then((response) => {
                if (response.status === 204) {
                    const expandContainer = existingRow.nextElementSibling;
                    if (expandContainer && expandContainer.classList.contains('project-expand-container')) {
                        expandContainer.remove();
                    }
                    existingRow.remove();
                    return null;
                }
                return response.ok ? response.text() : null;
            })
            .then((html) => {
                if (html === null || isColumnDragInProgress()) return;
                const temp = document.createElement('div');
                temp.innerHTML = html;
                const newRow = temp.querySelector('.project-row--link');
                if (newRow) existingRow.innerHTML = newRow.innerHTML;
            })
            .catch(() => {
                // Network blip: skip; the next ping tries again.
            });
    }

    function refreshWholeTable() {
        fetch('/projects-new/table-rows' + window.location.search)
            .then((response) => (response.ok ? response.text() : null))
            .then((html) => {
                if (html === null || isColumnDragInProgress()) return;
                table.innerHTML = html;
                if (window.helixRebindProjectTableColumns) {
                    window.helixRebindProjectTableColumns();
                }
                applyClientSearch();
            })
            .catch(() => {
                // Network blip: skip; the next ping tries again.
            });
    }

    function refreshProjectTable(projectId) {
        // A column drag holds live references to the header cells; skip
        // this refresh and let the next ping catch up.
        if (isColumnDragInProgress()) return;

        const existingRow = projectId ? table.querySelector('[data-project-id="' + projectId + '"]') : null;
        if (existingRow) {
            refreshOneRow(projectId, existingRow);
        } else {
            refreshWholeTable();
        }
    }

    window.helixRefreshProjectTable = refreshProjectTable;

    table.addEventListener('click', (e) => {
        const groupHeader = e.target.closest('.project-group-header');
        if (groupHeader) {
            const groupTable = groupHeader.nextElementSibling;
            if (!groupTable || !groupTable.classList.contains('project-group-table')) return;
            const isOpen = groupHeader.getAttribute('aria-expanded') === 'true';
            groupHeader.setAttribute('aria-expanded', isOpen ? 'false' : 'true');
            groupTable.hidden = isOpen;
            return;
        }

        // Matches the outer table's expand slot and the nested C&CM customer
        // sub-table's; both share the toggle and expand-container classes.
        const expandCell = e.target.closest('.project-col-expand, .expand-customer-col-expand');
        if (expandCell) {
            const toggle = expandCell.querySelector('.project-expand-toggle');
            if (!toggle) return;

            e.preventDefault();
            e.stopPropagation();

            const row = toggle.closest('.project-row, .expand-customer-row');
            const container = row.nextElementSibling;
            if (!container || !container.classList.contains('project-expand-container')) return;

            const isOpen = toggle.getAttribute('aria-expanded') === 'true';
            if (isOpen) {
                container.hidden = true;
                toggle.setAttribute('aria-expanded', 'false');
                return;
            }

            toggle.setAttribute('aria-expanded', 'true');
            container.hidden = false;

            if (container.dataset.loaded === 'true') return;

            fetch(toggle.dataset.expandUrl)
                .then((res) => res.text())
                .then((html) => {
                    container.innerHTML = html;
                    container.dataset.loaded = 'true';
                });
            return;
        }

        // "Handed to Production" pill jumps to the Design Completed tab (every
        // project at that status, see project_list.py's design_complete
        // branch). Other pills fall through to opening the overlay.
        const statusCell = e.target.closest('.project-col-status');
        if (statusCell && statusCell.dataset.statusValue === 'Handed to Production') {
            e.preventDefault();
            e.stopPropagation();
            softNavigate('/projects-new/?view=design_complete');
            return;
        }

        // Any other click on a project row opens the overlay.
        const rowLink = e.target.closest('.project-row--link');
        if (!rowLink) return;

        e.preventDefault();
        openProjectOverlay(rowLink.dataset.projectId);
    });

    const filterToggle = document.getElementById('filter-toggle');
    const filterPanel = document.getElementById('filter-panel');

    if (filterToggle && filterPanel) {
        filterToggle.addEventListener('click', () => {
            filterPanel.hidden = !filterPanel.hidden;
            filterToggle.classList.toggle('is-open', !filterPanel.hidden);
        });

        // Close the panel on an outside click (the date picker counts as inside).
        bindGlobal(document, 'click', 'filterOutsideClick', (e) => {
            if (!filterPanel.isConnected || filterPanel.hidden) return;
            if (filterPanel.contains(e.target) || filterToggle.contains(e.target)) return;
            if (dateRangePicker && dateRangePicker.contains(e.target)) return;
            filterPanel.hidden = true;
            filterToggle.classList.remove('is-open');
        });

        function buildFilterUrl() {
            const params = new URLSearchParams();

            // Preserve whichever view tab is active — filters should never change that.
            const currentView = new URLSearchParams(window.location.search).get('view') || 'my';
            params.set('view', currentView);

            // Chip groups: one comma-separated param per group, from rows with .is-selected.
            const chipGroups = ['cs_lead', 'project_owner', 'designers', 'client', 'brief_type', 'status', 'urgency', 'team', 'design_type'];
            chipGroups.forEach((name) => {
                const selected = Array.from(
                    filterPanel.querySelectorAll(`.filter-chip-row[data-filter-group="${name}"].is-selected`)
                ).map((el) => el.dataset.filterValue);
                if (selected.length) {
                    params.set(name, selected.join(','));
                }
            });

            // Date ranges live on each date button's data-from/data-to (set by
            // the date picker below, or rendered on load), so a chip click
            // keeps them.
            const dateButtons = [
                { btn: document.getElementById('initial-deadline-filter-btn'), from: 'initial_deadline_from', to: 'initial_deadline_to' },
                { btn: document.getElementById('next-deadline-filter-btn'), from: 'next_deadline_from', to: 'next_deadline_to' },
            ];
            dateButtons.forEach(({ btn, from, to }) => {
                if (!btn) return;
                if (btn.dataset.from) params.set(from, btn.dataset.from);
                if (btn.dataset.to) params.set(to, btn.dataset.to);
            });

            // Search stays out of the URL: it filters client-side and needs
            // the full row set loaded.

            // The query is rebuilt from scratch, so carry sort/group over too.
            const currentSort = new URLSearchParams(window.location.search).get('sort');
            const currentDir = new URLSearchParams(window.location.search).get('dir');
            if (currentSort) {
                params.set('sort', currentSort);
                if (currentDir) params.set('dir', currentDir);
            }

            const currentGroup = new URLSearchParams(window.location.search).get('group');
            if (currentGroup) params.set('group', currentGroup);

            return `${window.location.pathname}?${params.toString()}`;
        }

        function applyFilters() {
            softNavigate(buildFilterUrl());
        }

        // One delegated listener for every chip and #filter-clear-all, so it
        // survives filterPanel.innerHTML being replaced on soft navigation.
        filterPanel.addEventListener('click', (e) => {
            if (e.target.closest('#filter-clear-all')) {
                // Clears filters only; sort/group have their own Clear.
                const existing = new URLSearchParams(window.location.search);
                const params = new URLSearchParams();
                params.set('view', existing.get('view') || 'my');
                if (existing.get('sort')) {
                    params.set('sort', existing.get('sort'));
                    if (existing.get('dir')) params.set('dir', existing.get('dir'));
                }
                if (existing.get('group')) params.set('group', existing.get('group'));
                softNavigate(`${window.location.pathname}?${params.toString()}`);
                return;
            }
            const chip = e.target.closest('.filter-chip-row');
            if (!chip) return;
            chip.classList.toggle('is-selected');
            applyFilters();
        });

        if (toolbarSearch) {
            toolbarSearch.addEventListener('input', applyClientSearch);
        }
        if (searchClear && toolbarSearch) {
            searchClear.addEventListener('click', () => {
                toolbarSearch.value = '';
                applyClientSearch();
                toolbarSearch.focus();
            });
        }

        // ---- Show Cancelled toggle ----
        // Sets the status filter to exactly Cancelled (replacing any other
        // status); clicking again clears status. Other URL params survive.
        const showCancelledToggle = document.getElementById('show-cancelled-toggle');
        if (showCancelledToggle) {
            showCancelledToggle.addEventListener('click', () => {
                const params = new URLSearchParams(window.location.search);
                const currentStatus = (params.get('status') || '').split(',').filter(Boolean);
                const isCancelledOnly = currentStatus.length === 1 && currentStatus[0] === 'Cancelled';
                if (isCancelledOnly) {
                    params.delete('status');
                } else {
                    params.set('status', 'Cancelled');
                }
                softNavigate(`${window.location.pathname}?${params.toString()}`);
            });
        }

        // ---- Save current filters/sort/group as a new tab ----
        const saveNewViewBtn = document.getElementById('save-new-view-btn');
        if (saveNewViewBtn) {
            saveNewViewBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const existingPopover = document.getElementById('save-view-popover');
                if (existingPopover) {
                    existingPopover.remove();
                    return;
                }

                const popover = document.createElement('div');
                popover.id = 'save-view-popover';
                popover.className = 'save-view-popover';
                popover.innerHTML = `
                    <input type="text" class="save-view-popover-input" placeholder="View name" maxlength="100">
                    <div class="save-view-popover-actions">
                        <button type="button" class="save-view-popover-save">Save</button>
                        <button type="button" class="save-view-popover-cancel">Cancel</button>
                    </div>
                `;
                saveNewViewBtn.insertAdjacentElement('afterend', popover);
                const input = popover.querySelector('.save-view-popover-input');
                input.focus();

                function closePopover() {
                    popover.remove();
                    document.removeEventListener('click', outsideClose);
                }
                function outsideClose(ev) {
                    if (popover.contains(ev.target) || saveNewViewBtn.contains(ev.target)) return;
                    closePopover();
                }
                document.addEventListener('click', outsideClose);

                popover.querySelector('.save-view-popover-cancel').addEventListener('click', (ev) => {
                    ev.preventDefault();
                    ev.stopPropagation();
                    closePopover();
                });

                popover.querySelector('.save-view-popover-save').addEventListener('click', (ev) => {
                    ev.preventDefault();
                    ev.stopPropagation();
                    const name = input.value.trim();
                    if (!name) return;

                    // Every URL param except `view` is saved with the tab and
                    // replayed on landing (project_list.py's fresh-landing redirect).
                    const params = new URLSearchParams(window.location.search);
                    params.delete('view');
                    const filters = {};
                    params.forEach((value, key) => { filters[key] = value; });

                    fetch(saveNewViewBtn.dataset.createViewUrl, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            name,
                            base_view: window.__currentBaseView || 'my',
                            filters,
                        }),
                    })
                        .then((res) => res.json())
                        .then((data) => {
                            if (data.id) {
                                softNavigate(`${window.location.pathname}?view=view-${data.id}`);
                            }
                        });
                });

                input.addEventListener('keydown', (ev) => {
                    if (ev.key === 'Enter') popover.querySelector('.save-view-popover-save').click();
                    if (ev.key === 'Escape') closePopover();
                });
            });
        }

        // ---- Tab strip: plain tab clicks, saved-view rename / delete ----
        // One delegated listener, so it survives tabStrip.innerHTML being
        // replaced on soft navigation. The active tab class is `active`
        // (_tab_strip.html), not `is-active`.
        if (tabStrip) {
            tabStrip.addEventListener('click', (e) => {
                const menuBtn = e.target.closest('.project-list-tab-menu-btn');
                if (menuBtn) {
                    e.preventDefault();
                    e.stopPropagation();
                    const menu = menuBtn.closest('.project-list-tab-wrap').querySelector('.project-list-tab-menu');
                    tabStrip.querySelectorAll('.project-list-tab-menu').forEach((m) => {
                        if (m !== menu) m.hidden = true;
                    });
                    menu.hidden = !menu.hidden;
                    return;
                }

                const menuItem = e.target.closest('.project-list-tab-menu-item');
                if (menuItem) {
                    e.preventDefault();
                    e.stopPropagation();
                    const wrap = menuItem.closest('.project-list-tab-wrap');
                    const menu = wrap.querySelector('.project-list-tab-menu');
                    const label = wrap.querySelector('.project-list-tab-label');
                    const viewId = wrap.dataset.viewId;
                    menu.hidden = true;
                    if (!label || !viewId) return;

                    if (menuItem.dataset.action === 'rename') {
                        const currentName = label.textContent.trim();
                        const input = document.createElement('input');
                        input.type = 'text';
                        input.className = 'project-list-tab-rename-input';
                        input.value = currentName;
                        label.replaceWith(input);
                        input.focus();
                        input.select();

                        const commit = () => {
                            const newName = input.value.trim();
                            if (!newName || newName === currentName) {
                                input.replaceWith(label);
                                return;
                            }
                            fetch(`/projects-new/views/${viewId}/rename`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ name: newName }),
                            }).then(() => syncPageStateFromLocation(window.location.pathname + window.location.search));
                        };
                        input.addEventListener('keydown', (ev) => {
                            if (ev.key === 'Enter') input.blur();
                            if (ev.key === 'Escape') { input.value = currentName; input.blur(); }
                        });
                        input.addEventListener('blur', commit, { once: true });
                    }

                    if (menuItem.dataset.action === 'delete') {
                        // Small inline confirm, matching this page's popovers.
                        let confirmBox = wrap.querySelector('.project-list-tab-confirm-delete');
                        if (confirmBox) return;

                        confirmBox = document.createElement('div');
                        confirmBox.className = 'project-list-tab-confirm-delete';
                        confirmBox.innerHTML = `
                            <span>Delete this view?</span>
                            <button type="button" class="project-list-tab-confirm-yes">Delete</button>
                            <button type="button" class="project-list-tab-confirm-no">Cancel</button>
                        `;
                        wrap.appendChild(confirmBox);
                    }
                    return;
                }

                const confirmYes = e.target.closest('.project-list-tab-confirm-yes');
                if (confirmYes) {
                    e.preventDefault();
                    e.stopPropagation();
                    const wrap = confirmYes.closest('.project-list-tab-wrap');
                    const viewId = wrap.dataset.viewId;
                    const wasActive = wrap.classList.contains('active');
                    fetch(`/projects-new/views/${viewId}/delete`, { method: 'POST' })
                        .then(() => {
                            if (wasActive) {
                                softNavigate(`${window.location.pathname}?view=my`);
                            } else {
                                syncPageStateFromLocation(window.location.pathname + window.location.search);
                            }
                        });
                    return;
                }

                const confirmNo = e.target.closest('.project-list-tab-confirm-no');
                if (confirmNo) {
                    e.preventDefault();
                    e.stopPropagation();
                    confirmNo.closest('.project-list-tab-confirm-delete').remove();
                    return;
                }

                // Plain tab click: soft-navigate. Checked last because the
                // menu and confirm buttons above sit inside the same tab markup.
                const tabLink = e.target.closest('.tab-strip-item');
                if (tabLink && tabLink.tagName === 'A') {
                    e.preventDefault();
                    softNavigate(tabLink.href);
                }
            });

            // Close any open tab menu on an outside click.
            bindGlobal(document, 'click', 'tabMenuOutsideClick', (e) => {
                if (!tabStrip.isConnected || tabStrip.contains(e.target)) return;
                tabStrip.querySelectorAll('.project-list-tab-menu').forEach((m) => { m.hidden = true; });
            });
        }

        const searchToggle = document.getElementById('search-toggle');
        if (searchToggle && toolbarSearch) {
            searchToggle.addEventListener('click', () => {
                toolbarSearch.hidden = !toolbarSearch.hidden;
                if (toolbarSearch.hidden) {
                    if (searchClear) searchClear.hidden = true;
                } else {
                    toolbarSearch.focus();
                    if (searchClear) searchClear.hidden = !toolbarSearch.value;
                }
            });
        }
        // Apply any server-rendered search value on load (and set clear state).
        applyClientSearch();

        const newProjectBtn = document.getElementById('new-project-btn');
        if (newProjectBtn) {
            newProjectBtn.addEventListener('click', () => {
                openNewProjectOverlay();
            });
        }

        // ---- Sort ----
        const sortToggle = document.getElementById('sort-toggle');
        const sortPanel = document.getElementById('sort-panel');

        if (sortToggle && sortPanel) {
            sortToggle.addEventListener('click', (e) => {
                e.stopPropagation();
                sortPanel.hidden = !sortPanel.hidden;
                sortToggle.classList.toggle('is-open', !sortPanel.hidden);
            });

            // Close on outside click.
            bindGlobal(document, 'click', 'sortOutsideClick', (e) => {
                if (!sortPanel.isConnected || sortPanel.hidden) return;
                if (sortPanel.contains(e.target) || sortToggle.contains(e.target)) return;
                sortPanel.hidden = true;
                sortToggle.classList.remove('is-open');
            });

            // Sort/group options apply at once, editing only their own URL
            // params. #sort-clear-all is handled here too, so it survives
            // sortPanel.innerHTML being replaced on soft navigation.
            sortPanel.addEventListener('click', (e) => {
                if (e.target.closest('#sort-clear-all')) {
                    // Clears both sort and group; they share this button.
                    const params = new URLSearchParams(window.location.search);
                    params.delete('sort');
                    params.delete('dir');
                    params.delete('group');
                    softNavigate(`${window.location.pathname}?${params.toString()}`);
                    return;
                }

                const option = e.target.closest('.project-sort-option');
                if (option) {
                    const params = new URLSearchParams(window.location.search);
                    params.set('sort', option.dataset.sortField);
                    params.set('dir', option.dataset.sortDir);
                    softNavigate(`${window.location.pathname}?${params.toString()}`);
                    return;
                }

                // Group by is its own param; clicking the active option clears it.
                const groupOption = e.target.closest('.project-group-option');
                if (groupOption) {
                    const params = new URLSearchParams(window.location.search);
                    const field = groupOption.dataset.groupField;
                    if (params.get('group') === field) {
                        params.delete('group');
                    } else {
                        params.set('group', field);
                    }
                    softNavigate(`${window.location.pathname}?${params.toString()}`);
                }
            });
        }
        // ---- Date range picker (Initial Deadline / Next Deadline) ----
        const dateRangePicker = document.getElementById('date-range-picker');
        const dateRangeTitle = document.getElementById('date-range-picker-title');
        const dateRangePrev = document.getElementById('date-range-prev');
        const dateRangeNext = document.getElementById('date-range-next');
        const dateRangeClear = document.getElementById('date-range-clear');
        const dateRangeCancel = document.getElementById('date-range-cancel');
        const dateRangeApply = document.getElementById('date-range-apply');
        const monthLabels = document.querySelectorAll('[data-month-label]');
        const monthDayGrids = document.querySelectorAll('[data-days]');

        if (dateRangePicker && dateRangeTitle && dateRangePrev && dateRangeNext &&
            dateRangeClear && dateRangeCancel && dateRangeApply) {

            // The trigger button (Initial / Next Deadline) that opened the picker.
            let activeDateBtn = null;

            // The left-hand month on screen (0-indexed month, as in Date).
            let viewYear = null;
            let viewMonth = null;

            // In-progress selection; written to the button only on Apply.
            let rangeStart = null;
            let rangeEnd = null;

            function toISO(date) {
                const y = date.getFullYear();
                const m = String(date.getMonth() + 1).padStart(2, '0');
                const d = String(date.getDate()).padStart(2, '0');
                return `${y}-${m}-${d}`;
            }

            // Parses "YYYY-MM-DD" as a LOCAL date. `new Date(iso)` parses as
            // UTC and can land on the wrong day.
            function fromISO(iso) {
                const [y, m, d] = iso.split('-').map(Number);
                return new Date(y, m - 1, d);
            }

            function sameDay(a, b) {
                return a && b && a.getFullYear() === b.getFullYear() &&
                    a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
            }

            // One month's 42-cell grid (6 weeks, Monday first), padded with
            // the neighbouring months' days.
            function buildMonthCells(year, month) {
                const firstOfMonth = new Date(year, month, 1);
                const firstWeekday = (firstOfMonth.getDay() + 6) % 7; // Mon = 0 ... Sun = 6
                const gridStart = new Date(year, month, 1 - firstWeekday);

                const cells = [];
                for (let i = 0; i < 42; i++) {
                    cells.push(new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + i));
                }
                return cells;
            }

            function renderMonth(labelEl, gridEl, year, month) {
                labelEl.textContent = new Date(year, month, 1)
                    .toLocaleString('default', { month: 'long', year: 'numeric' });

                gridEl.innerHTML = '';
                const today = new Date();

                buildMonthCells(year, month).forEach((date) => {
                    const cell = document.createElement('button');
                    cell.type = 'button';
                    cell.className = 'date-range-picker-day';
                    cell.textContent = date.getDate();
                    cell.dataset.iso = toISO(date);

                    if (date.getMonth() !== month) cell.classList.add('is-other-month');
                    if (sameDay(date, today)) cell.classList.add('is-today');
                    if (sameDay(date, rangeStart)) cell.classList.add('is-range-start');
                    if (sameDay(date, rangeEnd)) cell.classList.add('is-range-end');
                    if (rangeStart && rangeEnd && date > rangeStart && date < rangeEnd) {
                        cell.classList.add('is-in-range');
                    }

                    gridEl.appendChild(cell);
                });
            }

            function renderCalendar() {
                renderMonth(monthLabels[0], monthDayGrids[0], viewYear, viewMonth);
                const next = new Date(viewYear, viewMonth + 1, 1);
                renderMonth(monthLabels[1], monthDayGrids[1], next.getFullYear(), next.getMonth());
            }

            function openPicker(btn) {
                activeDateBtn = btn;
                dateRangeTitle.textContent =
                    btn.dataset.paramPrefix === 'initial_deadline' ? 'Initial Deadline' : 'Next Deadline';

                // Start from the range already applied, if any.
                rangeStart = btn.dataset.from ? fromISO(btn.dataset.from) : null;
                rangeEnd = btn.dataset.to ? fromISO(btn.dataset.to) : null;

                const anchor = rangeStart || new Date();
                viewYear = anchor.getFullYear();
                viewMonth = anchor.getMonth();

                renderCalendar();
                dateRangePicker.hidden = false;
            }

            function closePicker() {
                dateRangePicker.hidden = true;
                activeDateBtn = null;
            }

            [document.getElementById('initial-deadline-filter-btn'), document.getElementById('next-deadline-filter-btn')]
                .forEach((btn) => {
                    if (!btn) return;
                    btn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        if (activeDateBtn === btn && !dateRangePicker.hidden) {
                            closePicker();
                            return;
                        }
                        openPicker(btn);
                    });
                });

            dateRangePrev.addEventListener('click', () => {
                const prev = new Date(viewYear, viewMonth - 1, 1);
                viewYear = prev.getFullYear();
                viewMonth = prev.getMonth();
                renderCalendar();
            });

            dateRangeNext.addEventListener('click', () => {
                const next = new Date(viewYear, viewMonth + 1, 1);
                viewYear = next.getFullYear();
                viewMonth = next.getMonth();
                renderCalendar();
            });

            // One delegated listener for every day cell in both months.
            dateRangePicker.addEventListener('click', (e) => {
                const cell = e.target.closest('.date-range-picker-day');
                if (!cell) return;
                e.stopPropagation();

                const clicked = fromISO(cell.dataset.iso);

                if (!rangeStart || (rangeStart && rangeEnd)) {
                    rangeStart = clicked;
                    rangeEnd = null;
                } else if (clicked < rangeStart) {
                    // Second click before the first: swap so start is earlier.
                    rangeEnd = rangeStart;
                    rangeStart = clicked;
                } else {
                    rangeEnd = clicked;
                }
                renderCalendar();
            });

            dateRangeClear.addEventListener('click', () => {
                rangeStart = null;
                rangeEnd = null;
                renderCalendar();
            });

            dateRangeCancel.addEventListener('click', () => {
                closePicker();
            });

            dateRangeApply.addEventListener('click', () => {
                if (!activeDateBtn || !rangeStart) {
                    closePicker();
                    return;
                }
                activeDateBtn.dataset.from = toISO(rangeStart);
                activeDateBtn.dataset.to = toISO(rangeEnd || rangeStart);
                closePicker();
                applyFilters();
            });

            // Close on outside click, ignoring the two trigger buttons (they toggle it).
            bindGlobal(document, 'click', 'datePickerOutsideClick', (e) => {
                if (!dateRangePicker.isConnected || dateRangePicker.hidden) return;
                if (dateRangePicker.contains(e.target)) return;
                if (e.target.closest('#initial-deadline-filter-btn') || e.target.closest('#next-deadline-filter-btn')) return;
                closePicker();
            });
        }
    }
})();