/*
 * HSE calendar: day selection, the day drawer, and the register picker.
 *
 * Grid and drawer are server-rendered; this only fetches a new drawer when
 * a day is clicked. "Log it" opens the entry overlay, and
 * hse_entry_modal.js re-navigates this page on close to refresh the day.
 *
 * init() runs directly: SPA navigation re-runs page scripts and
 * DOMContentLoaded never fires again.
 */
(function () {
    'use strict';

    var grid, drawer, picker;

    function el(id) { return document.getElementById(id); }

    // The document listeners below are wired on the first visit only, but
    // each SPA visit renders new elements, so they look them up again.
    function refresh() {
        grid = el('hse-cal-grid');
        drawer = el('hse-cal-drawer');
        picker = el('hse-picker');
    }

    // --- which day is open ------------------------------------------------

    function openDay() {
        // Prefer the drawer's date: it is the one actually on screen.
        var inner = drawer && drawer.querySelector('[data-drawer-date]');
        if (inner) { return inner.getAttribute('data-drawer-date'); }
        var selected = grid && grid.querySelector('.hse-cal-day.is-selected');
        return selected ? selected.getAttribute('data-day') : null;
    }

    function select(button) {
        grid.querySelectorAll('.hse-cal-day.is-selected').forEach(function (n) {
            n.classList.remove('is-selected');
        });
        button.classList.add('is-selected');
    }

    function rememberDay(day) {
        // Keep the open day in the URL (no history entry). The entry overlay
        // re-navigates to pathname + search after a save, so this reopens
        // the same day instead of today.
        try {
            var url = new URL(window.location.href);
            url.searchParams.set('day', day);
            window.history.replaceState(null, '', url.toString());
        } catch (err) {
            /* A browser without URL support just loses the selection. */
        }
    }

    function load(day) {
        var url = '/hse/calendar/day/' + day;
        var state = new URLSearchParams(window.location.search).get('state');
        if (state) { url += '?state=' + encodeURIComponent(state); }

        drawer.classList.add('is-loading');
        fetch(url, { headers: { 'X-Requested-With': 'fetch' } })
            .then(function (res) {
                if (!res.ok) { throw new Error('day failed'); }
                return res.text();
            })
            .then(function (html) {
                drawer.innerHTML = html;
                drawer.classList.remove('is-loading');
            })
            .catch(function () {
                drawer.classList.remove('is-loading');
                drawer.innerHTML =
                    '<p class="hse-cal-drawer-sum">Could not load that day.</p>';
            });
    }

    // --- the register picker ----------------------------------------------

    function showPicker() {
        if (!picker) { return; }
        picker.hidden = false;
        var first = picker.querySelector('.hse-picker-item');
        if (first) { first.focus(); }
    }

    function hidePicker() {
        if (picker) { picker.hidden = true; }
    }

    function logInto(registerKey) {
        // Unplanned entry: a register and a date, no occurrence. Defaults
        // to the open day.
        var day = openDay();
        var url = '/hse/' + encodeURIComponent(registerKey) + '/form';
        if (day) { url += '?date=' + encodeURIComponent(day); }
        hidePicker();
        if (window.hseOpenEntryForm) {
            window.hseOpenEntryForm(url);
        } else {
            window.location.href = url;
        }
    }

    // --- wiring -----------------------------------------------------------

    // Phones open on Agenda (the month grid is too small), but only when no
    // view was asked for, so an explicit view=month is respected.
    function agendaFirstOnPhone() {
        if (!el('hse-cal-grid')) { return false; }
        if (!window.matchMedia('(max-width: 48em)').matches) { return false; }
        var params = new URLSearchParams(window.location.search);
        if (params.has('view')) { return false; }
        params.set('view', 'agenda');
        var url = window.location.pathname + '?' + params.toString();
        history.replaceState(null, '', url);
        if (window.navigateTo) { window.navigateTo(url, false); }
        else { window.location.replace(url); }
        return true;
    }

    function init() {
        if (agendaFirstOnPhone()) { return; }
        grid = el('hse-cal-grid');
        drawer = el('hse-cal-drawer');
        picker = el('hse-picker');

        if (grid && drawer) {
            grid.addEventListener('click', function (e) {
                var button = e.target.closest('.hse-cal-day');
                if (!button) { return; }
                var day = button.getAttribute('data-day');
                if (!day) { return; }
                select(button);
                rememberDay(day);
                load(day);
            });
        }

        if (!picker) { return; }

        // Document-delegated (guarded against stacking): the drawer's
        // "+ Log something else" button arrives with fetched markup.
        if (!window._hsePickerWired) {
            window._hsePickerWired = true;
            document.addEventListener('click', function (e) {
                refresh();
                if (e.target.closest('[data-hse-open-picker]')) {
                    e.preventDefault();
                    showPicker();
                    return;
                }
                var item = e.target.closest('.hse-picker-item');
                if (item) {
                    e.preventDefault();
                    logInto(item.getAttribute('data-register'));
                    return;
                }
                if (e.target.closest('#hse-picker-close')) {
                    e.preventDefault();
                    hidePicker();
                }
            });
            document.addEventListener('keydown', function (e) {
                if (e.key === 'Escape') { refresh(); hidePicker(); }
            });
        }
    }

    init();
}());
