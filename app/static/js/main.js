// main.js — Vitamin-E v1.3
// Shared utilities (toast, confirm, refreshSection), dev tools, scroll position,
// dashboard (approved-projects view, filters, tab switching), account dropdown,
// drafts page. The create/edit brief page (sectionBasics) handler was
// removed at M10 cutover (20 Aug 2026) — that page (create.html) was
// deleted in task #5; this file's own #btnSubmitBrief/#sectionBasics
// block went with it in task #8, since it referenced an element that no
// longer exists anywhere. Briefing is now the overlay's Create mode
// (project_overlay_create.js).
// main.js must be loaded first; notifications.js, admin.js depend on it. (detail.js
// is gone too, same M10 cutover as create.html above — base.html's <script> tag for
// it was only found and removed 24 Aug 2026, see base.html's comment at that spot.)

// main.js - Vitamin-E
console.log("Vitamin-E loaded.");

// ── Open NAS folder in Synology Drive (M10 NAS migration, 21 Aug 2026) ──
// Shared by file-templates.js, project_list.js (project sidebar), and
// project_preproduction_card.js (per-deliverable "Files" button) — any
// button that opens a NAS folder now goes through Synology Drive instead
// of File Station. Drive addresses folders by an opaque internal file_id,
// not by path, so the URL can't be built at render time the way the old
// File Station links were — btn's data-url points at a small JSON route
// that resolves the folder server-side (see app/nas.py's
// build_drive_folder_url()) and hands back the real Drive URL to open.
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
           (matches the existing approval modal pattern) */
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
