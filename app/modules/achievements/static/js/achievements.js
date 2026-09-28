// Profile page achievement card: Recent / Pinned tabs, Show more / less on
// the checklist, and the Customize modal (active badge + pins).
// All controls are own-profile only; missing elements are skipped, so this
// is safe on any profile.

// IIFE, not DOMContentLoaded, so it also runs after SPA navigation.
(function () {

    // ── Recent / Pinned tab toggle ──────────────────────────────────────────
    var achievementTabButtons = document.querySelectorAll('.achievement-tab-btn');


    achievementTabButtons.forEach(function (btn) {
        btn.addEventListener('click', function () {
            var target = btn.dataset.achievementTab; // 'recent' or 'pinned'

            achievementTabButtons.forEach(function (b) { b.classList.remove('active'); });
            btn.classList.add('active');

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
            var wasHidden = checklist.classList.contains('hidden');
            checklist.classList.toggle('hidden');
            showMoreBtn.textContent = wasHidden ? 'Show less ↑' : 'Show more ↓';
        });
    }

    // ── Customize achievements modal ─────────────────────────────────────────
    // Driven by window.PROFILE_CUSTOMIZE (set by profile.html, own profile only).
    // The modal markup comes AFTER this <script> tag, so modal elements are
    // looked up lazily inside the functions; the Customize button is above
    // and safe to cache.

    var openCustomizeBtn = document.getElementById('edit-achievements-btn');

    // Working state while the modal is open; sent on Save.
    var selectedBadgeUaId = null;   // ua_id or null (no badge)
    var selectedPinIds    = [];     // ordered list of ua_ids (max 5)

    function escHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function updatePinCount() {
        var pinCountLabel = document.getElementById('pin-count-label');
        if (pinCountLabel) pinCountLabel.textContent = selectedPinIds.length;
    }

    function renderBadgePicker() {
        var badgePickerGrid = document.getElementById('badge-picker-grid');
        if (!badgePickerGrid || !window.PROFILE_CUSTOMIZE) return;

        var data = window.PROFILE_CUSTOMIZE;
        // Only achievements with an image can be a badge.
        var badgeable = data.earned.filter(function (ua) { return ua.badge_image; });

        var html = '';
        // "None" option clears the active badge.
        html += '<div class="badge-picker-item' + (selectedBadgeUaId === null ? ' badge-picker-item--selected' : '') +
                '" data-ua-id="null" title="No badge">' +
                '<span class="badge-picker-none">—</span>' +
                '</div>';

        badgeable.forEach(function (ua) {
            var isSelected = selectedBadgeUaId === ua.ua_id;
            html += '<div class="badge-picker-item' + (isSelected ? ' badge-picker-item--selected' : '') +
                    '" data-ua-id="' + ua.ua_id + '" title="' + escHtml(ua.name) + '">' +
                    '<img src="' + escHtml(ua.badge_url) + '" alt="' + escHtml(ua.name) + '">' +
                    '</div>';
        });

        badgePickerGrid.innerHTML = html;

        // Bind once; re-renders would otherwise stack listeners.
        if (!badgePickerGrid._helixBound) {
            badgePickerGrid._helixBound = true;
            badgePickerGrid.addEventListener('click', function (e) {
                var item = e.target.closest('.badge-picker-item');
                if (!item) return;
                var rawId = item.dataset.uaId;
                selectedBadgeUaId = (rawId === 'null') ? null : parseInt(rawId, 10);
                renderBadgePicker(); // re-render to move the selected ring
            });
        }
    }

    function renderPinPicker() {
        var pinPickerList = document.getElementById('pin-picker-list');
        if (!pinPickerList || !window.PROFILE_CUSTOMIZE) return;

        var data = window.PROFILE_CUSTOMIZE;
        var html = '';

        if (data.earned.length === 0) {
            html = '<p class="muted" style="padding:0.5rem 0;">No achievements earned yet.</p>';
            pinPickerList.innerHTML = html;
            return;
        }

        data.earned.forEach(function (ua) {
            var isPinned = selectedPinIds.indexOf(ua.ua_id) !== -1;
            var badgeHtml = ua.badge_image
                ? '<img src="' + escHtml(ua.badge_url) + '" alt="" class="pin-picker-badge">'
                : '<span class="achievement-badge-fallback pin-picker-badge">🏆</span>';
            var toggleClass = isPinned ? 'pin-toggle-btn pin-toggle-btn--active' : 'pin-toggle-btn';
            var toggleLabel = isPinned ? '★ Pinned' : '☆ Pin';

            html += '<div class="pin-picker-row" data-ua-id="' + ua.ua_id + '">' +
                    badgeHtml +
                    '<span class="pin-picker-name">' + escHtml(ua.name) + '</span>' +
                    '<button type="button" class="' + toggleClass + '">' + toggleLabel + '</button>' +
                    '</div>';
        });

        pinPickerList.innerHTML = html;

        // Bind once, as for the badge grid.
        if (pinPickerList._helixBound) return;
        pinPickerList._helixBound = true;
        pinPickerList.addEventListener('click', function (e) {
            var btn = e.target.closest('.pin-toggle-btn');
            if (!btn) return;
            var row = btn.closest('.pin-picker-row');
            var uaId = parseInt(row.dataset.uaId, 10);
            var idx = selectedPinIds.indexOf(uaId);

            if (idx !== -1) {
                selectedPinIds.splice(idx, 1);
            } else {
                if (selectedPinIds.length >= 5) {
                    if (typeof showToast === 'function') showToast('Maximum 5 achievements can be pinned.', 'warning');
                    return;
                }
                selectedPinIds.push(uaId);
            }
            updatePinCount();
            renderPinPicker();
        });
    }

    function openCustomizeModal() {
        var customizeModal = document.getElementById('achievement-customize-modal');
        if (!customizeModal || !window.PROFILE_CUSTOMIZE) return;

        // Copy the saved state so Cancel discards changes.
        selectedBadgeUaId = window.PROFILE_CUSTOMIZE.active_badge_ua_id;
        selectedPinIds    = (window.PROFILE_CUSTOMIZE.pinned_ids || []).slice();

        renderBadgePicker();
        renderPinPicker();
        updatePinCount();

        customizeModal.classList.remove('hidden');
        if (window.helixPolling) window.helixPolling.pause();

        // Wire cancel (once) and backdrop close now the modal exists.
        var cancelBtn = document.getElementById('achievement-customize-cancel-btn');
        if (cancelBtn && !cancelBtn._helixBound) {
            cancelBtn._helixBound = true;
            cancelBtn.addEventListener('click', closeCustomizeModal);
        }
        // Not {once:true}: a click inside the modal would use it up.
        if (!customizeModal._helixBound) {
            customizeModal._helixBound = true;
            customizeModal.addEventListener('click', function (e) {
                if (e.target === customizeModal) closeCustomizeModal();
            });
        }
    }

    function closeCustomizeModal() {
        var customizeModal = document.getElementById('achievement-customize-modal');
        if (!customizeModal) return;
        customizeModal.classList.add('hidden');
        if (window.helixPolling) window.helixPolling.resume();
    }

    if (openCustomizeBtn) openCustomizeBtn.addEventListener('click', openCustomizeModal);

    // Save button, delegated because the modal comes after this script.
    // The SPA router re-runs this script, so swap out the previous run's
    // handler: stacking would save N times, and it holds stale picker state.
    if (window._achievementSaveHandler) {
        document.removeEventListener('click', window._achievementSaveHandler);
    }
    window._achievementSaveHandler = function (e) {
        if (!e.target.closest || e.target.id !== 'achievement-customize-save-btn') return;
        var saveBtn = e.target;
        if (!window.PROFILE_CUSTOMIZE) return;
        if (typeof btnLoading === 'function') btnLoading(saveBtn);

        var data = window.PROFILE_CUSTOMIZE;

        var displayPromise = fetch('/account/display-settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                active_badge_id:  selectedBadgeUaId,
                active_title_id:  data.active_title_ua_id,
                active_border_id: data.active_border_id
            })
        }).then(function (r) { return r.json(); });

        var pinPromise = fetch('/account/pinned-achievements', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pinned_ids: selectedPinIds })
        }).then(function (r) { return r.json(); });

        Promise.all([displayPromise, pinPromise])
            .then(function (results) {
                if (typeof btnDone === 'function') btnDone(saveBtn);
                var badgeResult = results[0];
                var pinResult   = results[1];
                if (!badgeResult.success) {
                    if (typeof showToast === 'function') showToast(badgeResult.error || 'Could not save badge.', 'error');
                    return;
                }
                if (!pinResult.success) {
                    if (typeof showToast === 'function') showToast(pinResult.error || 'Could not save pins.', 'error');
                    return;
                }
                window.location.reload();
            })
            .catch(function () {
                if (typeof btnDone === 'function') btnDone(saveBtn);
                if (typeof showToast === 'function') showToast('Save failed.', 'error');
            });
    };
    document.addEventListener('click', window._achievementSaveHandler);

}());
