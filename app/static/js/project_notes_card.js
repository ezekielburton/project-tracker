// app/static/js/project_notes_card.js
//
// Site Visits tab controller (task #52/M9, notes half moved out M10 chat
// redesign — see project_chat_panel.js). Kept its original filename/
// module name (ProjectNotesCard) since renaming needs a real git mv this
// session's remote file tools can't do — a safe, non-blocking cleanup for
// later, along with the matching template rename noted in _overlay_notes.html.

window.ProjectNotesCard = (function () {

    function init(contentEl, projectId) {
        let designerPickerHandle = null;   // shared between wireSiteVisits() and destroy()
        let visitPickerOutsideClickHandler = null;          

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
            // create route only hands back an id, not the full rendered
            // row, and re-fetching the whole section avoids duplicating
            // that formatting logic in JS. Same tradeoff Deliverables'
            // own edit-save flow makes.
            return fetch(`/projects/${projectId}/overlay/notes`)
                .then((res) => res.text())
                .then((html) => {
                    contentEl.innerHTML = html;
                    wireSiteVisits();
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
            let selectedStart = null;   // full Date (date + time), set on Apply — same shape the submit handler always expected
            let selectedEnd = null;

            // ---- Designer picker (unchanged) ----
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
            // Custom widget, styled after the projects table's own
            // Initial/Next Deadline filter picker (project_list.js /
            // project_list.css's .date-range-picker) rather than Air
            // Datepicker — this needed future-only dates, a range OR a
            // single day, and typed H:MM time entry, which didn't map
            // cleanly onto Air Datepicker's own range+timepicker combo.
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
            const startAmpmBtn = contentEl.querySelector('#visit-start-ampm');
            const endHourInput = contentEl.querySelector('#visit-end-hour');
            const endMinuteInput = contentEl.querySelector('#visit-end-minute');
            const endAmpmBtn = contentEl.querySelector('#visit-end-ampm');
            const clockToggleBtns = contentEl.querySelectorAll('.visit-clock-toggle-btn');

            let clockMode = '12';       // '12' or '24' — shared by both time rows
            let viewYear = null;
            let viewMonth = null;
            let rangeStart = null;      // date-only (calendar selection) — Apply combines this with the time inputs into selectedStart/selectedEnd above
            let rangeEnd = null;

            if (datetimePicker && monthLabelEls.length === 2 && dayGridEls.length === 2) {

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
                        if (sameDay(date, rangeStart)) cell.classList.add('is-range-start');
                        if (sameDay(date, rangeEnd)) cell.classList.add('is-range-end');
                        if (rangeStart && rangeEnd && date > rangeStart && date < rangeEnd) {
                            cell.classList.add('is-in-range');
                        }
                        // Site visits are future-only — past days stay
                        // visible (so the grid still reads as a normal
                        // month) but greyed out and inert.
                        if (date < todayMidnight) cell.classList.add('is-disabled');

                        gridEl.appendChild(cell);
                    });
                }

                function renderVisitCalendar() {
                    renderVisitMonth(monthLabelEls[0], dayGridEls[0], viewYear, viewMonth);
                    const next = new Date(viewYear, viewMonth + 1, 1);
                    renderVisitMonth(monthLabelEls[1], dayGridEls[1], next.getFullYear(), next.getMonth());
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
                        const min = isMinute ? 0 : (clockMode === '24' ? 0 : 1);
                        const max = isMinute ? 59 : (clockMode === '24' ? 23 : 12);
                        if (isNaN(n)) n = min;
                        n = Math.max(min, Math.min(max, n));
                        el.value = String(n).padStart(2, '0');
                    });
                }
                bindTimeInput(startHourInput, false);
                bindTimeInput(startMinuteInput, true);
                bindTimeInput(endHourInput, false);
                bindTimeInput(endMinuteInput, true);

                function setClockMode(mode) {
                    clockMode = mode;
                    clockToggleBtns.forEach((b) => b.classList.toggle('is-active', b.dataset.clock === mode));
                    [startAmpmBtn, endAmpmBtn].forEach((btn) => {
                        if (btn) btn.classList.toggle('is-hidden', mode === '24');
                    });
                    // Re-clamp whatever's already typed into the new range.
                    // This is a simple fold, not a true 24h<->12h+AM/PM
                    // conversion (e.g. going 24h -> 12h just wraps 13-23
                    // down to 1-11, it doesn't also flip AM/PM to PM) —
                    // switching modes mid-entry should be rare, and it's a
                    // one-click fix with the AM/PM toggle if it guesses wrong.
                    [startHourInput, endHourInput].forEach((el) => {
                        if (!el || el.value === '') return;
                        let n = parseInt(el.value, 10);
                        if (isNaN(n)) return;
                        if (mode === '12') {
                            if (n === 0) n = 12;
                            if (n > 12) n -= 12;
                        }
                        const min = mode === '24' ? 0 : 1;
                        const max = mode === '24' ? 23 : 12;
                        el.value = String(Math.max(min, Math.min(max, n))).padStart(2, '0');
                    });
                }
                clockToggleBtns.forEach((btn) => {
                    btn.addEventListener('click', () => setClockMode(btn.dataset.clock));
                });
                [startAmpmBtn, endAmpmBtn].forEach((btn) => {
                    if (!btn) return;
                    btn.addEventListener('click', () => {
                        btn.textContent = btn.textContent.trim() === 'AM' ? 'PM' : 'AM';
                    });
                });

                function fillTimeInputs(hourEl, minuteEl, ampmBtn, date) {
                    if (!hourEl || !minuteEl) return;
                    const h = date.getHours();
                    if (clockMode === '12') {
                        const isPM = h >= 12;
                        let h12 = h % 12;
                        if (h12 === 0) h12 = 12;
                        hourEl.value = String(h12).padStart(2, '0');
                        if (ampmBtn) ampmBtn.textContent = isPM ? 'PM' : 'AM';
                    } else {
                        hourEl.value = String(h).padStart(2, '0');
                    }
                    minuteEl.value = String(date.getMinutes()).padStart(2, '0');
                }

                function readTimeAsHour24(hourEl, minuteEl, ampmBtn) {
                    const hourRaw = hourEl && hourEl.value ? parseInt(hourEl.value, 10) : NaN;
                    const minuteRaw = minuteEl && minuteEl.value ? parseInt(minuteEl.value, 10) : NaN;
                    if (isNaN(hourRaw) || isNaN(minuteRaw)) return null;
                    let hour24 = hourRaw;
                    if (clockMode === '12') {
                        const isPM = ampmBtn && ampmBtn.textContent.trim() === 'PM';
                        hour24 = hourRaw % 12;
                        if (isPM) hour24 += 12;
                    }
                    return { hour: hour24, minute: minuteRaw };
                }

                function openDatetimePicker() {
                    // Re-derive the calendar/time state from whatever was
                    // last applied, so reopening shows your last selection
                    // instead of starting blank — same behavior the table's
                    // own date filter has.
                    if (selectedStart) {
                        rangeStart = new Date(selectedStart.getFullYear(), selectedStart.getMonth(), selectedStart.getDate());
                        rangeEnd = selectedEnd ? new Date(selectedEnd.getFullYear(), selectedEnd.getMonth(), selectedEnd.getDate()) : null;
                        fillTimeInputs(startHourInput, startMinuteInput, startAmpmBtn, selectedStart);
                        if (selectedEnd) fillTimeInputs(endHourInput, endMinuteInput, endAmpmBtn, selectedEnd);
                    } else {
                        rangeStart = null;
                        rangeEnd = null;
                    }
                    const anchor = rangeStart || new Date();
                    viewYear = anchor.getFullYear();
                    viewMonth = anchor.getMonth();
                    renderVisitCalendar();
                    datetimePicker.hidden = false;
                }

                function closeDatetimePicker() {
                    datetimePicker.hidden = true;
                }

                if (rangeBtn) {
                    rangeBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        if (!datetimePicker.hidden) { closeDatetimePicker(); return; }
                        openDatetimePicker();
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

                // One delegated listener for every day cell across both
                // months, same pattern as the table's own picker.
                datetimePicker.addEventListener('click', (e) => {
                    const cell = e.target.closest('.date-range-picker-day');
                    if (!cell || cell.classList.contains('is-disabled')) return;
                    e.stopPropagation();
                    const clicked = fromISO(cell.dataset.iso);
                    if (!rangeStart || (rangeStart && rangeEnd)) {
                        rangeStart = clicked;
                        rangeEnd = null;
                    } else if (clicked < rangeStart) {
                        rangeEnd = rangeStart;
                        rangeStart = clicked;
                    } else {
                        rangeEnd = clicked;
                    }
                    renderVisitCalendar();
                });

                if (datetimeClear) datetimeClear.addEventListener('click', () => {
                    rangeStart = null;
                    rangeEnd = null;
                    [startHourInput, startMinuteInput, endHourInput, endMinuteInput].forEach((el) => { if (el) el.value = ''; });
                    renderVisitCalendar();
                });

                if (datetimeCancel) datetimeCancel.addEventListener('click', () => {
                    closeDatetimePicker();
                });

                if (datetimeApply) datetimeApply.addEventListener('click', () => {
                    if (!rangeStart) { closeDatetimePicker(); return; }
                    const startTime = readTimeAsHour24(startHourInput, startMinuteInput, startAmpmBtn);
                    const endTime = readTimeAsHour24(endHourInput, endMinuteInput, endAmpmBtn);
                    if (!startTime || !endTime) {
                        if (errorEl) { errorEl.textContent = 'Please enter a start and end time.'; errorEl.classList.remove('hidden'); }
                        return;
                    }
                    const endDateOnly = rangeEnd || rangeStart;
                    selectedStart = new Date(rangeStart.getFullYear(), rangeStart.getMonth(), rangeStart.getDate(), startTime.hour, startTime.minute);
                    selectedEnd = new Date(endDateOnly.getFullYear(), endDateOnly.getMonth(), endDateOnly.getDate(), endTime.hour, endTime.minute);
                    if (rangeDisplay) rangeDisplay.textContent = formatRangeLabel(selectedStart, selectedEnd);
                    if (errorEl) errorEl.classList.add('hidden');
                    closeDatetimePicker();
                });

                // Close on outside click. wireSiteVisits() re-runs on every
                // reload() against a freshly rebuilt contentEl, so the old
                // listener has to be removed first or these pile up one per
                // add/delete — same fix as the earlier project_list_layout.js
                // column-resize rebind.
                if (visitPickerOutsideClickHandler) {
                    document.removeEventListener('click', visitPickerOutsideClickHandler);
                }
                visitPickerOutsideClickHandler = function (e) {
                    if (datetimePicker.hidden) return;
                    if (datetimePicker.contains(e.target)) return;
                    if (rangeBtn && rangeBtn.contains(e.target)) return;
                    closeDatetimePicker();
                };
                document.addEventListener('click', visitPickerOutsideClickHandler);
            }

            if (addBtn) {
                addBtn.addEventListener('click', () => {
                    if (!selectedDesignerId) {
                        if (errorEl) { errorEl.textContent = 'Please select a designer.'; errorEl.classList.remove('hidden'); }
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
                    // M10: was bare window.confirm() — unified on showConfirm()
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
                if (visitPickerOutsideClickHandler) {
                    document.removeEventListener('click', visitPickerOutsideClickHandler);
                    visitPickerOutsideClickHandler = null;
                }
            }
        };
    }

    return { init: init };
})();
