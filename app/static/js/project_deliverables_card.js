window.ProjectDeliverablesCard = (function () {
    function init(rootEl, projectId, onChanged) {
        if (!rootEl) return null;
        var destroyed = false;

        function bindReadOnly() {
            wireDeliverablesRail(rootEl);
            wireFocusToggle(rootEl);

            var editBtn = rootEl.querySelector('#overlay-edit-deliverables-btn');
            if (editBtn) {
                editBtn.addEventListener('click', function () {
                    fetch(`/projects/${projectId}/overlay/deliverables/edit`)
                        .then(function (r) { return r.text(); })
                        .then(function (html) {
                            if (destroyed) return;
                            rootEl.innerHTML = html;
                            bindEdit();
                        });
                });
            }
        }

        function backToReadOnly() {
            fetch(`/projects/${projectId}/overlay/deliverables`)
                .then(function (r) { return r.text(); })
                .then(function (html) {
                    if (destroyed) return;
                    rootEl.innerHTML = html;
                    bindReadOnly();
                    if (onChanged) onChanged();
                });
        }

        function wireDeliverablesRail(rootEl) {
            var regionRail = rootEl.querySelector('#overlay-deliverables-region-rail');
            if (regionRail) {
                regionRail.querySelectorAll('.tab-strip-item').forEach(function (btn) {
                    btn.addEventListener('click', function () {
                        if (btn.classList.contains('active')) return;
                        regionRail.querySelectorAll('.tab-strip-item').forEach(function (b) {
                            b.classList.toggle('active', b === btn);
                        });
                        var regionKey = btn.dataset.region;
                        rootEl.querySelectorAll('.overlay-deliverables-customer-rail').forEach(function (rail) {
                            rail.classList.toggle('is-hidden', rail.dataset.regionRail !== regionKey);
                        });
                        var activeRail = rootEl.querySelector(
                            '.overlay-deliverables-customer-rail[data-region-rail="' + regionKey + '"]'
                        );
                        var firstPill = activeRail && activeRail.querySelector('.overlay-deliverables-customer-pill');
                        if (firstPill) activateCustomerPill(rootEl, firstPill);
                    });
                });
            }

            rootEl.querySelectorAll('.overlay-deliverables-customer-pill').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    activateCustomerPill(rootEl, btn);
                });
            });
        }

        function activateCustomerPill(rootEl, btn) {
            if (btn.classList.contains('active')) return;
            var rail = btn.closest('.overlay-deliverables-customer-rail');
            if (rail) {
                rail.querySelectorAll('.overlay-deliverables-customer-pill').forEach(function (b) {
                    b.classList.toggle('active', b === btn);
                });
            }
            var customerId = btn.dataset.customerId;
            rootEl.querySelectorAll('.overlay-deliverables-panel').forEach(function (panel) {
                panel.classList.toggle('is-hidden', panel.dataset.customerPanel !== customerId);
            });
        }

        function wireFocusToggle(rootEl) {
            var toggle = rootEl.querySelector('#overlay-deliverables-focus-toggle');
            var body = rootEl.querySelector('#overlay-deliverables-body');
            if (!toggle || !body) return;
            toggle.querySelectorAll('.overlay-focus-toggle-btn').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    if (btn.classList.contains('active')) return;
                    toggle.querySelectorAll('.overlay-focus-toggle-btn').forEach(function (b) {
                        b.classList.toggle('active', b === btn);
                    });
                    body.classList.toggle('is-focused', btn.dataset.scope === 'focused');
                });
            });
        }

        function collectRows(listEl) {
            return Array.prototype.map.call(listEl.querySelectorAll('.overlay-deliverables-edit-row'), function (row) {
                var teams = Array.prototype.filter.call(
                    row.querySelectorAll('.overlay-deliverables-edit-toggle'),
                    function (btn) { return btn.classList.contains('is-active'); }
                ).map(function (btn) { return btn.dataset.team; });
                return {
                    id: row.dataset.deliverableId || null,
                    name: row.querySelector('.overlay-deliverables-edit-name').value.trim(),
                    design_deadline: row.querySelector('.overlay-deliverables-edit-date').value || null,
                    design_deadline_time: row.querySelector('.overlay-deliverables-edit-time').value || null,
                    teams: teams,
                    deleted: row.dataset.deleted === 'true',
                };
            });
        }

        function wireRow(row) {
            row.querySelectorAll('.overlay-deliverables-edit-toggle').forEach(function (btn) {
                btn.addEventListener('click', function () { btn.classList.toggle('is-active'); });
            });
            var deleteBtn = row.querySelector('.overlay-deliverables-edit-delete');
            if (deleteBtn) {
                deleteBtn.addEventListener('click', function () {
                    if (row.dataset.deliverableId) {
                        row.dataset.deleted = 'true';
                        row.style.display = 'none';
                    } else {
                        row.remove();
                    }
                });
            }
        }

        function bindEdit() {
            var listEl = rootEl.querySelector('#overlay-deliverables-edit-list');
            var template = rootEl.querySelector('#overlay-deliverable-row-template');
            var addBtn = rootEl.querySelector('#overlay-add-deliverable-btn');
            var applyAllBtn = rootEl.querySelector('#overlay-apply-deadline-all-btn');
            var saveBtn = rootEl.querySelector('#overlay-save-deliverables-btn');

            if (listEl) { listEl.querySelectorAll('.overlay-deliverables-edit-row').forEach(wireRow); }

            if (addBtn && template && listEl) {
                addBtn.addEventListener('click', function () {
                    var clone = template.content.cloneNode(true);
                    var row = clone.querySelector('.overlay-deliverables-edit-row');
                    listEl.appendChild(clone);
                    wireRow(row);
                    row.querySelector('.overlay-deliverables-edit-name').focus();
                });
            }

            if (applyAllBtn && listEl) {
                applyAllBtn.addEventListener('click', function () {
                    var rows = listEl.querySelectorAll('.overlay-deliverables-edit-row');
                    if (!rows.length) return;
                    var sourceDate = rows[0].querySelector('.overlay-deliverables-edit-date').value;
                    var sourceTime = rows[0].querySelector('.overlay-deliverables-edit-time').value;
                    Array.prototype.forEach.call(rows, function (row, i) {
                        if (i === 0) return;
                        row.querySelector('.overlay-deliverables-edit-date').value = sourceDate;
                        row.querySelector('.overlay-deliverables-edit-time').value = sourceTime;
                    });
                });
            }

            if (saveBtn && listEl) {
                saveBtn.addEventListener('click', function () {
                    var deliverables = collectRows(listEl);
                    saveBtn.disabled = true;
                    var originalText = saveBtn.textContent;
                    saveBtn.textContent = 'Saving…';
                    fetch(`/projects/${projectId}/overlay/deliverables/save`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ deliverables: deliverables }),
                    })
                        .then(function (r) { return r.json(); })
                        .then(function (data) {
                            if (!data.success) {
                                saveBtn.disabled = false;
                                saveBtn.textContent = originalText;
                                alert(data.error || 'Could not save deliverables.');
                                return;
                            }
                            backToReadOnly();
                        })
                        .catch(function () {
                            saveBtn.disabled = false;
                            saveBtn.textContent = originalText;
                            alert('Something went wrong.');
                        });
                });
            }
        }

        if (rootEl.querySelector('#overlay-save-deliverables-btn')) {
            bindEdit();
        } else {
            bindReadOnly();
        }

        return { destroy: function () { destroyed = true; } };
    }
    return { init: init };
})();