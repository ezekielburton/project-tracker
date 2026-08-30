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

(() => {
    const table = document.getElementById('project-table');
    // #project-table (the grid itself) is no longer the element that
    // scrolls — it's sized with `width: max-content` in project_list.css
    // so it can be exactly as wide as its columns need, and the actual
    // scrollable viewport is one level up, #project-table-scroll (the
    // .project-table-rounded-clip wrapper). Every scrollLeft/scrollWidth/
    // clientWidth/getBoundingClientRect() read below that's about "how
    // much can be scrolled" or "what's actually visible" needs to be
    // against THIS element, not `table` — `table`'s own box now just
    // matches its content exactly, so scrollWidth === clientWidth on it
    // always, which would make the sticky scrollbar think there's never
    // anything to scroll. `table` itself is still correct for everything
    // about the grid's own custom properties (--track-N, --pos-*) and for
    // querying cells/header — that part is unchanged.
    const scrollContainer = document.getElementById('project-table-scroll') || table;
    const stickyScrollbar = document.getElementById('sticky-scrollbar');
    const stickyScrollbarInner = document.getElementById('sticky-scrollbar-inner');
    const dragIndicator = document.getElementById('resize-drag-indicator');

    function syncStickyScrollbar() {
        if (!stickyScrollbar || !stickyScrollbarInner) return;
        stickyScrollbarInner.style.width = `${scrollContainer.scrollWidth}px`;
        // No point showing a scrollbar if there's nothing to scroll.
        stickyScrollbar.hidden = scrollContainer.scrollWidth <= scrollContainer.clientWidth;
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
        team: 90,
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
    // Widths used to be fr strings ('2fr', '1.6fr', ...) — a shared-space
    // unit that let one column's content (next-deliverable, holding long
    // unbroken names) inflate every OTHER fr column via the grid spec's
    // "find the size of an fr" step, regardless of that other column's own
    // content (see the long comment on .project-table in project_list.css
    // for the full diagnosis — this was Pass 4 of the scroll/resize bug).
    // 'max-content' sidesteps that entirely: paired with the CSS's
    // minmax(min-content, max-content), each column is sized purely from
    // its own content, with no cross-column sharing at all.
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

    let layout = (window.__savedTableLayout && window.__savedTableLayout.length)
        ? window.__savedTableLayout
        : DEFAULT_LAYOUT.map((c) => ({ ...c }));

    // Auto-heal: an account that used this table before Pass 4 may have a
    // saved layout with the old fr-based widths (either an untouched
    // default, like '2fr', or a value a drag ended on, since the drag
    // handler used to compute its floor from an already fr-inflated
    // rendered width). Upgrade any fr-suffixed width to 'max-content'
    // transparently, so the fix applies immediately without asking anyone
    // to reset their saved column widths by hand.
    layout.forEach((col) => {
        if (typeof col.width === 'string' && /fr$/.test(col.width.trim())) {
            col.width = 'max-content';
        }
    });

    // Defensive: if a column gets added in some future build, an older
    // saved layout won't know about it yet — append it at its default
    // width instead of letting it silently disappear for existing users.
    DEFAULT_LAYOUT.forEach((def) => {
        if (!layout.find((c) => c.key === def.key)) {
            layout.push({ ...def });
        }
    });

    // Name is pinned right after Expand and can no longer be dragged (see
    // the reorder section below). The sticky CSS assumes it's always at
    // that spot, so move it there even if an older saved layout has it
    // somewhere else from before this was a fixed column.
    const nameIndex = layout.findIndex((c) => c.key === 'name');
    if (nameIndex > 0) {
        const [nameCol] = layout.splice(nameIndex, 1);
        layout.unshift(nameCol);
    }

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
    // Both wrapped in one named function, rather than left as bare
    // top-level code, so a table-content refresh (task #55 — the SSE live
    // update swaps in fresh header/row markup via #project-table.innerHTML)
    // can re-run just this part afterwards. Unlike the row-click handling
    // in project_list.js (one delegated listener on #project-table itself,
    // which survives an innerHTML swap of its children untouched), these
    // two are bound directly to the header cells themselves — querying
    // `table.querySelectorAll(...)` fresh each call, so calling this again
    // after a refresh naturally targets only whatever's in the DOM right
    // now. The OLD header cells (and their listeners) are simply garbage
    // collected along with the DOM nodes being replaced — no manual
    // teardown needed, and no risk of listeners piling up call over call.
    // Exposed as window.helixRebindProjectTableColumns for project_list.js
    // to call after that swap.
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

            // Never let a column shrink past what its own current content
            // actually needs — measured fresh at the start of each drag, so
            // it reflects whatever's really on screen right now rather than
            // a fixed guess that goes stale as the data changes.
            //
            // cell.scrollWidth alone is NOT safe here: a grid item stretches
            // to fill its track's assigned width by default, so if the
            // column is currently wider than its content needs (as it always
            // was under the old fr-sharing bug — see project_list.css),
            // scrollWidth just reports that already-inflated rendered width
            // back, not the content's real minimum. That's what made the
            // column self-reinforcing: every drag re-measured the bloat it
            // was trying to shrink, so the floor never moved and dragging
            // narrower appeared to do nothing. Forcing width: max-content
            // for the instant of measurement reads the cell's true intrinsic
            // size regardless of how wide its track currently is.
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
                // The edge-of-screen auto-extend check needs the visible
                // scrollable viewport's edges, not the (often much wider,
                // since it's sized to its own content now) grid's own
                // bounding box — so this reads scrollContainer, not table.
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

                // Position the bar from the column's actual rendered edge —
                // never from raw cursor position — so it's physically
                // impossible for it to show anywhere the column isn't.
                if (dragIndicator) {
                    const edgeX = headerCell.getBoundingClientRect().right;
                    dragIndicator.style.left = `${edgeX}px`;

                    // Only span the table itself, clamped to whatever's actually
                    // visible on screen right now — not the whole page top-to-bottom.
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
    // Name is left out of this list on purpose: it's a fixed column, so it
    // can't be dragged, and other columns can't be dropped onto it either.
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
            // Same purpose as resize's 'is-resizing-column' body class above —
            // lets refreshProjectTable() (project_list.js, task #55) detect a
            // drag in progress and skip that one live-update swap rather than
            // yank the header cell out from under an active reorder.
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
    window.helixRebindProjectTableColumns = bindColumnControls;

    window.addEventListener('resize', syncStickyScrollbar);

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
    // Every .expand-deliverable-table on the page — Standard's or C&CM's,
    // already open or fetched five minutes from now — shares ONE set of
    // column widths, written as CSS variables on .project-list-page rather
    // than on each table individually. Since custom properties inherit
    // down the page, a resize updates every currently-open sub-table at
    // once, and any sub-table fetched afterwards just inherits whatever
    // the current widths are — no re-initialization needed when new ones
    // show up later.
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

        // 'max-content' widths, not fr strings — same Pass 4 fix
        // DEFAULT_LAYOUT above got, applied here 22 Aug 2026. A bare fr
        // maximum is a shared-space unit: it let one column's content
        // (a long deliverable name) inflate every OTHER fr column's
        // rendered width regardless of what was actually in it — that's
        // exactly the giant, mostly-empty Status column this was
        // reported as. Paired with the CSS's minmax(min-content,
        // max-content) (project_list.css, .expand-deliverable-table),
        // each column now sizes purely from its own content.
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

        // Auto-heal: an account with a saved layout from before this fix
        // may still have fr-based widths (an untouched default, or a
        // value a drag ended on — the resize handler below already
        // forces max-content for the measurement instant, but the
        // RESULT it saved was still a plain px value layered on top of
        // whatever fr-inflated width was on screen at the time). Same
        // upgrade DEFAULT_LAYOUT's own auto-heal does above — applies
        // immediately, no manual layout reset needed.
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

        // Delegated on document, not bound per-handle — a sub-table can be
        // added to the page at any time (fetched the first time someone
        // expands a row), so one listener here beats trying to re-bind a
        // fresh one every time new content shows up.
        document.addEventListener('mousedown', (e) => {
            const handle = e.target.closest('.expand-deliverable-col-resize-handle');
            if (!handle) return;

            e.preventDefault();
            const headerCell = handle.closest('[data-col-key]');
            const key = headerCell.dataset.colKey;
            const entry = deliverableLayout.find((c) => c.key === key);

            // Same idea as the outer table, but scoped: "name", "deadline",
            // and "status" are key names used by BOTH tables, so a plain
            // [data-col-key] lookup would also catch the outer table's own
            // cells. The .closest() guard keeps this measuring only cells
            // that are actually inside a deliverable sub-table, across
            // every one currently open on the page.
            // Same contamination risk as the outer table's handler above —
            // scrollWidth on a cell that's currently stretched wider than
            // its content reports that inflated width back, not the true
            // minimum. Force max-content for the measurement instant only.
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