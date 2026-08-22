window.AvatarPicker = (function () {
    var activeClose = null;

    function init(pickerEl, onSelect) {
        if (!pickerEl) return null;

        var trigger = pickerEl.querySelector('.avatar-picker-trigger');
        var popover = pickerEl.querySelector('.avatar-picker-popover');
        if (!trigger || !popover) return null;

        function closeOnScroll(e) {
            // Scrolling the popover's own option list also fires a scroll
            // event (it captures up through window same as any other) —
            // only close for scrolling OUTSIDE the popover.
            if (popover.contains(e.target)) return;
            close();
        }

        function positionPopover() {
            // popover is position:fixed (shared.css) so it escapes any
            // ancestor's overflow clipping — computed here from the
            // trigger's actual on-screen position each time it opens.
            var rect = trigger.getBoundingClientRect();
            var margin = 8;
            var popoverWidth = popover.offsetWidth;
            var popoverHeight = popover.offsetHeight;

            var top = rect.bottom + margin;
            var left = rect.left;

            // Flip above the trigger if there's no room below — the
            // trigger button stays visible either way, since the popover
            // sits adjacent to it, never on top of it.
            if (top + popoverHeight > window.innerHeight && rect.top - popoverHeight - margin > 0) {
                top = rect.top - popoverHeight - margin;
            }

            // Clamp horizontally so it never renders off the right edge.
            if (left + popoverWidth > window.innerWidth) {
                left = Math.max(margin, window.innerWidth - popoverWidth - margin);
            }

            popover.style.top = top + 'px';
            popover.style.left = left + 'px';
        }

        function open() {
            if (activeClose && activeClose !== close) {
                activeClose();
            }
            popover.hidden = false;   // must be in the render tree before offsetWidth/Height can be measured
            positionPopover();
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
            if (!pickerEl.contains(e.target)) close();
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
                window.removeEventListener('scroll', closeOnScroll, true);
                if (activeClose === close) activeClose = null;
                document.removeEventListener('click', outsideClick);
                document.removeEventListener('keydown', escHandler);
            }
        };
    }

    return { init: init };
})();