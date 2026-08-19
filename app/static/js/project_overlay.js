// app/static/js/project_overlay.js
//
// Detail + Briefing overlay — sidebar section/sub-tab switching (rebuilt
// 13 Aug 2026 as a vertical sidebar, replacing the horizontal collapse-
// in-place rail), plus the three close affordances (X, backdrop click,
// Esc). Same separation of concerns as before: this file only knows
// about the overlay's own markup once it exists in the DOM — project_
// list.js still owns fetching/injecting/tearing down the overlay itself.

window.ProjectOverlay = (function () {
    // onBeforeNavigate(proceed) — task #37's unsaved-edit guard, injected
    // from project_list.js (only it knows about activeOverlayEdit). Optional:
    // when omitted, every navigation just proceeds immediately, same as
    // before this existed. Wraps close (X/backdrop/Esc) and sub-tab clicks
    // only — switching top-level sections doesn't touch #project-overlay-
    // content today (see enterSection below), so there's nothing to lose yet.
    function init(onCloseRequested, onSubTabSelected, onSectionSelected, onBeforeNavigate) {
        var backdrop = document.getElementById('project-overlay-backdrop');
        var closeBtn = document.getElementById('project-overlay-close');

        if (!backdrop) return null;

        function requestClose() {
            if (onBeforeNavigate) { onBeforeNavigate(onCloseRequested); } else { onCloseRequested(); }
        }

        if (closeBtn) {
            closeBtn.addEventListener('click', requestClose);
        }

        backdrop.addEventListener('click', function (e) {
            if (e.target === backdrop) requestClose();
        });

        function escHandler(e) {
            if (e.key === 'Escape') requestClose();
        }
        document.addEventListener('keydown', escHandler);

        // ---- Sidebar: section + sub-tab switching ----
        // No squeeze-for-room problem a vertical list, unlike the old
        // horizontal rail — every section just stays visible all the
        // time. Switching is only ever: toggle .active, show/hide
        // whichever section's own sub-tab group applies (today, only
        // Design has one).

        var SECTION_COLORS = {
            design: 'var(--tangerine)',
            finance: 'var(--ashen)',
            production: 'var(--oak)',
            logistics: 'var(--pine)'
        };

        var header = document.getElementById('project-overlay-header');
        var sidebar = document.getElementById('project-overlay-sidebar');
        var subgroup = document.getElementById('project-overlay-subrail');

        var restoreView = function () { };

        if (header && sidebar) {
            var mainItems = Array.prototype.slice.call(sidebar.querySelectorAll('.project-overlay-sidebar-item[data-main-tab]'));

            function enterSection(sectionKey, clickedBtn) {
                mainItems.forEach(function (btn) {
                    btn.classList.toggle('active', btn === clickedBtn);
                });
                header.style.setProperty('--section-color', SECTION_COLORS[sectionKey] || 'var(--tangerine)');
                if (subgroup) {
                    subgroup.classList.toggle('is-hidden', sectionKey !== 'design');
                }
            }

            mainItems.forEach(function (btn) {
                btn.addEventListener('click', function () {
                    if (btn.classList.contains('active')) return;  // already here
                    enterSection(btn.dataset.mainTab, btn);
                    if (onSectionSelected) onSectionSelected(btn.dataset.mainTab);
                });
            });

            if (subgroup) {
                subgroup.querySelectorAll('.project-overlay-sidebar-subitem').forEach(function (btn) {
                    btn.addEventListener('click', function () {
                        if (btn.classList.contains('active')) return;
                        // The .active flip and the actual content swap both
                        // live inside proceed() — gated behind the guard so a
                        // cancelled switch never leaves the sidebar pointing
                        // at a tab whose content didn't actually load.
                        var proceed = function () {
                            subgroup.querySelectorAll('.project-overlay-sidebar-subitem').forEach(function (b) {
                                b.classList.toggle('active', b === btn);
                            });
                            if (onSubTabSelected) onSubTabSelected(btn.dataset.subTab);
                        };
                        if (onBeforeNavigate) { onBeforeNavigate(proceed); } else { proceed(); }
                    });
                });
            }

            // Programmatic equivalent of a real click — puts the sidebar
            // back where the user last left it, called from outside on
            // open rather than from a click event.
            restoreView = function (sectionKey, subTabKey) {
                var targetBtn = null;
                mainItems.forEach(function (btn) {
                    if (btn.dataset.mainTab === sectionKey) targetBtn = btn;
                });
                if (!targetBtn) return;

                enterSection(sectionKey, targetBtn);

                if (subTabKey && subgroup) {
                    subgroup.querySelectorAll('.project-overlay-sidebar-subitem').forEach(function (b) {
                        b.classList.toggle('active', b.dataset.subTab === subTabKey);
                    });
                }
            };
        }

        return {
            destroy: function () {
                document.removeEventListener('keydown', escHandler);
            },
            restoreView: restoreView
        };
    }

    return { init: init };
})();