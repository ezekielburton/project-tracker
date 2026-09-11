window.AvatarPicker = (function () {
    var activeClose = null;

    function init(pickerEl, onSelect) {
        if (!pickerEl) return null;

        var trigger = pickerEl.querySelector('.avatar-picker-trigger');
        var popover = pickerEl.querySelector('.avatar-picker-popover');
        if (!trigger || !popover) return null;

        window.PopoverPosition.claim(pickerEl, popover);

        function closeOnScroll(e) {
            // Scrolling the popover's own option list also fires a scroll
            // event (it captures up through window same as any other) —
            // only close for scrolling OUTSIDE the popover.
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
            // A fixed-position popover doesn't move if an ancestor (e.g.
            // a card's own scrollable list) scrolls underneath it — close
            // on any scroll so it never visually detaches from the button
            // that opened it. Capture phase catches inner-container
            // scrolling too, not just the window itself.
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
            var option = e.target.closest('.avatar-picker-option');
            if (!option) return;
            close();
            onSelect(option.dataset.userId, pickerEl);
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