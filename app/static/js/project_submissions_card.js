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
            window.ProjectSubmissionsDraftCard.init(contentEl, projectId, currentParams, function () {
                loadContent(currentParams);
            });
            // Relocate the scope-level Current/History toggle (if this fetch
            // rendered one) out of contentEl and into the header row next to
            // the dropdown. This is a DOM move, not a rebuild, so the click
            // listeners ProjectSubmissionsDraftCard.init() just bound stay attached.
            if (toggleSlot) {
                var toggle = contentEl.querySelector('.overlay-submissions-view-toggle');
                toggleSlot.innerHTML = '';
                if (toggle) toggleSlot.appendChild(toggle);
            }
        }

        function loadContent(params) {
            currentParams = params;
            var query = new URLSearchParams(params).toString();
            fetch(`/projects/${projectId}/overlay/submissions/content?${query}`)
                .then(function (r) { return r.text(); })
                .then(function (html) {
                    if (destroyed) return;
                    contentEl.innerHTML = html;
                    refreshDraftCard();
                });
        }

        function selectValue(value) {
            if (scopeSelect) scopeSelect.value = value;
            if (value === 'ckv') {
                localStorage.setItem(storageKey, JSON.stringify({ scope: 'ckv' }));
                loadContent({ scope: 'ckv' });
            } else if (value.indexOf('customer:') === 0) {
                var customerId = value.slice('customer:'.length);
                localStorage.setItem(storageKey, JSON.stringify({ scope: 'customer', customerId: customerId }));
                loadContent({ scope: 'customer', customer_id: customerId });
            }
        }

        if (scopeSelect) {
            scopeSelect.addEventListener('change', function () {
                selectValue(scopeSelect.value);
            });

            // Resolve initial selection: last saved choice for this project,
            // else the server's suggested default (first customer, else CKV).
            var saved = null;
            try { saved = JSON.parse(localStorage.getItem(storageKey) || 'null'); } catch (e) { saved = null; }

            if (saved && saved.scope === 'ckv' && contentEl.dataset.showCkv === 'true') {
                selectValue('ckv');
            } else if (saved && saved.scope === 'customer' && saved.customerId) {
                selectValue('customer:' + saved.customerId);
            } else if (contentEl.dataset.defaultCustomerId) {
                selectValue('customer:' + contentEl.dataset.defaultCustomerId);
            } else if (contentEl.dataset.showCkv === 'true') {
                selectValue('ckv');
            }
        } else {
            // Standard Brief: no dropdown, content already server-rendered — just wire it.
            refreshDraftCard();
        }

        return { destroy: function () { destroyed = true; } };
    }
    return { init: init };
})();