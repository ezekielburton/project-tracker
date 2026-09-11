// Shared placement for the app's fixed-position popovers (avatar, status and
// deliverable pickers). Two jobs, and each picker previously got both wrong in
// its own copy of this logic.
//
// 1. Keep the popover inside the viewport, clamping on both axes. A flip above
//    the trigger is not enough on its own: when neither side has room the
//    popover still has to be pulled back on screen.
//
// 2. Make `position: fixed` actually mean the viewport. An ancestor carrying
//    backdrop-filter, filter or transform becomes the containing block for its
//    fixed-position descendants, so viewport coordinates computed here would be
//    applied relative to THAT element instead. The project overlay's backdrop
//    has backdrop-filter, so every picker inside it was drawn shifted right by
//    the sidebar's width — invisible with the sidebar collapsed, off-screen
//    with it pinned. Parking the popover on <body> while it is open leaves no
//    such ancestor, so the numbers mean what they say.
//
// Popovers are moved, not cloned, so listeners bound to them survive. Anything
// styling a popover through its picker's id must target
// [data-popover-owner="<that id>"] rather than a descendant selector, since
// while open the popover is no longer inside it.
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
