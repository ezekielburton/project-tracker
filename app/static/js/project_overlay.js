// app/static/js/project_overlay.js
//
// Detail + Briefing overlay — the rail's collapse-in-place section switch
// (Step 1), plus detecting the three close affordances (X, backdrop
// click, Esc). This file only knows about the overlay's OWN markup once
// it exists in the DOM — it does NOT know how the overlay got there or
// how to remove it. That's project_list.js's job (fetch the /overlay
// route, inject the HTML, call ProjectOverlay.init(), and on close call
// the returned destroy() and clear the mount) — kept separate so this
// stays a self-contained, reusable component, not tied to one page.
//
// init() is called explicitly rather than auto-running on
// DOMContentLoaded, because the overlay's markup is fetched and injected
// on open — not present in the page at load time — same render-on-demand
// principle as the rest of this rework (architecture doc §1).

window.ProjectOverlay = (function () {
    function init(onCloseRequested) {
        var backdrop = document.getElementById('project-overlay-backdrop');
        var closeBtn = document.getElementById('project-overlay-close');

        if (!backdrop) return null;  // nothing was injected — nothing to wire up

        function requestClose() {
            onCloseRequested();
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

        // ---- Rail: collapse-in-place section switch (unchanged from Step 1) ----

        var SECTION_COLORS = {
            design: 'var(--tangerine)',
            finance: 'var(--ashen)',
            production: 'var(--oak)',
            logistics: 'var(--pine)'
        };

        var SECTIONS_WITH_SUBTABS = ['design'];

        var header = document.getElementById('project-overlay-header');
        var rail = document.getElementById('project-overlay-rail');
        var backBtn = document.getElementById('project-overlay-back');
        var subrail = document.getElementById('project-overlay-subrail');

        if (header && rail && backBtn && subrail) {
            var mainTabs = Array.prototype.slice.call(rail.querySelectorAll('.tab-strip-item[data-main-tab]'));

            function measureExpandedWidth(el) {
                var wasCollapsed = el.classList.contains('is-collapsed');
                if (wasCollapsed) el.classList.remove('is-collapsed');
                var width = el.offsetWidth;
                if (wasCollapsed) el.classList.add('is-collapsed');
                return width;
            }

            var naturalWidths = {};
            mainTabs.forEach(function (btn) {
                naturalWidths[btn.dataset.mainTab] = measureExpandedWidth(btn);
            });
            var backNaturalWidth = measureExpandedWidth(backBtn);
            var subrailNaturalWidth = measureExpandedWidth(subrail);

            function collapseEl(el) {
                if (el.classList.contains('is-collapsed')) return;
                el.style.width = el.offsetWidth + 'px';
                el.offsetHeight;
                el.classList.add('is-collapsed');
                el.style.width = '0px';
            }

            function expandEl(el, naturalWidth) {
                if (!el.classList.contains('is-collapsed')) return;
                el.classList.remove('is-collapsed');
                el.style.width = naturalWidth + 'px';
            }

            function enterSection(sectionKey, clickedBtn) {
                mainTabs.forEach(function (btn) {
                    btn.classList.toggle('active', btn === clickedBtn);
                    if (btn === clickedBtn) {
                        expandEl(btn, naturalWidths[sectionKey]);
                    } else {
                        collapseEl(btn);
                    }
                });

                expandEl(backBtn, backNaturalWidth);
                header.style.setProperty('--section-color', SECTION_COLORS[sectionKey] || 'var(--tangerine)');

                if (SECTIONS_WITH_SUBTABS.indexOf(sectionKey) !== -1) {
                    expandEl(subrail, subrailNaturalWidth);
                } else {
                    collapseEl(subrail);
                }
            }

            function backToMain() {
                mainTabs.forEach(function (btn) {
                    expandEl(btn, naturalWidths[btn.dataset.mainTab]);
                });
                collapseEl(backBtn);
                collapseEl(subrail);
            }

            mainTabs.forEach(function (btn) {
                btn.addEventListener('click', function () {
                    var inSection = !backBtn.classList.contains('is-collapsed');
                    if (inSection && btn.classList.contains('active')) {
                        backToMain();
                    } else {
                        enterSection(btn.dataset.mainTab, btn);
                    }
                });
            });

            backBtn.addEventListener('click', backToMain);

            subrail.querySelectorAll('.tab-strip-item').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    subrail.querySelectorAll('.tab-strip-item').forEach(function (b) {
                        b.classList.toggle('active', b === btn);
                    });
                });
            });
        }

        // Handle for the caller to clean up the document-level Esc
        // listener — it won't get garbage-collected just because the
        // overlay's own DOM node was removed.
        return {
            destroy: function () {
                document.removeEventListener('keydown', escHandler);
            }
        };
    }

    return { init: init };
})();