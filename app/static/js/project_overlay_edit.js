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
        var isDirty = false;

        // Delegated once (not per-field) so any current or future editable
        // field marks the form dirty just by existing under contentEl — no
        // per-row wiring to keep in sync as fields get added later. Ignored
        // outside edit mode so page-load's initial input values (there
        // aren't any today, but future-proof) can't false-positive this.
        contentEl.addEventListener('input', markDirtyIfEditing);
        contentEl.addEventListener('change', markDirtyIfEditing);

        function markDirtyIfEditing(e) {
            // closest() (not classList.contains) so a control INSIDE an
            // .overlay-edit-input container — e.g. a checkbox in a
            // checkbox-group field — also marks the form dirty, not just a
            // bare input that is itself the .overlay-edit-input.
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
                    // Comma-joined checked values — the shape the server
                    // stores for design_teams_requested (and any future
                    // multi-select field that opts in the same way).
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
        }

        saveBtn.addEventListener('click', function () {
            // Any checkbox-group option that was checked on load and is now
            // unchecked, and declares data-confirm-uncheck, gates Save behind
            // a confirm — e.g. dropping a design team that still has a Design
            // Lead. Generic (data-driven), not teams-specific. defaultChecked
            // reflects the server's freshly-rendered original state; checked
            // reflects the current toggle.
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
                // Listeners live on the header buttons, torn down with the
                // rest of the overlay shell on close.
            },
            exitEditMode: exitEditMode,
            isEditing: function () { return isEditingNow; },
            hasUnsavedChanges: function () { return isEditingNow && isDirty; }
        };
    }

    return { init: init };
})();