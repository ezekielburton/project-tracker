// File Templates page: collapsible regions and customers (state kept in
// localStorage), the Simulation Files button and the Download All zips.

// The SPA router re-runs this script on every visit; guard so document
// does not stack click listeners (a double toggle cancels itself out).
if (!window._ftDispatcherWired) {
    window._ftDispatcherWired = true;
    document.addEventListener('click', function (e) {
        var regionToggle = e.target.closest('[data-action="toggle-ft-region"]');
        if (regionToggle) { toggleFtSection(regionToggle); return; }

        var customerToggle = e.target.closest('[data-action="toggle-ft-customer"]');
        if (customerToggle) { toggleFtSection(customerToggle); return; }

        // Delegated so it survives SPA navigation replacing the DOM.
        var simBtn = e.target.closest('#open-simulation-files-btn');
        if (simBtn) { openNasLink(simBtn); return; }

        var zipBtn = e.target.closest('[data-action="download-all-zip"]');
        if (zipBtn) { downloadAllZip(zipBtn); return; }
    });
}

// The build URL zips the files server-side and returns a one-shot download URL.
function downloadAllZip(btn) {
    var url = btn.getAttribute('data-zip-build-url');
    if (!url || btn.disabled) return;
    var originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Zipping...';
    function reset() { btn.disabled = false; btn.textContent = originalText; }
    fetch(url).then(function (r) { return r.json(); }).then(function (data) {
        reset();
        if (!data.success) { showToast(data.error || 'Could not build zip.', 'error'); return; }
        window.location = data.download_url;
    }).catch(function () {
        reset();
        showToast('Something went wrong.', 'error');
    });
}

// Shared by region and customer toggles; the collapsed state is saved per target id.
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