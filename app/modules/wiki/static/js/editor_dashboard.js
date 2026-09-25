/**
 * Wiki editor dashboard: drag ordering and the two metadata overlays.
 * Order saves the moment a row is dropped.
 */
(function () {
    'use strict';

    // A test reads this list and checks editor_dashboard.html still carries these ids.
    var TEMPLATE_CONTRACT = ['wiki-section-list', 'wiki-section-modal', 'wiki-article-modal',
        'wiki-new-section-btn', 'wiki-section-id', 'wiki-section-title', 'wiki-section-published',
        'wiki-new-article-section', 'wiki-new-article-template', 'wiki-new-article-help-key'];

    var ROLE_BOX = '#wiki-section-modal input[name="relevant_roles"]';

    function post(url, payload) {
        return fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify(payload)
        }).then(function (response) {
            if (!response.ok) { throw new Error('reorder failed'); }
            return response.json();
        });
    }

    function idsIn(container, selector, attribute) {
        return Array.prototype.slice.call(container.querySelectorAll(selector))
            .map(function (element) { return element.dataset[attribute]; });
    }

    function saveSectionOrder() {
        var list = document.getElementById('wiki-section-list');
        post(WIKI_REORDER_SECTIONS_URL, { section_ids: idsIn(list, '.wiki-editor-section-card', 'sectionId') })
            .catch(function () { showToast('Could not save the new order', 'error'); });
    }

    function saveArticleOrder(list) {
        post(WIKI_REORDER_ARTICLES_URL, { article_ids: idsIn(list, '.wiki-editor-article-row', 'articleId') })
            .catch(function () { showToast('Could not save the new order', 'error'); });
    }

    function startDragging() {
        var list = document.getElementById('wiki-section-list');
        if (!list || typeof Sortable === 'undefined') { return; }

        new Sortable(list, {
            handle: '.wiki-section-drag-handle',
            animation: 150,
            onEnd: saveSectionOrder
        });

        document.querySelectorAll('.wiki-editor-article-list').forEach(function (articles) {
            new Sortable(articles, {
                handle: '.wiki-article-drag-handle',
                animation: 150,
                onEnd: function () { saveArticleOrder(articles); }
            });
        });
    }

    // ------ Overlays ------

    function open(modal) { modal.classList.remove('hidden'); }

    function close(modal) { modal.classList.add('hidden'); }

    function fillSectionModal(card) {
        var isNew = !card;
        var roles = isNew ? [] : (card.dataset.roles || '').split(',').map(function (r) { return r.trim(); });

        document.getElementById('wiki-section-modal-title').textContent = isNew ? 'New section' : 'Edit section';
        document.getElementById('wiki-section-id').value = isNew ? '' : card.dataset.sectionId;
        document.getElementById('wiki-section-title').value = isNew ? '' : card.dataset.title;
        document.getElementById('wiki-section-published').checked = !isNew && card.dataset.published === '1';

        document.querySelectorAll(ROLE_BOX).forEach(function (box) {
            box.checked = roles.indexOf(box.dataset.role) !== -1;
        });
    }

    function wireSectionModal() {
        var modal = document.getElementById('wiki-section-modal');
        var newButton = document.getElementById('wiki-new-section-btn');
        if (!modal || !newButton) { return; }

        newButton.addEventListener('click', function () {
            fillSectionModal(null);
            open(modal);
        });

        document.querySelectorAll('.wiki-edit-section-btn').forEach(function (button) {
            button.addEventListener('click', function () {
                fillSectionModal(button.closest('.wiki-editor-section-card'));
                open(modal);
            });
        });
    }

    function wireArticleModal() {
        var modal = document.getElementById('wiki-article-modal');
        if (!modal) { return; }

        var sectionSelect = document.getElementById('wiki-new-article-section');
        var templateField = document.getElementById('wiki-new-article-template');
        var keySelect = document.getElementById('wiki-new-article-help-key');
        var titleField = document.getElementById('wiki-new-article-title');
        var options = document.getElementById('wiki-new-article-templates');

        document.querySelectorAll('.wiki-new-article-btn').forEach(function (button) {
            button.addEventListener('click', function () {
                sectionSelect.value = button.dataset.sectionId;
                titleField.value = '';
                keySelect.value = '';
                open(modal);
            });
        });

        // Coverage panel: start the article that fills this gap, key already chosen.
        document.querySelectorAll('.wiki-coverage__write').forEach(function (button) {
            button.addEventListener('click', function () {
                titleField.value = button.dataset.helpLabel || '';
                keySelect.value = button.dataset.helpKey;
                open(modal);
            });
        });

        // Arriving from the Help tray's "Write this article".
        var requested = new URLSearchParams(window.location.search).get('help_key');
        if (requested) {
            keySelect.value = requested;
            if (keySelect.value === requested) {
                titleField.value = keySelect.options[keySelect.selectedIndex].text.split(' — ').pop();
                open(modal);
            }
        }

        options.addEventListener('click', function (event) {
            var option = event.target.closest('.wiki-template-option');
            if (!option) { return; }
            options.querySelectorAll('.wiki-template-option').forEach(function (other) {
                other.classList.toggle('is-selected', other === option);
            });
            templateField.value = option.dataset.templateKey;
        });
    }

    function wireClosing() {
        document.querySelectorAll('.modal-overlay').forEach(function (modal) {
            modal.addEventListener('click', function (event) {
                if (event.target === modal || event.target.closest('[data-wiki-modal-close]')) {
                    close(modal);
                }
            });
        });
    }

    function init() {
        // The section list is absent when there are no sections; the modals are not.
        if (!document.getElementById(TEMPLATE_CONTRACT[1])) { return; }
        startDragging();
        wireSectionModal();
        wireArticleModal();
        wireClosing();
    }

    init();
}());
