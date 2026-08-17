// app/static/js/project_overlay_edit.js
//
// Design > Details edit mode (M4). Task #34 slice: Save now persists via
// a real POST, with the concurrent-edit check from _build_details_
// context's edit_snapshot_at. Field-level activity logging (task #36)
// and the SSE push to other viewers (task #35) aren't wired yet.

window.ProjectOverlayEdit = (function () {
    function init(headerEl, contentEl, projectId, onSaved) {
        var editBtn = headerEl.querySelector('#project-overlay-edit-btn');
        var saveBtn = headerEl.querySelector('#project-overlay-save-btn');
        var cancelBtn = headerEl.querySelector('#project-overlay-cancel-btn');
        if (!editBtn || !saveBtn || !cancelBtn) return null;

        var restoreFns = [];
        var editSnapshotAt = '';
        var isEditingNow = false;

        function enterEditMode() {
            restoreFns = [];
            isEditingNow = true;

            var snapshotEl = contentEl.querySelector('[data-edit-snapshot]');
            editSnapshotAt = snapshotEl ? snapshotEl.dataset.editSnapshot : '';

            contentEl.querySelectorAll('[data-field]').forEach(function (row) {
                var valueEl = row.querySelector('.overlay-property-value') || row;
                var viewEl = valueEl.querySelector('.overlay-edit-view');
                var inputEl = valueEl.querySelector('.overlay-edit-input');
                if (!viewEl || !inputEl) return;

                viewEl.classList.add('is-hidden');
                inputEl.classList.remove('is-hidden');
                restoreFns.push(function () {
                    viewEl.classList.remove('is-hidden');
                    inputEl.classList.add('is-hidden');
                });
            });

            editBtn.classList.add('is-hidden');
            saveBtn.classList.remove('is-hidden');
            cancelBtn.classList.remove('is-hidden');
        }

        function exitEditMode() {
            restoreFns.forEach(function (restore) { restore(); });
            restoreFns = [];
            isEditingNow = false;



            editBtn.classList.remove('is-hidden');
            saveBtn.classList.add('is-hidden');
            cancelBtn.classList.add('is-hidden');
        }

        editBtn.addEventListener('click', enterEditMode);
        cancelBtn.addEventListener('click', exitEditMode);

        saveBtn.addEventListener('click', function () {
            var fields = {};
            contentEl.querySelectorAll('[data-field]').forEach(function (row) {
                var input = row.querySelector('.overlay-edit-input');
                if (input) fields[row.dataset.field] = input.value;
            });

            saveBtn.disabled = true;
            fetch(`/projects/${projectId}/overlay/details/save`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ fields: fields, edit_snapshot_at: editSnapshotAt }),
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    saveBtn.disabled = false;
                    if (!data.success) {
                        alert(data.error || 'Could not save changes.');
                        return;
                    }
                    // Refresh brings back fresh view-mode content (new
                    // values baked in) and a fresh edit_snapshot_at, and
                    // loadSubTabContent already calls exitEditMode() on
                    // every switch — see project_list.js — so the header
                    // resets for free.
                    if (onSaved) onSaved();
                })
                .catch(function () {
                    saveBtn.disabled = false;
                    alert('Could not reach the server. Try again.');
                });
        });

        return {
            destroy: function () {
                // Listeners live on the header buttons, torn down with the
                // rest of the overlay shell on close.
            },
            exitEditMode: exitEditMode,
            isEditing: function () { return isEditingNow; }
        };
    }

    return { init: init };
})();