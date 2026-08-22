window.ProjectDetailsCard = (function () {
    function init(rootEl, projectId, onChanged) {
        if (!rootEl) return null;
        var pickerHandles = [];
        function handleResponse(res) { return res.json().then(function (data) { if (data.success) { onChanged(); } else { alert(data.error || 'Something went wrong.'); } }); }
        function postForm(url, body) { fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body }).then(handleResponse); }
        function postJson(url, body) { fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(handleResponse); }

        var csLeadPicker = rootEl.querySelector('#cs-lead-picker');
        if (csLeadPicker) pickerHandles.push(window.AvatarPicker.init(csLeadPicker, function (userId) { postJson(`/projects/${projectId}/reassign-cs-lead`, { new_cs_lead_id: userId }); }));

        var secondaryCsAddPicker = rootEl.querySelector('#secondary-cs-add-picker');
        if (secondaryCsAddPicker) pickerHandles.push(window.AvatarPicker.init(secondaryCsAddPicker, function (userId) { postForm(`/projects/${projectId}/secondary-cs`, `user_id=${userId}`); }));

        var ownerPicker = rootEl.querySelector('#project-owner-picker');
        if (ownerPicker) pickerHandles.push(window.AvatarPicker.init(ownerPicker, function (userId) { postForm(`/projects/${projectId}/set-project-owner`, `user_id=${userId}`); }));

        var conceptKvPicker = rootEl.querySelector('#concept-kv-designer-picker');
        if (conceptKvPicker) pickerHandles.push(window.AvatarPicker.init(conceptKvPicker, function (userId) { postForm(`/projects/${projectId}/assign-concept-kv`, `concept_designer_id=${userId}&kv_designer_id=${userId}`); }));

        rootEl.querySelectorAll('.avatar-picker[data-team]').forEach(function (pickerEl) {
            pickerHandles.push(window.AvatarPicker.init(pickerEl, function (userId) {
                postJson(`/projects/${projectId}/assign-lead`, { team: pickerEl.dataset.team, new_designer_id: userId });
            }));
        });

        // Project-level admin status override picker was removed (22 Aug
        // 2026 simplification, per Ezekiel) — #project-status-picker no
        // longer renders (see _details_top_cards.html), the pill is now a
        // pure live roll-up of the project's deliverables. Only the
        // deliverable-level override picker remains (see
        // project_deliverables_card.js), unaffected by this removal.

        rootEl.querySelectorAll('.overlay-secondary-cs-remove').forEach(function (btn) {
            btn.addEventListener('click', function () { postForm(`/projects/${projectId}/secondary-cs/${btn.dataset.userId}/remove`, ''); });
        });

        // ── Reference Files: upload, preview, remove, download all ─────
        var refFileBtn = rootEl.querySelector('#overlay-reference-file-btn');
        var refFileInput = rootEl.querySelector('#overlay-reference-file-input');
        if (refFileBtn && refFileInput) {
            refFileBtn.addEventListener('click', function () { refFileInput.click(); });

            refFileInput.addEventListener('change', function () {
                var file = refFileInput.files[0];
                if (!file) return;
                var status = rootEl.querySelector('#overlay-reference-file-status');
                if (status) status.textContent = 'Uploading...';

                var formData = new FormData();
                formData.append('file', file);

                fetch(`/projects/${projectId}/upload-file`, { method: 'POST', body: formData })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (!data.success) {
                            if (status) status.textContent = '';
                            alert(data.error || 'File could not be saved.');
                            return;
                        }
                        onChanged();
                    })
                    .catch(function () {
                        if (status) status.textContent = '';
                        alert('Upload failed. Please try again.');
                    });
            });
        }

        enableDragAndDrop();

        rootEl.querySelectorAll('.overlay-reference-file-remove').forEach(function (btn) {
            btn.addEventListener('click', function () {
                showConfirm('Remove this file? This cannot be undone.', function () {
                    fetch(`/projects/files/${btn.dataset.fileId}/delete`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' }
                    })
                        .then(function (r) { return r.json(); })
                        .then(function (data) {
                            if (!data.success) { alert(data.error || 'Could not delete file.'); return; }
                            onChanged();
                        });
                });
            });
        });

        rootEl.querySelectorAll('.overlay-reference-file-preview').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var item = btn.closest('.overlay-reference-file-item');
                var nameEl = item ? item.querySelector('.overlay-reference-file-name') : null;
                window.openFilePreview(btn.dataset.previewUrl, btn.dataset.downloadUrl, nameEl ? nameEl.textContent : 'file');
            });
        });

        // ── Start Project: the manual "Briefed" -> "In Design" gate ────
        var startProjectBtn = rootEl.querySelector('#overlay-start-project-btn');
        if (startProjectBtn) {
            startProjectBtn.addEventListener('click', function () {
                startProjectBtn.disabled = true;
                fetch(`/projects/${projectId}/overlay/start`, { method: 'POST' })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (!data.success) {
                            startProjectBtn.disabled = false;
                            alert(data.error || 'Could not start this project.');
                            return;
                        }
                        onChanged();
                    })
                    .catch(function () {
                        startProjectBtn.disabled = false;
                        alert('Something went wrong. Please try again.');
                    });
            });
        }

        // Cancel / Reactivate and Put on Hold / Resume now live in the
        // overlay sidebar, wired once per overlay-open in project_list.js
        // (see wireProjectLifecycleActions) — not here, since this init()
        // reruns on every Details sub-tab load and the sidebar isn't.

        var downloadAllBtn = rootEl.querySelector('#overlay-download-all-files');
        if (downloadAllBtn) {
            downloadAllBtn.addEventListener('click', function () {
                var originalText = downloadAllBtn.textContent;
                downloadAllBtn.disabled = true;
                downloadAllBtn.textContent = 'Zipping...';
                fetch(downloadAllBtn.dataset.downloadAllUrl)
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        downloadAllBtn.disabled = false;
                        downloadAllBtn.textContent = originalText;
                        if (!data.success) { alert(data.error || 'Could not build zip.'); return; }
                        window.location = data.download_url;
                    })
                    .catch(function () {
                        downloadAllBtn.disabled = false;
                        downloadAllBtn.textContent = originalText;
                        alert('Something went wrong.');
                    });
            });
        }

        // Flags (task #42) — Details' Flags card (project/concept/kv scope).
        // Reruns every load same as everything else in this file, since
        // project_flags.js just re-wires whatever .overlay-flag-section
        // elements are in the fresh HTML.
        if (window.ProjectFlags) window.ProjectFlags.init(rootEl, projectId, onChanged);

        return { destroy: function () { pickerHandles.forEach(function (h) { if (h) h.destroy(); }); } };
    }
    return { init: init };
})();