// Achievement card interactions on the profile page (Phase 4).
// Two independent, small behaviours — neither requires a server round trip:
//   1. Recent / Pinned tab toggle (own profile only)
//   2. Show more / Show less on the full category checklist (own profile only)
// Both are pure querySelector + no-op-if-missing, so this file is safe to
// load on every profile page even though these controls only ever render
// on your OWN profile — on someone else's page the selectors just find
// nothing and the listeners are never attached.

document.addEventListener('DOMContentLoaded', function () {

    // ── Recent / Pinned tab toggle ──────────────────────────────────────────
    var achievementTabButtons = document.querySelectorAll('.achievement-tab-btn');

    achievementTabButtons.forEach(function (btn) {
        btn.addEventListener('click', function () {
            var target = btn.dataset.achievementTab; // 'recent' or 'pinned'

            // Move the active state to the clicked tab...
            achievementTabButtons.forEach(function (b) { b.classList.remove('active'); });
            btn.classList.add('active');

            // ...and show only the matching tile row. Both rows are always
            // in the DOM (rendered by the template) — this just toggles
            // which one has the 'hidden' class, same pattern as the bio
            // edit-wrap show/hide elsewhere on this page.
            document.querySelectorAll('[data-achievement-panel]').forEach(function (panel) {
                panel.classList.toggle('hidden', panel.dataset.achievementPanel !== target);
            });
        });
    });

    // ── Show more / Show less checklist toggle ──────────────────────────────
    var showMoreBtn = document.getElementById('achievement-show-more-btn');
    var checklist = document.getElementById('achievement-checklist');

    if (showMoreBtn && checklist) {
        showMoreBtn.addEventListener('click', function () {
            // Read state BEFORE toggling, so the button label reflects what
            // just happened rather than what's about to happen.
            var wasHidden = checklist.classList.contains('hidden');
            checklist.classList.toggle('hidden');
            showMoreBtn.textContent = wasHidden ? 'Show less ↑' : 'Show more ↓';
        });
    }

});
