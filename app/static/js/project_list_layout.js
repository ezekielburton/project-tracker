//  app/static/js/project_list_layout.js
//
// Column resize + reorder for the Projects table. Silent, personal.
// The layout autosaves per user per table+view.
//
// Mechanism: .project-table's grid-template-columns is built from
// --track-1 to 12 and every project-col-* class reads its position
// from a --pos<key> variable. 
// Resizing changes a position's width, and reording changes which key
// points to which position.

document.addEventListener('DOMContentLoaded', () => {
    const table = document.getElementById('project-table');
    const stickyScrollbar = document.getElementById('sticky-scrollbar');
    const stickyScrollbarInner = document.getElementById('sticky-scrollbar-inner');
    const dragIndicator = document.getElementById('resize-drag-indicator');
    
    function syncStickyScrollbar() {
        if (!stickyScrollbar || !stickyScrollbarInner) return;
        stickyScrollbarInner.style.width = `${table.scrollWidth}px`;
        // No point showing a scrollbar if there's nothing to scroll.
        stickyScrollbar.hidden = table.scrollWidth <= table.clientWidth;
    }

    if (!table) return;

    const tableKey = table.dataset.tableKey;
    const saveUrl = table.dataset.saveLayoutUrl;

    // Absolute floor for each column — matches this build's current sizing.
    // A column added later gets its own entry here at that time.
    const MIN_WIDTHS = {
        name: 200,
        client: 100,
        cs: 120,
        designers: 140,
        teams: 130,
        deadline: 90,
        'next-deadline': 90,
        urgency: 90,
        'next-deliverable': 120,
        status: 90,
        summary: 90,
        job: 90,
    };

    // Used the first time a user visits this table+view, before they've
    // ever dragged anything — mirrors the original hand-written order/widths.
    // Expand is deliberately excluded everywhere below: pinned, always
    // position 1, never resizable or reorderable.
    const DEFAULT_LAYOUT = [
        { key: 'name', width: '2fr' },
        { key: 'client', width: '1.2fr' },
        { key: 'cs', width: '1.4fr' },
        { key: 'designers', width: '1.6fr' },
        { key: 'teams', width: '1.3fr'},
        { key: 'deadline', width: '1fr' },
        { key: 'next-deadline', width: '1fr' },
        { key: 'urgency', width: '1fr' },
        { key: 'next-deliverable', width: '1.4fr' },
        { key: 'status', width: '1fr' },
        { key: 'summary', width: '1fr' },
        { key: 'job', width: '1fr' },
    ];

    let layout = (window.__savedTableLayout && window.__savedTableLayout.length)
        ? window.__savedTableLayout
        : DEFAULT_LAYOUT.map((c) => ({ ...c }));

    // Defensive: if a column gets added in some future build, an older
    // saved layout won't know about it yet — append it at its default
    // width instead of letting it silently disappear for existing users.
    DEFAULT_LAYOUT.forEach((def) => {
        if (!layout.find((c) => c.key === def.key)) {
            layout.push({ ...def });
        }
    });

    function applyLayout() {
        table.style.setProperty('--track-1', '2.5rem');
        table.style.setProperty('--pos-expand', 1);

        layout.forEach((col, i) => {
            const position = i + 2; // position 1 is always expand
            table.style.setProperty(`--track-${position}`, col.width);
            table.style.setProperty(`--pos-${col.key}`, position);
        });

        syncStickyScrollbar();
    }

    applyLayout();

    let saveTimeout;
    function scheduleSave() {
        clearTimeout(saveTimeout);
        saveTimeout = setTimeout(() => {
            fetch(saveUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ table_key: tableKey, layout }),
            });
        }, 500);
    }

    // ---- Resize ----
    const EDGE_ZONE = 40;    // px from the table's edge that triggers auto-extend
    const EXTEND_SPEED = 8;  // px per frame while pinned at an edge

    table.querySelectorAll('.project-col-resize-handle').forEach((handle) => {
        handle.addEventListener('mousedown', (e) => {
            e.preventDefault();
            e.stopPropagation(); // don't also trigger a reorder-drag
            const headerCell = handle.closest('[data-col-key]');
            const key = headerCell.dataset.colKey;
            const entry = layout.find((c) => c.key === key);

            // Never let a column shrink past what its own current content
            // actually needs — measured fresh at the start of each drag, so
            // it reflects whatever's really on screen right now rather than
            // a fixed guess that goes stale as the data changes.
            let contentMinWidth = 0;
            table.querySelectorAll(`.project-col-${key}`).forEach((cell) => {
                contentMinWidth = Math.max(contentMinWidth, cell.scrollWidth);
            });
            const minWidth = Math.max(MIN_WIDTHS[key] || 80, contentMinWidth);

            let currentWidth = headerCell.getBoundingClientRect().width;
            let prevClientX = e.clientX;
            let lastClientX = e.clientX;
            let wasAtMin = false;
            let rafId = null;

            handle.classList.add('is-resizing');
            document.body.classList.add('is-resizing-column');
            if (dragIndicator) dragIndicator.hidden = false;

            function tick() {
                const rect = table.getBoundingClientRect();

                if (lastClientX >= rect.right - EDGE_ZONE) {
                    currentWidth += EXTEND_SPEED;
                    table.scrollLeft += EXTEND_SPEED;
                } else if (lastClientX <= rect.left + EDGE_ZONE) {
                    currentWidth -= EXTEND_SPEED;
                    table.scrollLeft -= EXTEND_SPEED;
                } else {
                    currentWidth += lastClientX - prevClientX;
                }

                const atMin = currentWidth <= minWidth;
                currentWidth = Math.max(minWidth, currentWidth);
                entry.width = `${currentWidth}px`;
                applyLayout();

                // Position the bar from the column's actual rendered edge —
                // never from raw cursor position — so it's physically
                // impossible for it to show anywhere the column isn't.
                if (dragIndicator) {
                    const edgeX = headerCell.getBoundingClientRect().right;
                    dragIndicator.style.left = `${edgeX}px`;

                    // Only span the table itself, clamped to whatever's actually
                    // visible on screen right now — not the whole page top-to-bottom.
                    const tableRect = table.getBoundingClientRect();
                    const top = Math.max(0, tableRect.top);
                    const bottom = Math.min(window.innerHeight, tableRect.bottom);
                    dragIndicator.style.top = `${top}px`;
                    dragIndicator.style.height = `${Math.max(0, bottom - top)}px`;

                    if (atMin && !wasAtMin) {
                        dragIndicator.classList.remove('is-pulsing');
                        void dragIndicator.offsetWidth;
                        dragIndicator.classList.add('is-pulsing');
                    }
                    wasAtMin = atMin;
                }

                prevClientX = lastClientX;
                rafId = requestAnimationFrame(tick);
            }

            rafId = requestAnimationFrame(tick);

            function onMouseMove(moveEvent) {
                lastClientX = moveEvent.clientX;
            }

            function onMouseUp() {
                document.removeEventListener('mousemove', onMouseMove);
                document.removeEventListener('mouseup', onMouseUp);
                cancelAnimationFrame(rafId);
                handle.classList.remove('is-resizing');
                document.body.classList.remove('is-resizing-column');
                if (dragIndicator) dragIndicator.hidden = true;
                scheduleSave();
            }

            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        });
    });

    // ---- Reorder ----
    const headerCells = Array.from(
        table.querySelectorAll('.project-table-header > span[data-col-key]')
    );

    headerCells.forEach((cell) => {
        cell.addEventListener('mousedown', (e) => {
            if (e.target.classList.contains('project-col-resize-handle')) return;

            const draggedKey = cell.dataset.colKey;
            const startX = e.clientX;
            let hasMoved = false;

            cell.classList.add('is-dragging');

            function onMouseMove(moveEvent) {
                if (Math.abs(moveEvent.clientX - startX) > 4) hasMoved = true;
                if (!hasMoved) return;

                const target = headerCells.find((other) => {
                    if (other === cell) return false;
                    const rect = other.getBoundingClientRect();
                    return moveEvent.clientX >= rect.left && moveEvent.clientX <= rect.right;
                });
                if (!target) return;

                const fromIndex = layout.findIndex((c) => c.key === draggedKey);
                const toIndex = layout.findIndex((c) => c.key === target.dataset.colKey);
                if (fromIndex === -1 || toIndex === -1 || fromIndex === toIndex) return;

                const [moved] = layout.splice(fromIndex, 1);
                layout.splice(toIndex, 0, moved);
                applyLayout();
            }

            function onMouseUp() {
                document.removeEventListener('mousemove', onMouseMove);
                document.removeEventListener('mouseup', onMouseUp);
                cell.classList.remove('is-dragging');
                if (hasMoved) scheduleSave();
            }

            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        });
    });

    window.addEventListener('resize', syncStickyScrollbar);

    if (stickyScrollbar) {
        let syncingScroll = false;

        table.addEventListener('scroll', () => {
            if (syncingScroll) return;
            syncingScroll = true;
            stickyScrollbar.scrollLeft = table.scrollLeft;
            syncingScroll = false;
        });

        stickyScrollbar.addEventListener('scroll', () => {
            if (syncingScroll) return;
            syncingScroll = true;
            table.scrollLeft = stickyScrollbar.scrollLeft;
            syncingScroll = false;
        });
    }
    // ---- Deliverable sub-table resize (shared across every open instance) ----
    // Every .expand-deliverable-table on the page — Standard's or C&CM's,
    // already open or fetched five minutes from now — shares ONE set of
    // column widths, written as CSS variables on .project-list-page rather
    // than on each table individually. Since custom properties inherit
    // down the page, a resize updates every currently-open sub-table at
    // once, and any sub-table fetched afterwards just inherits whatever
    // the current widths are — no re-initialization needed when new ones
    // show up later.
    const pageEl = document.querySelector('.project-list-page');

    // ---- Customer sub-table resize (shared across every open instance) ----
    // Same architecture as the deliverable sub-table above: one set of
    // column widths, written as --ctrack-* variables on .project-list-page,
    // shared by every .expand-customer-table on the page, present or future.
    const CUSTOMER_MIN_WIDTHS = {
        name: 150,
        'design-deadline': 110,
        'installation-date': 120,
        'deliverable-count': 90,
        'revision-count': 90,
        status: 90,
    };

    const CUSTOMER_DEFAULT_LAYOUT = [
        { key: 'name', width: '2fr' },
        { key: 'design-deadline', width: '1fr' },
        { key: 'installation-date', width: '1fr' },
        { key: 'deliverable-count', width: '1fr' },
        { key: 'revision-count', width: '1fr' },
        { key: 'status', width: '1fr' },
    ];

    let customerLayout = (window.__savedCustomerTableLayout && window.__savedCustomerTableLayout.length)
        ? window.__savedCustomerTableLayout
        : CUSTOMER_DEFAULT_LAYOUT.map((c) => ({ ...c }));

    CUSTOMER_DEFAULT_LAYOUT.forEach((def) => {
        if (!customerLayout.find((c) => c.key === def.key)) {
            customerLayout.push({ ...def });
        }
    });

    function applyCustomerLayout() {
        customerLayout.forEach((col) => {
            pageEl.style.setProperty(`--ctrack-${col.key}`, col.width);
        });
    }

    applyCustomerLayout();

    let customerSaveTimeout;
    function scheduleCustomerSave() {
        clearTimeout(customerSaveTimeout);
        customerSaveTimeout = setTimeout(() => {
            fetch('/projects-new/layout', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ table_key: 'project_list:customer_table', layout: customerLayout }),
            });
        }, 500);
    }

    document.addEventListener('mousedown', (e) => {
        const handle = e.target.closest('.expand-customer-col-resize-handle');
        if (!handle) return;

        e.preventDefault();
        const headerCell = handle.closest('[data-col-key]');
        const key = headerCell.dataset.colKey;
        const entry = customerLayout.find((c) => c.key === key);

        // Same .closest() scoping as the deliverable table's own handler —
        // "name" and "status" are key names shared with other tables on
        // this page, so a plain [data-col-key] lookup would also catch
        // cells that aren't part of a customer sub-table at all.
        let contentMinWidth = 0;
        document.querySelectorAll(`[data-col-key="${key}"]`).forEach((cell) => {
            if (cell.closest('.expand-customer-table')) {
                contentMinWidth = Math.max(contentMinWidth, cell.scrollWidth);
            }
        });
        const minWidth = Math.max(CUSTOMER_MIN_WIDTHS[key] || 80, contentMinWidth);

        let currentWidth = headerCell.getBoundingClientRect().width;
        let prevClientX = e.clientX;

        handle.classList.add('is-resizing');
        document.body.classList.add('is-resizing-column');

        function onMouseMove(moveEvent) {
            currentWidth += moveEvent.clientX - prevClientX;
            prevClientX = moveEvent.clientX;
            currentWidth = Math.max(minWidth, currentWidth);
            entry.width = `${currentWidth}px`;
            applyCustomerLayout();
        }

        function onMouseUp() {
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
            handle.classList.remove('is-resizing');
            document.body.classList.remove('is-resizing-column');
            scheduleCustomerSave();
        }

        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
    });
});