// main.js — Vitamin-E v1.3
// Shared utilities (toast, confirm, refreshSection), dev tools, scroll position,
// dashboard (approved-projects view, filters, tab switching), account dropdown,
// drafts page, create/edit brief page (sectionBasics).
// main.js must be loaded first; notifications.js, detail.js, admin.js depend on it.

// main.js - Vitamin-E
console.log("Vitamin-E loaded.");

// ── Dev Tools: Wipe Projects ─────────────────────────────────────────────────
// These functions only do anything if the wipe modal exists in the DOM, which
// only happens when DEV_TOOLS_ENABLED=true is set in .env (never on production).

function openWipeModal() {
    var modal = document.getElementById('wipe-modal');
    if (!modal) return;
    // Reset state every time modal opens — clear the input and re-disable the button
    document.getElementById('wipe-confirm-input').value = '';
    document.getElementById('wipe-confirm-btn').disabled = true;
    modal.classList.remove('hidden');
    setTimeout(function () { document.getElementById('wipe-confirm-input').focus(); }, 100);
}

function closeWipeModal() {
    var modal = document.getElementById('wipe-modal');
    if (modal) modal.classList.add('hidden');
}

// Enable the confirm button only when the user has typed exactly 'WIPE'
function checkWipeConfirm() {
    var val = document.getElementById('wipe-confirm-input').value;
    document.getElementById('wipe-confirm-btn').disabled = (val !== 'WIPE');
}

// POST to the wipe route — server double-checks DEV_TOOLS_ENABLED before touching any data
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
            // Reset button text for next time
            btn.textContent = 'Wipe Everything';
        })
        .catch(function () {
            showToast('Request failed. Check the server logs.', 'error');
            closeWipeModal();
            btn.textContent = 'Wipe Everything';
        });
}

// Synchronises horizontal scroll across all .table-wrapper elements within a view.
// Called ocne per view at init - not on every tab switch - to avoid slacking listeners.
// isSyncing prevents the programmatic scrollLeft assignment from firing as second scroll event.
function syncTableScroller(viewE1) {
    var wrappers = Array.from(viewE1.querySelectorAll('.table-wrapper'));
    if (wrappers.length < 2) return; // single-table views have nothing to sync

    var isSyncing = false;
    wrappers.forEach(function(wrapper) {
        wrapper.addEventListener('scroll', function() {
            if (isSyncing) return;
            isSyncing = true;
            var left = this.scrollLeft;
            wrappers.forEach(function(w) {
                w.scrollLeft = left; // mirror position to every other wrapper
            });
            isSyncing = false;
        })
    })
}

// ── Scroll Position: save before any form submit, restore on load ────────────
(function () {
    var SCROLL_KEY = 'helix_scroll_' + window.location.pathname;

    // On load: if we saved a scroll position for this page, jump there and clear it
    var savedY = sessionStorage.getItem(SCROLL_KEY);
    if (savedY !== null) {
        // requestAnimationFrame ensures the page has rendered before we scroll
        requestAnimationFrame(function () {
            window.scrollTo(0, parseInt(savedY, 10));
        });
        sessionStorage.removeItem(SCROLL_KEY);
    }

    // Before any form submit on this page, save current scroll position
    document.addEventListener('submit', function () {
        sessionStorage.setItem(SCROLL_KEY, window.scrollY);
    });
})();

function refreshSection(projectId, sectionId) {
    return fetch('/projects/' + projectId)
        .then(function (r) { return r.text(); })
        .then(function (html) {
            var doc = new DOMParser().parseFromString(html, 'text/html');
            var next = doc.getElementById(sectionId);
            var curr = document.getElementById(sectionId);
            if (next && curr) curr.outerHTML = next.outerHTML;
        });
}

/* ==========================================================================
   TOAST NOTIFICATION SYSTEM
   --------------------------------------------------------------------------
   showToast(message, type, duration)
     message  — string to display
     type     — 'success' | 'error' | 'warning' | 'info'  (default: 'info')
     duration — ms before auto-dismiss                     (default: 4000)

   Each toast is a <div> injected into #toast-container (base.html).
   CSS handles the slide-in animation; we add .toast--out to slide it back
   out, then remove the element once the animation finishes.
   ========================================================================== */
function showToast(message, type, duration) {
    /* Sensible defaults */
    type     = type     || 'info';
    duration = duration || 4000;

    /* Find (or create) the container defined in base.html */
    var container = document.getElementById('toast-container');
    if (!container) return;  /* bail if base.html didn't load the container */

    /* Build the toast element */
    var toast = document.createElement('div');
    toast.className = 'toast toast--' + type;
    toast.textContent = message;

    /* Clicking the toast dismisses it immediately */
    toast.addEventListener('click', function () { dismissToast(toast); });

    container.appendChild(toast);

    /* Auto-dismiss after `duration` ms */
    var timer = setTimeout(function () { dismissToast(toast); }, duration);

    /* If the user clicks before the timer fires, cancel the timer so we
       don't try to remove a node that's already been removed. */
    toast.addEventListener('click', function () { clearTimeout(timer); }, { once: true });
}

// --- Button loading state helpers ----
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
    /* Guard: already animating out */
    if (toast.classList.contains('toast--out')) return;

    toast.classList.add('toast--out');

    /* Remove the element after the CSS animation finishes (0.25s) */
    toast.addEventListener('animationend', function () {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, { once: true });
}

// ── Achievement Toast ───────────────────────────────────────────────────────
// Displays a special gold trophy toast in #achievement-toast-container,
// which sits ABOVE the regular #toast-container in the layout.
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

   The modal HTML lives in base.html (#confirm-modal).
   Clicking "Cancel" or the backdrop closes without calling onConfirm.
   Only one confirm dialog can be open at a time.
   ========================================================================== */
(function () {
    /* _confirmCallback holds the function to call on "Confirm".
       It lives inside this IIFE so it's private — only showConfirm can set it. */
    var _confirmCallback = null;

    /* Public function — attached to window so any other script can call it. */
    window.showConfirm = function (message, onConfirm, title) {
        var modal  = document.getElementById('confirm-modal');
        var body   = document.getElementById('confirm-modal-body');
        var titleEl = document.getElementById('confirm-modal-title');
        if (!modal || !body) return;  /* bail if base.html didn't load the modal */

        /* Populate the text */
        body.textContent    = message;
        titleEl.textContent = title || 'Are you sure?';

        /* Store the callback for when the user clicks Confirm */
        _confirmCallback = onConfirm || null;

        /* Show the overlay — pause live polling while waiting for user input */
        modal.classList.remove('hidden');
        if (window.helixPolling) window.helixPolling.pause();
    };

    /* Wire up the buttons — runs once when the DOM is ready */
    document.addEventListener('DOMContentLoaded', function () {
        var modal     = document.getElementById('confirm-modal');
        var btnOk     = document.getElementById('confirm-modal-ok');
        var btnCancel = document.getElementById('confirm-modal-cancel');
        if (!modal) return;

        function _closeConfirm() {
            modal.classList.add('hidden');
            if (window.helixPolling) window.helixPolling.resume();
        }

        /* "Confirm" — save callback, close first, THEN call.
           (matches the existing approval modal pattern in CLAUDE.md) */
        btnOk.addEventListener('click', function () {
            var fn = _confirmCallback;
            _confirmCallback = null;       /* clear before calling */
            _closeConfirm();
            if (fn) fn();
        });

        /* "Cancel" — just close */
        btnCancel.addEventListener('click', function () {
            _confirmCallback = null;
            _closeConfirm();
        });

        /* Clicking the dark backdrop also cancels */
        modal.addEventListener('click', function (e) {
            if (e.target === modal) {
                _confirmCallback = null;
                _closeConfirm();
            }
        });
    });
}());

document.addEventListener('submit', function (e) {
    var form = e.target.closest('.inline-form, .secondary-cs-form');
    if (!form) return;
    e.preventDefault();

    var action = form.getAttribute('action');
    var projectId = action.split('/')[2];
    var btn = form.querySelector('button[type="submit"]');
    if (btn) btn.disabled = false;

    fetch(action, {
        method: 'POST',
        body: new FormData(form)
    })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.success) {
                refreshSection(projectId, 'section-assignments');
            } else {
                showToast(data.error || 'Something went wrong.', 'error');
                if (btn) btn.disabled = false;
            }
        })
        .catch(function () {
            if (btn) btn.disabled = false;
        });
});

// Archive All (inbox)

// ── Approved Projects view — shared across all three dashboards ───────────────
// buildApprovedView() groups window.PAGE.approvedProjects by year→month and renders
// collapsible year sections with per-month data tables into the given container.

function _escHtml(str) {
    if (!str) return '—';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function buildApprovedView(containerId, projects) {
    var container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = '';

    if (!projects || projects.length === 0) {
        container.innerHTML = '<p class="empty-state">No approved projects yet.</p>';
        return;
    }

    // Wrap all year groups in a single scroll container for one shared scrollbar
    var viewScroll = document.createElement('div');
    viewScroll.className = 'view-scroll';
    container.appendChild(viewScroll);

    // Group into { year: { monthName: { order: N, rows: [...] } } }
    var grouped = {};
    projects.forEach(function (p) {
        var d = new Date(p.approved_at);
        var yr = d.getFullYear();
        var mo = d.toLocaleString('en-GB', { month: 'long' });
        var moOrd = d.getMonth(); // 0-based, used for sorting
        if (!grouped[yr]) grouped[yr] = {};
        if (!grouped[yr][mo]) grouped[yr][mo] = { order: moOrd, rows: [] };
        grouped[yr][mo].rows.push(p);
    });

    // Render years descending
    var years = Object.keys(grouped).map(Number).sort(function (a, b) { return b - a; });

    years.forEach(function (yr) {
        var yearEl = document.createElement('div');
        yearEl.className = 'approved-year-group';

        // Collapsible year header
        var toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'approved-year-toggle';
        toggle.innerHTML = '<span class="approved-chevron">▼</span> ' + yr;

        var body = document.createElement('div');
        body.className = 'approved-year-body';

        toggle.addEventListener('click', function () {
            var isOpen = !body.classList.contains('hidden');
            body.classList.toggle('hidden', isOpen);
            toggle.querySelector('.approved-chevron').textContent = isOpen ? '▶' : '▼';
        });

        yearEl.appendChild(toggle);
        yearEl.appendChild(body);

        // Render months descending within the year
        var months = Object.keys(grouped[yr]).sort(function (a, b) {
            return grouped[yr][b].order - grouped[yr][a].order;
        });

        months.forEach(function (mo) {
            var monthLabel = document.createElement('h4');
            monthLabel.className = 'approved-month-label';
            monthLabel.textContent = mo;
            body.appendChild(monthLabel);

            var wrapper = document.createElement('div');
            wrapper.className = 'table-wrapper table-wrapper--card';

            var table = document.createElement('table');
            table.className = 'data-table data-table--card-rows';

            // Table header
            var thead = document.createElement('thead');
            thead.innerHTML = '<tr>' +
                '<th>Project Name</th>' +
                '<th>Brief Date</th>' +
                '<th>Client</th>' +
                '<th>Brief Type</th>' +
                '<th>CS Lead</th>' +
                '<th>Approved By</th>' +
                '<th>Approved Date</th>' +
                '</tr>';
            table.appendChild(thead);

            // Table body — one row per project
            var tbody = document.createElement('tbody');
            grouped[yr][mo].rows.forEach(function (p) {
                var dateStr = p.approved_at_display;
                var briefLabel = (p.brief_type === 'ccm') ? 'C&amp;CM' : 'Standard';

                var tr = document.createElement('tr');
                tr.className = 'clickable';
                tr.dataset.href = p.url;
                tr.innerHTML =
                    '<td>' + _escHtml(p.name) + '</td>' +
                    '<td class="mono">' + _escHtml(p.briefing_date || '—') + '</td>' +
                    '<td>' + _escHtml(p.client) + '</td>' +
                    '<td>' + briefLabel + '</td>' +
                    '<td>' + _escHtml(p.cs_lead) + '</td>' +
                    '<td>' + _escHtml(p.approved_by) + '</td>' +
                    '<td class="mono">' + dateStr + '</td>';

                // Make the row clickable (navigate to project detail)
                tr.addEventListener('click', function () {
                    if (window.navigateTo) { window.navigateTo(this.dataset.href); } else { window.location.href = this.dataset.href; }
                });
                tbody.appendChild(tr);
            });

            table.appendChild(tbody);
            wrapper.appendChild(table);
            body.appendChild(wrapper);
        });

        viewScroll.appendChild(yearEl);
    });
}

// ── Approved Projects filters ─────────────────────────────────────────────────
    // Three functions work together: 
    // populateApprovedFilters() - runs once on first open, fills the CS lead and designer dropdowns with unique values from window.PAGE.approvedProjects
    // getFilteredApprovedProjects() - reads the current filter inputs and returns a filtered subset of window.PAGE.approvedProjects (AND logic across all filters)
    // initApprovedFilters() - Called afteer buildApprovedView() on first tab open; populates dropdowns and wires up all filter event listeners
    function populateApprovedFilters() {
        var projects = window.PAGE.approvedProjects || [];
        var csSelect = document.getElementById('approved-cs-filter');
        var designerSelect = document.getElementById('approved-designer-filter');
        if (!csSelect || !designerSelect) return;

        // Collect unique CS leads and designers using objects as sets (key = name)
        var csLeads = {}, designers = {};
        projects.forEach(function (p) {
            if (p.cs_lead) csLeads[p.cs_lead] = true;
            (p.assigned_designers || []).forEach(function (d) { designers[d] = true; });
        });

        // Sort alphabetically and append as <option> elements
        Object.keys(csLeads).sort().forEach(function (name) {
            var opt = document.createElement('option');
            opt.value = name; opt.textContent = name;
            csSelect.appendChild(opt);
        });

        Object.keys(designers).sort().forEach(function (name) {
            var opt = document.createElement('option');
            opt.value = name; opt.textContent = name;
            designerSelect.appendChild(opt);
        });
    }

    function getFilteredApprovedProjects() {

        // Read current values from all 5 filter inputs (|| {} guards against missing elements)
        var nameQ = (document.getElementById('approved-search') || {}).value || '';
        var csQ = (document.getElementById('approved-cs-filter') || {}).value || '';
        var designerQ = (document.getElementById('approved-designer-filter') || {}).value || '';
        var fromVal = (document.getElementById('approved-from') || {}).value || '';
        var toVal = (document.getElementById('approved-to') || {}).value || '';

        nameQ = nameQ.trim().toLowerCase();

        // Parse date inputs into Date objects; extend toDate to end of day so the full "to" date is included (not just midnight of that day)
        var fromDate = fromVal ? new Date(fromVal) : null;
        var toDate = toVal ? new Date(toVal) : null;
        if (toDate) toDate.setHours(23, 59, 59, 999);

        return (window.PAGE.approvedProjects || []).filter(function (p) {
            // Empty filter value = match everything (no restriction applied)
            var matchName = !nameQ || p.name.toLowerCase().indexOf(nameQ) !== -1;
            var matchCS = !csQ || p.cs_lead === csQ;

            // indexOf works on the assigned_designers string array
            var matchDesigner = !designerQ || (p.assigned_designers || []).indexOf(designerQ) !== -1;

            // p.approved_at is a UTC ISO string - parse for date comparison
            var pDate = new Date(p.approved_at);
            var matchFrom = !fromDate || pDate >= fromDate;
            var matchTo = !toDate || pDate <= toDate;

            // All conditions must be pass (AND logic)
            return matchName && matchCS && matchDesigner && matchFrom && matchTo;
        });
    }

    function initApprovedFilters() {
        // Populate the CS lead and designer dropdowns on first call
        populateApprovedFilters();

        // Wire up all filter inputs — any change re-renders with the filtered list
        var inputs = ['approved-search', 'approved-cs-filter', 'approved-designer-filter', 'approved-from', 'approved-to'];
        inputs.forEach(function (id) {
            var el = document.getElementById(id);
            if (el) el.addEventListener('input', function () {
                buildApprovedView('approved-projects-container', getFilteredApprovedProjects());
            });
        });

        // Clear button resets all inputs and re-renders the full unfiltered list
        var clearBtn = document.getElementById('approved-clear-filters');
        if (clearBtn) clearBtn.addEventListener('click', function () {
            inputs.forEach(function (id) {
                var el = document.getElementById(id);
                if (el) el.value = '';
            });
            buildApprovedView('approved-projects-container', window.PAGE.approvedProjects || []);
        });
    }

// ── All Projects filters ──────────────────────────────────────────────────────
// Reads data attributes from server-rendered rows to populate dropdowns,
// then hides/shows rows on change. Called once on page load — table is
// already in the DOM so no lazy-render needed.
function initAllProjectsFilters() {
    var tbody = document.querySelector('#all-projects-view .data-table tbody');
    var csFilter = document.getElementById('ap-cs-filter');
    var statusFilter = document.getElementById('ap-status-filter');
    var designerFilter = document.getElementById('ap-designer-filter');
    var orderFilter = document.getElementById('ap-order-filter');
    var searchInput = document.getElementById('ap-search');
    var clearBtn = document.getElementById('ap-clear-filters');

    // Not on this dashboard — bail out
    if (!tbody || !csFilter) return;

    // Collect unique values from each filterable row (main rows only, not expansion rows)
    var csLeads = {}, statuses = {}, designers = {};
    var rows = Array.from(tbody.querySelectorAll('tr[data-status]'));

    rows.forEach(function (row) {
        var cs = row.getAttribute('data-cs-lead');
        var status = row.getAttribute('data-status');
        var designerStr = row.getAttribute('data-designers');

        if (cs) csLeads[cs] = true;
        if (status) statuses[status] = true;
        if (designerStr) {
            designerStr.split(',').forEach(function (d) {
                var name = d.trim();
                if (name) designers[name] = true;
            });
        }
    });

    // Populate dropdowns alphabetically
    Object.keys(csLeads).sort().forEach(function (name) {
        var opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        csFilter.appendChild(opt);
    });

    Object.keys(statuses).sort().forEach(function (status) {
        var opt = document.createElement('option');
        opt.value = status;
        // Convert snake_case to Title Case for display
        opt.textContent = status.replace(/_/g, ' ').replace(/\b\w/g, function (l) { return l.toUpperCase(); });
        statusFilter.appendChild(opt);
    });

    Object.keys(designers).sort().forEach(function (name) {
        var opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        designerFilter.appendChild(opt);
    });

    // Apply filters — hide rows that don't match all active filters
    function applyFilters() {
        var csVal = csFilter.value;
        var statusVal = statusFilter.value;
        var designerVal = designerFilter.value;
        var searchVal = searchInput ? searchInput.value.trim().toLowerCase() : '';

        rows.forEach(function (row) {
            var cs = row.getAttribute('data-cs-lead') || '';
            var status = row.getAttribute('data-status') || '';
            var designerNames = (row.getAttribute('data-designers') || '').split(',').map(function (d) { return d.trim(); });
            var name = (row.getAttribute('data-name') || '').toLowerCase();

            var match = (!csVal || cs === csVal) &&
                (!statusVal || status === statusVal) &&
                (!designerVal || designerNames.indexOf(designerVal) !== -1) &&
                (!searchVal || name.indexOf(searchVal) !== -1);

            row.classList.toggle('hidden', !match);

            // If a CCM parent row is hidden, also hide its expansion row
            var expandId = row.getAttribute('data-expand');
            if (expandId) {
                var expansionRow = document.getElementById('expand_' + expandId);
                if (expansionRow && !match) expansionRow.classList.add('hidden');
            }
        });
        // Re-sort after filtering
        sortTableBy(tbody, orderFilter ? (orderFilter.value || 'firstDeadline') : 'firstDeadline');
    }

    csFilter.addEventListener('change', applyFilters);
    statusFilter.addEventListener('change', applyFilters);
    designerFilter.addEventListener('change', applyFilters);
    if (orderFilter) orderFilter.addEventListener('change', applyFilters);
    if (searchInput) searchInput.addEventListener('input', applyFilters);

    clearBtn.addEventListener('click', function () {
        csFilter.value = '';
        statusFilter.value = '';
        designerFilter.value = '';
        if (orderFilter) orderFilter.value = 'firstDeadline';
        if (searchInput) searchInput.value = '';
        applyFilters();
    });

    // Initial sort
    sortTableBy(tbody, 'firstDeadline');
}

// ── My Projects filters (Status, Designer, Ordering) ─────────────────────────
function initMyProjectsFilters() {
    var tbody = document.querySelector('#my-projects-view .data-table tbody');
    var csFilter = document.getElementById('mp-cs-filter');
    var statusFilter = document.getElementById('mp-status-filter');
    var designerFilter = document.getElementById('mp-designer-filter');
    var orderFilter = document.getElementById('mp-order-filter');
    var searchInput = document.getElementById('mp-search');
    var clearBtn = document.getElementById('mp-clear-filters');

    if (!tbody || !statusFilter) return;

    var csLeads = {}, statuses = {}, designers = {};
    var rows = Array.from(tbody.querySelectorAll('tr[data-status]'));

    rows.forEach(function (row) {
        var cs = row.getAttribute('data-cs-lead');
        var status = row.getAttribute('data-status');
        var designerStr = row.getAttribute('data-designers');
        if (cs) csLeads[cs] = true;
        if (status) statuses[status] = true;
        if (designerStr) {
            designerStr.split(',').forEach(function (d) {
                var name = d.trim();
                if (name) designers[name] = true;
            });
        }
    });

    if (csFilter) {
        Object.keys(csLeads).sort().forEach(function (name) {
            var opt = document.createElement('option');
            opt.value = name;
            opt.textContent = name;
            csFilter.appendChild(opt);
        });
    }

    Object.keys(statuses).sort().forEach(function (status) {
        var opt = document.createElement('option');
        opt.value = status;
        opt.textContent = status.replace(/_/g, ' ').replace(/\b\w/g, function (l) { return l.toUpperCase(); });
        statusFilter.appendChild(opt);
    });

    Object.keys(designers).sort().forEach(function (name) {
        var opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        designerFilter.appendChild(opt);
    });

    function applyFilters() {
        var csVal = csFilter ? csFilter.value : '';
        var statusVal = statusFilter.value;
        var designerVal = designerFilter.value;
        var searchVal = searchInput ? searchInput.value.trim().toLowerCase() : '';

        rows.forEach(function (row) {
            var cs = row.getAttribute('data-cs-lead') || '';
            var status = row.getAttribute('data-status') || '';
            var designerNames = (row.getAttribute('data-designers') || '').split(',').map(function (d) { return d.trim(); });
            var name = (row.getAttribute('data-name') || '').toLowerCase();
            var match = (!csVal || cs === csVal) &&
                (!statusVal || status === statusVal) &&
                (!designerVal || designerNames.indexOf(designerVal) !== -1) &&
                (!searchVal || name.indexOf(searchVal) !== -1);
            row.classList.toggle('hidden', !match);
            var expandId = row.getAttribute('data-expand');
            if (expandId) {
                var expansionRow = document.getElementById('expand_' + expandId);
                if (expansionRow && !match) expansionRow.classList.add('hidden');
            }
        });
        sortTableBy(tbody, orderFilter ? (orderFilter.value || 'firstDeadline') : 'firstDeadline');
    }

    if (csFilter) csFilter.addEventListener('change', applyFilters);
    statusFilter.addEventListener('change', applyFilters);
    designerFilter.addEventListener('change', applyFilters);
    if (orderFilter) orderFilter.addEventListener('change', applyFilters);
    if (searchInput) searchInput.addEventListener('input', applyFilters);

    clearBtn.addEventListener('click', function () {
        if (csFilter) csFilter.value = '';
        statusFilter.value = '';
        designerFilter.value = '';
        if (orderFilter) orderFilter.value = 'firstDeadline';
        if (searchInput) searchInput.value = '';
        applyFilters();
    });

    // Initial sort
    sortTableBy(tbody, 'firstDeadline');
}

// ── Designer Team View filters ────────────────────────────────────────────────
function initDesignerTeamFilters() {
    var tbody = document.getElementById('designer-team-tbody');
    var csFilter = document.getElementById('des-team-cs-filter');
    var statusFilter = document.getElementById('des-team-status-filter');
    var orderFilter = document.getElementById('des-team-order-filter');
    var searchInput = document.getElementById('des-team-search');
    var clearBtn = document.getElementById('des-team-clear-filters');

    if (!tbody || !statusFilter) return;

    var csLeads = {}, statuses = {};
    var rows = Array.from(tbody.querySelectorAll('tr[data-status]'));

    rows.forEach(function (row) {
        var cs = row.getAttribute('data-cs-lead');
        var status = row.getAttribute('data-status');
        if (cs) csLeads[cs] = true;
        if (status) statuses[status] = true;
    });

    if (csFilter) {
        Object.keys(csLeads).sort().forEach(function (name) {
            var opt = document.createElement('option');
            opt.value = name;
            opt.textContent = name;
            csFilter.appendChild(opt);
        });
    }

    Object.keys(statuses).sort().forEach(function (status) {
        var opt = document.createElement('option');
        opt.value = status;
        opt.textContent = status.replace(/_/g, ' ').replace(/\b\w/g, function (l) { return l.toUpperCase(); });
        statusFilter.appendChild(opt);
    });

    function applyFilters() {
        var csVal = csFilter ? csFilter.value : '';
        var statusVal = statusFilter.value;
        var searchVal = searchInput ? searchInput.value.trim().toLowerCase() : '';

        rows.forEach(function (row) {
            var cs = row.getAttribute('data-cs-lead') || '';
            var status = row.getAttribute('data-status') || '';
            var name = (row.getAttribute('data-name') || '').toLowerCase();
            var match = (!csVal || cs === csVal) &&
                (!statusVal || status === statusVal) &&
                (!searchVal || name.indexOf(searchVal) !== -1);
            row.classList.toggle('hidden', !match);
            var expandId = row.getAttribute('data-expand');
            if (expandId) {
                var expansionRow = document.getElementById('expand_' + expandId);
                if (expansionRow && !match) expansionRow.classList.add('hidden');
            }
        });
        sortTableBy(tbody, orderFilter ? (orderFilter.value || 'firstDeadline') : 'firstDeadline');
    }

    if (csFilter) csFilter.addEventListener('change', applyFilters);
    statusFilter.addEventListener('change', applyFilters);
    if (orderFilter) orderFilter.addEventListener('change', applyFilters);
    if (searchInput) searchInput.addEventListener('input', applyFilters);

    if (clearBtn) clearBtn.addEventListener('click', function () {
        if (csFilter) csFilter.value = '';
        statusFilter.value = '';
        if (orderFilter) orderFilter.value = 'firstDeadline';
        if (searchInput) searchInput.value = '';
        applyFilters();
    });

    sortTableBy(tbody, 'firstDeadline');
}

// ── Designer Personal View filters ────────────────────────────────────────────
function initDesignerPersonalFilters() {
    var tbody = document.getElementById('designer-personal-tbody');
    var csFilter = document.getElementById('des-personal-cs-filter');
    var statusFilter = document.getElementById('des-personal-status-filter');
    var orderFilter = document.getElementById('des-personal-order-filter');
    var searchInput = document.getElementById('des-personal-search');
    var clearBtn = document.getElementById('des-personal-clear-filters');

    if (!tbody || !statusFilter) return;

    var csLeads = {}, statuses = {};
    var rows = Array.from(tbody.querySelectorAll('tr[data-status]'));

    rows.forEach(function (row) {
        var cs = row.getAttribute('data-cs-lead');
        var status = row.getAttribute('data-status');
        if (cs) csLeads[cs] = true;
        if (status) statuses[status] = true;
    });

    if (csFilter) {
        Object.keys(csLeads).sort().forEach(function (name) {
            var opt = document.createElement('option');
            opt.value = name;
            opt.textContent = name;
            csFilter.appendChild(opt);
        });
    }

    Object.keys(statuses).sort().forEach(function (status) {
        var opt = document.createElement('option');
        opt.value = status;
        opt.textContent = status.replace(/_/g, ' ').replace(/\b\w/g, function (l) { return l.toUpperCase(); });
        statusFilter.appendChild(opt);
    });

    function applyFilters() {
        var csVal = csFilter ? csFilter.value : '';
        var statusVal = statusFilter.value;
        var searchVal = searchInput ? searchInput.value.trim().toLowerCase() : '';

        rows.forEach(function (row) {
            var cs = row.getAttribute('data-cs-lead') || '';
            var status = row.getAttribute('data-status') || '';
            var name = (row.getAttribute('data-name') || '').toLowerCase();
            var match = (!csVal || cs === csVal) &&
                (!statusVal || status === statusVal) &&
                (!searchVal || name.indexOf(searchVal) !== -1);
            row.classList.toggle('hidden', !match);
            var expandId = row.getAttribute('data-expand');
            if (expandId) {
                var expansionRow = document.getElementById('expand_' + expandId);
                if (expansionRow && !match) expansionRow.classList.add('hidden');
            }
        });
        sortTableBy(tbody, orderFilter ? (orderFilter.value || 'firstDeadline') : 'firstDeadline');
    }

    if (csFilter) csFilter.addEventListener('change', applyFilters);
    statusFilter.addEventListener('change', applyFilters);
    if (orderFilter) orderFilter.addEventListener('change', applyFilters);
    if (searchInput) searchInput.addEventListener('input', applyFilters);

    if (clearBtn) clearBtn.addEventListener('click', function () {
        if (csFilter) csFilter.value = '';
        statusFilter.value = '';
        if (orderFilter) orderFilter.value = 'firstDeadline';
        if (searchInput) searchInput.value = '';
        applyFilters();
    });

    sortTableBy(tbody, 'firstDeadline');
}

// ── Team Lead Team View filters ───────────────────────────────────────────────
function initTeamLeadTeamFilters() {
    var tbody = document.getElementById('tl-team-tbody');
    var csFilter = document.getElementById('tl-team-cs-filter');
    var statusFilter = document.getElementById('tl-team-status-filter');
    var orderFilter = document.getElementById('tl-team-order-filter');
    var searchInput = document.getElementById('tl-team-search');
    var clearBtn = document.getElementById('tl-team-clear-filters');

    if (!tbody || !statusFilter) return;

    var csLeads = {}, statuses = {};
    var rows = Array.from(tbody.querySelectorAll('tr[data-status]'));

    rows.forEach(function (row) {
        var cs = row.getAttribute('data-cs-lead');
        var status = row.getAttribute('data-status');
        if (cs) csLeads[cs] = true;
        if (status) statuses[status] = true;
    });

    if (csFilter) {
        Object.keys(csLeads).sort().forEach(function (name) {
            var opt = document.createElement('option');
            opt.value = name;
            opt.textContent = name;
            csFilter.appendChild(opt);
        });
    }

    Object.keys(statuses).sort().forEach(function (status) {
        var opt = document.createElement('option');
        opt.value = status;
        opt.textContent = status.replace(/_/g, ' ').replace(/\b\w/g, function (l) { return l.toUpperCase(); });
        statusFilter.appendChild(opt);
    });

    function applyFilters() {
        var csVal = csFilter ? csFilter.value : '';
        var statusVal = statusFilter.value;
        var searchVal = searchInput ? searchInput.value.trim().toLowerCase() : '';

        rows.forEach(function (row) {
            var cs = row.getAttribute('data-cs-lead') || '';
            var status = row.getAttribute('data-status') || '';
            var name = (row.getAttribute('data-name') || '').toLowerCase();
            var match = (!csVal || cs === csVal) &&
                (!statusVal || status === statusVal) &&
                (!searchVal || name.indexOf(searchVal) !== -1);
            row.classList.toggle('hidden', !match);
            var expandId = row.getAttribute('data-expand');
            if (expandId) {
                var expansionRow = document.getElementById('expand_' + expandId);
                if (expansionRow && !match) expansionRow.classList.add('hidden');
            }
        });
        sortTableBy(tbody, orderFilter ? (orderFilter.value || 'firstDeadline') : 'firstDeadline');
    }

    if (csFilter) csFilter.addEventListener('change', applyFilters);
    statusFilter.addEventListener('change', applyFilters);
    if (orderFilter) orderFilter.addEventListener('change', applyFilters);
    if (searchInput) searchInput.addEventListener('input', applyFilters);

    if (clearBtn) clearBtn.addEventListener('click', function () {
        if (csFilter) csFilter.value = '';
        statusFilter.value = '';
        if (orderFilter) orderFilter.value = 'firstDeadline';
        if (searchInput) searchInput.value = '';
        applyFilters();
    });

    sortTableBy(tbody, 'firstDeadline');
}

// ── Team Lead Personal View filters ──────────────────────────────────────────
function initTeamLeadPersonalFilters() {
    var tbody = document.getElementById('tl-personal-tbody');
    var csFilter = document.getElementById('tl-personal-cs-filter');
    var statusFilter = document.getElementById('tl-personal-status-filter');
    var orderFilter = document.getElementById('tl-personal-order-filter');
    var searchInput = document.getElementById('tl-personal-search');
    var clearBtn = document.getElementById('tl-personal-clear-filters');

    if (!tbody || !statusFilter) return;

    var csLeads = {}, statuses = {};
    var rows = Array.from(tbody.querySelectorAll('tr[data-status]'));

    rows.forEach(function (row) {
        var cs = row.getAttribute('data-cs-lead');
        var status = row.getAttribute('data-status');
        if (cs) csLeads[cs] = true;
        if (status) statuses[status] = true;
    });

    if (csFilter) {
        Object.keys(csLeads).sort().forEach(function (name) {
            var opt = document.createElement('option');
            opt.value = name;
            opt.textContent = name;
            csFilter.appendChild(opt);
        });
    }

    Object.keys(statuses).sort().forEach(function (status) {
        var opt = document.createElement('option');
        opt.value = status;
        opt.textContent = status.replace(/_/g, ' ').replace(/\b\w/g, function (l) { return l.toUpperCase(); });
        statusFilter.appendChild(opt);
    });

    function applyFilters() {
        var csVal = csFilter ? csFilter.value : '';
        var statusVal = statusFilter.value;
        var searchVal = searchInput ? searchInput.value.trim().toLowerCase() : '';

        rows.forEach(function (row) {
            var cs = row.getAttribute('data-cs-lead') || '';
            var status = row.getAttribute('data-status') || '';
            var name = (row.getAttribute('data-name') || '').toLowerCase();
            var match = (!csVal || cs === csVal) &&
                (!statusVal || status === statusVal) &&
                (!searchVal || name.indexOf(searchVal) !== -1);
            row.classList.toggle('hidden', !match);
            var expandId = row.getAttribute('data-expand');
            if (expandId) {
                var expansionRow = document.getElementById('expand_' + expandId);
                if (expansionRow && !match) expansionRow.classList.add('hidden');
            }
        });
        sortTableBy(tbody, orderFilter ? (orderFilter.value || 'firstDeadline') : 'firstDeadline');
    }

    if (csFilter) csFilter.addEventListener('change', applyFilters);
    statusFilter.addEventListener('change', applyFilters);
    if (orderFilter) orderFilter.addEventListener('change', applyFilters);
    if (searchInput) searchInput.addEventListener('input', applyFilters);

    if (clearBtn) clearBtn.addEventListener('click', function () {
        if (csFilter) csFilter.value = '';
        statusFilter.value = '';
        if (orderFilter) orderFilter.value = 'firstDeadline';
        if (searchInput) searchInput.value = '';
        applyFilters();
    });

    sortTableBy(tbody, 'firstDeadline');
}

// Synchronises horizontal scroll across all .table-wrapper elements within a view.
// Called once per view at init — not on every tab switch — to avoid stacking listeners.
// isSyncing prevents the programmatic scrollLeft assignment from firing a second scroll event.
function syncTableScrollers(viewEl) {
    var wrappers = Array.from(viewEl.querySelectorAll('.table-wrapper'));
    if (wrappers.length < 2) return; // single-table views have nothing to sync

    var isSyncing = false;
    wrappers.forEach(function (wrapper) {
        wrapper.addEventListener('scroll', function () {
            if (isSyncing) return;
            isSyncing = true;
            var left = this.scrollLeft;
            wrappers.forEach(function (w) {
                w.scrollLeft = left; // mirror position to every other wrapper
            });
            isSyncing = false;
        });
    });
}


    function initDashboardTabs() {
    // Shared approved-projects toggle elements — present on all three dashboards
    var btnApprovedProjects = document.getElementById('btn-approved-projects');
    var approvedProjectsView = document.getElementById('approved-projects-view');

    // Team lead + designer toggle — team view / personal view / deliverable view / approved projects
    const btnTeamView = document.getElementById('btn-team-view');
    const btnPersonalView = document.getElementById('btn-personal-view');
    const btnDeliverableViewDT = document.getElementById('btn-deliverable-view');
    const teamView = document.getElementById('team-view');
    const personalView = document.getElementById('personal-view');
    const deliverableViewDT = document.getElementById('deliverable-view');

    if (btnTeamView && btnPersonalView && teamView && personalView) {
        var dtAllViews = [teamView, personalView];
        var dtAllBtns = [btnTeamView, btnPersonalView];
        if (deliverableViewDT) dtAllViews.push(deliverableViewDT);
        if (btnDeliverableViewDT) dtAllBtns.push(btnDeliverableViewDT);
        if (approvedProjectsView) dtAllViews.push(approvedProjectsView);
        if (btnApprovedProjects) dtAllBtns.push(btnApprovedProjects);

        function switchDTView(activeBtn, activeView) {
            dtAllViews.forEach(function (v) { v.classList.add('hidden'); });
            dtAllBtns.forEach(function (b) { b.classList.remove('active'); });
            activeView.classList.remove('hidden');
            activeBtn.classList.add('active');
        }

        btnTeamView.addEventListener('click', function () { switchDTView(btnTeamView, teamView); });
        btnPersonalView.addEventListener('click', function () { switchDTView(btnPersonalView, personalView); });
        if (btnDeliverableViewDT && deliverableViewDT) {
            btnDeliverableViewDT.addEventListener('click', function () { switchDTView(btnDeliverableViewDT, deliverableViewDT); });
        }

        if (btnApprovedProjects && approvedProjectsView) {
            btnApprovedProjects.addEventListener('click', function () {
                switchDTView(btnApprovedProjects, approvedProjectsView);
                // Lazy-render on first open so we don't build the DOM unnecessarily
                if (!approvedProjectsView.dataset.rendered) {
                    buildApprovedView('approved-projects-container', window.PAGE.approvedProjects || []);
                    syncTableScrollers(approvedProjectsView); // sync after DOM is built
                    initApprovedFilters();
                    approvedProjectsView.dataset.rendered = '1';
                }
            });
        }

        // ── Default view persistence (designer / team lead) ──────────────
        var DT_DEFAULT_KEY = 'helix_dt_default_view';
        var dtViewMap = {
            'team-view':              { btn: btnTeamView,           view: teamView },
            'personal-view':          { btn: btnPersonalView,       view: personalView },
            'deliverable-view':       { btn: btnDeliverableViewDT,  view: deliverableViewDT },
            'approved-projects-view': { btn: btnApprovedProjects,   view: approvedProjectsView }
        };
        function updateDTDefaultBadges(activeViewId) {
            document.querySelectorAll('.btn-set-default').forEach(function (b) {
                b.classList.toggle('is-default', b.dataset.view === activeViewId);
                b.textContent = b.dataset.view === activeViewId ? '✓ Default view' : 'Set as default';
            });
        }
        var savedDTViewId = localStorage.getItem(DT_DEFAULT_KEY);
        if (savedDTViewId && dtViewMap[savedDTViewId] && dtViewMap[savedDTViewId].btn && dtViewMap[savedDTViewId].view) {
            dtViewMap[savedDTViewId].btn.click();
        }
        updateDTDefaultBadges(savedDTViewId);
        document.querySelectorAll('.btn-set-default').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var viewId = this.dataset.view;
                localStorage.setItem(DT_DEFAULT_KEY, viewId);
                updateDTDefaultBadges(viewId);
                showToast('Default view saved', 'success');
            });
        });
    }

    // Wire up scroll sync for each view once on page load.
    // Approved projects is handled separately after buildApprovedView() since its
    // table-wrappers are built dynamically and don't exist in the DOM yet.
    if (teamView) syncTableScrollers(teamView);
    if (personalView) syncTableScrollers(personalView);

    // Conditional team dropdown on register page - shows team selector for designer/team_lead roles
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

    // CS dashboard toggle — my projects / all projects / approved projects / deliverable view
    const btnMyProjects = document.getElementById('btn-my-projects');
    const btnAllProjects = document.getElementById('btn-all-projects');
    const myProjectsView = document.getElementById('my-projects-view');
    const allProjectsView = document.getElementById('all-projects-view');
    const btnDeliverableView = document.getElementById('btn-deliverable-view');
    const deliverableView = document.getElementById('deliverable-view');

    if (btnMyProjects && btnAllProjects && myProjectsView && allProjectsView) {
        var csAllViews = [myProjectsView, allProjectsView];
        var csAllBtns = [btnMyProjects, btnAllProjects];
        if (approvedProjectsView) csAllViews.push(approvedProjectsView);
        if (btnApprovedProjects) csAllBtns.push(btnApprovedProjects);
        if (deliverableView) csAllViews.push(deliverableView);
        if (btnDeliverableView) csAllBtns.push(btnDeliverableView);

        function switchCSView(activeBtn, activeView) {
            csAllViews.forEach(function (v) { v.classList.add('hidden'); });
            csAllBtns.forEach(function (b) { b.classList.remove('active'); });
            activeView.classList.remove('hidden');
            activeBtn.classList.add('active');
        }

        btnMyProjects.addEventListener('click', function () { switchCSView(btnMyProjects, myProjectsView); });
        btnAllProjects.addEventListener('click', function () { switchCSView(btnAllProjects, allProjectsView); });

        if (btnApprovedProjects && approvedProjectsView) {
            btnApprovedProjects.addEventListener('click', function () {
                switchCSView(btnApprovedProjects, approvedProjectsView);
                // Lazy-render on first open
                if (!approvedProjectsView.dataset.rendered) {
                    buildApprovedView('approved-projects-container', window.PAGE.approvedProjects || []);
                    syncTableScrollers(approvedProjectsView);
                    initApprovedFilters();
                    approvedProjectsView.dataset.rendered = '1';
                }
            });
        }

        if (btnDeliverableView && deliverableView) {
            btnDeliverableView.addEventListener('click', function () {
                switchCSView(btnDeliverableView, deliverableView);
                syncTableScrollers(deliverableView);
            });
        }

        // ── Default view persistence ───────────────────────────────────
        var DEFAULT_KEY = 'helix_cs_default_view';

        // Map view ID → { btn, view, onSwitch } so we can trigger lazy renders
        var viewMap = {
            'my-projects-view':       { btn: btnMyProjects,      view: myProjectsView },
            'all-projects-view':      { btn: btnAllProjects,     view: allProjectsView },
            'deliverable-view':       { btn: btnDeliverableView, view: deliverableView },
            'approved-projects-view': { btn: btnApprovedProjects, view: approvedProjectsView }
        };

        function updateDefaultBadges(activeViewId) {
            document.querySelectorAll('.btn-set-default').forEach(function (b) {
                b.classList.toggle('is-default', b.dataset.view === activeViewId);
                b.textContent = b.dataset.view === activeViewId ? '✓ Default view' : 'Set as default';
            });
        }

        // On first load, switch to saved default if one is stored
        var savedViewId = localStorage.getItem(DEFAULT_KEY);
        if (savedViewId && viewMap[savedViewId] && viewMap[savedViewId].btn && viewMap[savedViewId].view) {
            viewMap[savedViewId].btn.click();
        }
        updateDefaultBadges(savedViewId);

        // "Set as default" buttons
        document.querySelectorAll('.btn-set-default').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var viewId = this.dataset.view;
                localStorage.setItem(DEFAULT_KEY, viewId);
                updateDefaultBadges(viewId);
                showToast('Default view saved', 'success');
            });
        });
    }

    // Wire up scroll sync for each CS view once on page load.
    if (myProjectsView) syncTableScrollers(myProjectsView);
    if (allProjectsView) syncTableScrollers(allProjectsView);
    initAllProjectsFilters();       // CS — All Projects filter bar
    initMyProjectsFilters();        // CS — My Projects filter bar
    initDesignerTeamFilters();      // Designer — Team View filter bar
    initDesignerPersonalFilters();  // Designer — Personal View filter bar
    initTeamLeadTeamFilters();      // Team Lead — Team View filter bar
    initTeamLeadPersonalFilters();  // Team Lead — Personal View filter bar
    }
    initDashboardTabs();
    document.addEventListener('helix:navigated', initDashboardTabs);  

    // Account dropdown toggle
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

    // ============================================================
    // DRAFTS PAGE
    // ============================================================
    // All listeners are delegated on document so they survive SPA navigation —
    // sidebar.js replaces innerHTML without re-running main.js, so caching
    // elements at parse time (the old pattern) meant listeners were never wired
    // after navigating to /projects/drafts via the sidebar.
    // _draftPageWired prevents the single handler from being stacked on re-runs.

    if (!window._draftPageWired) {
        window._draftPageWired = true;

        var _draftPendingId  = null;
        var _draftPendingRow = null;

        document.addEventListener('click', function (e) {

            // ── Delete button → open confirm overlay ──────────────
            // Check this FIRST so clicking Delete doesn't also toggle the item.
            var deleteBtn = e.target.closest('.draft-delete-btn');
            if (deleteBtn) {
                _draftPendingId  = deleteBtn.dataset.draftId;
                _draftPendingRow = deleteBtn.closest('.draft-item');
                var overlay = document.getElementById('draftConfirmOverlay');
                if (overlay) overlay.classList.remove('hidden');
                return;
            }

            // ── Confirm Yes → perform delete ─────────────────────
            if (e.target.id === 'draftConfirmYes') {
                if (!_draftPendingId) return;
                var confirmYes = e.target;
                btnLoading(confirmYes);

                var pendingId  = _draftPendingId;
                var pendingRow = _draftPendingRow;

                fetch('/projects/drafts/' + pendingId + '/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                })
                    .then(function (res) { return res.json(); })
                    .then(function (data) {
                        if (data.success) {
                            btnDone(confirmYes);
                            var ov = document.getElementById('draftConfirmOverlay');
                            if (ov) ov.classList.add('hidden');
                            if (pendingRow) {
                                var rowHeight = pendingRow.offsetHeight;
                                pendingRow.style.transition = 'opacity 0.25s ease, max-height 0.35s ease 0.2s, margin-bottom 0.35s ease 0.2s, padding 0.35s ease 0.2s';
                                pendingRow.style.overflow = 'hidden';
                                pendingRow.style.maxHeight = rowHeight + 'px';
                                pendingRow.style.opacity = '0';
                                setTimeout(function () {
                                    pendingRow.style.maxHeight = '0';
                                    pendingRow.style.marginBottom = '0';
                                    pendingRow.style.padding = '0';
                                }, 250);
                                setTimeout(function () {
                                    pendingRow.remove();
                                    if (document.querySelectorAll('.draft-item').length === 0) {
                                        window.location.href = '/';
                                    }
                                }, 850);
                            }
                            _draftPendingId  = null;
                            _draftPendingRow = null;
                        } else {
                            showToast(data.error || 'Could not delete draft.', 'error');
                            btnDone(confirmYes);
                        }
                    })
                    .catch(function (err) {
                        console.error('Draft delete failed:', err);
                        btnDone(document.getElementById('draftConfirmYes'));
                    });
                return;
            }

            // ── Confirm Cancel → dismiss ──────────────────────────
            if (e.target.id === 'draftConfirmCancel') {
                var ov2 = document.getElementById('draftConfirmOverlay');
                if (ov2) ov2.classList.add('hidden');
                _draftPendingId  = null;
                _draftPendingRow = null;
                return;
            }

            // ── Draft item click → toggle active ─────────────────
            var item = e.target.closest('.draft-item');
            if (item) {
                var isActive = item.classList.contains('active');
                document.querySelectorAll('.draft-item').forEach(function (i) { i.classList.remove('active'); });
                if (!isActive) item.classList.add('active');
                return;
            }

            // ── Click outside → deactivate all ───────────────────
            document.querySelectorAll('.draft-item').forEach(function (i) { i.classList.remove('active'); });
        });
    }

    // ── Toast Notifications ──────────────────────────────────────

    // ============================================================
    // CREATE PROJECT PAGE
    // ============================================================

    if (document.getElementById('sectionBasics')) {

        // ── State ────────────────────────────────────────────────
        let currentDraftId = null;
        let autosaveTimeout = null;
        const briefSavedState = {};

        // ── Completion Bar ───────────────────────────────────────
        var currentCompletion = 0;

        function calculateCompletion() {
            if (typeof EDIT_MODE !== 'undefined' && EDIT_MODE) {
                document.getElementById('completionBarFill').style.width = '100%';
                document.getElementById('completionLabel').textContent = '100% Complete';
                currentCompletion = 100;
                return;
            }

            let score = 0;

            const basicChecks = [
                function () { return document.getElementById('client_id').value !== ''; },
                function () { return document.getElementById('project_name').value.trim() !== ''; },
                function () { return document.getElementById('cs_lead_id').value !== ''; },
                function () { return document.getElementById('job_number').value.trim() !== ''; },
                function () { return document.querySelectorAll('input[name="design_teams"]:checked').length > 0; },
                function () { return document.getElementById('briefing_date').value !== ''; },
                function () { return document.getElementById('first_output_deadline').value !== ''; },
                function () { return document.getElementById('final_deadline').value !== ''; },
            ];

            var basicWeight = 25 / basicChecks.length;
            basicChecks.forEach(function (check) {
                if (check()) score += basicWeight;
            });

            var briefType = document.getElementById('brief_type').value;
            if (briefType === 'ccm') {
                // Only urgency is required — region/customers/deliverables are optional at
                // creation time and can be filled in later via Edit Project.
                var ccmChecks = [
                    function () { return document.getElementById('urgency').value !== ''; },
                ];
                var ccmWeight = 75 / ccmChecks.length;
                ccmChecks.forEach(function (check) {
                    if (check()) score += ccmWeight;
                });
            } else if (briefType === 'standard') {
                // Only design_type_id remains — design_direction was removed from the brief form
                var standardChecks = [
                    function () { return document.getElementById('design_type_id') && document.getElementById('design_type_id').value !== ''; },
                ];
                var standardWeight = 75 / standardChecks.length;
                standardChecks.forEach(function (check) {
                    if (check()) score += standardWeight;
                });
            }

            var pct = Math.min(Math.round(score), 100);
            document.getElementById('completionBarFill').style.width = pct + '%';
            document.getElementById('completionLabel').textContent = pct + '% Complete';
            currentCompletion = pct;
        }

        // ── Brief Type Switcher ──────────────────────────────────
        // silent=true suppresses scheduleAutosave() so that internal calls during
        // page initialisation (restoreEditState) don't queue a POST before the
        // user has touched anything. User-initiated clicks leave silent unset (falsy).
        function switchBriefType(type, silent) {
            var currentType = document.getElementById('brief_type').value;
            if (currentType) {
                briefSavedState[currentType] = captureBriefState(currentType);
            }

            document.getElementById('brief_type').value = type;

            document.querySelectorAll('.brief-type-btn').forEach(function (btn) {
                btn.classList.toggle('active', btn.dataset.type === type);
            });

            var isCCM = type === 'ccm';
            document.getElementById('sectionConceptKV').classList.add('hidden');
            document.getElementById('sectionCCM').classList.toggle('hidden', !isCCM);
            var conceptKVToggleBtn = document.getElementById('btnConceptKVToggle');
            if (conceptKVToggleBtn) conceptKVToggleBtn.classList.remove('active');
            var hasConceptEl2 = document.getElementById('has_concept');
            if (hasConceptEl2) hasConceptEl2.value = 'false';
            document.getElementById('sectionDeliverables').classList.toggle('hidden', true);
            document.getElementById('sectionStandard').classList.toggle('hidden', type !== 'standard');

            if (briefSavedState[type]) {
                restoreBriefState(type, briefSavedState[type]);
            }

            calculateCompletion();
            if (!silent) { scheduleAutosave(); }
        }

        function captureBriefState(type) {
            if (type === 'ccm') {
                return {
                    urgency: document.getElementById('urgency').value,
                    region_uae: document.getElementById('region_uae').classList.contains('active'),
                    region_gulf: document.getElementById('region_gulf').classList.contains('active'),
                    gulf_kuwait: document.getElementById('gulf_kuwait').classList.contains('active'),
                    gulf_qatar: document.getElementById('gulf_qatar').classList.contains('active'),
                    gulf_bahrain: document.getElementById('gulf_bahrain').classList.contains('active'),
                    gulf_oman: document.getElementById('gulf_oman').classList.contains('active'),
                };
            }
            return {};
        }

        function restoreBriefState(type, state) {
            if (type === 'ccm') {
                document.getElementById('urgency').value = state.urgency || '';

                var uaeBtn = document.getElementById('region_uae');
                var gulfBtn = document.getElementById('region_gulf');
                if (state.region_uae) { uaeBtn.classList.add('active'); } else { uaeBtn.classList.remove('active'); }
                if (state.region_gulf) { gulfBtn.classList.add('active'); } else { gulfBtn.classList.remove('active'); }

                ['kuwait', 'qatar', 'bahrain', 'oman'].forEach(function (c) {
                    var btn = document.getElementById('gulf_' + c);
                    if (btn) {
                        if (state['gulf_' + c]) { btn.classList.add('active'); } else { btn.classList.remove('active'); }
                    }
                });

                handleRegionChange();

                ['kuwait', 'qatar', 'bahrain', 'oman'].forEach(function (c) {
                    if (state['gulf_' + c]) {
                        buildGulfCountryCustomers(c);
                    }
                });
            }
        }

        // ── Customer List Builders ───────────────────────────────
        function buildCustomerChecklist(region, containerId) {
            var container = document.getElementById(containerId);
            if (!container) return;

            var customers = CUSTOMERS_BY_REGION[region] || [];

            customers.forEach(function (customer) {
                var existing = container.querySelector('[data-customer-id="' + customer.id + '"]');
                if (existing) return;

                var pill = document.createElement('div');
                pill.className = 'customer-pill';
                pill.dataset.customerId = customer.id;
                pill.dataset.customerName = customer.name;
                pill.dataset.region = region;
                pill.textContent = customer.name;

                pill.addEventListener('click', function () {
                    this.classList.toggle('selected');
                    handleCustomerToggle(this);
                    calculateCompletion();
                    scheduleAutosave();
                });

                container.appendChild(pill);
            });
        }

        function selectAllCustomers(containerId, btn) {
            var container = document.getElementById(containerId);
            if (!container) return;
            var pills = container.querySelectorAll('.customer-pill');
            var allSelected = Array.from(pills).every(function (p) { return p.classList.contains('selected'); });

            if (allSelected) {
                pills.forEach(function (pill) {
                    pill.classList.remove('selected');
                    handleCustomerToggle(pill);
                });
                if (btn) btn.textContent = 'Select All';
            } else {
                pills.forEach(function (pill) {
                    if (!pill.classList.contains('selected')) {
                        pill.classList.add('selected');
                        handleCustomerToggle(pill);
                    }
                });
                if (btn) btn.textContent = 'Deselect All';
            }
            calculateCompletion();
            scheduleAutosave();
        }

        function buildGulfCountryCustomers(country) {
            var grid = document.getElementById('gulfCustomerGrid');
            if (grid.querySelector('[data-country="' + country + '"]')) return;

            var customers = CUSTOMERS_BY_REGION[country] || [];
            if (customers.length === 0) return;

            var block = document.createElement('div');
            block.className = 'gulf-country-block';
            block.dataset.country = country;

            var label = document.createElement('div');
            label.className = 'gulf-country-label';
            label.textContent = country.charAt(0).toUpperCase() + country.slice(1) + ' Customers';
            block.appendChild(label);

            var checklist = document.createElement('div');
            checklist.className = 'customer-checklist';
            checklist.id = 'gulfCustomers_' + country;
            block.appendChild(checklist);

            var selectAllBtn = document.createElement('button');
            selectAllBtn.type = 'button';
            selectAllBtn.className = 'btn btn--secondary btn--sm';
            selectAllBtn.textContent = 'Select All';
            selectAllBtn.addEventListener('click', function () {
                selectAllCustomers('gulfCustomers_' + country, this);
            });
            block.insertBefore(selectAllBtn, checklist);

            grid.appendChild(block);
            buildCustomerChecklist(country, 'gulfCustomers_' + country);
        }

        function removeGulfCountryCustomers(country) {
            var grid = document.getElementById('gulfCustomerGrid');
            var block = grid.querySelector('[data-country="' + country + '"]');
            if (block) {
                block.querySelectorAll('.customer-pill.selected').forEach(function (pill) {
                    removeDeliverableBlock(pill.dataset.customerId);
                });
                block.remove();
            }
        }

        // ── Region Handling ──────────────────────────────────────
        function handleRegionChange() {
            var uaeActive = document.getElementById('region_uae').classList.contains('active');
            var gulfActive = document.getElementById('region_gulf').classList.contains('active');

            var uaeBlock = document.getElementById('blockUAECustomers');
            var gulfBlock = document.getElementById('blockGulf');

            if (uaeActive) {
                uaeBlock.classList.remove('hidden');
                buildCustomerChecklist('uae', 'uaeCustomerList');
            } else {
                uaeBlock.classList.add('hidden');
                document.querySelectorAll('#uaeCustomerList .customer-pill.selected').forEach(function (pill) {
                    removeDeliverableBlock(pill.dataset.customerId);
                });
            }

            if (gulfActive) {
                gulfBlock.classList.remove('hidden');
            } else {
                gulfBlock.classList.add('hidden');
                ['kuwait', 'qatar', 'bahrain', 'oman'].forEach(function (country) {
                    var el = document.getElementById('gulf_' + country);
                    if (el) el.classList.remove('active');
                    removeGulfCountryCustomers(country);
                });
            }

            calculateCompletion();
        }

        // ── Customer Toggle ──────────────────────────────────────
        function handleCustomerToggle(pill) {
            if (pill.classList.contains('selected')) {
                addDeliverableBlock(
                    pill.dataset.customerId,
                    pill.dataset.customerName,
                    pill.dataset.region
                );
            } else {
                removeDeliverableBlock(pill.dataset.customerId);
            }
        }

        // ── Deliverable Blocks ───────────────────────────────────
        function addDeliverableBlock(customerId, customerName, region) {
            var body = document.getElementById('deliverablesBody');
            if (body.querySelector('[data-customer-id="' + customerId + '"]')) return;

            document.getElementById('sectionDeliverables').classList.remove('hidden');

            var regionSection = body.querySelector(
                '.deliverables-region-section[data-region="' + region + '"]'
            );
            if (!regionSection) {
                regionSection = document.createElement('div');
                regionSection.className = 'deliverables-region-section';
                regionSection.dataset.region = region;

                var heading = document.createElement('div');
                heading.className = 'deliverables-region-heading';
                heading.textContent = region === 'uae' ? 'UAE' :
                    region.charAt(0).toUpperCase() + region.slice(1);
                regionSection.appendChild(heading);

                if (region !== 'uae') {
                    var applyBtn = document.createElement('button');
                    applyBtn.type = 'button';
                    applyBtn.className = 'btn btn--secondary apply-dates-btn';
                    applyBtn.textContent = 'Apply same dates to all ' +
                        region.charAt(0).toUpperCase() + region.slice(1) + ' customers';
                    applyBtn.addEventListener('click', function () {
                        applyDatesToRegion(region);
                    });
                    regionSection.appendChild(applyBtn);
                }

                body.appendChild(regionSection);
            }

            var block = document.createElement('div');
            block.className = 'deliverables-customer-block';
            block.dataset.customerId = customerId;

            // Build the 00:00–23:00 time options once and reuse per block
            var timeOptions = '<option value="">— Any —</option>';
            for (var h = 0; h < 24; h++) {
                var hh = (h < 10 ? '0' : '') + h + ':00';
                timeOptions += '<option value="' + hh + '">' + hh + '</option>';
            }

            block.innerHTML =
                '<h4 class="deliverables-customer-heading">' + customerName + '</h4>' +
                '<div class="deliverables-customer-dates">' +
                '<div class="customer-date-field">' +
                '<label class="customer-date-label">Design Deadline</label>' +
                '<input type="date" class="form-input" id="design_deadline_' + customerId + '">' +
                '</div>' +
                '<div class="customer-date-field">' +
                '<label class="customer-date-label">Time</label>' +
                '<select class="form-select" id="design_deadline_time_' + customerId + '" style="max-width:110px;">' +
                timeOptions +
                '</select>' +
                '</div>' +
                '<div class="customer-date-field">' +
                '<label class="customer-date-label">Installation Date</label>' +
                '<input type="date" class="form-input" id="installation_date_' + customerId + '">' +
                '</div>' +
                '</div>' +
                '<div class="deliverable-rows" id="deliverableRows_' + customerId + '"></div>' +
                '<button type="button" class="btn-add-inline add-deliverable-btn" ' +
                'data-customer-id="' + customerId + '">+ Add Deliverable</button>';

            var applyBtn = regionSection.querySelector('.apply-dates-btn');
            if (applyBtn) {
                regionSection.insertBefore(block, applyBtn);
            } else {
                regionSection.appendChild(block);
            }

            block.querySelector('.add-deliverable-btn').addEventListener('click', function () {
                fetchAndShowDeliverableSelector(customerId);
            });
        }

        function removeDeliverableBlock(customerId) {
            var block = document.querySelector(
                '.deliverables-customer-block[data-customer-id="' + customerId + '"]'
            );
            if (block) {
                var regionSection = block.closest('.deliverables-region-section');
                block.remove();
                if (regionSection &&
                    regionSection.querySelectorAll('.deliverables-customer-block').length === 0) {
                    regionSection.remove();
                }
            }

            if (document.querySelectorAll('.deliverables-customer-block').length === 0) {
                document.getElementById('sectionDeliverables').classList.add('hidden');
            }
            calculateCompletion();
        }

        function applyDatesToRegion(region) {
            var blocks = document.querySelectorAll(
                '.deliverables-region-section[data-region="' + region + '"] .deliverables-customer-block'
            );
            if (blocks.length < 2) return;

            var firstId = blocks[0].dataset.customerId;
            var designVal = document.getElementById('design_deadline_' + firstId).value;
            var timeEl = document.getElementById('design_deadline_time_' + firstId);
            var timeVal = timeEl ? timeEl.value : '';
            var installVal = document.getElementById('installation_date_' + firstId).value;

            for (var i = 1; i < blocks.length; i++) {
                var cid = blocks[i].dataset.customerId;
                var ddEl = document.getElementById('design_deadline_' + cid);
                var ddtEl = document.getElementById('design_deadline_time_' + cid);
                var instEl = document.getElementById('installation_date_' + cid);
                if (ddEl) ddEl.value = designVal;
                if (ddtEl) ddtEl.value = timeVal;
                if (instEl) instEl.value = installVal;
            }
        }

        // ── Deliverable Selector ─────────────────────────────────
        function fetchAndShowDeliverableSelector(customerId) {
            var clientId = document.getElementById('client_id').value;
            fetch('/projects/deliverable-types/' + customerId + '?client_id=' + clientId)
                .then(function (res) { return res.json(); })
                .then(function (types) {
                    showDeliverableSelector(customerId, clientId, types);
                })
                .catch(function (err) {
                    console.error('Could not load deliverable types:', err);
                });
        }

        function showDeliverableSelector(customerId, clientId, types) {
            var existingSelector = document.getElementById('delSelector_' + customerId);
            if (existingSelector) existingSelector.remove();

            var rowsContainer = document.getElementById('deliverableRows_' + customerId);

            var selector = document.createElement('div');
            selector.id = 'delSelector_' + customerId;
            selector.style.marginTop = '10px';

            var select = document.createElement('select');
            select.className = 'form-select';

            var defaultOpt = document.createElement('option');
            defaultOpt.value = '';
            defaultOpt.textContent = '— Select deliverable —';
            select.appendChild(defaultOpt);

            types.forEach(function (type) {
                var opt = document.createElement('option');
                opt.value = type.id;
                opt.textContent = type.is_custom ? type.name + ' (Custom)' : type.name;
                opt.dataset.disciplines = JSON.stringify(type.disciplines);
                opt.dataset.referenceImage = type.reference_image || '';
                select.appendChild(opt);
            });

            var customOpt = document.createElement('option');
            customOpt.value = 'custom';
            customOpt.textContent = '+ Add custom deliverable';
            select.appendChild(customOpt);

            selector.appendChild(select);
            rowsContainer.after(selector);

            select.addEventListener('change', function () {
                var selected = this.options[this.selectedIndex];
                if (this.value === 'custom') {
                    selector.remove();
                    showCustomDeliverableForm(customerId, clientId, types);
                } else if (this.value) {
                    var disciplines = JSON.parse(selected.dataset.disciplines);
                    addDeliverableRow(customerId, this.value, selected.text, disciplines, selected.dataset.referenceImage);
                    selector.remove();
                }
            });
        }

        function addDeliverableRow(customerId, typeId, name, disciplines, referenceImage) {
            var rowsContainer = document.getElementById('deliverableRows_' + customerId);

            var row = document.createElement('div');
            row.className = 'deliverable-row';
            row.dataset.typeId = typeId;
            row.dataset.name = name;

            var disciplineTags = disciplines.map(function (d) {
                return '<span class="discipline-tag tag--' + d + '">' + d.toUpperCase() + '</span>';
            }).join('');

            // Thumbnail is optional — most rows simply won't have one, so
            // this collapses to an empty string and the row looks exactly
            // like it did before whenever there's no image to show.
            var thumbnail = referenceImage ?
                '<img src="/static/deliverable-images/' + referenceImage + '" class="deliverable-row-thumb">' : '';

            row.innerHTML =
                thumbnail +
                '<span class="deliverable-row-name">' + name + '</span>' +
                '<div class="deliverable-row-disciplines">' + disciplineTags + '</div>' +
                '<button type="button" class="btn-remove-deliverable" title="Remove">&times;</button>';

            row.querySelector('.btn-remove-deliverable').addEventListener('click', function () {
                row.remove();
                calculateCompletion();
            });

            rowsContainer.appendChild(row);
            calculateCompletion();
        }

        function showCustomDeliverableForm(customerId, clientId, types) {
            var rowsContainer = document.getElementById('deliverableRows_' + customerId);

            var form = document.createElement('div');
            form.className = 'inline-add-form';
            form.style.flexDirection = 'column';
            form.style.alignItems = 'flex-start';
            form.style.gap = '8px';
            form.style.marginTop = '10px';

            var nameInput = document.createElement('input');
            nameInput.type = 'text';
            nameInput.className = 'form-input';
            nameInput.placeholder = 'Deliverable name';

            var disciplineRow = document.createElement('div');
            disciplineRow.style.display = 'flex';
            disciplineRow.style.gap = '12px';

            ['2d', '3d', 'technical'].forEach(function (d) {
                var lbl = document.createElement('label');
                lbl.style.display = 'flex';
                lbl.style.alignItems = 'center';
                lbl.style.gap = '4px';
                lbl.style.fontSize = '0.85rem';
                var cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.value = d;
                lbl.appendChild(cb);
                lbl.appendChild(document.createTextNode(d.toUpperCase()));
                disciplineRow.appendChild(lbl);
            });

            // NEW — optional reference image. Just builds a labeled file input;
            // nothing happens with whatever gets chosen until Add is clicked.
            var imageLabel = document.createElement('label');
            imageLabel.style.fontSize = '0.85rem';
            imageLabel.style.display = 'flex';
            imageLabel.style.flexDirection = 'column';
            imageLabel.style.gap = '4px';
            imageLabel.textContent = 'Reference image (optional)';

            var imageInput = document.createElement('input');
            imageInput.type = 'file';
            imageInput.accept = 'image/*';
            imageLabel.appendChild(imageInput);

            var warningMsg = document.createElement('div');
            warningMsg.style.color = 'var(--rose)';
            warningMsg.style.fontSize = '0.85rem';
            warningMsg.style.display = 'none';

            var btnRow = document.createElement('div');
            btnRow.style.display = 'flex';
            btnRow.style.gap = '8px';

            var confirmBtn = document.createElement('button');
            confirmBtn.type = 'button';
            confirmBtn.className = 'btn btn--primary btn--sm';
            confirmBtn.textContent = 'Add';

            var cancelBtn = document.createElement('button');
            cancelBtn.type = 'button';
            cancelBtn.className = 'btn btn--secondary btn--sm';
            cancelBtn.textContent = 'Cancel';

            btnRow.appendChild(confirmBtn);
            btnRow.appendChild(cancelBtn);

            form.appendChild(nameInput);
            form.appendChild(disciplineRow);
            form.appendChild(imageLabel);   // NEW
            form.appendChild(warningMsg);
            form.appendChild(btnRow);

            rowsContainer.after(form);

            // Actually creates the DeliverableType, given whatever reference image
            // filename we ended up with (or null if none was chosen). Pulled out
            // as its own function so the click handler below can call it either
            // straight away (no image picked) or after the upload finishes (image
            // picked) — same creation call either way, just a different starting point.
            function createDeliverableType(referenceImage) {
                fetch('/projects/deliverable-types/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: nameInput.value.trim(),
                        client_id: clientId,
                        customer_id: customerId,
                        disciplines: Array.from(
                            form.querySelectorAll('input[type="checkbox"]:checked')
                        ).map(function (cb) { return cb.value; }),
                        reference_image: referenceImage
                    })
                })
                    .then(function (res) { return res.json(); })
                    .then(function (data) {
                        if (data.error) {
                            warningMsg.textContent = data.error;
                            warningMsg.style.display = 'block';
                            btnDone(confirmBtn);
                            return;
                        }
                        types.push({ id: data.id, name: data.name, disciplines: data.disciplines, is_custom: true });
                        addDeliverableRow(customerId, data.id, data.name, data.disciplines, data.reference_image);
                        form.remove();
                    })
                    .catch(function (err) {
                        warningMsg.textContent = 'Something went wrong. Please try again.';
                        warningMsg.style.display = 'block';
                        btnDone(confirmBtn);
                    });
            }

            confirmBtn.addEventListener('click', function () {
                var name = nameInput.value.trim();
                var disciplines = Array.from(
                    form.querySelectorAll('input[type="checkbox"]:checked')
                ).map(function (cb) { return cb.value; });

                warningMsg.style.display = 'none';
                warningMsg.textContent = '';
                nameInput.style.borderColor = '';

                if (!name) {
                    warningMsg.textContent = 'Please enter a deliverable name.';
                    warningMsg.style.display = 'block';
                    nameInput.style.borderColor = 'var(--rose)';
                    return;
                }

                if (disciplines.length === 0) {
                    warningMsg.textContent = 'Please select at least one discipline.';
                    warningMsg.style.display = 'block';
                    return;
                }

                var duplicate = types.find(function (t) {
                    return t.name.toLowerCase() === name.toLowerCase();
                });

                if (duplicate) {
                    warningMsg.textContent = 'A deliverable called "' + name + '" already exists for this customer.';
                    warningMsg.style.display = 'block';
                    nameInput.style.borderColor = 'var(--rose)';
                    return;
                }

                btnLoading(confirmBtn);

                // NEW — if an image was chosen, upload it first and only create the
                // deliverable type once we have a filename back. No image chosen?
                // Skip straight to creation.
                var chosenFile = imageInput.files[0];
                if (chosenFile) {
                    var formData = new FormData();
                    formData.append('file', chosenFile);

                    fetch('/projects/deliverable-types/upload-image', {
                        method: 'POST',
                        body: formData
                    })
                        .then(function (res) { return res.json(); })
                        .then(function (uploadData) {
                            if (!uploadData.success) {
                                warningMsg.textContent = uploadData.error || 'Image upload failed.';
                                warningMsg.style.display = 'block';
                                btnDone(confirmBtn);
                                return;
                            }
                            createDeliverableType(uploadData.filename);
                        })
                        .catch(function () {
                            warningMsg.textContent = 'Something went wrong uploading the image.';
                            warningMsg.style.display = 'block';
                            btnDone(confirmBtn);
                        });
                } else {
                    createDeliverableType(null);
                }
            });

            cancelBtn.addEventListener('click', function () {
                form.remove();
            });
        }

        // ── Autosave ─────────────────────────────────────────────
        function collectFormData() {
            var teams = Array.from(
                document.querySelectorAll('input[name="design_teams"]:checked')
            ).map(function (cb) { return cb.value; });

            // Concept & KV are now merged — has_kv always mirrors has_concept
            var hasConceptMergedEl = document.getElementById('has_concept');
            var hasKv = hasConceptMergedEl ? hasConceptMergedEl.value === 'true' : false;

            var customerDates = {};
            document.querySelectorAll('.deliverables-customer-block').forEach(function (block) {
                var cid = block.dataset.customerId;
                var ddEl = document.getElementById('design_deadline_' + cid);
                var ddtEl = document.getElementById('design_deadline_time_' + cid);
                var instEl = document.getElementById('installation_date_' + cid);
                customerDates[cid] = {
                    design_deadline: ddEl ? ddEl.value || null : null,
                    design_deadline_time: ddtEl ? ddtEl.value || null : null,
                    installation_date: instEl ? instEl.value || null : null
                };
            });

            return {
                draft_id: currentDraftId,
                name: document.getElementById('project_name').value.trim(),
                client_id: document.getElementById('client_id').value || null,
                // contact_id is optional (unlike client_id) - a brief can be saved
                // with a client but no specific contact person picked yet, so this
                // guards for the element existing at all (defensive, same pattern
                // used for every other optional field below) AND falls back to null
                // when the placeholder ("— Select Contact —") is still selected.
                contact_id: document.getElementById('contact_id') ? document.getElementById('contact_id').value || null : null,
                cs_lead_id: document.getElementById('cs_lead_id').value || null,
                job_number: document.getElementById('job_number').value.trim() || null,
                design_teams: teams,
                brief_type: document.getElementById('brief_type').value || null,
                urgency: document.getElementById('urgency') ? document.getElementById('urgency').value || null : null,
                required_output: document.getElementById('required_output') ? document.getElementById('required_output').value || null : null,
                concept_requirements: document.getElementById('concept_requirements') ? document.getElementById('concept_requirements').value.trim() || null : null,
                concept_deadline: document.getElementById('concept_deadline') ? document.getElementById('concept_deadline').value || null : null,
                concept_deadline_time: document.getElementById('concept_deadline_time') ? document.getElementById('concept_deadline_time').value || null : null,
                has_concept: document.getElementById('has_concept') ? document.getElementById('has_concept').value === 'true' : false,
                concept_options_required: document.getElementById('concept_options_required') ? parseInt(document.getElementById('concept_options_required').value) || null : null,
                has_kv: hasKv,  // always mirrors has_concept — merged in UI
                kv_requirements: null,
                kv_deadline: null,
                kv_options_required: null,
                briefing_date: document.getElementById('briefing_date') ? document.getElementById('briefing_date').value || null : null,
                first_output_deadline: document.getElementById('first_output_deadline') ? document.getElementById('first_output_deadline').value || null : null,
                final_deadline: document.getElementById('final_deadline') ? document.getElementById('final_deadline').value || null : null,
                customer_dates: customerDates,
                standard_deliverables: (function () { var el = document.getElementById('standard_deliverables_json'); try { return el ? JSON.parse(el.value || '[]') : []; } catch (e) { return []; } })(),
                design_type_id: document.getElementById('design_type_id') ? document.getElementById('design_type_id').value || null : null,
                design_direction_id: document.getElementById('design_direction_id') ? document.getElementById('design_direction_id').value || null : null,
                client_expectation: document.getElementById('client_expectation') ? document.getElementById('client_expectation').value.trim() || null : null,
                what_to_avoid: document.getElementById('what_to_avoid') ? document.getElementById('what_to_avoid').value.trim() || null : null,
                additional_information: document.getElementById('additional_information') ? document.getElementById('additional_information').value.trim() || null : null,
            };
        }

        function hasAnyData(data) {
            return data.name || data.client_id || data.job_number ||
                data.design_teams.length > 0 || data.briefing_date ||
                data.brief_type;
        }

        function autosave() {
            var data = collectFormData();
            if (!hasAnyData(data)) return;

            var statusEl = document.getElementById('autosaveStatus');
            statusEl.textContent = 'Saving...';

            fetch('/projects/autosave', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            })
                .then(function (res) { return res.json(); })
                .then(function (result) {
                    if (result.success) {
                        currentDraftId = result.draft_id;

                        // Show saved confirmation, then fade it out after 2s
                        statusEl.textContent = 'Saved ✓';
                        setTimeout(function () { statusEl.textContent = ''; }, 2000);

                        // Enable the reference file upload button now that a draft exists
                        var createRefBtn = document.getElementById('createRefFileBtn');
                        if (createRefBtn && !createRefBtn.dataset.projectId) {
                            createRefBtn.dataset.projectId = result.draft_id;
                            createRefBtn.disabled = false;
                            var createStatus = document.getElementById('createRefFileStatus');
                            if (createStatus) createStatus.textContent = '';
                        }
                    } else {
                        // Server returned success: false — show the error message
                        statusEl.textContent = 'Save failed';
                    }
                })
                .catch(function () {
                    // Network or parse error
                    statusEl.textContent = 'Save failed';
                });
        }

        function scheduleAutosave() {
            if (typeof EDIT_MODE !== 'undefined' && EDIT_MODE) return;
            clearTimeout(autosaveTimeout);
            autosaveTimeout = setTimeout(autosave, 2000);
        }

        // Exposed on window so client_directory.js (a separate file/closure,
        // loaded further down this same page) can trigger these after it
        // programmatically adds/selects an option - e.g. right after a new
        // company is created via the shared Add Company modal and selected
        // in #client_id. Everything else in THIS closure already calls them
        // as plain local functions; this is purely an external hook.
        window.calculateCompletion = calculateCompletion;
        window.scheduleAutosave = scheduleAutosave;

        // ── Add New Client / Add New Contact: RETIRED ──────────────────
        //
        // setupAddClient(), fetchContactsForClient(), setupContactCascade(),
        // and setupAddContact() used to live here - a button + inline
        // reveal-form next to #client_id, and the same next to #contact_id.
        // Both were replaced (Client Directory UI work) by a single shared
        // pattern: a "+ Add new company…" / "+ Add new contact…" sentinel
        // option at the bottom of each select, which opens the same Add
        // Company / Add Contact modal used on the Client Directory page
        // instead of a per-page reveal-form. That logic - including the
        // #client_id -> #contact_id cascade fetch, which still needs to
        // happen, just from a different owner now - lives in
        // client_directory.js's initBriefFormIntegration() function.
        //
        // If you're looking for the old reveal-form markup (#btnAddClient /
        // #addClientForm / #btnAddContact / #addContactForm), it's gone
        // from create.html too - removed in the same change.

        // ── Submit Form ───────────────────────────────────────────
        function showSubmitBlockedMessage() {
            showToast('Please complete all required fields before submitting.', 'error');
        }

        function openReviewModal() {
            var projectName = document.getElementById('project_name').value.trim();
            var jobNumber = document.getElementById('job_number').value.trim();
            var csLeadEl = document.getElementById('cs_lead_id');
            var csLeadText = csLeadEl.tagName === 'SELECT'
                ? csLeadEl.options[csLeadEl.selectedIndex].text
                : (document.querySelector('.form-static-value') || { textContent: '' }).textContent.trim();
            var briefType = document.getElementById('brief_type').value;

            document.getElementById('reviewProjectName').textContent = projectName;
            document.getElementById('reviewJobNumber').textContent = jobNumber;
            document.getElementById('reviewCSLead').textContent = csLeadText;
            document.getElementById('reviewBriefType').textContent = briefType === 'ccm' ? 'C&CM' : 'Standard';

            var list = document.getElementById('reviewDeliverablesList');
            list.innerHTML = '';

            if (briefType === 'standard') {
                var dtEl = document.getElementById('design_type_id');
                var dtText = dtEl && dtEl.options[dtEl.selectedIndex] ? dtEl.options[dtEl.selectedIndex].text : '—';
                var note = document.createElement('div');
                note.className = 'review-customer-item';
                note.innerHTML = '<div class="review-meta-grid" style="margin:0"><div class="review-meta-item"><span class="review-meta-label">Type of Design</span><span class="review-meta-value">' + dtText + '</span></div></div><p style="margin-top:0.75rem;font-size:0.85rem;color:var(--text-muted)">Deliverables are added after the project is created.</p>';
                list.appendChild(note);
            }

            var regionSections = document.querySelectorAll('.deliverables-region-section');

            regionSections.forEach(function (regionSection) {
                var region = regionSection.dataset.region;

                var regionHeading = document.createElement('div');
                regionHeading.className = 'review-region-heading';
                regionHeading.textContent = region === 'uae' ? 'UAE' :
                    region.charAt(0).toUpperCase() + region.slice(1);
                list.appendChild(regionHeading);

                var customerBlocks = regionSection.querySelectorAll('.deliverables-customer-block');

                customerBlocks.forEach(function (block) {
                    var customerName = block.querySelector('.deliverables-customer-heading').textContent;

                    var customerItem = document.createElement('div');
                    customerItem.className = 'review-customer-item';

                    var customerNameEl = document.createElement('div');
                    customerNameEl.className = 'review-customer-name';
                    customerNameEl.textContent = customerName;
                    customerItem.appendChild(customerNameEl);

                    var deliverableRows = block.querySelectorAll('.deliverable-row');

                    deliverableRows.forEach(function (row) {
                        var name = row.dataset.name;
                        var disciplines = row.querySelectorAll('.discipline-tag');

                        var deliverableRow = document.createElement('div');
                        deliverableRow.className = 'review-deliverable-row';

                        var nameSpan = document.createElement('span');
                        nameSpan.textContent = name;
                        deliverableRow.appendChild(nameSpan);

                        disciplines.forEach(function (tag) {
                            var tagClone = tag.cloneNode(true);
                            deliverableRow.appendChild(tagClone);
                        });

                        customerItem.appendChild(deliverableRow);
                    });

                    list.appendChild(customerItem);
                });
            });

            document.getElementById('reviewModalOverlay').classList.remove('hidden');
            if (window.helixPolling) window.helixPolling.pause();
        }
        
        // ── Start Project modal ───────────────────────────────────────────────────────
        // The start-project-modal already exists in detail.html.
        // These functions open/close it and POST to the start-project route on confirm.

        var _startProjectId = null; // stores the project ID between open and confirm

        function openStartProjectModal(projectId) {
            _startProjectId = projectId;
            document.getElementById('start-project-modal').classList.remove('hidden');
            if (window.helixPolling) window.helixPolling.pause();
        }

        function closeStartProjectModal() {
            document.getElementById('start-project-modal').classList.add('hidden');
            _startProjectId = null;
            if (window.helixPolling) window.helixPolling.resume();
        }

        var startConfirmBtn = document.getElementById('start-project-confirm');
        if (startConfirmBtn) {
            startConfirmBtn.addEventListener('click', function () {
                if (!_startProjectId) return;
                btnLoading(startConfirmBtn);
                // POST to the existing start-project route
                fetch('/projects/' + _startProjectId + '/start-project', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                })
                    .then(function (res) { return res.json(); })
                    .then(function (data) {
                        if (data.success) {
                            // Reload so the status badge and button update correctly
                            window.location.reload();
                        } else {
                            showToast(data.error || 'Could not start project.', 'error');
                            btnDone(startConfirmBtn);
                            closeStartProjectModal();
                        }
                    })
                    .catch(function () {
                        showToast('Something went wrong.', 'error');
                        btnDone(startConfirmBtn);
                    });
            });
        }

        // ── Edit Mode: Restore State ─────────────────────────────
        function restoreEditState() {
            // Snapshot has_concept BEFORE switchBriefType resets it to 'false'.
            // switchBriefType always clears the flag as part of its reset logic,
            // so if we read it afterwards the check always fails and C&KV is lost.
            var hasConceptEl = document.getElementById('has_concept');
            var savedHasConcept = hasConceptEl ? hasConceptEl.value : 'false';

            var briefTypeEl = document.getElementById('brief_type');
            if (briefTypeEl && briefTypeEl.value) {
                switchBriefType(briefTypeEl.value, true); // silent — don't autosave on restore
            }

            // Restore the saved value — switchBriefType just wiped it to 'false'
            if (hasConceptEl) hasConceptEl.value = savedHasConcept;
            if (savedHasConcept === 'true') {
                document.getElementById('sectionConceptKV').classList.remove('hidden');
                var conceptKVBtn = document.getElementById('btnConceptKVToggle');
                if (conceptKVBtn) conceptKVBtn.classList.add('active');
            }

            if (!EXISTING_CUSTOMERS || EXISTING_CUSTOMERS.length === 0) {
                calculateCompletion();
                return;
            }

            var hasUAE = EXISTING_CUSTOMERS.some(function (c) { return c.region === 'uae'; });
            var gulfCountries = ['kuwait', 'qatar', 'bahrain', 'oman'];
            var activeGulfCountries = gulfCountries.filter(function (country) {
                return EXISTING_CUSTOMERS.some(function (c) { return c.region === country; });
            });

            if (hasUAE) {
                var uaeBtn = document.getElementById('region_uae');
                if (uaeBtn) {
                    uaeBtn.classList.add('active');
                    document.getElementById('blockUAECustomers').classList.remove('hidden');
                    buildCustomerChecklist('uae', 'uaeCustomerList');
                }
            }

            if (activeGulfCountries.length > 0) {
                var gulfBtn = document.getElementById('region_gulf');
                if (gulfBtn) {
                    gulfBtn.classList.add('active');
                    document.getElementById('blockGulf').classList.remove('hidden');
                }
                activeGulfCountries.forEach(function (country) {
                    var btn = document.getElementById('gulf_' + country);
                    if (btn) {
                        btn.classList.add('active');
                        buildGulfCountryCustomers(country);
                    }
                });
            }

            EXISTING_CUSTOMERS.forEach(function (ec) {
                var pill = document.querySelector('.customer-pill[data-customer-id="' + ec.customer_id + '"]');
                if (pill && !pill.classList.contains('selected')) {
                    pill.classList.add('selected');
                    addDeliverableBlock(ec.customer_id, pill.dataset.customerName, ec.region);
                }
                var ddEl = document.getElementById('design_deadline_' + ec.customer_id);
                var ddtEl = document.getElementById('design_deadline_time_' + ec.customer_id);
                var instEl = document.getElementById('installation_date_' + ec.customer_id);
                if (ddEl && ec.design_deadline) ddEl.value = ec.design_deadline;
                if (ddtEl && ec.design_deadline_time) ddtEl.value = ec.design_deadline_time;
                if (instEl && ec.installation_date) instEl.value = ec.installation_date;
            });

            EXISTING_DELIVERABLES.forEach(function (ed) {
                addDeliverableRow(ed.customer_id, ed.type_id, ed.name, ed.disciplines);
            });

            calculateCompletion();
        }

        // ── Edit Mode: Submit ────────────────────────────────────
        function submitEditedProject() {
            var btn = document.getElementById('btnReviewSubmit');
            btnLoading(btn);

            var formData = collectFormData();

            var regions = [];
            var uaeBtn2 = document.getElementById('region_uae');
            if (uaeBtn2 && uaeBtn2.classList.contains('active')) regions.push('uae');
            var gulfBtn2 = document.getElementById('region_gulf');
            if (gulfBtn2 && gulfBtn2.classList.contains('active')) {
                ['kuwait', 'qatar', 'bahrain', 'oman'].forEach(function (country) {
                    var b = document.getElementById('gulf_' + country);
                    if (b && b.classList.contains('active')) regions.push(country);
                });
            }

            var deliverables = [];
            document.querySelectorAll('.deliverables-customer-block').forEach(function (block) {
                var customerId = block.dataset.customerId;
                var regionSection = block.closest('.deliverables-region-section');
                var region = regionSection.dataset.region;
                block.querySelectorAll('.deliverable-row').forEach(function (row) {
                    deliverables.push({
                        customer_id: customerId,
                        region: region,
                        type_id: row.dataset.typeId,
                        name: row.dataset.name
                    });
                });
            });

            var payload = Object.assign({}, formData, { regions: regions, deliverables: deliverables });

            fetch('/projects/' + EDIT_PROJECT_ID + '/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
                .then(function (res) { return res.json(); })
                .then(function (data) {
                    if (data.error) {
                        showToast(data.error, 'error');
                        btnDone(btn);
                        return;
                    }
                    window.location.href = data.redirect_url + '?toast=Project+updated+successfully';
                })
                .catch(function () {
                    showToast('Something went wrong. Please try again.', 'error');
                    btnDone(btn);
                });
        }

        // ── Event Listeners ──────────────────────────────────────

        document.querySelectorAll('.brief-type-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var clientId = document.getElementById('client_id').value;
                if (!clientId) {
                    showToast('Please select a client before choosing a brief type.', 'error');
                    return;
                }
                switchBriefType(this.dataset.type);
            });
        });

        var btnConceptKVToggle = document.getElementById('btnConceptKVToggle');
        if (btnConceptKVToggle) {
            btnConceptKVToggle.addEventListener('click', function () {
                var section = document.getElementById('sectionConceptKV');
                var hasConceptInput = document.getElementById('has_concept');
                var isOpen = !section.classList.contains('hidden');
                section.classList.toggle('hidden', isOpen);
                hasConceptInput.value = isOpen ? 'false' : 'true';
                btnConceptKVToggle.classList.toggle('active', !isOpen);
                scheduleAutosave();
            });
        }

        document.querySelectorAll('.region-btn[data-region]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                this.classList.toggle('active');
                handleRegionChange();
            });
        });

        ['kuwait', 'qatar', 'bahrain', 'oman'].forEach(function (country) {
            var el = document.getElementById('gulf_' + country);
            if (el) {
                el.addEventListener('click', function () {
                    this.classList.toggle('active');
                    if (this.classList.contains('active')) {
                        buildGulfCountryCustomers(country);
                    } else {
                        removeGulfCountryCustomers(country);
                    }
                    calculateCompletion();
                });
            }
        });

        document.querySelectorAll(
            '#sectionBasics input, #sectionBasics select'
        ).forEach(function (el) {
            el.addEventListener('change', function () {
                calculateCompletion();
                scheduleAutosave();
            });
            if (el.type === 'text') {
                el.addEventListener('keyup', function () {
                    calculateCompletion();
                    scheduleAutosave();
                });
            }
        });

        document.querySelectorAll(
            '#sectionCCM select, #sectionCCM textarea'
        ).forEach(function (el) {
            el.addEventListener('change', function () {
                calculateCompletion();
                scheduleAutosave();
            });
        });

        document.querySelectorAll(
            '#sectionStandard select, #sectionStandard textarea'
        ).forEach(function (el) {
            el.addEventListener('change', function () {
                calculateCompletion();
                scheduleAutosave();
            });
        });

        // btnConceptToggle and btnKVToggle replaced by merged btnConceptKVToggle above

        var btnReviewSubmit = document.getElementById('btnReviewSubmit');
        if (btnReviewSubmit) {
            btnReviewSubmit.addEventListener('click', function () {
                if (typeof EDIT_MODE !== 'undefined' && EDIT_MODE) {
                    submitEditedProject();
                } else if (currentCompletion < 100) {
                    showSubmitBlockedMessage();
                } else {
                    openReviewModal();
                }
            });
        }

        var reviewModalClose = document.getElementById('reviewModalClose');
        if (reviewModalClose) {
            reviewModalClose.addEventListener('click', function () {
                document.getElementById('reviewModalOverlay').classList.add('hidden');
                if (window.helixPolling) window.helixPolling.resume();
            });
        }

        var reviewModalCancel = document.getElementById('reviewModalCancel');
        if (reviewModalCancel) {
            reviewModalCancel.addEventListener('click', function () {
                document.getElementById('reviewModalOverlay').classList.add('hidden');
                if (window.helixPolling) window.helixPolling.resume();
            });
        }

        var btnSubmitBrief = document.getElementById('btnSubmitBrief');
        if (btnSubmitBrief) {
            btnSubmitBrief.addEventListener('click', function () {
                btnLoading(btnSubmitBrief);

                var formData = collectFormData();

                var regions = [];
                var uaeBtn = document.getElementById('region_uae');
                if (uaeBtn && uaeBtn.classList.contains('active')) {
                    regions.push('uae');
                }
                var gulfBtn = document.getElementById('region_gulf');
                if (gulfBtn && gulfBtn.classList.contains('active')) {
                    ['kuwait', 'qatar', 'bahrain', 'oman'].forEach(function (country) {
                        var btn = document.getElementById('gulf_' + country);
                        if (btn && btn.classList.contains('active')) {
                            regions.push(country);
                        }
                    });
                }

                var deliverables = [];
                document.querySelectorAll('.deliverables-customer-block').forEach(function (block) {
                    var customerId = block.dataset.customerId;
                    var regionSection = block.closest('.deliverables-region-section');
                    var region = regionSection.dataset.region;

                    block.querySelectorAll('.deliverable-row').forEach(function (row) {
                        deliverables.push({
                            customer_id: customerId,
                            region: region,
                            type_id: row.dataset.typeId,
                            name: row.dataset.name
                        });
                    });
                });

                var payload = Object.assign({}, formData, {
                    regions: regions,
                    deliverables: deliverables
                });

                fetch('/projects/submit', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                })
                    .then(function (res) { return res.json(); })
                    .then(function (data) {
                        if (data.error) {
                            showToast(data.error, 'error');
                            btnDone(btnSubmitBrief);
                            return;
                        }
                        clearTimeout(autosaveTimeout);
                        // If the FOC number was already taken by another project, the server
                        // silently assigned the next available one and signals us here.
                        var toastMsg = data.job_number_changed
                            ? 'Project submitted. Job number updated to ' + data.new_job_number + ' — ' + data.old_job_number + ' was already taken.'
                            : 'Project submitted successfully';
                        window.location.href = data.redirect_url + '?toast=' + encodeURIComponent(toastMsg);
                    })
                    .catch(function () {
                        showToast('Something went wrong. Please try again.', 'error');
                        btnDone(btnSubmitBrief);
                    });
            });
        }

        // ── Initialise ───────────────────────────────────────────
        var btnSelectAllUAE = document.getElementById('btnSelectAllUAE');
        if (btnSelectAllUAE) {
            btnSelectAllUAE.addEventListener('click', function () {
                selectAllCustomers('uaeCustomerList', this);
            });
        }

        // setupAddClient() / setupContactCascade() / setupAddContact() used
        // to be called here - all three retired, see the comment block
        // above scheduleAutosave() for where that logic moved to.

        var urlParams = new URLSearchParams(window.location.search);
        var draftIdParam = urlParams.get('draft_id');
        if (draftIdParam) {
            currentDraftId = parseInt(draftIdParam);
            var briefTypeEl = document.getElementById('brief_type');
            if (briefTypeEl && briefTypeEl.value) {
                switchBriefType(briefTypeEl.value, true); // silent — don't autosave on draft restore
            }
            var hasConceptEl = document.getElementById('has_concept');
            if (hasConceptEl && hasConceptEl.value === 'true') {
                document.getElementById('sectionConceptKV').classList.remove('hidden');
                var conceptKVToggleBtn = document.getElementById('btnConceptKVToggle');
                if (conceptKVToggleBtn) conceptKVToggleBtn.classList.add('active');
            }
        } else if (typeof EDIT_MODE !== 'undefined' && EDIT_MODE) {
            restoreEditState();
        }

        calculateCompletion();

        // ── Reference File Upload on Create Page ─────────────────
        var createRefFileBtn = document.getElementById('createRefFileBtn');
        var createRefFileInput = document.getElementById('createRefFileInput');

        if (createRefFileBtn && createRefFileInput) {
            createRefFileBtn.addEventListener('click', function () {
                if (!this.disabled) createRefFileInput.click();
            });

            createRefFileInput.addEventListener('change', function () {
                var file = createRefFileInput.files[0];
                if (!file) return;

                var projectId = createRefFileBtn.dataset.projectId;
                if (!projectId) return;

                var status = document.getElementById('createRefFileStatus');
                status.textContent = 'Uploading...';

                var formData = new FormData();
                formData.append('file', file);

                fetch('/projects/' + projectId + '/upload-file', {
                    method: 'POST',
                    body: formData
                })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (!data.success) {
                            status.textContent = 'Upload failed.';
                            showToast(data.error || 'File could not be saved to storage.', 'error');
                            return;
                        }
                        status.textContent = 'Uploaded.';
                        setTimeout(function () { status.textContent = ''; }, 3000);
                        createRefFileInput.value = '';

                        var list = document.getElementById('create-reference-files-list');
                        var noFilesMsg = list.querySelector('.no-files-msg');
                        if (noFilesMsg) noFilesMsg.remove();

                        var icons = { jpg: '🖼', jpeg: '🖼', png: '🖼', pdf: '📄', docx: '📝', xlsx: '📊', zip: '📁' };
                        var icon = icons[data.file.file_type] || '📎';

                        var item = document.createElement('div');
                        item.className = 'reference-file-item';
                        item.dataset.fileId = data.file.id;
                        item.innerHTML = `
                    <span class="reference-file-icon">${icon}</span>
                    <span class="reference-file-name">${data.file.original_filename}</span>
                    <span class="reference-file-meta">${data.file.uploaded_by}</span>
                    <div class="reference-file-actions">
                        <a href="/projects/files/${data.file.id}/download"
                           class="btn-secondary btn-sm">Download</a>
                        <button class="btn-danger btn-sm reference-file-delete-btn"
                                data-file-id="${data.file.id}">Remove</button>
                    </div>
                `;
                        item.querySelector('.reference-file-delete-btn').addEventListener('click', handleCreateFileDelete);
                        list.appendChild(item);
                    })
                    .catch(function (err) {
                        status.textContent = 'Upload failed.';
                        console.error(err);
                    });
            });

            function handleCreateFileDelete(e) {
                /* Capture DOM references before the async confirm dialog opens,
                   because 'this' won't be available inside the callback. */
                var fileId = this.dataset.fileId;
                var item = this.closest('.reference-file-item');
                showConfirm('Remove this file?', function () {
                    fetch('/projects/files/' + fileId + '/delete', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' }
                    })
                        .then(function (r) { return r.json(); })
                        .then(function (data) {
                            if (!data.success) return;
                            item.remove();
                            var list = document.getElementById('create-reference-files-list');
                            if (list.querySelectorAll('.reference-file-item').length === 0) {
                                var msg = document.createElement('p');
                                msg.className = 'no-files-msg';
                                msg.textContent = 'No reference files uploaded yet.';
                                list.appendChild(msg);
                            }
                        });
                });
            }

            document.querySelectorAll('#create-reference-files-list .reference-file-delete-btn').forEach(function (btn) {
                btn.addEventListener('click', handleCreateFileDelete);
            });
        }

    } // end sectionBasics wrapper

// ── Dashboard deadline sort ───────────────────────────────────────────────────
// Sorts project table rows by first-output-deadline or final-deadline.
// Exposed at module scope so initAllProjectsFilters / initMyProjectsFilters
// can call it from the ordering dropdown handler.
function sortTableBy(tbody, field) {
    var children = Array.from(tbody.rows);
    var groups = [];
    var i = 0;
    while (i < children.length) {
        var row = children[i];
        if (row.dataset.projectId) {
            var group = [row];
            var next = children[i + 1];
            if (next && next.classList.contains('expansion-row')) {
                group.push(next);
                i += 2;
            } else {
                i++;
            }
            groups.push(group);
        } else {
            i++;
        }
    }
    groups.sort(function (a, b) {
        var aVal = a[0].dataset[field] || '9999-12-31';
        var bVal = b[0].dataset[field] || '9999-12-31';
        return aVal.localeCompare(bVal);
    });
    groups.forEach(function (group) {
        group.forEach(function (row) { tbody.appendChild(row); });
    });
}
