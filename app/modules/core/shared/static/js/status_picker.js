// app/static/js/status_picker.js
// Admin-only status override control (22 Aug 2026, per Ezekiel) — click a
// status pill in the overlay, see every possible status, pick one to
// override it. Same generic popover mechanics as avatar_picker.js (open/
// close/position/outside-click/Esc/close-on-scroll), just its own class
// hooks (.status-picker*) and reading data-status-value instead of
// data-user-id — kept as its own small file rather than generalizing
// avatar_picker.js, since that component is already wired up and shipping
// for the Deliverables assign feature and touching it risks regressing
// that unrelated, already-working flow.
//
// Deliberately as dumb as AvatarPicker: this file only knows how to open/
// close a popover and report which option was clicked. It doesn't know
// what a "project" or "deliverable" is, or how to POST — see
// project_details_card.js / project_deliverables_card.js for the actual
// override request + DOM refresh built around this.
window.StatusPicker = (function () {
    var activeClose = null;

    function init(pickerEl, onSelect) {
        if (!pickerEl) return null;

        var trigger = pickerEl.querySelector('.status-picker-trigger');
        var popover = pickerEl.querySelector('.status-picker-popover');
        if (!trigger || !popover) return null;

        window.PopoverPosition.claim(pickerEl, popover);

        function closeOnScroll(e) {
            if (popover.contains(e.target)) return;
            close();
        }

        function open() {
            if (activeClose && activeClose !== close) {
                activeClose();
            }
            window.PopoverPosition.attach(popover);
            popover.hidden = false;   // must be in the render tree before it can be measured
            window.PopoverPosition.place(popover, trigger);
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
            if (popover.hidden) {
                open();
            } else {
                close();
            }
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
            var option = e.target.closest('.status-picker-option');
            if (!option) return;
            close();
            onSelect(option.dataset.statusValue, pickerEl);
        });

        return {
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
