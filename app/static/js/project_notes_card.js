// app/static/js/project_notes_card.js
//
// Notes + Site Visits section (task #52/M9). Both cards live in one
// fragment (_overlay_notes.html) and share this one controller — simplest
// thing that works, since neither card has enough independent complexity
// to justify its own file (unlike Deliverables/Pre-Production).

window.ProjectNotesCard = (function () {
    // Air Datepicker defaults to Russian (its own default locale is
    // locale/ru) — the CDN build we load is the plain UMD bundle, not the
    // ES-module package, so pulling in air-datepicker/locale/en.js isn't
    // straightforward. Inlining the English locale object here (exact
    // shape from Air Datepicker's own docs) sidesteps that entirely and
    // has zero dependency on a second CDN file resolving correctly.
    const AIR_DATEPICKER_LOCALE_EN = {
        days: ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'],
        daysShort: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
        daysMin: ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'],
        months: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
        monthsShort: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
        today: 'Today',
        clear: 'Clear',
        dateFormat: 'MM/dd/yyyy',
        timeFormat: 'hh:mm aa',
        firstDay: 0,
    };

    function init(contentEl, projectId) {
        let designerPickerHandle = null;   // shared between wireSiteVisits() and destroy()
        let rangePicker = null;            // ditto — single Air Datepicker range+time instance

        function toLocalIso(date) {
            // Air Datepicker hands back a real JS Date in the browser's local
            // timezone. date.toISOString() would convert to UTC and silently
            // shift the hour/day — every other date field in this app stores a
            // naive local datetime, so build the string from local components
            // instead.
            const pad = (n) => String(n).padStart(2, '0');
            return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
                `T${pad(date.getHours())}:${pad(date.getMinutes())}:00`;
        }

        function formatRangeLabel(start, end) {
            const opts = { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' };
            return `${start.toLocaleString(undefined, opts)} → ${end.toLocaleString(undefined, opts)}`;
        }

        function postJson(url, body) {
            return fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body || {}),
            }).then((res) => res.json().then((data) => ({ ok: res.ok, data })));
        }

        function reload() {
            // Simplest safe way to reflect a successful add/delete — the
            // create routes only hand back an id, not the full rendered
            // row (author name, formatted dates, etc.), and re-fetching
            // the whole section avoids duplicating that formatting logic
            // in JS. Same tradeoff Deliverables' own edit-save flow makes.
            // Returns the fetch chain so callers (e.g. wireNotes()'s add
            // handler) can do something once the fresh content is in —
            // like refocusing the note textarea for fast repeated entry.
            return fetch(`/projects/${projectId}/overlay/notes`)
                .then((res) => res.text())
                .then((html) => {
                    contentEl.innerHTML = html;
                    wireNotes();
                    wireSiteVisits();
                });
        }

        // ---- Notes ----
        function wireNotes() {
            const addBtn = contentEl.querySelector('#overlay-note-add-btn');
            const bodyInput = contentEl.querySelector('#overlay-note-body');
            const errorEl = contentEl.querySelector('#overlay-note-error');

            if (addBtn) {
                addBtn.addEventListener('click', () => {
                    const body = bodyInput ? bodyInput.value.trim() : '';
                    if (!body) {
                        if (errorEl) { errorEl.textContent = 'Note text is required.'; errorEl.classList.remove('hidden'); }
                        return;
                    }
                    addBtn.disabled = true;
                    if (errorEl) errorEl.classList.add('hidden');
                    postJson(`/projects/${projectId}/overlay/notes/create`, { body: body }).then(({ ok, data }) => {
                        addBtn.disabled = false;
                        if (!ok || !data.success) {
                            if (errorEl) { errorEl.textContent = data.error || 'Could not add this note.'; errorEl.classList.remove('hidden'); }
                            return;
                        }
                        // Notes are meant to accumulate as an ongoing log,
                        // not a one-off — refocus the fresh textarea so
                        // adding the next one doesn't need an extra click.
                        reload().then(() => {
                            const freshBody = contentEl.querySelector('#overlay-note-body');
                            if (freshBody) freshBody.focus();
                        });
                    });
                });
            }

            contentEl.querySelectorAll('.overlay-note-delete').forEach((btn) => {
                btn.addEventListener('click', () => {
                    if (!window.confirm('Delete this note?')) return;
                    const noteId = btn.getAttribute('data-note-id');
                    postJson(`/projects/${projectId}/overlay/notes/${noteId}/delete`, {}).then(({ ok, data }) => {
                        if (!ok || !data.success) {
                            if (window.showToast) window.showToast(data.error || 'Could not delete this note.', 'error');
                            return;
                        }
                        reload();
                    });
                });
            });
        }

        // ---- Site Visits ----
        function showOverlapModal(conflict) {
            const wrapper = document.createElement('div');
            wrapper.innerHTML = `
                <div class="modal-overlay" id="overlay-visit-conflict-modal">
                    <div class="modal-box">
                        <h3 class="modal-title">This site visit conflicts with another site visit</h3>
                        <p class="overlay-submit-summary-note">
                            ${conflict.project_name} — ${conflict.start_at} to ${conflict.end_at}
                            ${conflict.location ? ' · ' + conflict.location : ''}
                        </p>
                        <div class="modal-actions">
                            <button type="button" class="overlay-file-action-btn overlay-file-action-btn--action"
                                id="overlay-visit-conflict-okay">Okay</button>
                        </div>
                    </div>
                </div>`;
            const modal = wrapper.firstElementChild;
            document.body.appendChild(modal);
            const close = () => modal.remove();
            modal.querySelector('#overlay-visit-conflict-okay').addEventListener('click', close);
            modal.addEventListener('click', (e) => { if (e.target === modal) close(); });
        }

        function wireSiteVisits() {
            const addBtn = contentEl.querySelector('#overlay-visit-add-btn');
            const rangeBtn = contentEl.querySelector('#overlay-visit-range-btn');
            const rangeDisplay = contentEl.querySelector('#overlay-visit-range-display');
            const locationInput = contentEl.querySelector('#overlay-visit-location');
            const notesInput = contentEl.querySelector('#overlay-visit-notes');
            const errorEl = contentEl.querySelector('#overlay-visit-error');
            const designerPickerEl = contentEl.querySelector('#overlay-visit-designer-picker');

            let selectedDesignerId = null;
            let selectedStart = null;
            let selectedEnd = null;

            // Same reasoning as designerPickerHandle below: reload() just
            // replaced contentEl's innerHTML, so any previous Air Datepicker
            // instance is bound to a now-detached DOM node — the freshly
            // rendered button has nothing attached until this is recreated.
            if (rangePicker) { rangePicker.destroy(); rangePicker = null; }

            if (rangeBtn) {
                rangePicker = new AirDatepicker(rangeBtn, {
                    locale: AIR_DATEPICKER_LOCALE_EN,
                    range: true,
                    timepicker: true,
                    timeFormat: 'hh:mm AA',
                    dateFormat: 'dd MMM yyyy',
                    onSelect({ date }) {
                        const dates = Array.isArray(date) ? date : (date ? [date] : []);
                        if (dates.length >= 2) {
                            selectedStart = dates[0];
                            selectedEnd = dates[1];
                            if (rangeDisplay) rangeDisplay.textContent = formatRangeLabel(selectedStart, selectedEnd);
                        } else {
                            // First click of a fresh range — nothing complete
                            // to submit yet, don't show a stale/partial label.
                            selectedStart = null;
                            selectedEnd = null;
                            if (rangeDisplay) rangeDisplay.textContent = '';
                        }
                    },
                });
            }

            // reload() just replaced contentEl's innerHTML, so the OLD
            // picker's trigger/popover elements are already gone from the
            // DOM — but AvatarPicker.init() also registers document-level
            // click/keydown listeners that don't get cleaned up just
            // because their target elements were removed. Kill the
            // previous handle before creating a new one, every time this
            // runs (first call and every reload() after it).
            if (designerPickerHandle) {
                designerPickerHandle.destroy();
                designerPickerHandle = null;
            }
            if (designerPickerEl) {
                designerPickerHandle = window.AvatarPicker.init(designerPickerEl, function (userId, pickerEl) {
                    selectedDesignerId = userId;
                    const option = pickerEl.querySelector('.avatar-picker-option[data-user-id="' + userId + '"]');
                    const trigger = pickerEl.querySelector('.avatar-picker-trigger');
                    if (option && trigger) trigger.innerHTML = option.innerHTML;
                });
            }

            if (addBtn) {
                addBtn.addEventListener('click', () => {
                    if (!selectedDesignerId) {
                        if (errorEl) { errorEl.textContent = 'Please select a technical designer.'; errorEl.classList.remove('hidden'); }
                        return;
                    }
                    if (!selectedStart || !selectedEnd) {
                        if (errorEl) { errorEl.textContent = 'Please select a start and end time.'; errorEl.classList.remove('hidden'); }
                        return;
                    }
                    addBtn.disabled = true;
                    if (errorEl) errorEl.classList.add('hidden');
                    postJson(`/projects/${projectId}/overlay/site-visits/create`, {
                        user_id: selectedDesignerId,
                        start_at: toLocalIso(selectedStart),
                        end_at: toLocalIso(selectedEnd),
                        location: locationInput ? locationInput.value.trim() : '',
                        notes: notesInput ? notesInput.value.trim() : '',
                    }).then(({ data }) => {
                        addBtn.disabled = false;
                        if (data.success) { reload(); return; }
                        if (data.error_type === 'overlap') {
                            showOverlapModal(data.conflict);
                        } else if (errorEl) {
                            errorEl.textContent = data.error || 'Could not log this site visit.';
                            errorEl.classList.remove('hidden');
                        }
                    });
                });
            }

            contentEl.querySelectorAll('.overlay-visit-delete').forEach((btn) => {
                btn.addEventListener('click', () => {
                    if (!window.confirm('Delete this site visit?')) return;
                    const visitId = btn.getAttribute('data-visit-id');
                    postJson(`/projects/${projectId}/overlay/site-visits/${visitId}/delete`, {}).then(({ ok, data }) => {
                        if (!ok || !data.success) {
                            if (window.showToast) window.showToast(data.error || 'Could not delete this visit.', 'error');
                            return;
                        }
                        reload();
                    });
                });
            });
        }

        wireNotes();
        wireSiteVisits();

        return {
            destroy: function () {
                if (designerPickerHandle) { designerPickerHandle.destroy(); designerPickerHandle = null; }
                if (rangePicker) { rangePicker.destroy(); rangePicker = null; }
            }
        };
    }

    return { init: init };
})();
