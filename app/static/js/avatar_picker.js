// app/static/js/avatar_picker.js
//
// Generic avatar-picker: a button showing the current pick (or a
// placeholder) that opens a small popover list of avatar+name rows.
// Used wherever the overlay needs someone picked with their photo
// visible — CS Lead / Secondary CS / Project Owner so far (Project Name
// card), likely more later. This file only knows how to open/close/pick
// — it has no idea what picking someone should DO (saving a CS lead vs
// a Project Owner are different routes with different rules), so the
// caller supplies an onSelect(userId, pickerEl) callback per instance.
//
// init() is explicit, not an auto-running IIFE — same reasoning as
// ProjectOverlay.init(): this markup is fetched/injected into the
// overlay on demand, not present in the page at load time.

window.AvatarPicker = (function () {
    function init(pickerEl, onSelect) {
        if (!pickerEl) return null;

        var trigger = pickerEl.querySelector('.avatar-picker-trigger');
        var popover = pickerEl.querySelector('.avatar-picker-popover');
        if (!trigger || !popover) return null;

        function open() {
            popover.hidden = false;
        }

        function close() {
            popover.hidden = true;
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
                document.removeEventListener('click', outsideClick);
                document.removeEventListener('keydown', escHandler);
            }
        };
    }

    return { init: init };
})();