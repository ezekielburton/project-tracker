// Drag-and-drop for every <input type="file">: its parent element becomes
// the drop zone, and a drop fills the input and fires 'change'.
function enableDragAndDrop() {
    document.querySelectorAll('input[type="file"]').forEach(function (input){
        var dropZone = input.parentElement;
        // A hidden picker sitting straight in the page shell has no zone of
        // its own; binding there would turn the whole page into a drop target.
        if (!dropZone || dropZone === document.body || dropZone.id === 'main-content') return;

        // Flag the zone, not the input: a zone that outlives its input
        // (SPA swaps, re-rendered forms) must not collect a second set of listeners.
        if (dropZone.dataset.dndZone) return;
        dropZone.dataset.dndZone = 'true';

        ['dragenter', 'dragover'].forEach(function (evt) {
            dropZone.addEventListener(evt, function (e) {
                e.preventDefault();
                e.stopPropagation();
                dropZone.classList.add('drag-over');
            });
        });

        ['dragleave', 'drop'].forEach(function (evt) {
            dropZone.addEventListener(evt, function (e) {
                e.preventDefault();
                e.stopPropagation();
                dropZone.classList.remove('drag-over');
            });
        });

        // Look the input up on each drop, so a replaced one is the one filled.
        dropZone.addEventListener('drop', function (e) {
            var target = dropZone.querySelector(':scope > input[type="file"]');
            if (!target || !e.dataTransfer.files.length) return;
            target.files = e.dataTransfer.files;
            target.dispatchEvent(new Event('change', {bubbles: true}));
        });
    });
}

document.addEventListener('DOMContentLoaded', enableDragAndDrop);
document.addEventListener('helix:navigated', enableDragAndDrop);
