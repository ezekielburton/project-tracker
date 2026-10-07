// Admin system pages (Overview, System, and the pages that follow): each card
// loads from its part URL, and every card reloads when /sse/system pings,
// at most once every few seconds. The stream closes when the admin leaves.

// The template hooks this file binds to. test_admin_pages.py reads this
// declaration and checks the rendered pages still carry each one.
var ADMIN_LIVE_CONTRACT = {
    root: '[data-admin-live]',
    part: '[data-admin-part]',
    partUrl: 'data-part-url',
    streamUrl: 'data-stream-url',
    headline: '[data-admin-headline]',
    headlineData: 'template[data-headline-state]'
};

(function () {
    'use strict';

    var C = ADMIN_LIVE_CONTRACT;
    var REFRESH_GAP_MS = 3000;

    // The header line comes back inside the Needs attention card.
    function syncHeadline(part) {
        var data = part.querySelector(C.headlineData);
        var head = document.querySelector(C.headline);
        if (!data || !head) return;
        var dot = document.createElement('span');
        dot.className = 'dash-admin-dot dash-admin--' + data.getAttribute('data-headline-state');
        head.textContent = '';
        head.appendChild(dot);
        head.appendChild(document.createTextNode(data.getAttribute('data-headline-text')));
    }

    function loadPart(part) {
        return fetch(part.getAttribute(C.partUrl), { credentials: 'same-origin' })
            .then(function (response) {
                if (!response.ok) throw new Error(response.status);
                return response.text();
            })
            .then(function (html) {
                part.innerHTML = html;
                part.setAttribute('data-loaded', '');
                syncHeadline(part);
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
            if (!onlyEmpty || !part.hasAttribute('data-loaded')) loadPart(part);
        });
    }

    var pending = null;
    var last = 0;
    function onPing() {
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
            window._adminSystemStream = stream;
        } else if (!root && window._adminSystemStream) {
            window._adminSystemStream.close();
            window._adminSystemStream = null;
        }
    }

    // A card that came with the page counts as loaded.
    document.querySelectorAll(C.root + ' ' + C.part).forEach(function (part) {
        if (!part.querySelector('.dash-admin-loading')) {
            part.setAttribute('data-loaded', '');
            syncHeadline(part);
        }
    });
    loadAll(true);
    syncStream();
    if (!window._adminSystemWired) {
        window._adminSystemWired = true;
        document.addEventListener('helix:navigated', syncStream);
    }
    if (window.watchFillHeight) window.watchFillHeight('.dash-admin-fill', '--fill-height');
})();
