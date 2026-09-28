window.ProjectSubmissionsCard = (function () {
    function init(rootEl, projectId, onChanged) {
        if (!rootEl) return null;
        var destroyed = false;

        var contentEl = rootEl.querySelector('#overlay-submissions-content');
        var scopeSelect = rootEl.querySelector('#overlay-submissions-scope-select');
        var toggleSlot = rootEl.querySelector('#overlay-submissions-toggle-slot');
        if (!contentEl) {
            return { destroy: function () { destroyed = true; } };
        }

        var storageKey = 'submissions-selection-' + projectId;
        var currentParams = { scope: contentEl.dataset.scope || 'ckv', customer_id: contentEl.dataset.customerId || '' };

        function refreshDraftCard() {
            // afterRender is optional: runs once the toggle is in the header,
            // so layout-dependent work (the main-deck reorder) sees final positions.
            window.ProjectSubmissionsDraftCard.init(contentEl, projectId, currentParams, function (afterRender) {
                loadContent(currentParams, afterRender);
            });
            // Move the Current/History toggle into the header row. Must run
            // after init(): a DOM move keeps the listeners it just bound.
            if (toggleSlot) {
                var toggle = contentEl.querySelector('.overlay-submissions-view-toggle');
                toggleSlot.innerHTML = '';
                if (toggle) toggleSlot.appendChild(toggle);
            }
        }

        function loadContent(params, afterRender) {
            currentParams = params;
            var query = new URLSearchParams(params).toString();
            fetch(`/projects/${projectId}/overlay/submissions/content?${query}`)
                .then(function (r) { return r.text(); })
                .then(function (html) {
                    if (destroyed) return;
                    contentEl.innerHTML = html;
                    refreshDraftCard();
                    if (afterRender) afterRender();
                });
        }

        // Storage can throw (private windows, blocked site data); the
        // selection still works, it just isn't remembered.
        function saveSelection(selection) {
            try { localStorage.setItem(storageKey, JSON.stringify(selection)); } catch (e) { /* not remembered */ }
        }

        function hasOption(value) {
            return !!scopeSelect && Array.prototype.some.call(scopeSelect.options, function (o) { return o.value === value; });
        }

        function selectValue(value) {
            if (scopeSelect) scopeSelect.value = value;
            if (value === 'ckv') {
                saveSelection({ scope: 'ckv' });
                loadContent({ scope: 'ckv' });
            } else if (value.indexOf('customer:') === 0) {
                var customerId = value.slice('customer:'.length);
                saveSelection({ scope: 'customer', customerId: customerId });
                loadContent({ scope: 'customer', customer_id: customerId });
            }
        }

        if (scopeSelect) {
            scopeSelect.addEventListener('change', function () {
                selectValue(scopeSelect.value);
            });

            // Initial selection: last saved choice for this project if it is
            // still offered (a customer may have been removed), else the
            // server's default (first customer, else CKV).
            var saved = null;
            try { saved = JSON.parse(localStorage.getItem(storageKey) || 'null'); } catch (e) { saved = null; }

            if (saved && saved.scope === 'ckv' && contentEl.dataset.showCkv === 'true') {
                selectValue('ckv');
            } else if (saved && saved.scope === 'customer' && saved.customerId && hasOption('customer:' + saved.customerId)) {
                selectValue('customer:' + saved.customerId);
            } else if (contentEl.dataset.defaultCustomerId) {
                selectValue('customer:' + contentEl.dataset.defaultCustomerId);
            } else if (contentEl.dataset.showCkv === 'true') {
                selectValue('ckv');
            }
        } else {
            // Standard: no dropdown; content is already server-rendered.
            refreshDraftCard();
        }

        return { destroy: function () { destroyed = true; } };
    }
    return { init: init };
})();