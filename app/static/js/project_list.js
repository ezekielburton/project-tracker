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
});