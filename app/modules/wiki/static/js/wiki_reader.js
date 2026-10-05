/**
 * Wiki reader pages: fills the reading area and the rail to the footer, and
 * forwards old /wiki#article-N links to the article's own page.
 */
(function () {
    'use strict';

    // A test reads this list and checks every reader template still carries these ids.
    var TEMPLATE_CONTRACT = ['wiki-reader'];

    var reader = document.getElementById(TEMPLATE_CONTRACT[0]);
    if (!reader) { return; }

    // Outside any guard: every SPA swap brings fresh boxes to measure.
    if (window.watchFillHeight) {
        window.watchFillHeight('#wiki-reader', '--fill-height');
        window.watchFillHeight('.wiki-page .module-rail', '--wiki-rail-height');
    }

    // Only the home page carries the article URL, so only it forwards.
    var legacy = window.location.hash.match(/^#article-(\d+)$/);
    if (legacy && reader.dataset.articleUrl) {
        window.location.replace(reader.dataset.articleUrl + legacy[1]);
    }
}());
