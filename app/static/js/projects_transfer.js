// projects_transfer.js — C&CM deliverable transfer modal
//
// IIFE (not DOMContentLoaded) so it runs correctly on SPA navigation
// (sidebar.js re-executes <script> tags on every renav; DOMContentLoaded
// only fires once on the initial full-page load — see feedback_spa_navigation_js.md).
//
// The modal lives in detail.html and is shown/hidden by this script.
// Data flow:
//   1. User clicks "Transfer" on a deliverable row.
//   2. The button carries data-deliverable-id, data-deliverable-name,
//      data-source-customer (human label for the current customer).
//   3. Modal opens: user picks a target customer (search) + mode (move/duplicate).
//   4. On confirm: POST /projects/<id>/deliverables/<d_id>/transfer
//   5. On success: reload the page so the updated brief section re-renders.
//
// TRANSFER_CUSTOMERS (set by detail.html as var) is { region: [{id, name}] }.
// DETAIL_PROJECT_ID (set by detail.html as var) is the current project's integer id.

(function () {
    'use strict';

    // ── State ─────────────────────────────────────────────────────────────────
    var _deliverableId   = null;
    var _selectedCustId  = null;
    var _mode            = 'move';   // 'move' | 'duplicate'
    var _allCustomers    = [];       // flat list: [{id, name, region}]

    // ── DOM refs (lazy — looked up when modal opens, not at IIFE time) ────────
    function _overlay()      { return document.getElementById('transfer-modal-overlay'); }
    function _searchInput()  { return document.getElementById('transfer-customer-search'); }
    function _customerList() { return document.getElementById('transfer-customer-list'); }
    function _modeMove()     { return document.getElementById('transfer-mode-move'); }
    function _modeDupe()     { return document.getElementById('transfer-mode-duplicate'); }
    function _modeHint()     { return document.getElementById('transfer-mode-hint'); }
    function _confirmBtn()   { return document.getElementById('transfer-confirm-btn'); }
    function _errorEl()      { return document.getElementById('transfer-modal-error'); }
    function _fromLabel()    { return document.getElementById('transfer-from-label'); }
    function _titleEl()      { return document.getElementById('transfer-modal-deliverable-name'); }

    // ── Build flat customer list from TRANSFER_CUSTOMERS ──────────────────────
    function _buildCustomerList() {
        _allCustomers = [];
        var cbr = window.TRANSFER_CUSTOMERS || {};
        Object.keys(cbr).sort().forEach(function (region) {
            (cbr[region] || []).forEach(function (c) {
                _allCustomers.push({ id: c.id, name: c.name, region: region });
            });
        });
    }

    // ── Filter + render the customer option list ──────────────────────────────
    function _renderCustomerOptions(query) {
        var list = _customerList();
        if (!list) return;

        var q = (query || '').toLowerCase().trim();
        var filtered = q
            ? _allCustomers.filter(function (c) {
                return c.name.toLowerCase().indexOf(q) !== -1 ||
                       c.region.toLowerCase().indexOf(q) !== -1;
              })
            : _allCustomers;

        if (filtered.length === 0) {
            list.innerHTML = '<div class="transfer-customer-none">No customers found.</div>';
            return;
        }

        list.innerHTML = filtered.map(function (c) {
            var sel = c.id === _selectedCustId ? ' selected' : '';
            return (
                '<button type="button" class="transfer-customer-option' + sel + '" ' +
                'data-id="' + c.id + '" data-name="' + escapeHtml(c.name) + '">' +
                '<span>' + escapeHtml(c.name) + '</span>' +
                '<span class="transfer-region-tag">' + escapeHtml(c.region.toUpperCase()) + '</span>' +
                '</button>'
            );
        }).join('');

        // Attach click handlers to the freshly rendered buttons
        list.querySelectorAll('.transfer-customer-option').forEach(function (btn) {
            btn.addEventListener('click', function () {
                _selectedCustId = parseInt(this.dataset.id, 10);
                _renderCustomerOptions(_searchInput() ? _searchInput().value : '');
                _updateConfirmState();
            });
        });
    }

    // ── Confirm button enabled only when a customer is selected ──────────────
    function _updateConfirmState() {
        var btn = _confirmBtn();
        if (!btn) return;
        btn.disabled = !_selectedCustId;
    }

    // ── Mode toggle ───────────────────────────────────────────────────────────
    var MODE_HINTS = {
        move: 'The deliverable (and its revision history, assignments, and flags) moves to the new customer. The original slot is removed.',
        duplicate: 'A copy is created under the new customer with the same name and assignments. The original remains in place.',
    };

    function _setMode(m) {
        _mode = m;
        var mv = _modeMove();
        var dp = _modeDupe();
        var hint = _modeHint();
        if (mv) mv.classList.toggle('active', m === 'move');
        if (dp) dp.classList.toggle('active', m === 'duplicate');
        if (hint) hint.textContent = MODE_HINTS[m] || '';
    }

    // ── Open / close ──────────────────────────────────────────────────────────
    function openTransferModal(deliverableId, deliverableName, sourceLabel) {
        _deliverableId  = deliverableId;
        _selectedCustId = null;

        var overlay = _overlay();
        if (!overlay) return;

        // Populate header info
        var titleEl = _titleEl();
        if (titleEl) titleEl.textContent = deliverableName;
        var fromLbl = _fromLabel();
        if (fromLbl) fromLbl.innerHTML = 'Currently under <strong>' + escapeHtml(sourceLabel) + '</strong>';

        // Reset state
        _setMode('move');
        var si = _searchInput();
        if (si) si.value = '';
        var err = _errorEl();
        if (err) err.textContent = '';

        _buildCustomerList();
        _renderCustomerOptions('');
        _updateConfirmState();

        // Pause polling while modal is open (pattern from existing modals)
        if (window.helixPolling) window.helixPolling.pause();

        overlay.classList.add('active');
        if (si) si.focus();
    }

    function closeTransferModal() {
        var overlay = _overlay();
        if (overlay) overlay.classList.remove('active');
        _deliverableId  = null;
        _selectedCustId = null;
        if (window.helixPolling) window.helixPolling.resume();
    }

    // ── Submit ────────────────────────────────────────────────────────────────
    function _submitTransfer() {
        if (!_deliverableId || !_selectedCustId) return;

        var projectId = window.DETAIL_PROJECT_ID;
        if (!projectId) return;

        var btn = _confirmBtn();
        var err = _errorEl();
        if (btn) btn.disabled = true;
        if (err) err.textContent = '';

        fetch('/projects/' + projectId + '/deliverables/' + _deliverableId + '/transfer', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target_customer_id: _selectedCustId, mode: _mode }),
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.success) {
                closeTransferModal();
                window.location.reload();
            } else {
                if (err) err.textContent = data.error || 'Transfer failed. Please try again.';
                if (btn) btn.disabled = false;
            }
        })
        .catch(function () {
            if (err) err.textContent = 'Network error — please try again.';
            if (btn) btn.disabled = false;
        });
    }

    // ── Escape helper (matches the one in dashboard.js) ──────────────────────
    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    // ── Wire up document-level event delegation ───────────────────────────────
    // Uses delegation (not per-element listeners) so it survives SPA renav
    // without stacking duplicate listeners — the guard is the `_bound` flag.
    if (!document._transferListenerBound) {
        document._transferListenerBound = true;

        document.addEventListener('click', function (e) {
            // Transfer trigger buttons
            var triggerBtn = e.target.closest('[data-action="open-transfer-modal"]');
            if (triggerBtn) {
                e.preventDefault();
                openTransferModal(
                    parseInt(triggerBtn.dataset.deliverableId, 10),
                    triggerBtn.dataset.deliverableName || 'Deliverable',
                    triggerBtn.dataset.sourceCustomer || '—'
                );
                return;
            }

            // Close button
            if (e.target.closest('#transfer-modal-close')) {
                closeTransferModal();
                return;
            }

            // Overlay backdrop click → close
            var overlay = _overlay();
            if (overlay && e.target === overlay) {
                closeTransferModal();
                return;
            }

            // Mode buttons
            if (e.target.closest('#transfer-mode-move'))      { _setMode('move');      return; }
            if (e.target.closest('#transfer-mode-duplicate')) { _setMode('duplicate'); return; }

            // Confirm
            if (e.target.closest('#transfer-confirm-btn')) { _submitTransfer(); return; }

            // Cancel
            if (e.target.closest('#transfer-cancel-btn')) { closeTransferModal(); return; }
        });

        // Live search
        document.addEventListener('input', function (e) {
            if (e.target && e.target.id === 'transfer-customer-search') {
                _renderCustomerOptions(e.target.value);
            }
        });

        // Escape key
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') {
                var overlay = _overlay();
                if (overlay && overlay.classList.contains('active')) {
                    closeTransferModal();
                }
            }
        });
    }

    // Expose for external callers (not currently needed, but follows the pattern
    // window.helixPolling etc. use for modal pause/resume)
    window.helixTransfer = { open: openTransferModal, close: closeTransferModal };

})();
