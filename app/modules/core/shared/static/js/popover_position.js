// Shared placement for fixed-position popovers (avatar, status and
// deliverable pickers).
//
// 1. Keeps the popover inside the viewport: flips above the trigger when
//    there's no room below, then clamps on both axes.
//
// 2. Moves the popover to <body> while open. An ancestor with
//    backdrop-filter, filter or transform becomes the containing block for
//    position: fixed, which would offset the viewport coordinates set here.
//
// Popovers are moved, not cloned, so their listeners survive. Style a
// popover via [data-popover-owner="<picker id>"], not a descendant
// selector: while open it is not inside its picker.
window.PopoverPosition = (function () {
    var MARGIN = 8;
    var homes = new WeakMap();

    function claim(pickerEl, popover) {
        // Stamped once at init and never removed, so the attribute selector
        // matches whether the popover is parked on body or back at home.
        if (pickerEl.id) popover.dataset.popoverOwner = pickerEl.id;
    }

    function attach(popover) {
        if (homes.has(popover)) return;
        homes.set(popover, { parent: popover.parentNode, next: popover.nextSibling });
        document.body.appendChild(popover);
    }

    function release(popover) {
        var home = homes.get(popover);
        if (!home) return;
        homes.delete(popover);
        if (home.parent && home.parent.isConnected) {
            home.parent.insertBefore(popover, home.next);
        } else if (popover.parentNode) {
            // The card re-rendered while this was open — putting it back would
            // orphan it in a detached tree, so drop it instead.
            popover.parentNode.removeChild(popover);
        }
    }

    function place(popover, trigger, options) {
        var opts = options || {};
        var rect = trigger.getBoundingClientRect();
        var width = popover.offsetWidth;
        var height = popover.offsetHeight;
        var top, left;

        if (opts.align === 'above-center') {
            top = rect.top - height - MARGIN;
            left = rect.left + (rect.width / 2) - (width / 2);
        } else {
            top = rect.bottom + MARGIN;
            left = rect.left;
            if (top + height > window.innerHeight && rect.top - height - MARGIN > 0) {
                top = rect.top - height - MARGIN;
            }
        }

        left = Math.min(Math.max(left, MARGIN),
                        Math.max(MARGIN, window.innerWidth - width - MARGIN));
        top = Math.min(Math.max(top, MARGIN),
                       Math.max(MARGIN, window.innerHeight - height - MARGIN));

        popover.style.top = top + 'px';
        popover.style.left = left + 'px';
    }

    return { claim: claim, attach: attach, release: release, place: place };
})();
