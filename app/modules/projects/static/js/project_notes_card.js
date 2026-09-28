// Site Visits tab controller (data-main-tab="notes", _overlay_notes.html).
// Despite the "notes" name, it only handles Site Visits.

window.ProjectNotesCard = (function () {

    function init(contentEl, projectId) {
        let designerPickerHandle = null;   // shared between wireSiteVisits() and destroy()        

        function toLocalIso(date) {
            // The server stores naive local datetimes; toISOString() would
            // shift to UTC and move the hour or day.
            const pad = (n) => String(n).padStart(2, '0');
            return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
                `T${pad(date.getHours())}:${pad(date.getMinutes())}:00`;
        }

        function escapeHtml(str) {
            const div = document.createElement('div');
            div.textContent = str == null ? '' : String(str);
            return div.innerHTML;
        }

        function postJson(url, body) {
            return fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body || {}),
            }).then((res) => res.json().then((data) => ({ ok: res.ok, data })));
        }

        function reload() {
            // Re-render the whole tab after add/delete; the create route
            // returns only an id, not the rendered row.
            return fetch(`/projects/${projectId}/overlay/notes`)
                .then((res) => res.text())
                .then((html) => {
                    contentEl.innerHTML = html;
                    wireSiteVisits();
                });
        }

        // ---- Site Visits ----
        // Project name and location are user-entered, so escape before innerHTML.
        function showOverlapModal(conflict) {
            const wrapper = document.createElement('div');
            wrapper.innerHTML = `
                <div class="modal-overlay" id="overlay-visit-conflict-modal">
                    <div class="modal-box">
                        <h3 class="modal-title">This site visit conflicts with another site visit</h3>
                        <p class="overlay-submit-summary-note">
                            ${escapeHtml(conflict.project_name)} — ${escapeHtml(conflict.start_at)} to ${escapeHtml(conflict.end_at)}
                            ${conflict.location ? ' · ' + escapeHtml(conflict.location) : ''}
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
            const openModalBtn = contentEl.querySelector('#overlay-visit-open-modal-btn');
            const visitModal = contentEl.querySelector('#overlay-visit-modal');
            const locationInput = contentEl.querySelector('#overlay-visit-location');
            const locationLinkInput = contentEl.querySelector('#overlay-visit-location-link');
            const notesInput = contentEl.querySelector('#overlay-visit-notes');
            const errorEl = contentEl.querySelector('#overlay-visit-error');
            const designerPickerEl = contentEl.querySelector('#overlay-visit-designer-picker');

            let selectedDesignerId = null;
            let selectedStart = null;   // full Date (date + time), set on Apply
            let selectedEnd = null;

            // ---- Designer picker ----
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

            // ---- Date & Time picker ----
            // Custom one-month widget reusing the .date-range-picker styles
            // from project_list.css. Future days only; typed HH:MM times.
            const datetimePicker = contentEl.querySelector('#visit-datetime-picker');
            const datetimePrev = contentEl.querySelector('#visit-date-prev');
            const datetimeNext = contentEl.querySelector('#visit-date-next');
            const datetimeClear = contentEl.querySelector('#visit-date-clear');
            const datetimeCancel = contentEl.querySelector('#visit-date-cancel');
            const datetimeApply = contentEl.querySelector('#visit-date-apply');
            const monthLabelEls = contentEl.querySelectorAll('[data-visit-month-label]');
            const dayGridEls = contentEl.querySelectorAll('[data-visit-days]');
            const startHourInput = contentEl.querySelector('#visit-start-hour');
            const startMinuteInput = contentEl.querySelector('#visit-start-minute');
            const endHourInput = contentEl.querySelector('#visit-end-hour');
            const endMinuteInput = contentEl.querySelector('#visit-end-minute');

            let viewYear = null;
            let viewMonth = null;
            let rangeStart = null;      // selected day; Apply adds the times to make selectedStart/selectedEnd


            if (datetimePicker && monthLabelEls.length === 1 && dayGridEls.length === 1) {

                function toISO(date) {
                    const y = date.getFullYear();
                    const m = String(date.getMonth() + 1).padStart(2, '0');
                    const d = String(date.getDate()).padStart(2, '0');
                    return `${y}-${m}-${d}`;
                }
                function fromISO(iso) {
                    const [y, m, d] = iso.split('-').map(Number);
                    return new Date(y, m - 1, d);
                }
                function sameDay(a, b) {
                    return a && b && a.getFullYear() === b.getFullYear() &&
                        a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
                }
                function buildMonthCells(year, month) {
                    const firstOfMonth = new Date(year, month, 1);
                    const firstWeekday = (firstOfMonth.getDay() + 6) % 7; // Mon = 0 ... Sun = 6
                    const gridStart = new Date(year, month, 1 - firstWeekday);
                    const cells = [];
                    for (let i = 0; i < 42; i++) {
                        cells.push(new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + i));
                    }
                    return cells;
                }

                function renderVisitMonth(labelEl, gridEl, year, month) {
                    labelEl.textContent = new Date(year, month, 1)
                        .toLocaleString('default', { month: 'long', year: 'numeric' });

                    gridEl.innerHTML = '';
                    const today = new Date();
                    const todayMidnight = new Date(today.getFullYear(), today.getMonth(), today.getDate());

                    buildMonthCells(year, month).forEach((date) => {
                        const cell = document.createElement('button');
                        cell.type = 'button';
                        cell.className = 'date-range-picker-day';
                        cell.textContent = date.getDate();
                        cell.dataset.iso = toISO(date);

                        if (date.getMonth() !== month) cell.classList.add('is-other-month');
                        if (sameDay(date, today)) cell.classList.add('is-today');
                        if (sameDay(date, rangeStart)) cell.classList.add ('is-range-start');
                        // Past days show but are disabled.
                        if (date < todayMidnight) cell.classList.add('is-disabled');

                        gridEl.appendChild(cell);
                    });
                }

                function renderVisitCalendar() {
                    renderVisitMonth(monthLabelEls[0], dayGridEls[0], viewYear, viewMonth);
                }

                // ---- Time inputs: typed, digit-only, clamped on blur ----
                function bindTimeInput(el, isMinute) {
                    if (!el) return;
                    el.addEventListener('input', () => {
                        el.value = el.value.replace(/\D/g, '').slice(0, 2);
                    });
                    el.addEventListener('blur', () => {
                        if (el.value === '') return; // leave empty until Apply validates
                        let n = parseInt(el.value, 10);
                        const min = 0;
                        const max = isMinute ? 59 : 23;
                        if (isNaN(n)) n = min;
                        n = Math.max(min, Math.min(max, n));
                        el.value = String(n).padStart(2, '0');
                    });
                }
                bindTimeInput(startHourInput, false);
                bindTimeInput(startMinuteInput, true);
                bindTimeInput(endHourInput, false);
                bindTimeInput(endMinuteInput, true);

                function fillTimeInputs(hourEl, minuteEl, date) {
                    if (!hourEl || !minuteEl) return;
                    hourEl.value = String(date.getHours()).padStart(2, '0');
                    minuteEl.value = String(date.getMinutes()).padStart(2, '0');
                }

                function readTimeAsHour24(hourEl, minuteEl) {
                    const hourRaw = hourEl && hourEl.value ? parseInt(hourEl.value, 10) : NaN;
                    const minuteRaw = minuteEl && minuteEl.value ? parseInt(minuteEl.value, 10) : NaN;
                    if (isNaN(hourRaw) || isNaN(minuteRaw)) return null;
                    return { hour: hourRaw, minute: minuteRaw };
                }

                function openDatetimePicker() {
                    // Reopening shows the last applied selection.
                    if (selectedStart) {
                        rangeStart = new Date(selectedStart.getFullYear(), selectedStart.getMonth(), selectedStart.getDate());
                        fillTimeInputs(startHourInput, startMinuteInput, selectedStart);
                        if (selectedEnd) fillTimeInputs(endHourInput, endMinuteInput, selectedEnd);
                    } else {
                        rangeStart = null;
                    }
                    const anchor = rangeStart || new Date();
                    viewYear = anchor.getFullYear();
                    viewMonth = anchor.getMonth();
                    renderVisitCalendar();
                }

                function closeDatetimePicker() {
                    if (visitModal) visitModal.classList.add('hidden');
                }

                if (openModalBtn) {
                    openModalBtn.addEventListener('click', () => {
                        openDatetimePicker();
                        if (visitModal) visitModal.classList.remove('hidden');
                    });
                }

                if (visitModal) {
                    visitModal.addEventListener('click', (e) => {
                        if (e.target === visitModal) closeDatetimePicker();
                    });
                }

                if (datetimePrev) datetimePrev.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const prev = new Date(viewYear, viewMonth - 1, 1);
                    viewYear = prev.getFullYear();
                    viewMonth = prev.getMonth();
                    renderVisitCalendar();
                });
                if (datetimeNext) datetimeNext.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const next = new Date(viewYear, viewMonth + 1, 1);
                    viewYear = next.getFullYear();
                    viewMonth = next.getMonth();
                    renderVisitCalendar();
                });

                // One delegated listener for every day cell.
                datetimePicker.addEventListener('click', (e) => {
                    const cell = e.target.closest('.date-range-picker-day');
                    if (!cell || cell.classList.contains('is-disabled')) return;
                    e.stopPropagation();
                    rangeStart = fromISO(cell.dataset.iso);
                    renderVisitCalendar();
                });

                if (datetimeClear) datetimeClear.addEventListener('click', () => {
                    rangeStart = null;
                    [startHourInput, startMinuteInput, endHourInput, endMinuteInput].forEach((el) => { if (el) el.value = ''; });
                    renderVisitCalendar();
                });

                if (datetimeCancel) datetimeCancel.addEventListener('click', () => {
                    closeDatetimePicker();
                });

                // #visit-date-apply ("Add Site Visit") is the modal's only
                // submit: it validates every field, then posts.
                function showError(msg) {
                    if (errorEl) { errorEl.textContent = msg; errorEl.classList.remove('hidden'); }
                }

                if (datetimeApply) datetimeApply.addEventListener('click', () => {
                    if (!selectedDesignerId) { showError('Please select a designer.'); return; }
                    if (!rangeStart) { showError('Please select a date.'); return; }

                    const startTime = readTimeAsHour24(startHourInput, startMinuteInput);
                    const endTime = readTimeAsHour24(endHourInput, endMinuteInput);
                    if (!startTime && !endTime) { showError('Please enter a start and end time.'); return; }
                    if (!startTime) { showError('Please enter a start time.'); return; }
                    if (!endTime) { showError('Please enter an end time.'); return; }

                    const location = locationInput ? locationInput.value.trim() : '';
                    if (!location) { showError('Please enter a location name.'); return; }
                    const locationLink = locationLinkInput ? locationLinkInput.value.trim() : '';

                    selectedStart = new Date(rangeStart.getFullYear(), rangeStart.getMonth(), rangeStart.getDate(), startTime.hour, startTime.minute);
                    selectedEnd = new Date(rangeStart.getFullYear(), rangeStart.getMonth(), rangeStart.getDate(), endTime.hour, endTime.minute);
                    if (errorEl) errorEl.classList.add('hidden');

                    datetimeApply.disabled = true;
                    postJson(`/projects/${projectId}/overlay/site-visits/create`, {
                        user_id: selectedDesignerId,
                        start_at: toLocalIso(selectedStart),
                        end_at: toLocalIso(selectedEnd),
                        location: location,
                        location_link: locationLink,
                        notes: notesInput ? notesInput.value.trim() : '',
                    }).then(({ data }) => {
                        datetimeApply.disabled = false;
                        if (data.success) { reload(); return; }
                        if (data.error_type === 'overlap') {
                            showOverlapModal(data.conflict);
                        } else {
                            showError(data.error || 'Could not log this site visit.');
                        }
                    });
                });
            }

            contentEl.querySelectorAll('.overlay-visit-delete').forEach((btn) => {
                btn.addEventListener('click', () => {
                    window.showConfirm('Delete this site visit?', () => {
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
            });
        }

        wireSiteVisits();

        return {
            destroy: function () {
                if (designerPickerHandle) { designerPickerHandle.destroy(); designerPickerHandle = null; }
            }
        };
    }

    return { init: init };
})();
