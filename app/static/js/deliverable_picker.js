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

        function closeOnScroll() { close(); }

        // Opt-in via data-popover-align="above-center" on the root element
        // (set by Mark Approved's picker only — see _submissions_draft_card.
        // html) so this doesn't change the default below/left-aligned
        // behavior every other picker on the page still uses.
        var alignAboveCenter = pickerEl.dataset.popoverAlign === 'above-center';

        function positionPopover() {
            var rect = trigger.getBoundingClientRect();
            var margin = 8;
            var popoverWidth = popover.offsetWidth;
            var popoverHeight = popover.offsetHeight;
            var top, left;

            if (alignAboveCenter) {
                top = Math.max(rect.top - popoverHeight - margin, margin);
                left = rect.left + (rect.width / 2) - (popoverWidth / 2);
                left = Math.min(Math.max(left, margin), window.innerWidth - popoverWidth - margin);
            } else {
                // Unchanged default behavior — below the trigger, left-
                // aligned, only flipping/clamping on overflow.
                top = rect.bottom + margin;
                left = rect.left;
                if (top + popoverHeight > window.innerHeight && rect.top - popoverHeight - margin > 0) {
                    top = rect.top - popoverHeight - margin;
                }
                if (left + popoverWidth > window.innerWidth) {
                    left = Math.max(margin, window.innerWidth - popoverWidth - margin);
                }
            }

            popover.style.top = top + 'px';
            popover.style.left = left + 'px';
        }

        function open() {
            if (activeClose && activeClose !== close) activeClose();
            popover.hidden = false;
            positionPopover();
            activeClose = close;
            window.addEventListener('scroll', closeOnScroll, true);
        }

        function close() {
            popover.hidden = true;
            window.removeEventListener('scroll', closeOnScroll, true);
            if (activeClose === close) activeClose = null;
        }

        function toggle(e) {
            e.stopPropagation();
            if (popover.hidden) open(); else close();
        }

        function outsideClick(e) {
            if (!pickerEl.contains(e.target)) close();
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
                window.removeEventListener('scroll', closeOnScroll, true);
                if (activeClose === close) activeClose = null;
                document.removeEventListener('click', outsideClick);
                document.removeEventListener('keydown', escHandler);
            }
        };
    }

    return { init: init };
})();