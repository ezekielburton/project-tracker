/**
 * The Help tray: the contextual "?" and the dock's Help pill.
 * Loaded from base.html, so it binds once and survives SPA page swaps —
 * every click is handled by delegation rather than per-page wiring.
 */
(function () {
    'use strict';

    var BROWSE_URL = '/wiki/help';
    var pending = null;

    function body() {
        return window.HelixTrays ? window.HelixTrays.body() : null;
    }

    function show(html) {
        var target = body();
        if (target) { target.innerHTML = html; }
    }

    function load(url) {
        show('<p class="wiki-help__loading">Loading…</p>');
        fetch(url, { credentials: 'same-origin' })
            .then(function (response) {
                if (!response.ok) { throw new Error('help fetch failed'); }
                return response.text();
            })
            .then(show)
            .catch(function () {
                show('<p class="wiki-help__loading">Could not load that article.</p>');
            });
    }

    /** Open the tray on a key. The shell clears the body, so the load waits for onOpen. */
    function openKey(key) {
        pending = '/wiki/help/' + encodeURIComponent(key);
        if (window.HelixTrays.isOpen('help')) {
            load(pending);
            pending = null;
        } else {
            window.HelixTrays.open('help');
        }
    }

    function onOpen() {
        load(pending || BROWSE_URL);
        pending = null;
    }

    // Any "?" anywhere on the page, now or after a swap.
    document.addEventListener('click', function (event) {
        var trigger = event.target.closest ? event.target.closest('[data-help-key]') : null;
        if (!trigger) { return; }
        event.preventDefault();
        openKey(trigger.dataset.helpKey);
    });

    // Inside the tray: the browse list opens an article in place.
    document.addEventListener('click', function (event) {
        var link = event.target.closest ? event.target.closest('.wiki-help__link') : null;
        if (!link) { return; }
        load('/wiki/help/article/' + link.dataset.articleId);
    });

    if (window.HelixTrays) {
        window.HelixTrays.register('help', { onOpen: onOpen });
    }
}());
