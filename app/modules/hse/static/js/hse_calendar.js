/*
 * HSE calendar — day selection, the drawer, and the register picker.
 *
 * The grid and the drawer are both server-rendered; this swaps the drawer
 * when another day is clicked, so no date logic lives here. The calendar
 * never writes: "Log it" opens the ordinary entry overlay, and
 * hse_entry_modal.js re-navigates this page on close, which is what brings
 * the day back updated.
 *
 * IIFE calling init at the bottom — SPA navigation re-runs page scripts
 * after DOMContentLoaded has long gone (spa-navigation.md, trap 1).
 */
(function () {
    'use strict';

    var grid, drawer, picker;

    function el(id) { return document.getElementById(id); }

    // --- which day is open ------------------------------------------------

    function openDay() {
        // The drawer's own date first: it is the one actually on screen.
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
        // Put the open day in the URL without adding a history entry. The
        // entry overlay re-navigates to location.pathname + search when it
        // closes after a save, so this is what brings the drawer back on
        // the same day rather than jumping to today.
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
        // Unplanned work: a date and a register, no occurrence. The form
        // opens on the day he is looking at, which is almost always the day
        // he means.
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

    function init() {
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

        // Delegated on document: the drawer's "+ Log something else" button
        // arrives with fetched markup and has no wiring of its own.
        if (!window._hsePickerWired) {
            window._hsePickerWired = true;
            document.addEventListener('click', function (e) {
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
                if (e.key === 'Escape') { hidePicker(); }
            });
        }
    }

    init();
}());
