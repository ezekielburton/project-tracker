window.AvatarPicker = (function () {
    var activeClose = null;

    function init(pickerEl, onSelect) {
        if (!pickerEl) return null;

        var trigger = pickerEl.querySelector('.avatar-picker-trigger');
        var popover = pickerEl.querySelector('.avatar-picker-popover');
        if (!trigger || !popover) return null;

        window.PopoverPosition.claim(pickerEl, popover);

        function closeOnScroll(e) {
            // The popover's own list scrolling is caught too; ignore it.
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
            // A fixed popover would drift from its trigger on scroll, so
            // any scroll closes it. Capture phase catches inner containers.
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
            // While open the popover lives on <body>, outside pickerEl.
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
                // Hide first: release() puts an open popover back at home,
                // where it would show inline if the picker is still on the page.
                popover.hidden = true;
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