window.ProjectSubmissionsCard = (function () {
    function init(rootEl, projectId, onChanged) {
        if (!rootEl) return null;
        var destroyed = false;

        var contentEl = rootEl.querySelector('#overlay-submissions-content');
        var topRail = rootEl.querySelector('#overlay-submissions-top-rail');
        if (!contentEl) {
            // Standard Brief — static placeholder, nothing to wire.
            return { destroy: function () { destroyed = true; } };
        }

        var storageKey = 'submissions-selection-' + projectId;

        function loadContent(params) {
            var query = new URLSearchParams(params).toString();
            fetch(`/projects/${projectId}/overlay/submissions/content?${query}`)
                .then(function (r) { return r.text(); })
                .then(function (html) {
                    if (destroyed) return;
                    contentEl.innerHTML = html;
                });
        }

        function setActiveTopPill(btn) {
            if (!topRail || !btn) return;
            topRail.querySelectorAll('button').forEach(function (b) {
                b.classList.toggle('active', b === btn);
            });
        }

        function selectCkv() {
            setActiveTopPill(topRail.querySelector('[data-scope="ckv"]'));
            rootEl.querySelectorAll('.overlay-deliverables-customer-rail[data-region-rail]').forEach(function (rail) {
                rail.classList.add('is-hidden');
            });
            localStorage.setItem(storageKey, JSON.stringify({ scope: 'ckv' }));
            loadContent({ scope: 'ckv' });
        }

        function selectRegion(regionKey, opts) {
            setActiveTopPill(topRail.querySelector('[data-region="' + regionKey + '"]'));
            rootEl.querySelectorAll('.overlay-deliverables-customer-rail[data-region-rail]').forEach(function (rail) {
                rail.classList.toggle('is-hidden', rail.dataset.regionRail !== regionKey);
            });
            var rail = rootEl.querySelector('.overlay-deliverables-customer-rail[data-region-rail="' + regionKey + '"]');
            var firstPill = rail && rail.querySelector('.overlay-deliverables-customer-pill');
            var customerId = (opts && opts.customerId) || (firstPill && firstPill.dataset.customerId);
            if (customerId) selectCustomer(customerId, { fromRegion: regionKey, skipTopPill: true });
        }

        function selectCustomer(customerId, opts) {
            opts = opts || {};
            if (!opts.skipTopPill) {
                setActiveTopPill(topRail.querySelector('[data-customer-id="' + customerId + '"]'));
            }
            var rail = opts.fromRegion
                ? rootEl.querySelector('.overlay-deliverables-customer-rail[data-region-rail="' + opts.fromRegion + '"]')
                : null;
            if (rail) {
                rail.querySelectorAll('.overlay-deliverables-customer-pill').forEach(function (b) {
                    b.classList.toggle('active', b.dataset.customerId === String(customerId));
                });
            }
            localStorage.setItem(storageKey, JSON.stringify(opts.fromRegion
                ? { scope: 'region', region: opts.fromRegion, customerId: customerId }
                : { scope: 'customer', customerId: customerId }));
            loadContent({ scope: 'customer', customer_id: customerId });
        }

        if (topRail) {
            topRail.querySelectorAll('button').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    if (btn.dataset.scope === 'ckv') selectCkv();
                    else if (btn.dataset.scope === 'region') selectRegion(btn.dataset.region);
                    else if (btn.dataset.scope === 'customer') selectCustomer(btn.dataset.customerId);
                });
            });
        }

        rootEl.querySelectorAll('.overlay-deliverables-customer-rail[data-region-rail] .overlay-deliverables-customer-pill').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var rail = btn.closest('.overlay-deliverables-customer-rail');
                selectCustomer(btn.dataset.customerId, { fromRegion: rail && rail.dataset.regionRail });
            });
        });

        // Resolve initial selection: last saved choice for this project, else the
        // server's suggested default. Only ONE of these fires.
        var saved = null;
        try { saved = JSON.parse(localStorage.getItem(storageKey) || 'null'); } catch (e) { saved = null; }

        if (saved && saved.scope === 'ckv' && contentEl.dataset.showCkv === 'true') {
            selectCkv();
        } else if (saved && saved.scope === 'region' && contentEl.dataset.hasGulfRegions === 'true') {
            selectRegion(saved.region, { customerId: saved.customerId });
        } else if (saved && saved.scope === 'customer') {
            selectCustomer(saved.customerId);
        } else if (contentEl.dataset.hasGulfRegions === 'true' && contentEl.dataset.defaultRegion) {
            selectRegion(contentEl.dataset.defaultRegion);
        } else if (contentEl.dataset.defaultCustomerId) {
            selectCustomer(contentEl.dataset.defaultCustomerId);
        } else if (contentEl.dataset.showCkv === 'true') {
            selectCkv();
        }

        return { destroy: function () { destroyed = true; } };
    }
    return { init: init };
})();