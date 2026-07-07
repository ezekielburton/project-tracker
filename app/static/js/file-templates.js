// file-templates.js — Vitamin-E
// Drives the C&CM File Templates library page: collapsible regions and
// customers, both persisted to localStorage the same mechanism as the
// C&CM detail page's customer rows use, so state survives reloads.
//
// The "Download All" buttons on this page are NOT wired here — they reuse
// the exact same data-action="download-all-zip" hook (and
// triggerZipDownload() function) already defined in detail.js, which
// loads globally on every page. Nothing new needed for those.

document.addEventListener('click', function (e) {
    var regionToggle = e.target.closest('[data-action="toggle-ft-region"]');
    if (regionToggle) { toggleFtSection(regionToggle); return; }

    var customerToggle = e.target.closest('[data-action="toggle-ft-customer"]');
    if (customerToggle) { toggleFtSection(customerToggle); return; }
});

// One shared toggle for both regions and customers — the behavior is
// identical (toggle the target's hidden class, remember the choice), only
// the CSS classes involved differ, and that's handled purely by which
// element .collapsed lands on.
function toggleFtSection(toggleArea) {
    var targetId = toggleArea.getAttribute('data-target');
    var body = document.getElementById(targetId);
    if (!body) return;
    var collapsed = body.classList.toggle('hidden');
    toggleArea.classList.toggle('collapsed', collapsed);
    localStorage.setItem('helix_ft_collapsed_' + targetId, collapsed ? '1' : '0');
}

function restoreFileTemplatesCollapseState() {
    document.querySelectorAll('[data-action="toggle-ft-region"], [data-action="toggle-ft-customer"]').forEach(function (toggleArea) {
        var targetId = toggleArea.getAttribute('data-target');
        if (localStorage.getItem('helix_ft_collapsed_' + targetId) !== '1') return;
        var body = document.getElementById(targetId);
        if (!body) return;
        body.classList.add('hidden');
        toggleArea.classList.add('collapsed');
    });
}

function initFileTemplatesPage() {
    if (!document.querySelector('.ft-region-block')) return; // not on this page
    restoreFileTemplatesCollapseState();
}

document.addEventListener('DOMContentLoaded', initFileTemplatesPage);
document.addEventListener('helix:navigated', initFileTemplatesPage);