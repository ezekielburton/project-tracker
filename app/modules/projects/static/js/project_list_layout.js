// app/modules/projects/static/js/project_list_layout.js
//
// Column resize + reorder for the Projects table, autosaved per user per
// table+view. Also the shared column widths for deliverable sub-tables.
//
// Mechanism: .project-table's grid-template-columns is built from
// --track-1 to 12 and every project-col-* class reads its position
// from a --pos-<key> variable.
// Resizing changes a position's width; reordering changes which key
// points to which position.

(() => {
    const table = document.getElementById('project-table');
    // The grid is sized to its content (width: max-content), so scrolling
    // happens on #project-table-scroll. Use scrollContainer for scroll and
    // visible-area reads (on `table`, scrollWidth always equals clientWidth);
    // use `table` for the grid variables and cell queries.
    const scrollContainer = document.getElementById('project-table-scroll') || table;
    const stickyScrollbar = document.getElementById('sticky-scrollbar');
    const stickyScrollbarInner = document.getElementById('sticky-scrollbar-inner');
    const dragIndicator = document.getElementById('resize-drag-indicator');

    function syncStickyScrollbar() {
        if (!stickyScrollbar || !stickyScrollbarInner) return;
        stickyScrollbarInner.style.width = `${scrollContainer.scrollWidth}px`;
        stickyScrollbar.hidden = scrollContainer.scrollWidth <= scrollContainer.clientWidth;
    }

    if (!table) return;

    // The SPA router re-runs this file on every visit, and window/document
    // listeners outlive the page, so each run swaps out the previous run's copy.
    function bindGlobal(target, type, key, handler) {
        const handlers = window.__projectListLayoutGlobalHandlers || (window.__projectListLayoutGlobalHandlers = {});
        if (handlers[key]) target.removeEventListener(type, handlers[key]);
        handlers[key] = handler;
        target.addEventListener(type, handler);
    }

    // Re-read by refreshForCurrentTable() on every view switch: each view has
    // its own table_key and saved layout, and a stale key would save one
    // view's layout under another's.
    let tableKey = table.dataset.tableKey;
    let saveUrl = table.dataset.saveLayoutUrl;

    // Minimum width per column in px (unlisted columns default to 80).
    const MIN_WIDTHS = {
        name: 200,
        client: 100,
        cs: 120,
        designers: 140,
        team: 90,
        deadline: 90,
        'next-deadline': 90,
        urgency: 90,
        'next-deliverable': 120,
        status: 90,
        summary: 90,
        job: 90,
    };

    // Layout for a user with no saved layout. Expand is excluded: it is
    // pinned at position 1 and never resized or reordered.
    // Use 'max-content', not fr: fr widths let one column's long content
    // inflate every other fr column (see .project-table in project_list.css).
    const DEFAULT_LAYOUT = [
        { key: 'name', width: 'max-content' },
        { key: 'client', width: 'max-content' },
        { key: 'cs', width: 'max-content' },
        { key: 'designers', width: 'max-content' },
        { key: 'team', width: 'max-content' },
        { key: 'deadline', width: 'max-content' },
        { key: 'next-deadline', width: 'max-content' },
        { key: 'urgency', width: 'max-content' },
        { key: 'next-deliverable', width: 'max-content' },
        { key: 'status', width: 'max-content' },
        { key: 'summary', width: 'max-content' },
        { key: 'job', width: 'max-content' },
    ];

    // Builds the layout from window.__savedTableLayout as it is right now,
    // so refreshForCurrentTable() can call it again after a view switch.
    function deriveLayout() {
        const derived = (window.__savedTableLayout && window.__savedTableLayout.length)
            ? window.__savedTableLayout
            : DEFAULT_LAYOUT.map((c) => ({ ...c }));

        // Saved layouts may still hold fr widths; treat those as 'max-content'.
        derived.forEach((col) => {
            if (typeof col.width === 'string' && /fr$/.test(col.width.trim())) {
                col.width = 'max-content';
            }
        });

        // Append any column missing from a saved layout, so it can't vanish.
        DEFAULT_LAYOUT.forEach((def) => {
            if (!derived.find((c) => c.key === def.key)) {
                derived.push({ ...def });
            }
        });

        // Name is pinned right after Expand (the sticky CSS assumes it), so
        // move it first even if a saved layout has it elsewhere.
        const nameIndex = derived.findIndex((c) => c.key === 'name');
        if (nameIndex > 0) {
            const [nameCol] = derived.splice(nameIndex, 1);
            derived.unshift(nameCol);
        }

        return derived;
    }

    let layout = deriveLayout();

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

    // ---- Resize + Reorder ----
    // Bound directly to the header cells, so bindColumnControls() must
    // re-run after project_list.js swaps #project-table's innerHTML (via
    // window.helixRebindProjectTableColumns). Old cells go with their
    // listeners, so nothing stacks.
    const EDGE_ZONE = 40;    // px from the table's edge that triggers auto-extend
    const EXTEND_SPEED = 8;  // px per frame while pinned at an edge

    function bindColumnControls() {
    table.querySelectorAll('.project-col-resize-handle').forEach((handle) => {
        handle.addEventListener('mousedown', (e) => {
            e.preventDefault();
            e.stopPropagation(); // don't also trigger a reorder-drag
            const headerCell = handle.closest('[data-col-key]');
            const key = headerCell.dataset.colKey;
            const entry = layout.find((c) => c.key === key);

            // Floor = the column's current content width, measured at drag start.
            // A grid item stretches to its track, so plain scrollWidth reports
            // the current column width; force max-content while measuring.
            let contentMinWidth = 0;
            table.querySelectorAll(`.project-col-${key}`).forEach((cell) => {
                const prevWidth = cell.style.width;
                cell.style.width = 'max-content';
                contentMinWidth = Math.max(contentMinWidth, cell.scrollWidth);
                cell.style.width = prevWidth;
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
                // Edge auto-extend uses the visible viewport (scrollContainer), not the grid.
                const rect = scrollContainer.getBoundingClientRect();

                if (lastClientX >= rect.right - EDGE_ZONE) {
                    currentWidth += EXTEND_SPEED;
                    scrollContainer.scrollLeft += EXTEND_SPEED;
                } else if (lastClientX <= rect.left + EDGE_ZONE) {
                    currentWidth -= EXTEND_SPEED;
                    scrollContainer.scrollLeft -= EXTEND_SPEED;
                } else {
                    currentWidth += lastClientX - prevClientX;
                }

                const atMin = currentWidth <= minWidth;
                currentWidth = Math.max(minWidth, currentWidth);
                entry.width = `${currentWidth}px`;
                applyLayout();

                // Place the bar at the column's rendered edge, not the cursor.
                if (dragIndicator) {
                    const edgeX = headerCell.getBoundingClientRect().right;
                    dragIndicator.style.left = `${edgeX}px`;

                    // Span only the visible part of the table.
                    const tableRect = scrollContainer.getBoundingClientRect();
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
    // Name is fixed: it can't be dragged or dropped onto.
    const headerCells = Array.from(
        table.querySelectorAll('.project-table-header > span[data-col-key]')
    ).filter((cell) => cell.dataset.colKey !== 'name');

    headerCells.forEach((cell) => {
        cell.addEventListener('mousedown', (e) => {
            if (e.target.classList.contains('project-col-resize-handle')) return;

            const draggedKey = cell.dataset.colKey;
            const startX = e.clientX;
            let hasMoved = false;

            cell.classList.add('is-dragging');
            // project_list.js reads this body class (and is-resizing-column)
            // to skip live table swaps mid-drag.
            document.body.classList.add('is-reordering-column');

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
                document.body.classList.remove('is-reordering-column');
                if (hasMoved) scheduleSave();
            }

            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        });
    });

    syncStickyScrollbar();
    } // end bindColumnControls()

    bindColumnControls();

    // Re-reads tableKey/saveUrl/layout from the table and
    // window.__savedTableLayout, then re-binds header cells. Called by
    // project_list.js after every table swap (view switch or live refresh).
    function refreshForCurrentTable() {
        tableKey = table.dataset.tableKey;
        saveUrl = table.dataset.saveLayoutUrl;
        layout = deriveLayout();
        applyLayout();
        bindColumnControls();
    }

    window.helixRebindProjectTableColumns = refreshForCurrentTable;

    bindGlobal(window, 'resize', 'resize', () => {
        if (table.isConnected) syncStickyScrollbar();
    });

    if (stickyScrollbar) {
        let syncingScroll = false;

        scrollContainer.addEventListener('scroll', () => {
            if (syncingScroll) return;
            syncingScroll = true;
            stickyScrollbar.scrollLeft = scrollContainer.scrollLeft;
            syncingScroll = false;
        });

        stickyScrollbar.addEventListener('scroll', () => {
            if (syncingScroll) return;
            syncingScroll = true;
            scrollContainer.scrollLeft = stickyScrollbar.scrollLeft;
            syncingScroll = false;
        });
    }
    // ---- Deliverable sub-table resize (shared across every open instance) ----
    // All .expand-deliverable-table instances (Standard and C&CM) share one
    // set of widths, set as CSS variables on .project-list-page, so open and
    // later-fetched sub-tables inherit them.
    const pageEl = document.querySelector('.project-list-page');

    if (pageEl) {
        const DELIVERABLE_MIN_WIDTHS = {
            name: 150,
            deadline: 90,
            'deadline-time': 90,
            '2d': 110,
            '3d': 110,
            technical: 110,
            status: 90,
        };

        // 'max-content', not fr, for the same reason as DEFAULT_LAYOUT above
        // (see .expand-deliverable-table in project_list.css).
        const DELIVERABLE_DEFAULT_LAYOUT = [
            { key: 'name', width: 'max-content' },
            { key: 'deadline', width: 'max-content' },
            { key: 'deadline-time', width: 'max-content' },
            { key: '2d', width: 'max-content' },
            { key: '3d', width: 'max-content' },
            { key: 'technical', width: 'max-content' },
            { key: 'status', width: 'max-content' },
        ];

        let deliverableLayout = (window.__savedDeliverableTableLayout && window.__savedDeliverableTableLayout.length)
            ? window.__savedDeliverableTableLayout
            : DELIVERABLE_DEFAULT_LAYOUT.map((c) => ({ ...c }));

        // Saved layouts may still hold fr widths; treat those as 'max-content'.
        deliverableLayout.forEach((col) => {
            if (typeof col.width === 'string' && /fr$/.test(col.width.trim())) {
                col.width = 'max-content';
            }
        });

        DELIVERABLE_DEFAULT_LAYOUT.forEach((def) => {
            if (!deliverableLayout.find((c) => c.key === def.key)) {
                deliverableLayout.push({ ...def });
            }
        });

        function applyDeliverableLayout() {
            deliverableLayout.forEach((col) => {
                pageEl.style.setProperty(`--dtrack-${col.key}`, col.width);
            });
        }

        applyDeliverableLayout();

        let deliverableSaveTimeout;
        function scheduleDeliverableSave() {
            clearTimeout(deliverableSaveTimeout);
            deliverableSaveTimeout = setTimeout(() => {
                fetch('/projects-new/layout', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ table_key: 'project_list:deliverable_table', layout: deliverableLayout }),
                });
            }, 500);
        }

        // Delegated on document because sub-tables are fetched on first expand.
        bindGlobal(document, 'mousedown', 'deliverableResize', (e) => {
            if (!pageEl.isConnected) return;
            const handle = e.target.closest('.expand-deliverable-col-resize-handle');
            if (!handle) return;

            e.preventDefault();
            const headerCell = handle.closest('[data-col-key]');
            const key = headerCell.dataset.colKey;
            const entry = deliverableLayout.find((c) => c.key === key);

            // Keys like "name" and "status" exist in the outer table too, so
            // only measure cells inside a deliverable sub-table. Force
            // max-content while measuring, as in the outer table.
            let contentMinWidth = 0;
            document.querySelectorAll(`[data-col-key="${key}"]`).forEach((cell) => {
                if (cell.closest('.expand-deliverable-table')) {
                    const prevWidth = cell.style.width;
                    cell.style.width = 'max-content';
                    contentMinWidth = Math.max(contentMinWidth, cell.scrollWidth);
                    cell.style.width = prevWidth;
                }
            });
            const minWidth = Math.max(DELIVERABLE_MIN_WIDTHS[key] || 80, contentMinWidth);

            let currentWidth = headerCell.getBoundingClientRect().width;
            let prevClientX = e.clientX;

            handle.classList.add('is-resizing');
            document.body.classList.add('is-resizing-column');

            function onMouseMove(moveEvent) {
                currentWidth += moveEvent.clientX - prevClientX;
                prevClientX = moveEvent.clientX;
                currentWidth = Math.max(minWidth, currentWidth);
                entry.width = `${currentWidth}px`;
                applyDeliverableLayout();
            }

            function onMouseUp() {
                document.removeEventListener('mousemove', onMouseMove);
                document.removeEventListener('mouseup', onMouseUp);
                handle.classList.remove('is-resizing');
                document.body.classList.remove('is-resizing-column');
                scheduleDeliverableSave();
            }

            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        });
    }
})();