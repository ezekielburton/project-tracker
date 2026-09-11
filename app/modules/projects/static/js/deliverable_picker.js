window.DeliverablePicker = (function () {
    var activeClose = null;

    function init(pickerEl, onChange) {
        if (!pickerEl) return null;

        var trigger = pickerEl.querySelector('.deliverable-picker-trigger');
        var triggerLabel = pickerEl.querySelector('.deliverable-picker-trigger-label');
        var popover = pickerEl.querySelector('.deliverable-picker-popover');
        if (!trigger || !popover) return null;

        // Seed selection state from whatever the server already rendered
        // as .is-selected, rather than needing a second data-* payload —
        // same "server drives initial state, JS drives interaction" split
        // as the main-deck highlight class elsewhere in Submissions.
        var selected = {};
        popover.querySelectorAll('.deliverable-picker-option.is-selected').forEach(function (opt) {
            selected[opt.dataset.deliverableId] = true;
        });

        function selectedIds() {
            return Object.keys(selected).filter(function (id) { return selected[id]; });
        }

        function updateLabel() {
            var count = selectedIds().length;
            triggerLabel.textContent = count === 0
                ? 'Select deliverables to include'
                : count + ' deliverable' + (count === 1 ? '' : 's') + ' selected';
        }

        window.PopoverPosition.claim(pickerEl, popover);

        function closeOnScroll(e) {
            // The popover's own option list is a scroll container too —
            // only close for scrolling OUTSIDE it.
            if (popover.contains(e.target)) return;
            close();
        }

        function open() {
            if (activeClose && activeClose !== close) activeClose();
            window.PopoverPosition.attach(popover);
            popover.hidden = false;   // must be in the render tree before it can be measured
            // Opt-in via data-popover-align="above-center" on the root element
            // (Mark Approved's and Client Revision's pickers only, set in
            // project_submissions_draft_card.js); every other picker keeps
            // the default below/left-aligned placement.
            window.PopoverPosition.place(popover, trigger, { align: pickerEl.dataset.popoverAlign });
            activeClose = close;
            window.addEventListener('scroll', closeOnScroll, true);
        }

        function close() {
            popover.hidden = true;
            window.PopoverPosition.release(popover);
            window.removeEventListener('scroll', closeOnScroll, true);
            if (activeClose === close) activeClose = null;
        }

        function toggle(e) {
            e.stopPropagation();
            if (popover.hidden) open(); else close();
        }

        function outsideClick(e) {
            // While open the popover lives on <body>, so it is no longer a
            // descendant of pickerEl — both have to count as inside.
            if (pickerEl.contains(e.target) || popover.contains(e.target)) return;
            close();
        }
        function escHandler(e) {
            if (e.key === 'Escape') close();
        }

        trigger.addEventListener('click', toggle);
        document.addEventListener('click', outsideClick);
        document.addEventListener('keydown', escHandler);

        popover.addEventListener('click', function (e) {
            if (e.target.closest('.deliverable-picker-select-all')) {
                popover.querySelectorAll('.deliverable-picker-option').forEach(function (opt) {
                    selected[opt.dataset.deliverableId] = true;
                    opt.classList.add('is-selected');
                });
                updateLabel();
                if (onChange) onChange(selectedIds());
                return;
            }
            if (e.target.closest('.deliverable-picker-clear')) {
                selected = {};
                popover.querySelectorAll('.deliverable-picker-option').forEach(function (opt) {
                    opt.classList.remove('is-selected');
                });
                updateLabel();
                if (onChange) onChange(selectedIds());
                return;
            }
            var option = e.target.closest('.deliverable-picker-option');
            if (option) {
                var id = option.dataset.deliverableId;
                selected[id] = !selected[id];
                option.classList.toggle('is-selected', !!selected[id]);
                updateLabel();
                if (onChange) onChange(selectedIds());
            }
        });

        return {
            getSelectedIds: selectedIds,
            destroy: function () {
                window.PopoverPosition.release(popover);
                window.removeEventListener('scroll', closeOnScroll, true);
                if (activeClose === close) activeClose = null;
                document.removeEventListener('click', outsideClick);
                document.removeEventListener('keydown', escHandler);
            }
        };
    }

    return { init: init };
})();