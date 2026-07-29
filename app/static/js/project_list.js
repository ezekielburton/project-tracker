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
        const groupHeader = e.target.closest('.project-group-header');
        if (groupHeader) {
            const toggle = groupHeader.querySelector('.project-group-header-toggle');
            const body = groupHeader.nextElementSibling;
            const isCollapsed = toggle.getAttribute('aria-expanded') === 'false';
            toggle.setAttribute('aria-expanded', isCollapsed ? 'true' : 'false');
            body.hidden = !isCollapsed;
            return;
        }

        // ...everything already here stays exactly the same...
        const toggle = e.target.closest('.project-expand-toggle');
        if (!toggle) return;

        // The button lives inside the row's <a> — without these two lines,
        // clicking it would also follow the link to the detail page.
        e.preventDefault();
        e.stopPropagation();

        const row = toggle.closest('.project-row, .expand-customer-row');
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

    function addSortParams(params) {
        const panel = document.getElementById('sort-panel');
        if (!panel) return;

        const selectedGroup = panel.querySelector('.project-sort-option[data-param="group"].is-selected');
        if (selectedGroup && selectedGroup.dataset.value) {
            params.set('group', selectedGroup.dataset.value);
        }

        const selectedSort = panel.querySelector('.project-sort-option[data-param="sort"].is-selected');
        if (selectedSort) {
            params.set('sort', selectedSort.dataset.value);
            params.set('dir', selectedSort.dataset.dir);
        }
    }
    

    const filterToggle = document.getElementById('filter-toggle');
    const filterPanel = document.getElementById('filter-panel');

    if (filterToggle && filterPanel) {
        filterToggle.addEventListener('click', () => {
            filterPanel.hidden = !filterPanel.hidden;
            filterToggle.classList.toggle('is-open', !filterPanel.hidden);
        });

        // Close the panel on any click outside it, so it doesn't stay open
        // hovering over the table while someone's trying to do something else.
        document.addEventListener('click', (e) => {
            if (filterPanel.hidden) return;
            if (filterPanel.contains(e.target) || filterToggle.contains(e.target)) return;
            if (dateRangePicker && dateRangePicker.contains(e.target)) return;
            filterPanel.hidden = true;
            filterToggle.classList.remove('is-open');
        });

        function buildFilterUrl() {
            const params = new URLSearchParams();

            // Preserve whichever view tab is active — filters should never change that.
            const currentView = new URLSearchParams(window.location.search).get('view') || 'my';
            params.set('view', currentView);

            // Multi-value chip groups: one comma-separated param per group,
            // read from whichever chip rows currently carry .is-selected —
            // replaces the old checkbox :checked reads now that these are
            // buttons, not inputs.
            const chipGroups = ['cs_lead', 'designers', 'client', 'brief_type', 'status', 'urgency', 'team', 'design_type'];
            chipGroups.forEach((name) => {
                const selected = Array.from(
                    filterPanel.querySelectorAll(`.filter-chip-row[data-filter-group="${name}"].is-selected`)
                ).map((el) => el.dataset.filterValue);
                if (selected.length) {
                    params.set(name, selected.join(','));
                }
            });

            // Date-range pairs aren't editable yet (the calendar picker isn't
            // built), but whatever's already active is sitting on the date
            // button's own data-from/data-to attributes (rendered from
            // active_filters on page load) — read those so toggling a chip
            // elsewhere never silently wipes an existing date filter.
            const dateButtons = [
                { btn: document.getElementById('initial-deadline-filter-btn'), from: 'initial_deadline_from', to: 'initial_deadline_to' },
                { btn: document.getElementById('next-deadline-filter-btn'), from: 'next_deadline_from', to: 'next_deadline_to' },
            ];
            dateButtons.forEach(({ btn, from, to }) => {
                if (!btn) return;
                if (btn.dataset.from) params.set(from, btn.dataset.from);
                if (btn.dataset.to) params.set(to, btn.dataset.to);
            });

            const searchEl = document.querySelector('[name="search"]');
            if (searchEl && searchEl.value.trim()) {
                params.set('search', searchEl.value.trim());
            }

            addSortParams(params);
            return `${window.location.pathname}?${params.toString()}`;
        }

        function applyFilters() {
            window.location.href = buildFilterUrl();
        }
        

        // Clicking any chip row toggles its own selected state, then applies
        // instantly — one delegated listener on the whole panel handles
        // every group, rather than one listener per chip.
        filterPanel.addEventListener('click', (e) => {
            const chip = e.target.closest('.filter-chip-row');
            if (!chip) return;
            chip.classList.toggle('is-selected');
            applyFilters();
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

        const clearAllBtn = document.getElementById('filter-clear-all');
        if (clearAllBtn) {
            clearAllBtn.addEventListener('click', () => {
                const currentView = new URLSearchParams(window.location.search).get('view') || 'my';
                const params = new URLSearchParams();
                params.set('view', currentView);
                addSortParams(params);
                window.location.href = `${window.location.pathname}?${params.toString()}`;
            });
        }

        const saveNewViewBtn = document.getElementById('save-new-view-btn');
        if (saveNewViewBtn) {
            saveNewViewBtn.addEventListener('click', () => {
                const name = prompt('Name this view:');
                if (!name || !name.trim()) return;

                // Every currently active filter is already sitting in the page's
                // own URL - applyFilters() only ever adds a param when that
                // dimension actually has something selected - so this is exactly
                // the {param: value} shape create_view() wants to store. No need
                // to re-read every chip/date input a second time here.
                const params = new URLSearchParams(window.location.search);
                params.delete('view');
                const filters = Object.fromEntries(params.entries());

                fetch(saveNewViewBtn.dataset.createViewUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: name.trim(),
                        base_view: window.__currentBaseView,
                        filters,
                    }),
                })
                    .then((res) => res.json())
                    .then((data) => {
                        if (data.url) {
                            window.location.href = data.url;
                        } else {
                            alert(data.error || 'Could not save this view.');
                        }
                    });
            });
        }

        const tabsContainer = document.querySelector('.project-list-tabs');
        if (tabsContainer) {
            function closeAllTabPopovers() {
                tabsContainer.querySelectorAll('.project-list-tab-menu.is-open, .project-list-tab-confirm.is-open')
                    .forEach((el) => el.classList.remove('is-open'));
            }

            function startRenameInPlace(wrap, menuItem) {
                const tabLink = wrap.querySelector('.project-list-tab');
                const currentName = menuItem.dataset.viewName;

                const input = document.createElement('input');
                input.type = 'text';
                input.className = 'project-list-tab-rename-input';
                input.value = currentName;
                input.size = Math.max(currentName.length + 1, 6);

                tabLink.style.display = 'none';
                wrap.insertBefore(input, tabLink);
                input.focus();
                input.select();

                function finish(save) {
                    input.removeEventListener('keydown', onKeydown);
                    input.removeEventListener('blur', onBlur);

                    const newName = input.value.trim();
                    input.remove();
                    tabLink.style.display = '';

                    if (!save || !newName || newName === currentName) return;

                    fetch(menuItem.dataset.renameUrl, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name: newName }),
                    })
                        .then((res) => res.json())
                        .then((data) => {
                            if (data.error) { alert(data.error); return; }
                            tabLink.textContent = data.name;
                            menuItem.dataset.viewName = data.name;
                        });
                }

                function onKeydown(e) {
                    if (e.key === 'Enter') { e.preventDefault(); finish(true); }
                    if (e.key === 'Escape') { e.preventDefault(); finish(false); }
                }
                function onBlur() { finish(true); }

                input.addEventListener('keydown', onKeydown);
                input.addEventListener('blur', onBlur);
            }

            document.addEventListener('click', (e) => {
                const menuBtn = e.target.closest('.project-list-tab-menu-btn');
                if (menuBtn) {
                    e.preventDefault();
                    const menu = menuBtn.nextElementSibling;
                    const wasOpen = menu.classList.contains('is-open');
                    closeAllTabPopovers();
                    if (!wasOpen) menu.classList.add('is-open');
                    return;
                }

                const menuItem = e.target.closest('.project-list-tab-menu-item');
                if (menuItem) {
                    const wrap = menuItem.closest('.project-list-tab-wrap');
                    closeAllTabPopovers();

                    if (menuItem.dataset.action === 'rename') startRenameInPlace(wrap, menuItem);
                    if (menuItem.dataset.action === 'delete') {
                        wrap.querySelector('.project-list-tab-confirm').classList.add('is-open');
                    }
                    return;
                }

                const cancelBtn = e.target.closest('[data-action="cancel-delete"]');
                if (cancelBtn) { closeAllTabPopovers(); return; }

                const confirmBtn = e.target.closest('[data-action="confirm-delete"]');
                if (confirmBtn) {
                    const wrap = confirmBtn.closest('.project-list-tab-wrap');
                    fetch(confirmBtn.dataset.deleteUrl, { method: 'POST' })
                        .then((res) => res.json())
                        .then((data) => {
                            if (data.error) { alert(data.error); return; }
                            if (wrap.querySelector('.project-list-tab.active')) {
                                window.location.href = confirmBtn.dataset.redirectUrl;
                                return;
                            }
                            wrap.remove();
                        });
                    return;
                }

                closeAllTabPopovers();
            });
        }

        const sortToggle = document.getElementById('sort-btn');
        const sortPanel = document.getElementById('sort-panel');

        if (sortToggle && sortPanel) {
            sortToggle.addEventListener('click', () => {
                sortPanel.hidden = !sortPanel.hidden;
                sortToggle.classList.toggle('is-open', !sortPanel.hidden);
            });

            document.addEventListener('click', (e) => {
                if (sortPanel.hidden) return;
                if (sortPanel.contains(e.target) || sortToggle.contains(e.target)) return;
                sortPanel.hidden = true;
                sortToggle.classList.remove('is-open');
            });

            sortPanel.addEventListener('click', (e) => {
                const option = e.target.closest('.project-sort-option');
                if (!option) return;

                // Radio behaviour, not toggle: picking one clears the others in
                // its own section (Group by / Order by), unlike filter chips
                // where several can be selected at once.
                option.closest('.project-sort-panel-section')
                    .querySelectorAll('.project-sort-option.is-selected')
                    .forEach((el) => el.classList.remove('is-selected'));
                option.classList.add('is-selected');

                applyFilters();
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

        // ---- Date range picker (Initial Deadline / Next Deadline) ----
        const dateRangePicker = document.getElementById('date-range-picker');
        const dateRangeTitle = document.getElementById('date-range-picker-title');
        const dateRangePrev = document.getElementById('date-range-prev');
        const dateRangeNext = document.getElementById('date-range-next');
        const dateRangeClear = document.getElementById('date-range-clear');
        const dateRangeCancel = document.getElementById('date-range-cancel');
        const dateRangeApply = document.getElementById('date-range-apply');
        const monthLabels = document.querySelectorAll('[data-month-label]');
        const monthDayGrids = document.querySelectorAll('[data-days]');

        if (dateRangePicker && dateRangeTitle && dateRangePrev && dateRangeNext &&
            dateRangeClear && dateRangeCancel && dateRangeApply) {

            // Which trigger button (Initial Deadline / Next Deadline) opened
            // the picker — set the moment one of them is clicked.
            let activeDateBtn = null;

            // The two months currently on screen. "left" month is always
            // one month before "right" — month is 0-indexed, same as
            // native Date.
            let viewYear = null;
            let viewMonth = null;

            // The in-progress selection. Nothing is written back to the
            // triggering button until Apply is clicked — Cancel just
            // throws these away.
            let rangeStart = null;
            let rangeEnd = null;

            function toISO(date) {
                const y = date.getFullYear();
                const m = String(date.getMonth() + 1).padStart(2, '0');
                const d = String(date.getDate()).padStart(2, '0');
                return `${y}-${m}-${d}`;
            }

            // Parses "YYYY-MM-DD" as a LOCAL date. Deliberately not using
            // `new Date(isoString)` here — that form parses as UTC
            // midnight, which can land on the wrong calendar day once
            // converted back to local time depending on the visitor's
            // timezone. Splitting and building the date manually avoids
            // that entirely.
            function fromISO(iso) {
                const [y, m, d] = iso.split('-').map(Number);
                return new Date(y, m - 1, d);
            }

            function sameDay(a, b) {
                return a && b && a.getFullYear() === b.getFullYear() &&
                    a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
            }

            // Builds one month's 42-cell grid (6 weeks), starting the week
            // on Monday to match the Mo/Tu/.../Su header, and filling in
            // the previous/next month's trailing days so the grid is
            // always a full rectangle — same as Google Calendar's picker.
            function buildMonthCells(year, month) {
                const firstOfMonth = new Date(year, month, 1);
                const firstWeekday = (firstOfMonth.getDay() + 6) % 7; // Mon = 0 ... Sun = 6
                const gridStart = new Date(year, month, 1 - firstWeekday);

                const cells = [];
                for (let i = 0; i < 42; i++) {
                    cells.push(new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + i));
                }
                return cells;
            }

            function renderMonth(labelEl, gridEl, year, month) {
                labelEl.textContent = new Date(year, month, 1)
                    .toLocaleString('default', { month: 'long', year: 'numeric' });

                gridEl.innerHTML = '';
                const today = new Date();

                buildMonthCells(year, month).forEach((date) => {
                    const cell = document.createElement('button');
                    cell.type = 'button';
                    cell.className = 'date-range-picker-day';
                    cell.textContent = date.getDate();
                    cell.dataset.iso = toISO(date);

                    if (date.getMonth() !== month) cell.classList.add('is-other-month');
                    if (sameDay(date, today)) cell.classList.add('is-today');
                    if (sameDay(date, rangeStart)) cell.classList.add('is-range-start');
                    if (sameDay(date, rangeEnd)) cell.classList.add('is-range-end');
                    if (rangeStart && rangeEnd && date > rangeStart && date < rangeEnd) {
                        cell.classList.add('is-in-range');
                    }

                    gridEl.appendChild(cell);
                });
            }

            function renderCalendar() {
                renderMonth(monthLabels[0], monthDayGrids[0], viewYear, viewMonth);
                const next = new Date(viewYear, viewMonth + 1, 1);
                renderMonth(monthLabels[1], monthDayGrids[1], next.getFullYear(), next.getMonth());
            }

            function openPicker(btn) {
                activeDateBtn = btn;
                dateRangeTitle.textContent =
                    btn.dataset.paramPrefix === 'initial_deadline' ? 'Initial Deadline' : 'Next Deadline';

                // Pick up whatever's already applied, so re-opening shows
                // the existing selection instead of starting blank.
                rangeStart = btn.dataset.from ? fromISO(btn.dataset.from) : null;
                rangeEnd = btn.dataset.to ? fromISO(btn.dataset.to) : null;

                const anchor = rangeStart || new Date();
                viewYear = anchor.getFullYear();
                viewMonth = anchor.getMonth();

                renderCalendar();
                dateRangePicker.hidden = false;
            }

            function closePicker() {
                dateRangePicker.hidden = true;
                activeDateBtn = null;
            }

            [document.getElementById('initial-deadline-filter-btn'), document.getElementById('next-deadline-filter-btn')]
                .forEach((btn) => {
                    if (!btn) return;
                    btn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        if (activeDateBtn === btn && !dateRangePicker.hidden) {
                            closePicker();
                            return;
                        }
                        openPicker(btn);
                    });
                });

            dateRangePrev.addEventListener('click', () => {
                const prev = new Date(viewYear, viewMonth - 1, 1);
                viewYear = prev.getFullYear();
                viewMonth = prev.getMonth();
                renderCalendar();
            });

            dateRangeNext.addEventListener('click', () => {
                const next = new Date(viewYear, viewMonth + 1, 1);
                viewYear = next.getFullYear();
                viewMonth = next.getMonth();
                renderCalendar();
            });

            // One delegated listener for every day cell across both months —
            // same event-delegation approach as the row-expand and
            // chip-filter handlers above, rather than one listener per cell.
            dateRangePicker.addEventListener('click', (e) => {
                const cell = e.target.closest('.date-range-picker-day');
                if (!cell) return;
                e.stopPropagation();

                const clicked = fromISO(cell.dataset.iso);

                if (!rangeStart || (rangeStart && rangeEnd)) {
                    // Starting a fresh selection.
                    rangeStart = clicked;
                    rangeEnd = null;
                } else if (clicked < rangeStart) {
                    // Second click landed before the first — swap so start
                    // is always the earlier date.
                    rangeEnd = rangeStart;
                    rangeStart = clicked;
                } else {
                    rangeEnd = clicked;
                }
                renderCalendar();
            });

            dateRangeClear.addEventListener('click', () => {
                rangeStart = null;
                rangeEnd = null;
                renderCalendar();
            });

            dateRangeCancel.addEventListener('click', () => {
                closePicker();
            });

            dateRangeApply.addEventListener('click', () => {
                if (!activeDateBtn || !rangeStart) {
                    closePicker();
                    return;
                }
                activeDateBtn.dataset.from = toISO(rangeStart);
                activeDateBtn.dataset.to = toISO(rangeEnd || rangeStart);
                closePicker();
                applyFilters();
            });

            // Close on outside click — same pattern as the filter panel
            // itself — but ignore clicks on the two trigger buttons, which
            // already have their own open/close/toggle logic above.
            document.addEventListener('click', (e) => {
                if (dateRangePicker.hidden) return;
                if (dateRangePicker.contains(e.target)) return;
                if (e.target.closest('#initial-deadline-filter-btn') || e.target.closest('#next-deadline-filter-btn')) return;
                closePicker();
            });
        }
    }
});