// Admin system pages: each card loads from its part URL, and every card
// reloads when /sse/system pings, at most once every few seconds. A card
// being typed in is left alone, open rows stay open across a reload, and the
// stream closes when the admin leaves. The badge in the header reads Live while
// the stream is up and the snapshot is fresh, else minutes since it updated.
// Also Run now (two clicks) and the incident note form on Uptime.

// The template hooks this file binds to. test_admin_pages.py reads this
// declaration and checks the rendered pages still carry each one.
var ADMIN_LIVE_CONTRACT = {
    root: '[data-admin-live]',
    part: '[data-admin-part]',
    partUrl: 'data-part-url',
    streamUrl: 'data-stream-url',
    badge: '[data-admin-badge]',
    badgeAge: 'data-age',
    badgeDay: 'data-day',
    badgeText: '[data-badge-text]',
    keepOpen: 'details[data-key]',
    runJob: '[data-run-job]',
    runUrl: 'data-run-url',
    incidentForm: 'form[data-incident-form]',
    formError: '[data-form-error]'
};

(function () {
    'use strict';

    var C = ADMIN_LIVE_CONTRACT;
    var REFRESH_GAP_MS = 3000;
    var CONFIRM_MS = 4000;
    var NOTE_MS = 3000;
    var LIVE_SECONDS = 180;
    var BADGE_TICK_MS = 30000;

    // Kept on window: the stream and the ticking clock outlive an SPA visit.
    var badge = window._adminBadge || (window._adminBadge = { age: null, at: 0, open: true });

    function badgeAge() {
        return badge.age === null ? null : badge.age + (Date.now() - badge.at) / 1000;
    }

    function drawBadge() {
        var el = document.querySelector(C.badge);
        if (!el) return;
        var age = badgeAge();
        var state, text;
        if (age === null) {
            state = 'none';
            text = 'No data yet';
        } else if (badge.open && age < LIVE_SECONDS) {
            state = 'live';
            text = 'Live · ' + el.getAttribute(C.badgeDay);
        } else {
            state = 'stale';
            text = 'Updated ' + Math.max(1, Math.floor(age / 60)) + ' min ago';
        }
        el.className = 'dash-admin-live dash-admin-live--' + state;
        el.querySelector(C.badgeText).textContent = text;
    }

    // The page arrives with the snapshot's age in seconds; count on from there.
    function readBadge() {
        var el = document.querySelector(C.badge);
        if (!el) return;
        var age = el.getAttribute(C.badgeAge);
        badge.age = age === '' ? null : Number(age);
        badge.at = Date.now();
        drawBadge();
    }

    // A card someone is typing in, or has armed a button in, is not reloaded under them.
    function busy(part) {
        var active = document.activeElement;
        if (active && part.contains(active) && /^(INPUT|TEXTAREA|SELECT)$/.test(active.tagName)) return true;
        if (part.querySelector(C.runJob + '[data-armed]')) return true;
        return Array.prototype.some.call(part.querySelectorAll('input:not([type=date]), textarea'), function (field) {
            return field.value !== '';
        });
    }

    function loadPart(part) {
        var open = Array.prototype.map.call(part.querySelectorAll(C.keepOpen + '[open]'), function (row) {
            return row.getAttribute('data-key');
        });
        return fetch(part.getAttribute(C.partUrl), { credentials: 'same-origin' })
            .then(function (response) {
                if (!response.ok) throw new Error(response.status);
                return response.text();
            })
            .then(function (html) {
                part.innerHTML = html;
                part.setAttribute('data-loaded', '');
                part.querySelectorAll(C.keepOpen).forEach(function (row) {
                    if (open.indexOf(row.getAttribute('data-key')) !== -1) row.open = true;
                });
                if (window.markScrollable) window.markScrollable(part);
            })
            .catch(function () {
                // A refresh that fails keeps the last good card.
                if (!part.hasAttribute('data-loaded')) {
                    part.innerHTML = '<p class="dash-quiet">No data</p>';
                }
            });
    }

    function loadAll(onlyEmpty) {
        document.querySelectorAll(C.root + ' ' + C.part).forEach(function (part) {
            if (onlyEmpty ? !part.hasAttribute('data-loaded') : !busy(part)) loadPart(part);
        });
    }

    var pending = null;
    var last = 0;
    function onPing(event) {
        if (event && event.data === 'snapshot') {
            badge.age = 0;
            badge.at = Date.now();
        }
        badge.open = true;
        drawBadge();
        if (pending) return;
        var wait = Math.max(0, last + REFRESH_GAP_MS - Date.now());
        pending = setTimeout(function () {
            pending = null;
            last = Date.now();
            loadAll(false);
        }, wait);
    }

    // One stream for as long as an admin system page is showing.
    function syncStream() {
        var root = document.querySelector(C.root);
        if (root && !window._adminSystemStream && typeof EventSource !== 'undefined') {
            var stream = new EventSource(root.getAttribute(C.streamUrl));
            stream.onmessage = onPing;
            stream.onopen = function () { badge.open = true; drawBadge(); };
            stream.onerror = function () { badge.open = false; drawBadge(); };
            window._adminSystemStream = stream;
        } else if (!root && window._adminSystemStream) {
            window._adminSystemStream.close();
            window._adminSystemStream = null;
        }
    }

    function postJson(url, body) {
        return fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body || {})
        }).then(function (response) {
            return response.json().catch(function () { return {}; }).then(function (data) {
                if (!response.ok || !data.success) throw new Error(data.error || 'Something went wrong');
                return data;
            });
        });
    }

    function settle(button, text, disabled) {
        button.removeAttribute('data-armed');
        button.textContent = text;
        button.disabled = disabled;
    }

    // First click arms the button, a second within CONFIRM_MS starts the job.
    function onRunJob(button) {
        if (!button.hasAttribute('data-armed')) {
            button.setAttribute('data-armed', '');
            button.textContent = 'Confirm';
            setTimeout(function () {
                if (button.hasAttribute('data-armed')) settle(button, 'Run now', false);
            }, CONFIRM_MS);
            return;
        }
        settle(button, 'Starting…', true);
        postJson(button.getAttribute(C.runUrl))
            .then(function () { settle(button, 'Queued', true); })
            .catch(function (error) {
                settle(button, error.message, true);
                setTimeout(function () { settle(button, 'Run now', false); }, NOTE_MS);
            });
    }

    function onIncidentSubmit(form) {
        var error = form.querySelector(C.formError);
        var body = {};
        new FormData(form).forEach(function (value, key) { body[key] = value; });
        if (error) error.textContent = '';
        postJson(form.getAttribute('action'), body)
            .then(function () {
                form.reset();
                var part = form.closest(C.part);
                if (part) loadPart(part);
            })
            .catch(function (problem) {
                if (error) error.textContent = problem.message;
            });
    }

    // A card that came with the page counts as loaded.
    document.querySelectorAll(C.root + ' ' + C.part).forEach(function (part) {
        if (!part.querySelector('.dash-admin-loading')) part.setAttribute('data-loaded', '');
    });
    readBadge();
    loadAll(true);
    syncStream();
    if (!window._adminBadgeTick) window._adminBadgeTick = setInterval(drawBadge, BADGE_TICK_MS);
    if (!window._adminSystemWired) {
        window._adminSystemWired = true;
        document.addEventListener('helix:navigated', syncStream);
        document.addEventListener('click', function (event) {
            var button = event.target.closest ? event.target.closest(C.runJob) : null;
            if (button && !button.disabled) onRunJob(button);
        });
        document.addEventListener('submit', function (event) {
            var form = event.target.closest ? event.target.closest(C.incidentForm) : null;
            if (!form) return;
            event.preventDefault();
            onIncidentSubmit(form);
        });
    }
    if (window.watchFillHeight) window.watchFillHeight('.dash-admin-fill', '--fill-height');
})();
