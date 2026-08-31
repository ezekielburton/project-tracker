// app/static/js/project_list.js
//
// Projects page — row expansion. One click listener on the table handles
// every row (event delegation), rather than attaching a listener per row —
// consistent with the client-side performance principles locked at the
// start of this build.

(() => {
    // ---- Detail + Briefing overlay: open/close + URL state ----
    // Real click-to-open wiring (M3 Step 2) — replaces the old full-page
    // navigation to project_detail.detail with an overlay fetched and
    // injected on demand, addressable via a `project=<id>` query param so
    // links/refreshes/back-forward all keep working (architecture doc §1).
    // Deliberately declared above the `if (!table) return` guard below —
    // the overlay mount isn't inside the table, so it must still work on
    // an empty-state page (e.g. a direct link into a filtered, empty view).

    const overlayMount = document.getElementById('project-overlay-mount');
    let activeOverlay = null;
    let activeSubTabCard = null;   // whichever sub-tab's card module is currently mounted (Details, Deliverables, ...)
    let activeOverlayEdit = null;  // M4 edit-mode handle — reset (not destroyed) on every sub-tab switch, see loadSubTabContent
    let activeChatPanel = null;    // M10 chat redesign — the persistent drawer's controller, independent of activeSubTabCard

    // ---- Detail + Briefing overlay: remember last section + sub-tab ----
    // Per-project localStorage, same kebab-case-plus-projectId key shape
    // project_submissions_card.js's own scope-memory already uses. Written
    // on every rail click (main tab or sub-tab), not just on close, so a
    // mid-session refresh or browser-back doesn't lose the last spot. The
    // read side (acting on this to restore the view on open) is a
    // separate, later chunk — this one only wires up the writes.
    function lastViewKey(projectId) {
        return 'overlay-last-view-' + projectId;
    }

    function saveLastView(projectId, section, subTab) {
        try {
            localStorage.setItem(lastViewKey(projectId), JSON.stringify({ section: section, subTab: subTab }));
        } catch (e) {
            // localStorage unavailable (private browsing, quota, etc.) —
            // silently falls back to today's hardcoded Design/Details default.
        }
    }

    function getLastView(projectId) {
        try {
            return JSON.parse(localStorage.getItem(lastViewKey(projectId)) || 'null');
        } catch (e) {
            return null;
        }
    }

    // Registry of sub-tab content loaders, keyed by the subrail button's
    // data-sub-tab value. Submissions/Pre-Production aren't built yet
    // (later M3 steps) — clicking them just changes the active tab
    // styling with no content swap until they get an entry here.
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
        // Key is 'pre-production' (hyphenated) — matches the rail button's
        // data-sub-tab value in _overlay.html exactly, since that value is
        // read straight off the DOM and used as this object's key.
        'pre-production': {
            url: (projectId) => `/projects/${projectId}/overlay/preproduction`,
            module: () => window.ProjectPreproductionCard,
        },
    };

    // Task #37 — the guard passed into ProjectOverlay.init as onBeforeNavigate.
    // Only project_list.js knows about activeOverlayEdit, so this is where
    // the check has to live; project_overlay.js just calls it before any
    // navigation that would tear out the edit-mode DOM (close, sub-tab
    // switch) and trusts it to call proceed() when it's actually safe to go.
    function guardUnsavedEdit(proceed) {
        if (activeOverlayEdit && activeOverlayEdit.isEditing() && activeOverlayEdit.hasUnsavedChanges()) {
            // M10: showConfirm/#confirm-modal load on every page via
            // base.html, so the native window.confirm() fallback this used
            // to have was dead code — dropped.
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

        // Any sub-tab switch invalidates edit mode — the DOM it was
        // editing is about to be torn out from under it either way. Reset
        // now so the header (Edit/Save/Cancel) can't end up stuck showing
        // Save/Cancel over content that isn't actually in edit state
        // (e.g. Edit clicked on Deliverables, then navigate back to
        // Details). No confirm here — that's task #37's job once there's
        // a real "unsaved changes" guard to build.
        if (activeOverlayEdit) {
            activeOverlayEdit.exitEditMode();
        }

        // Edit module (M4) is scoped to Details only (17 Aug 2026) —
        // Deliverables already has its own separate structural edit mode
        // (Step 3), Submissions/Pre-Production don't need field editing.
        // Hide the header's Edit control outside Details.
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

        // Edit button only makes sense on Details — hide it here too, same as
        // every non-Details sub-tab already does.
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

    // Chat drawer (M10 chat redesign) — independent of loadNotesSection/
    // loadSubTabContent above: the drawer is reachable from any rail tab,
    // not a section of its own, so its content lives in its own container
    // (#project-overlay-chat-content) and is never touched by a sub-tab
    // switch. Called once by project_overlay.js's onChatOpened the first
    // time someone opens the drawer for this overlay session, and again
    // any time the panel itself needs a fresh fetch (send/delete, and —
    // once the live-update hookup lands — an incoming SSE ping while open).
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

    // Cancel / Reactivate + Put on Hold / Resume — wired once per overlay
    // open (the sidebar isn't re-rendered on sub-tab switches, so this
    // can't live in a per-sub-tab card module like project_details_card.js).
    // Each button pair is dual-rendered (both states in the DOM, one
    // hidden) and toggled directly on success — cheaper than refetching
    // the whole sidebar, and mirrors the header's Edit/Save/Cancel pattern.
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

        // After any lifecycle change, refresh Details content if that's
        // the tab currently showing — it's the only sub-tab with a status
        // pill / cancellation banner to keep in sync.
        function refreshDetailsIfActive() {
            const lastView = getLastView(projectId);
            if (lastView && lastView.section === 'design' && (lastView.subTab || 'details') === 'details') {
                loadSubTabContent(projectId, 'details');
            }
        }

        // ── Flag Issue (project-level) — same inline reveal-form pattern
        // as Cancel Project. Raising is the only action here; replying/
        // resolving/history still happen on the Details tab itself (see
        // project_flags.js), since those need the full flag list to work with. ──
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
                window.showConfirm('Put this project on hold?', go); // M10: dropped dead native-confirm fallback
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

        // Open Project Folder (Synology Drive, M10 NAS migration, 21 Aug 2026) —
        // click-triggered, see main.js's openNasLink().
        const openFolderBtn = sidebarEl.querySelector('#overlay-open-folder-btn');
        if (openFolderBtn) {
            openFolderBtn.addEventListener('click', () => openNasLink(openFolderBtn));
        }

        // Request Editing Access (26 Aug 2026, per Ezekiel) — single button,
        // no confirm gate (unlike Cancel/Hold, this isn't destructive — it's
        // just asking). Flips itself to the disabled "pending" state
        // in-place on success rather than waiting for the sidebar's next
        // full render, same optimistic-update approach as Hold/Cancel below.
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
                // A reason was already required, but that's not the same as a
                // confirmation — nothing stopped a stray click on "Confirm
                // Cancel" from firing immediately. 24 Aug 2026 (per Ezekiel,
                // "add redundancy to the cancel process"): gate the actual
                // request behind window.showConfirm(), same as every other
                // destructive action here (Put on Hold above, delete draft,
                // etc.).
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

    function openProjectOverlay(projectId, pushHistory = true) {
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
                    // in project_list.js, openProjectOverlay()'s onSectionSelected callback:
                    // defaultSubTabKey is project_overlay.js's freshly-picked
                    // FIRST sub-category for whichever section was just
                    // clicked (null for sections with no sub-tab strip,
                    // e.g. Notes, or Finance/Production/Logistics today).
                    // Actually loading it here — not just remembering it —
                    // is the fix for the "click Design, click Details,
                    // nothing happens" bug: previously this branch only
                    // ever called saveLastView(), never loadSubTabContent(),
                    // so the content pane kept showing whatever the
                    // PREVIOUS section had rendered until some other click
                    // happened to trigger a load.
                    function (sectionKey, defaultSubTabKey) {
                        if (sectionKey === 'design') {
                            const subTab = defaultSubTabKey || 'details';
                            saveLastView(projectId, 'design', subTab);
                            loadSubTabContent(projectId, subTab);
                        } else {
                            saveLastView(projectId, sectionKey, null);
                            if (sectionKey === 'notes') {
                                loadNotesSection(projectId);
                            }
                        }
                    },
                    guardUnsavedEdit,
                    // onChatOpened — chat is a persistent drawer, not a rail
                    // section, so this fires once (first open only, see
                    // project_overlay.js's chatLoaded) rather than every
                    // section switch.
                    function () {
                        loadChatDrawer(projectId);
                    }
                );

                // Edit mode (M4) — header (name/Edit/Save/Cancel) is part of
                // the outer shell rendered once here, not re-injected per
                // sub-tab like contentEl is, so it only needs initializing
                // once per overlay open, same as ProjectOverlay itself.
                const overlayHeader = document.getElementById('project-overlay-header');
                if (overlayHeader && window.ProjectOverlayEdit) {
                    activeOverlayEdit = window.ProjectOverlayEdit.init(overlayHeader, contentEl, projectId, function () {
                        loadSubTabContent(projectId, 'details');
                    });
                }

                // Cancel/Hold sidebar actions (task #56) — lives in the
                // persistent shell alongside the header, so wire it once
                // here too, not per sub-tab load.
                const sidebarEl = document.getElementById('project-overlay-sidebar');
                wireProjectLifecycleActions(sidebarEl, projectId);

                // Live updates (task #35) — someone else saving an edit to
                // this same project (or any other watched change — see
                // live_events.py's _PROJECT_ID_GETTERS) pings this stream.
                // Skipped while THIS viewer is mid-edit, so an incoming
                // refresh can never wipe out fields they're actively
                // typing into — the concurrent-edit check from task #34
                // already covers that case safely at Save time instead.
                if (window.helixPolling) {
                    window.helixPolling.startOverlayStream(projectId, function () {
                        // Chat drawer — independent of whichever rail section is showing underneath.
                        if (activeChatPanel && activeOverlay && activeOverlay.isChatOpen && activeOverlay.isChatOpen()) {
                            activeChatPanel.liveRefresh();
                        }

                        if (activeOverlayEdit && activeOverlayEdit.isEditing()) return;
                        const lastView = getLastView(projectId);
                        if (lastView && lastView.section === 'notes') {
                            // Notes & Visits (M9) has real content behind it,
                            // same as the Design sub-tabs below — not a
                            // placeholder section, so it needs its own live
                            // refresh instead of silently falling through to
                            // the "nothing to do" branch placeholders use.
                            loadNotesSection(projectId);
                            return;
                        }
                        const subTab = (lastView && lastView.section === 'design') ? (lastView.subTab || 'details') : null;
                        if (subTab) loadSubTabContent(projectId, subTab);
                    });
                }

                const lastView = getLastView(projectId);
                if (lastView && lastView.section === 'design' && lastView.subTab && lastView.subTab !== 'details' && SUBTAB_LOADERS[lastView.subTab]) {
                    // Remembered a real sub-tab other than the default —
                    // fetch its content fresh and sync the rail to match.
                    activeOverlay.restoreView('design', lastView.subTab);
                    loadSubTabContent(projectId, lastView.subTab);
                } else if (lastView && lastView.section === 'notes') {
                    // Notes has real content behind it (unlike Finance/Production/
                    // Logistics, still placeholders) — sync the rail AND actually fetch
                    // it, same shape as the Design-sub-tab branch above.
                    activeOverlay.restoreView('notes', null);
                    loadNotesSection(projectId);
                } else {
                    // Nothing remembered, remembered view was already 'details', or
                    // it's a still-placeholder section (Finance/Production/Logistics —
                    // no real content yet) — just sync the rail's visual state and fall
                    // back to the embedded Details content underneath.
                    if (lastView && lastView.section && lastView.section !== 'design') {
                        activeOverlay.restoreView(lastView.section, null);
                    }
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

    // Create-mode overlay (task #61) — deliberately its own pair of
    // open/close functions rather than reusing openProjectOverlay/
    // closeProjectOverlay above: those wire up ProjectOverlay.init's
    // sub-tab rail, SSE live-updates stream, and the edit-mode header,
    // none of which exist in the create-mode shell (no sub-tabs, no
    // Cancel/Hold sidebar, no lifecycle actions yet — see
    // _overlay_create.html). Keeping the two paths separate means neither
    // has to guard against the other's DOM not being there.
    function openCreateShellForDraft(projectId) {
        return fetch(`/projects/${projectId}/overlay/create`)
            .then((res) => res.text())
            .then((html) => {
                overlayMount.innerHTML = html;
                if (window.ProjectOverlayCreate) {
                    // onFinalized: after a successful Confirm on the create
                    // summary modal, open the newly-created project straight
                    // into the full live overlay.
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

    // Resumable drafts (task #65) — "+ New Project" checks for any open
    // drafts first (the creator's own, or — for admin/management —
    // anyone's) and, if there are some, shows a picker instead of
    // immediately starting a fresh one. Mirrors the confirm-summary
    // modal's append-to-body/remove-on-close pattern in
    // project_overlay_create.js rather than reusing overlayMount, since
    // this picker has to exist BEFORE any create-mode shell is loaded.
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
                window.showConfirm('Delete this draft? This cannot be undone.', () => { // M10: was bare window.confirm()
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
                                // Last one just got deleted — leave the picker
                                // open (don't presume they want a new project
                                // right now just because they cleaned up an old
                                // one) with just Cancel / Start New left to
                                // choose from.
                                const list = modal.querySelector('.overlay-create-drafts-list');
                                if (list) list.remove();
                                const intro = modal.querySelector('.overlay-submit-summary-intro');
                                if (intro) intro.textContent = 'No drafts left. Start a new project, or cancel below.';
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

    // Browser Back/Forward: re-derive open/closed state from the URL
    // rather than trusting the popstate event's direction, since the user
    // could navigate multiple steps at once.
    window.addEventListener('popstate', () => {
        const params = new URLSearchParams(window.location.search);
        const projectId = params.get('project');
        if (projectId) {
            openProjectOverlay(projectId, false);
        } else {
            closeProjectOverlay(false);
        }
        // Re-sync the tab strip / filter+sort panels / table from wherever
        // Back/Forward just landed — a soft-navigated view/filter/sort
        // change is a history entry too (see softNavigate below), so this
        // has to cover it the same way the overlay branch above does.
        // No history write here — the browser already moved; this only
        // patches the DOM to match.
        syncPageStateFromLocation(window.location.pathname + window.location.search, {
            onDone: (finalQuery, failed) => {
                if (!failed && finalQuery && finalQuery !== window.location.search) {
                    history.replaceState({ softNav: true }, '', `${window.location.pathname}${finalQuery}`);
                }
            },
        });
    });

    // Direct load / refresh with `?project=<id>` already in the URL —
    // every inbound link (notifications, achievements, escalations) will
    // depend on this once the old detail page is deleted at M10.
    (function autoOpenFromUrl() {
        const params = new URLSearchParams(window.location.search);
        const projectId = params.get('project');
        if (projectId) openProjectOverlay(projectId, false);
    })();

    // ---- Row expansion + row-click-to-open (existing table, unchanged structure) ----

    const table = document.querySelector('.project-table');

    // ---- Soft navigation: tabs / filters / sort / group / search / show-cancelled ----
    // Added 28 Aug 2026, per Ezekiel: "can we have this spa injected too?"
    // — every one of these previously did `window.location.href = url`, a
    // full page reload (the original complaint was specifically about
    // switching view tabs, but every other toolbar control did the exact
    // same full-reload thing, so this covers all of them). Now they fetch
    // /projects-new/page-state and patch the existing DOM instead.
    //
    // #filter-panel, #sort-panel and .tab-strip only ever get their
    // INNERHTML replaced below — never the elements themselves — so the
    // delegated listeners already bound directly on them (chip clicks and
    // #filter-clear-all on filterPanel; sort/group option clicks and
    // #sort-clear-all on sortPanel; tab/menu/confirm clicks on tabStrip)
    // keep working with no re-binding needed, exactly the same reasoning
    // _table_rows.html's swap into #project-table has always relied on.
    const tabStrip = document.querySelector('.tab-strip');

    // Bug fix (28 Aug 2026, found via console error after Ezekiel reported
    // a reload-flash on soft navigation): sortToggle/sortPanel/
    // showCancelledToggle/saveNewViewBtn/toolbarSearch are declared again
    // further down, but INSIDE the nested `if (filterToggle &&
    // filterPanel) { ... }` block that wires up their listeners — a
    // block-scoped `const`, invisible up here. applyPageState() below
    // referencing that inner `sortPanel` threw "ReferenceError: sortPanel
    // is not defined" on every call, which softNavigate's catch() silently
    // swallowed before falling back to a full page reload — the actual
    // cause of the flash. These are separate, harmless duplicate
    // getElementById lookups (cheap, and this file already does the same
    // "unconditional lookup + guarded listener attachment" split for
    // filterToggle/filterPanel above) purely so applyPageState() has its
    // own outer-scope reference; the inner block's own `const` of the same
    // name still shadows these within its own listener-wiring code, untouched.
    const sortToggle = document.getElementById('sort-toggle');
    const sortPanel = document.getElementById('sort-panel');
    const showCancelledToggle = document.getElementById('show-cancelled-toggle');
    const saveNewViewBtn = document.getElementById('save-new-view-btn');
    const toolbarSearch = document.getElementById('toolbar-search');

    function toPageStateUrl(url) {
        const qIndex = url.indexOf('?');
        const query = qIndex >= 0 ? url.slice(qIndex + 1) : '';
        return '/projects-new/page-state' + (query ? '?' + query : '');
    }

    function applyPageState(data) {
        // Matches refreshWholeTable()'s existing guard below: a resize or
        // reorder drag holds direct references to the exact header-cell
        // nodes and live measurements off them, so touching the table
        // (content, table_key, or the saved-layout globals) mid-drag would
        // either freeze it or have it silently fail against now-detached
        // nodes. Skip the whole table side of this update — the next
        // soft-nav or SSE ping picks it up once the user lets go.
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
        if (toolbarSearch) {
            toolbarSearch.value = data.search || '';
        }
    }

    // requestId guards against a fast double-click (e.g. two tabs clicked
    // before the first fetch resolves) applying stale data out of order —
    // only the most recently issued request is allowed to touch the DOM.
    let pageStateRequestId = 0;

    function syncPageStateFromLocation(url, { onDone } = {}) {
        const requestId = ++pageStateRequestId;
        fetch(toPageStateUrl(url))
            .then((res) => {
                if (!res.ok) throw new Error('page-state fetch failed: ' + res.status);
                // response.url is the final URL after following any redirect
                // — the "fresh landing on a saved view replays its saved
                // filters" case (see page_state()'s docstring in
                // project_list.py) — so its query string, not the one we
                // requested, is what the address bar should end up showing.
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
                // Logged, not swallowed (28 Aug 2026) — this catch covers
                // both a real fetch/network failure AND any exception
                // thrown inside applyPageState() above (a thrown error
                // inside a .then() lands here too), and the caller's
                // onDone(..., true) falls back to a full page reload
                // either way. Without this log, that fallback silently
                // masks whatever actually went wrong — the reload lands on
                // index() and looks fine, so the only visible symptom is
                // the flash of a real navigation where a soft one was
                // expected. See it in the console instead of guessing.
                console.error('page-state sync failed, falling back to a full navigation:', err);
                if (onDone) onDone(null, true);
            });
    }

    function softNavigate(url) {
        // Optimistic history entry first, same instant-feel precedent as
        // the overlay's openProjectOverlay/closeProjectOverlay pushState
        // calls above — corrected via replaceState below only in the rare
        // saved-view-replay case where the resolved URL differs from what
        // was actually clicked.
        history.pushState({ softNav: true }, '', url);
        syncPageStateFromLocation(url, {
            onDone: (finalQuery, failed) => {
                if (failed) {
                    // Something went wrong (network blip, non-OK response)
                    // — fall back to a real navigation rather than leaving
                    // the click looking like it silently did nothing.
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

    // ---- Live table refresh (task #55, table-side SSE) ----
    // polling.js opens a stream to /sse/dashboard (the same generic "some
    // project changed somewhere" doorbell the old and new dashboards
    // already use) whenever .project-list-page is on screen, and calls
    // this on every ping via window.helixRefreshProjectTable(projectId),
    // projectId being whatever the SSE payload named (see polling.js's
    // _connectLiveStream). Two paths:
    //
    //   - projectId is already showing (a matching [data-project-id] row
    //     exists) — fetch just that project's row (table_row() in
    //     project_list.py) and update the existing row node's content in
    //     place, leaving its DOM position and its sibling
    //     .project-expand-container (any open breakdown panel) untouched.
    //   - anything else — no projectId (plain fallback-interval tick), or
    //     the project isn't in the DOM yet — re-fetch the whole view
    //     (table_rows()) and swap it into #project-table, same as before
    //     this existed. Needed for a project entering the current view for
    //     the first time, since a single-row fetch has nowhere to insert it.
    //
    // Known trade-off: a targeted update never moves a row (Group/Sort
    // position) or corrects a group header's count — those only catch up
    // on the next full refresh. Most pings are content-only changes to an
    // already-visible row, so this is the common case; something that
    // would actually reorder a row settles itself next time the page/
    // filter/sort refreshes for any other reason.
    //
    // #project-overlay-mount is a SIBLING of .project-list-page's table
    // region, not nested inside it, so replacing #project-table's content
    // never touches an open overlay.
    //
    // Only #project-table's innerHTML is replaced — never the #project-table
    // element itself — because project_list_layout.js's saved column
    // widths/order live as CSS custom properties set directly on that
    // element (see applyLayout()), and the row-click delegation just above
    // this comment is bound to it too. Both survive a content-only swap for
    // free. What does NOT survive it: the resize-handle and header-cell
    // reorder listeners, which are bound directly to the header cells
    // (not delegated) — bindColumnControls() has to re-run against the
    // fresh cells afterwards, hence window.helixRebindProjectTableColumns.
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
                // Network blip — silently skip, same as every other poll/
                // stream callback in this app. The next ping tries again.
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
            })
            .catch(() => {
                // Network blip — silently skip, same as every other poll/
                // stream callback in this app. The next ping tries again.
            });
    }

    function refreshProjectTable(projectId) {
        // A resize or reorder drag holds direct references to the exact
        // header-cell nodes being dragged and reads live measurements off
        // them every animation frame — replacing them mid-drag would either
        // freeze it or have it silently fail against now-detached nodes.
        // Simplest safe fix: skip this one refresh. Nothing is lost — the
        // next SSE ping picks up whatever changed once the user lets go.
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

        // Matches both the outer table's expand slot (.project-col-expand /
        // .project-row) and the nested C&CM customer sub-table's expand slot
        // (.expand-customer-col-expand / .expand-customer-row) — the two
        // tables share the same toggle button class and expand-container
        // pattern, they just wrap it in different column/row classes.
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

        // Handed to Production pill — jumps to the Design Completed tab
        // instead of opening the overlay, since that tab is exactly "every
        // project currently at this status" (see project_list.py's
        // design_complete branch). Retargeted from the old 'Design
        // Completed' pill value (22 Aug 2026 simplification, per Ezekiel)
        // — that separate label is gone, 'Handed to Production' is now the
        // one pill value that lands here for both Standard and C&CM. Every
        // other status pill still falls through to the normal
        // row-opens-overlay behavior below.
        const statusCell = e.target.closest('.project-col-status');
        if (statusCell && statusCell.dataset.statusValue === 'Handed to Production') {
            e.preventDefault();
            e.stopPropagation();
            softNavigate('/projects-new/?view=design_complete');
            return;
        }

        // Not the expand toggle — a click anywhere else on a project row
        // opens the overlay instead of navigating to the old detail page.
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

        // Close the panel on any click outside it, so it doesn't stay open
        // hovering over the table while someone's trying to do something else.
        document.addEventListener('click', (e) => {
            if (filterPanel.hidden) return;
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

            // Multi-value chip groups: one comma-separated param per group,
            // read from whichever chip rows currently carry .is-selected —
            // replaces the old checkbox :checked reads now that these are
            // buttons, not inputs.
            const chipGroups = ['cs_lead', 'project_owner', 'designers', 'client', 'brief_type', 'status', 'urgency', 'team', 'design_type'];
            chipGroups.forEach((name) => {
                const selected = Array.from(
                    filterPanel.querySelectorAll(`.filter-chip-row[data-filter-group="${name}"].is-selected`)
                ).map((el) => el.dataset.filterValue);
                if (selected.length) {
                    params.set(name, selected.join(','));
                }
            });

            // Date-range pairs aren't editable yet (the calendar picker isn't
            // built), but whatever's already active is sitting on the date
            // button's own data-from/data-to attributes (rendered from
            // active_filters on page load) — read those so toggling a chip
            // elsewhere never silently wipes an existing date filter.
            const dateButtons = [
                { btn: document.getElementById('initial-deadline-filter-btn'), from: 'initial_deadline_from', to: 'initial_deadline_to' },
                { btn: document.getElementById('next-deadline-filter-btn'), from: 'next_deadline_from', to: 'next_deadline_to' },
            ];
            dateButtons.forEach(({ btn, from, to }) => {
                if (!btn) return;
                if (btn.dataset.from) params.set(from, btn.dataset.from);
                if (btn.dataset.to) params.set(to, btn.dataset.to);
            });

            const searchEl = document.querySelector('[name="search"]');
            if (searchEl && searchEl.value.trim()) {
                params.set('search', searchEl.value.trim());
            }

            // Same idea as the view tab above — this function rebuilds the
            // whole query string from scratch, so without this, clicking any
            // filter chip would silently wipe out whatever sort/group was active.
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

        // Clicking any chip row toggles its own selected state, then applies
        // instantly — one delegated listener on the whole panel handles
        // every group (and, since 28 Aug 2026, #filter-clear-all too —
        // folded in here rather than bound separately, so it survives
        // filterPanel.innerHTML getting replaced on every soft navigation;
        // see applyPageState() above), rather than one listener per chip.
        filterPanel.addEventListener('click', (e) => {
            if (e.target.closest('#filter-clear-all')) {
                // Clears filters only — sort/group are a separate control
                // with its own Clear button, so they stay active across this click.
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

        // Search debounces instead — reloading the page on every keystroke
        // would be a rough experience, so wait for a short pause after typing
        // stops before actually navigating.
        const searchInput = document.querySelector('[name="search"]');
        if (searchInput) {
            let searchTimeout;
            searchInput.addEventListener('input', () => {
                clearTimeout(searchTimeout);
                searchTimeout = setTimeout(applyFilters, 400);
            });
        }

        // ---- Show Cancelled toggle ----
        // Shortcut for "set the status filter to exactly Cancelled" — same
        // effect as picking the Cancelled chip in the filter panel by hand,
        // just one click instead of opening the panel. Filters to cancelled
        // projects ONLY (replaces whatever status selection was active,
        // rather than adding to it) — every OTHER filter dimension (client,
        // designers, etc.) still combines on top normally, and clicking
        // again clears status back out. Reads current URL and reloads, same
        // "read, mutate one thing, reload" pattern as the Sort panel below,
        // so everything else active (filters, sort, group) survives.
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

                    // Everything currently in the URL except `view` itself is
                    // this new tab's remembered filter/sort/group selection —
                    // replayed as real query params the moment someone lands
                    // on this tab (see project_list.py's fresh-landing redirect).
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
        // One delegated listener on tabStrip (28 Aug 2026, replacing what
        // was a per-element .forEach(wrap => ...) bind) — tabStrip.innerHTML
        // gets replaced on every soft navigation (see applyPageState above),
        // which would otherwise silently drop these listeners the first
        // time a tab, filter, sort, or search changed. Delegation means
        // they never need re-binding.
        //
        // Bug fix in the same pass: the delete-confirm handler used to
        // check `wrap.classList.contains('is-active')` to decide whether
        // the view being deleted was the current one — but the class this
        // markup actually sets (_tab_strip.html) is `active`, not
        // `is-active`, so that check was always false and deleting the
        // active saved view fell through to a full reload instead of
        // redirecting to My Projects.
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
                        // Small inline confirm, not window.confirm() — keeps
                        // every popover on this page the same custom style.
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

                // Plain tab click (My Projects / All-or-Team / Design
                // Completed / a saved view's own link) — soft-navigate
                // instead of a full page reload. Checked last so it never
                // shadows the menu-btn/menu-item/confirm buttons above,
                // all of which sit inside the same .tab-strip-item /
                // .project-list-tab-wrap markup.
                const tabLink = e.target.closest('.tab-strip-item');
                if (tabLink && tabLink.tagName === 'A') {
                    e.preventDefault();
                    softNavigate(tabLink.href);
                }
            });

            // Close any open tab menu on an outside click — tabStrip's own
            // delegated handler above only sees clicks inside the tab strip.
            document.addEventListener('click', (e) => {
                if (tabStrip.contains(e.target)) return;
                tabStrip.querySelectorAll('.project-list-tab-menu').forEach((m) => { m.hidden = true; });
            });
        }

        const searchToggle = document.getElementById('search-toggle');
        const toolbarSearch = document.getElementById('toolbar-search');
        if (searchToggle && toolbarSearch) {
            searchToggle.addEventListener('click', () => {
                toolbarSearch.hidden = !toolbarSearch.hidden;
                if (!toolbarSearch.hidden) {
                    toolbarSearch.focus();
                }
            });
        }

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

            // Same "close on outside click" pattern as the filter panel above.
            document.addEventListener('click', (e) => {
                if (sortPanel.hidden) return;
                if (sortPanel.contains(e.target) || sortToggle.contains(e.target)) return;
                sortPanel.hidden = true;
                sortToggle.classList.remove('is-open');
            });

            // Picking a direction navigates straight away — same
            // instant-apply feel as clicking a filter chip. Built on top
            // of whatever's already in the URL (view, filters, search)
            // rather than rebuilding the whole query string from scratch,
            // since sort is the only thing this needs to change.
            //
            // #sort-clear-all is folded into this same delegated listener
            // (28 Aug 2026) rather than bound separately, so it survives
            // sortPanel.innerHTML getting replaced on every soft
            // navigation — same reasoning as #filter-clear-all above.
            sortPanel.addEventListener('click', (e) => {
                if (e.target.closest('#sort-clear-all')) {
                    // Clears both halves of this combined panel — Sort and
                    // Group by — since they share this one Clear button.
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

                // Group by lives in the same combined panel, but is a fully
                // independent query param from Sort — clicking a group
                // option toggles it on, clicking the already-active one
                // again clears it, same "click to toggle" feel as a filter chip.
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

            // Which trigger button (Initial Deadline / Next Deadline) opened
            // the picker — set the moment one of them is clicked.
            let activeDateBtn = null;

            // The two months currently on screen. "left" month is always
            // one month before "right" — month is 0-indexed, same as
            // native Date.
            let viewYear = null;
            let viewMonth = null;

            // The in-progress selection. Nothing is written back to the
            // triggering button until Apply is clicked — Cancel just
            // throws these away.
            let rangeStart = null;
            let rangeEnd = null;

            function toISO(date) {
                const y = date.getFullYear();
                const m = String(date.getMonth() + 1).padStart(2, '0');
                const d = String(date.getDate()).padStart(2, '0');
                return `${y}-${m}-${d}`;
            }

            // Parses "YYYY-MM-DD" as a LOCAL date. Deliberately not using
            // `new Date(isoString)` here — that form parses as UTC
            // midnight, which can land on the wrong calendar day once
            // converted back to local time depending on the visitor's
            // timezone. Splitting and building the date manually avoids
            // that entirely.
            function fromISO(iso) {
                const [y, m, d] = iso.split('-').map(Number);
                return new Date(y, m - 1, d);
            }

            function sameDay(a, b) {
                return a && b && a.getFullYear() === b.getFullYear() &&
                    a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
            }

            // Builds one month's 42-cell grid (6 weeks), starting the week
            // on Monday to match the Mo/Tu/.../Su header, and filling in
            // the previous/next month's trailing days so the grid is
            // always a full rectangle — same as Google Calendar's picker.
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

                // Pick up whatever's already applied, so re-opening shows
                // the existing selection instead of starting blank.
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

            // One delegated listener for every day cell across both months —
            // same event-delegation approach as the row-expand and
            // chip-filter handlers above, rather than one listener per cell.
            dateRangePicker.addEventListener('click', (e) => {
                const cell = e.target.closest('.date-range-picker-day');
                if (!cell) return;
                e.stopPropagation();

                const clicked = fromISO(cell.dataset.iso);

                if (!rangeStart || (rangeStart && rangeEnd)) {
                    // Starting a fresh selection.
                    rangeStart = clicked;
                    rangeEnd = null;
                } else if (clicked < rangeStart) {
                    // Second click landed before the first — swap so start
                    // is always the earlier date.
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

            // Close on outside click — same pattern as the filter panel
            // itself — but ignore clicks on the two trigger buttons, which
            // already have their own open/close/toggle logic above.
            document.addEventListener('click', (e) => {
                if (dateRangePicker.hidden) return;
                if (dateRangePicker.contains(e.target)) return;
                if (e.target.closest('#initial-deadline-filter-btn') || e.target.closest('#next-deadline-filter-btn')) return;
                closePicker();
            });
        }
    }
})();