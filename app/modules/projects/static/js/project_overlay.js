// app/modules/projects/static/js/project_overlay.js
//
// Project overlay shell: sidebar switching, the chat drawer toggle, and the
// three close paths (X, backdrop click, Esc). Works only on markup already
// in the DOM; project_list.js fetches, injects and tears down the overlay.

window.ProjectOverlay = (function () {
    // onBeforeNavigate(proceed) is the unsaved-edit guard from project_list.js.
    // Optional. It wraps close and every sidebar click.
    function init(onCloseRequested, onSubTabSelected, onSectionSelected, onBeforeNavigate, onChatOpened) {
        var backdrop = document.getElementById('project-overlay-backdrop');
        var closeBtn = document.getElementById('project-overlay-close');

        if (!backdrop) return null;

        // Lock body scroll so wheel events can't chain through to the table behind.
        document.body.classList.add('project-overlay-locked');

        function requestClose() {
            if (onBeforeNavigate) { onBeforeNavigate(onCloseRequested); } else { onCloseRequested(); }
        }

        if (closeBtn) {
            closeBtn.addEventListener('click', requestClose);
        }

        // ---- Chat drawer ----
        // Reachable from any sidebar page. Opening adds .chat-open to the
        // sheet (widens it) and .is-open to the drawer (slides it out).
        var sheet = document.getElementById('project-overlay-sheet');
        var chatBtn = document.getElementById('project-overlay-chat-btn');
        var chatDrawer = document.getElementById('project-overlay-chat-drawer');
        var chatCloseBtn = document.getElementById('project-overlay-chat-close');
        var chatLoaded = false;   // content is fetched on first open only

        function openChat() {
            if (!sheet || !chatDrawer) return;
            sheet.classList.add('chat-open');
            chatDrawer.classList.add('is-open');
            if (chatBtn) chatBtn.classList.add('is-active');
            if (!chatLoaded) {
                chatLoaded = true;
                if (onChatOpened) onChatOpened();
            }
        }

        function closeChat() {
            if (!sheet || !chatDrawer) return;
            sheet.classList.remove('chat-open');
            chatDrawer.classList.remove('is-open');
            if (chatBtn) chatBtn.classList.remove('is-active');
        }

        function isChatOpen() {
            return !!(chatDrawer && chatDrawer.classList.contains('is-open'));
        }

        if (chatBtn) {
            chatBtn.addEventListener('click', function () {
                if (isChatOpen()) { closeChat(); } else { openChat(); }
            });
        }
        if (chatCloseBtn) {
            chatCloseBtn.addEventListener('click', closeChat);
        }

        backdrop.addEventListener('click', function (e) {
            if (e.target === backdrop) requestClose();
        });

        function escHandler(e) {
            if (e.key === 'Escape') requestClose();
        }
        document.addEventListener('keydown', escHandler);

        // ---- Sidebar: one flat list ----
        // The four Design pages (sub-tab buttons, data-sub-tab) and Site
        // Visits (a section button, data-main-tab="notes"). Exactly one
        // button is active at a time across both kinds.

        var header = document.getElementById('project-overlay-header');
        var sidebar = document.getElementById('project-overlay-sidebar');
        var subgroup = document.getElementById('project-overlay-subrail');

        var restoreView = function () { };

        if (header && sidebar) {
            var mainItems = Array.prototype.slice.call(sidebar.querySelectorAll('.project-overlay-sidebar-item[data-main-tab]'));
            var subItems = subgroup
                ? Array.prototype.slice.call(subgroup.querySelectorAll('.project-overlay-sidebar-subitem'))
                : [];

            // Marks one button active and clears every other.
            function markActive(activeBtn) {
                mainItems.concat(subItems).forEach(function (b) {
                    b.classList.toggle('active', b === activeBtn);
                });
            }

            mainItems.forEach(function (btn) {
                btn.addEventListener('click', function () {
                    if (btn.classList.contains('active')) return;
                    // Same guard as the sub-tabs: switching away discards Details edits.
                    var proceed = function () {
                        markActive(btn);
                        if (onSectionSelected) onSectionSelected(btn.dataset.mainTab, null);
                    };
                    if (onBeforeNavigate) { onBeforeNavigate(proceed); } else { proceed(); }
                });
            });

            subItems.forEach(function (btn) {
                btn.addEventListener('click', function () {
                    if (btn.classList.contains('active')) return;
                    // The active flip and the content swap both wait for the
                    // unsaved-edit guard, so a cancelled switch leaves the
                    // sidebar pointing at what is actually showing.
                    var proceed = function () {
                        markActive(btn);
                        if (onSubTabSelected) onSubTabSelected(btn.dataset.subTab);
                    };
                    if (onBeforeNavigate) { onBeforeNavigate(proceed); } else { proceed(); }
                });
            });

            // Puts the sidebar back where the user last left it. A saved view
            // for a section that no longer exists changes nothing, so the
            // default (Details) stays marked.
            restoreView = function (sectionKey, subTabKey) {
                var target = null;
                if (sectionKey === 'design') {
                    subItems.forEach(function (b) {
                        if (b.dataset.subTab === subTabKey) target = b;
                    });
                } else {
                    mainItems.forEach(function (b) {
                        if (b.dataset.mainTab === sectionKey) target = b;
                    });
                }
                if (target) markActive(target);
            };
        }

        return {
            destroy: function () {
                document.body.classList.remove('project-overlay-locked');
                document.removeEventListener('keydown', escHandler);
            },
            restoreView: restoreView,
            isChatOpen: isChatOpen,
            // Used by project_list.js for ?chat=1 deep links (chat-mention notifications).
            openChat: openChat
        };
    }

    return { init: init };
})();