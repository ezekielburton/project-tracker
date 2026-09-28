// app/modules/projects/static/js/project_overlay_edit.js
//
// Details edit mode: the header's Edit/Save/Cancel. Save POSTs every
// [data-field] with edit_snapshot_at so the server can reject a concurrent edit.

window.ProjectOverlayEdit = (function () {
    function init(headerEl, contentEl, projectId, onSaved) {
        var editBtn = headerEl.querySelector('#project-overlay-edit-btn');
        var saveBtn = headerEl.querySelector('#project-overlay-save-btn');
        var cancelBtn = headerEl.querySelector('#project-overlay-cancel-btn');
        if (!editBtn || !saveBtn || !cancelBtn) return null;

        var restoreFns = [];
        var editSnapshotAt = '';
        var isEditingNow = false;
        var isDirty = false;

        // Delegated on contentEl, which persists across page switches, so any
        // edit field marks the form dirty. Ignored outside edit mode.
        contentEl.addEventListener('input', markDirtyIfEditing);
        contentEl.addEventListener('change', markDirtyIfEditing);

        function markDirtyIfEditing(e) {
            // closest() so controls inside an .overlay-edit-input (checkbox groups) count too.
            if (isEditingNow && e.target.closest && e.target.closest('.overlay-edit-input')) isDirty = true;
        }

        function enterEditMode() {
            restoreFns = [];
            isEditingNow = true;
            isDirty = false;

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
            isDirty = false;

            editBtn.classList.remove('is-hidden');
            saveBtn.classList.add('is-hidden');
            cancelBtn.classList.add('is-hidden');
        }

        editBtn.addEventListener('click', enterEditMode);
        cancelBtn.addEventListener('click', exitEditMode);

        function collectFields() {
            var fields = {};
            contentEl.querySelectorAll('[data-field]').forEach(function (row) {
                var input = row.querySelector('.overlay-edit-input');
                if (!input) return;
                if (input.dataset.editType === 'checkbox-group') {
                    // Comma-joined checked values, as the server stores them.
                    var picked = [];
                    input.querySelectorAll('input[type="checkbox"]').forEach(function (cb) {
                        if (cb.checked) picked.push(cb.value);
                    });
                    fields[row.dataset.field] = picked.join(',');
                } else {
                    fields[row.dataset.field] = input.value;
                }
            });
            return fields;
        }

        function postSave() {
            saveBtn.disabled = true;
            fetch(`/projects/${projectId}/overlay/details/save`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ fields: collectFields(), edit_snapshot_at: editSnapshotAt }),
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    saveBtn.disabled = false;
                    if (!data.success) {
                        alert(data.error || 'Could not save changes.');
                        return;
                    }
                    // onSaved reloads Details (fresh values and snapshot);
                    // project_list.js's loadSubTabContent resets the header.
                    if (onSaved) onSaved();
                })
                .catch(function () {
                    saveBtn.disabled = false;
                    alert('Could not reach the server. Try again.');
                });
        }

        saveBtn.addEventListener('click', function () {
            // Unticking a box that has data-confirm-uncheck (e.g. a team with
            // a Design Lead) asks for confirmation. defaultChecked is the
            // server-rendered state.
            var warnings = [];
            contentEl.querySelectorAll('.overlay-edit-input input[type="checkbox"][data-confirm-uncheck]').forEach(function (cb) {
                if (cb.defaultChecked && !cb.checked) warnings.push(cb.dataset.confirmUncheck);
            });

            if (warnings.length && window.showConfirm) {
                window.showConfirm(warnings.join(' ') + ' Continue?', postSave, 'Confirm changes');
            } else {
                postSave();
            }
        });

        return {
            destroy: function () {
                // Listeners are on overlay nodes and go with them on close.
            },
            exitEditMode: exitEditMode,
            isEditing: function () { return isEditingNow; },
            hasUnsavedChanges: function () { return isEditingNow && isDirty; }
        };
    }

    return { init: init };
})();