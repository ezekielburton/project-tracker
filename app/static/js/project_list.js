// app/static/js/project_list.js
//
// Projects page — row expansion. One click listener on the table handles
// every row (event delegation), rather than attaching a listener per row —
// consistent with the client-side performance principles locked at the
// start of this build.

document.addEventListener('DOMContentLoaded', () => {
    const table = document.querySelector('.project-table');
  
    if (!table) return;

    table.addEventListener('click', (e) => {
        const toggle = e.target.closest('.project-expand-toggle');
        if (!toggle) return;

        // The button lives inside the row's <a> — without these two lines,
        // clicking it would also follow the link to the detail page.
        e.preventDefault();
        e.stopPropagation();

        const row = toggle.closest('.project-row');
        const container = row.nextElementSibling;
        if (!container || !container.classList.contains('project-expand-container')) return;

        const isOpen = toggle.getAttribute('aria-expanded') === 'true';
        if (isOpen) {
            container.hidden = true;
            toggle.setAttribute('aria-expanded', 'false');
            return;
        }

        toggle.setAttribute('aria-expanded', 'true');
        container.hidden = false;

        // Fetch only the first time this row is opened — cached in the DOM
        // afterwards so re-opening it never re-hits the server. This is the
        // render-on-demand principle: fetch when it's actually needed, not
        // pre-loaded for every row up front.
        if (container.dataset.loaded === 'true') return;

        fetch(toggle.dataset.expandUrl)
            .then((res) => res.text())
            .then((html) => {
                container.innerHTML = html;
                container.dataset.loaded = 'true';
            });
    });

    const filterToggle = document.getElementById('filter-toggle');
    const filterPanel = document.getElementById('filter-panel');

    if (filterToggle && filterPanel) {
        filterToggle.addEventListener('click', () => {
            filterPanel.hidden = !filterPanel.hidden;
        });

        // Close the panel on any click outside it, so it doesn't stay open
        // hovering over the table while someone's trying to do something else.
        document.addEventListener('click', (e) => {
            if (filterPanel.hidden) return;
            if (filterPanel.contains(e.target) || filterToggle.contains(e.target)) return;
            filterPanel.hidden = true;
        });
        
        function buildFilterUrl() {
            const params = new URLSearchParams();

            // Preserve whichever view tab is active — filters should never change that.
            const currentView = new URLSearchParams(window.location.search).get('view') || 'my';
            params.set('view', currentView);

            // Multi-value checkbox groups: one comma-separated param per group name.
            const checkboxGroups = ['cs_lead', 'designers', 'client', 'brief_type', 'status', 'urgency'];
            checkboxGroups.forEach((name) => {
                const checked = Array.from(
                    filterPanel.querySelectorAll(`input[type="checkbox"][name="${name}"]:checked`)
                ).map((el) => el.value);
                if (checked.length) {
                    params.set(name, checked.join(','));
                }
            });

            // Single-value inputs: search text and the four date fields.
            const singleInputs = ['search', 'initial_deadline_from', 'initial_deadline_to', 'next_deadline_from', 'next_deadline_to'];
            singleInputs.forEach((name) => {
                const el = document.querySelector(`[name="${name}"]`);
                if (el && el.value.trim()) {
                    params.set(name, el.value.trim());
                }
            });

            return `${window.location.pathname}?${params.toString()}`;
        }

        function applyFilters() {
            window.location.href = buildFilterUrl();
        }

        // Checkboxes and date inputs apply instantly — a click/pick is already
        // one discrete action, no need to wait for anything further.
        filterPanel.querySelectorAll('input[type="checkbox"], input[type="date"]').forEach((el) => {
            el.addEventListener('change', applyFilters);
        });

        // Search debounces instead — reloading the page on every keystroke
        // would be a rough experience, so wait for a short pause after typing
        // stops before actually navigating.
        const searchInput = document.querySelector('[name="search"]'); 
        if (searchInput) {
            let searchTimeout;
            searchInput.addEventListener('input', () => {
                clearTimeout(searchTimeout);
                searchTimeout = setTimeout(applyFilters, 400);
            });
        }

        const saveViewBtn = document.getElementById('save-view-btn');
        if (saveViewBtn) {
            saveViewBtn.addEventListener('click', () => {
                // TODO: once the views system exists, this should create a new
                // saved view from the current URL's filters. Placeholder for now.
                console.log('Save this view — not wired up yet.');
            });
        } 

        const searchToggle = document.getElementById('search-toggle');
        const toolbarSearch = document.getElementById('toolbar-search');
        if (searchToggle && toolbarSearch) {
            searchToggle.addEventListener('click', () => {
                toolbarSearch.hidden = !toolbarSearch.hidden;
                if (!toolbarSearch.hidden) {
                    toolbarSearch.focus();
                }
            });
        }

        const newProjectBtn = document.getElementById('new-project-btn');
        if (newProjectBtn) {
            newProjectBtn.addEventListener('click', () => {
                // TODO: wire up once the New Project flow (per your planning doc) is built.
                console.log('New Project — not wired up yet.');
            });
        }

        const sortBtn = document.getElementById('sort-btn');
        if (sortBtn) {
            sortBtn.addEventListener('click', () => {
                // TODO: wire up real interactive sorting later.
                console.log('Sort — not wired up yet.');
            });
        }
    }
});