// main.js — shared shell utilities: toast, confirm modal, button loading state,
// NAS links, dev wipe tools, scroll restore, register-page team picker, account
// dropdown.
// Loaded once from base.html, outside #main-content, so it does NOT re-run on
// SPA navigation. Load before notifications.js and admin.js (they use its globals).

console.log("Vitamin-E loaded.");

// ── Open NAS folder in Synology Drive ──
// Used by file-templates.js, project_list.js and project_preproduction_card.js.
// Drive addresses folders by an internal file_id, not a path, so btn's data-url
// is a JSON route that resolves the folder server-side
// (services/nas.py build_drive_folder_url) and returns the URL to open.
function openNasLink(btn) {
    var url = btn.getAttribute('data-url');
    if (!url) return;
    btn.disabled = true;
    fetch(url).then(function (r) { return r.json(); }).then(function (data) {
        btn.disabled = false;
        if (data.success) {
            window.open(data.url, '_blank', 'noopener');
        } else {
            showToast(data.error || 'Could not open the NAS folder.', 'error');
        }
    }).catch(function () {
        btn.disabled = false;
        showToast('Could not reach the NAS.', 'error');
    });
}

// ── Dev Tools: Wipe Projects ─────────────────────────────────────────────────
// The wipe modal only renders when DEV_TOOLS_ENABLED=true (never in production).

function openWipeModal() {
    var modal = document.getElementById('wipe-modal');
    if (!modal) return;
    document.getElementById('wipe-confirm-input').value = '';
    document.getElementById('wipe-confirm-btn').disabled = true;
    modal.classList.remove('hidden');
    setTimeout(function () { document.getElementById('wipe-confirm-input').focus(); }, 100);
}

function closeWipeModal() {
    var modal = document.getElementById('wipe-modal');
    if (modal) modal.classList.add('hidden');
}

// Confirm stays disabled until the user types exactly 'WIPE'.
function checkWipeConfirm() {
    var val = document.getElementById('wipe-confirm-input').value;
    document.getElementById('wipe-confirm-btn').disabled = (val !== 'WIPE');
}

// The server re-checks DEV_TOOLS_ENABLED before deleting anything.
function confirmWipe() {
    var btn = document.getElementById('wipe-confirm-btn');
    btn.disabled = true;
    btn.textContent = 'Wiping…';

    fetch('/admin/api/dev/wipe-projects', { method: 'POST' })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            closeWipeModal();
            if (data.success) {
                showToast('All projects wiped. FOC counter reset to FOC-001.', 'success');
            } else {
                showToast(data.error || 'Wipe failed.', 'error');
            }
            btn.textContent = 'Wipe Everything';
        })
        .catch(function () {
            showToast('Request failed. Check the server logs.', 'error');
            closeWipeModal();
            btn.textContent = 'Wipe Everything';
        });
}

// ── Scroll Position: save before any form submit, restore on load ────────────
// The key is built at save time, not once at load: this file does not re-run on
// SPA navigation, so a load-time key would still name the first page opened.
(function () {
    function scrollKey() { return 'helix_scroll_' + window.location.pathname; }

    var savedY = sessionStorage.getItem(scrollKey());
    if (savedY !== null) {
        // Wait a frame so the page has laid out before scrolling.
        requestAnimationFrame(function () {
            window.scrollTo(0, parseInt(savedY, 10));
        });
        sessionStorage.removeItem(scrollKey());
    }

    document.addEventListener('submit', function () {
        sessionStorage.setItem(scrollKey(), window.scrollY);
    });
})();

/* ==========================================================================
   TOAST NOTIFICATION SYSTEM
   --------------------------------------------------------------------------
   showToast(message, type, duration)
     message  — string to display
     type     — 'success' | 'error' | 'warning' | 'info'  (default: 'info')
     duration — ms before auto-dismiss                     (default: 4000)

   Toasts go into #toast-container (base.html). CSS slides them in;
   .toast--out slides them out, then the element is removed.
   ========================================================================== */
function showToast(message, type, duration) {
    type     = type     || 'info';
    duration = duration || 4000;

    var container = document.getElementById('toast-container');
    if (!container) return;

    var toast = document.createElement('div');
    toast.className = 'toast toast--' + type;
    toast.textContent = message;

    /* Click dismisses immediately. */
    toast.addEventListener('click', function () { dismissToast(toast); });

    container.appendChild(toast);

    var timer = setTimeout(function () { dismissToast(toast); }, duration);

    /* A manual dismiss cancels the auto-dismiss timer. */
    toast.addEventListener('click', function () { clearTimeout(timer); }, { once: true });
}

// --- Button loading state: swap in a spinner, restore the original HTML ----
function btnLoading(btn) {
    if (!btn) return;
    btn.dataset.originalHTML = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="btn-spinner"></span>';
}

function btnDone (btn) {
    if (!btn) return;
    btn.disabled = false;
    btn.innerHTML = btn.dataset.originalHTML || '';
    delete btn.dataset.originalHTML
}

/* Animate the toast out, then remove it from the DOM. */
function dismissToast(toast) {
    if (toast.classList.contains('toast--out')) return;

    toast.classList.add('toast--out');

    toast.addEventListener('animationend', function () {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, { once: true });
}

// ── Achievement Toast ───────────────────────────────────────────────────────
// Gold trophy toast in its own #achievement-toast-container (separate from
// #toast-container). Auto-dismisses after 7s.
function showAchievementToast(message) {
    var container = document.getElementById('achievement-toast-container');
    if (!container) return;

    var toast = document.createElement('div');
    toast.className = 'achievement-toast';
    toast.innerHTML =
        '<span class="achievement-toast__icon">🏆</span>' +
        '<div class="achievement-toast__body">' +
            '<strong class="achievement-toast__label">Achievement Unlocked</strong>' +
            '<span class="achievement-toast__msg">' + _escHtml(message) + '</span>' +
        '</div>' +
        '<button class="achievement-toast__close" aria-label="Dismiss">&times;</button>';

    toast.querySelector('.achievement-toast__close').addEventListener('click', function () {
        dismissAchievementToast(toast);
    });

    container.appendChild(toast);

    var timer = setTimeout(function () { dismissAchievementToast(toast); }, 7000);
    toast.querySelector('.achievement-toast__close').addEventListener('click', function () {
        clearTimeout(timer);
    }, { once: true });
}

function dismissAchievementToast(toast) {
    if (toast.classList.contains('achievement-toast--out')) return;
    toast.classList.add('achievement-toast--out');
    toast.addEventListener('animationend', function () {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, { once: true });
}

/* ==========================================================================
   CONFIRM MODAL SYSTEM
   --------------------------------------------------------------------------
   showConfirm(message, onConfirm, title)
     message    — body text asking the user to confirm
     onConfirm  — function called if the user clicks "Confirm"
     title      — optional header string (default: 'Are you sure?')

   Modal markup is #confirm-modal in base.html. Cancel or a backdrop click
   closes without calling onConfirm. One dialog at a time: a second call
   replaces the pending callback.
   ========================================================================== */
(function () {
    var _confirmCallback = null;

    window.showConfirm = function (message, onConfirm, title) {
        var modal  = document.getElementById('confirm-modal');
        var body   = document.getElementById('confirm-modal-body');
        var titleEl = document.getElementById('confirm-modal-title');
        if (!modal || !body) return;

        body.textContent    = message;
        titleEl.textContent = title || 'Are you sure?';

        _confirmCallback = onConfirm || null;

        /* Pause live polling so a refresh can't reload the page under the open modal. */
        modal.classList.remove('hidden');
        if (window.helixPolling) window.helixPolling.pause();
    };

    /* Buttons live in base.html, so wiring them once is enough. */
    document.addEventListener('DOMContentLoaded', function () {
        var modal     = document.getElementById('confirm-modal');
        var btnOk     = document.getElementById('confirm-modal-ok');
        var btnCancel = document.getElementById('confirm-modal-cancel');
        if (!modal) return;

        function _closeConfirm() {
            modal.classList.add('hidden');
            if (window.helixPolling) window.helixPolling.resume();
        }

        /* Close before calling, so the callback may open another confirm. */
        btnOk.addEventListener('click', function () {
            var fn = _confirmCallback;
            _confirmCallback = null;
            _closeConfirm();
            if (fn) fn();
        });

        btnCancel.addEventListener('click', function () {
            _confirmCallback = null;
            _closeConfirm();
        });

        /* Backdrop click cancels. */
        modal.addEventListener('click', function (e) {
            if (e.target === modal) {
                _confirmCallback = null;
                _closeConfirm();
            }
        });
    });
}());

// HTML-escapes text for innerHTML; empty input renders as an em dash.
function _escHtml(str) {
    if (!str) return '—';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// Register page: the team picker shows (and is required) only for designer / team_lead.
// Re-runs after SPA navigation, since main.js itself does not.
function initRegisterTeamPicker() {
    const roleSelect = document.getElementById('role');
    const teamGroup = document.getElementById('team-group');
    const teamSelect = document.getElementById('team');

    if (roleSelect && teamGroup && teamSelect) {
        roleSelect.addEventListener('change', function () {
            const needsTeam = this.value === 'designer' || this.value === 'team_lead';

            if (needsTeam) {
                teamGroup.classList.remove('hidden');
                teamSelect.required = true;
            } else {
                teamGroup.classList.add('hidden');
                teamSelect.required = false;
                teamSelect.value = '';
            }
        });
    }
}
initRegisterTeamPicker();
document.addEventListener('helix:navigated', initRegisterTeamPicker);

    // Account dropdown (header, outside #main-content, so bound once).
    const accountTrigger = document.getElementById('account-trigger');
    const accountDropdown = document.getElementById('account-dropdown');

    if (accountTrigger && accountDropdown) {
        accountTrigger.addEventListener('click', function (event) {
            event.stopPropagation();
            accountDropdown.classList.toggle('hidden');
        });

        document.addEventListener('click', function (event) {
            if (!accountDropdown.classList.contains('hidden')) {
                if (!accountDropdown.contains(event.target) && event.target !== accountTrigger) {
                    accountDropdown.classList.add('hidden');
                }
            }
        });
    }
