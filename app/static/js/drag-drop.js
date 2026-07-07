// Generic Drag & Drop for every existting file upload in the app.
// Works by finding every <input type="file"> and allows dropping a file into its container.
function enableDragAndDrop() {
    document.querySelectorAll('input[type="file"]').forEach(function (input){
        if (input.dataset.dndEnabled) return; 
        input.dataset.dndEnabled = 'true';

        // The drop zione is whatever visually cotnain this input and its
        // button - the immediate parent, in every upload block in the app

        var dropZone = input.parentElement;
        if (!dropZone) return;

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

        dropZone.addEventListener('drop', function (e) {
            if (!e.dataTransfer.files.length) return;
            input.files = e.dataTransfer.files;
            input.dispatchEvent(new Event('change', {bubbles: true}));
        });
    });
}

document.addEventListener('DOMContentLoaded', enableDragAndDrop);
document.addEventListener('helix:navigatied', enableDragAndDrop);