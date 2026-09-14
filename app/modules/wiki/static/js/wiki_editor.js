/**
 * Editor.js setup for the wiki article editor.
 * Runs on both a hard load and an SPA swap, so it tears down any editor left
 * behind by the previous visit before starting a new one.
 */
(function () {
    'use strict';

    // A test reads this list and checks editor_article.html still carries these ids.
    var TEMPLATE_CONTRACT = ['wiki-article-form', 'wiki-editor', 'wiki-sections-json'];

    function readDocument() {
        try {
            var parsed = window.WIKI_ARTICLE_JSON ? JSON.parse(window.WIKI_ARTICLE_JSON) : null;
            if (parsed && Array.isArray(parsed.blocks)) { return parsed; }
        } catch (error) {
            /* fall through to an empty article */
        }
        return { blocks: [] };
    }

    /** Editor.js wants {success, file:{url}}; our endpoint answers {success, url}. */
    function uploadImage(file) {
        var form = new FormData();
        form.append('file', file);

        return fetch(window.WIKI_UPLOAD_IMAGE_URL, { method: 'POST', body: form, credentials: 'same-origin' })
            .then(function (response) { return response.json(); })
            .then(function (result) {
                if (!result.success) { throw new Error(result.error || 'Upload failed'); }
                return { success: 1, file: { url: result.url } };
            })
            .catch(function () { return { success: 0 }; });
    }

    function tools() {
        return {
            header: {
                class: window.Header,
                inlineToolbar: true,
                config: { levels: [3], defaultLevel: 3, placeholder: 'Heading' }
            },
            list: { class: window.List, inlineToolbar: true },
            helixCallout: { class: window.HelixCallout, inlineToolbar: true },
            helixVideo: { class: window.HelixVideo, config: { uploadUrl: window.WIKI_UPLOAD_VIDEO_URL } },
            image: {
                class: window.ImageTool,
                config: {
                    captionPlaceholder: 'Caption',
                    buttonContent: 'Choose an image',
                    uploader: { uploadByFile: uploadImage }
                }
            }
        };
    }

    function teardown() {
        if (window.helixWikiEditor && typeof window.helixWikiEditor.destroy === 'function') {
            window.helixWikiEditor.destroy();
        }
        window.helixWikiEditor = null;
    }

    function wireSubmit(form, field) {
        form.addEventListener('submit', function (event) {
            event.preventDefault();
            window.helixWikiEditor.save().then(function (output) {
                field.value = JSON.stringify(output);
                form.submit();
            }).catch(function () {
                showToast('Could not read the article content', 'error');
            });
        });
    }

    function init() {
        var form = document.getElementById(TEMPLATE_CONTRACT[0]);
        var holder = document.getElementById(TEMPLATE_CONTRACT[1]);
        var field = document.getElementById(TEMPLATE_CONTRACT[2]);
        if (!form || !holder || !field) { return; }

        teardown();

        window.helixWikiEditor = new window.EditorJS({
            holder: holder,
            data: readDocument(),
            tools: tools(),
            placeholder: 'Write the article. Press / to add a block.',
            minHeight: 200
        });

        wireSubmit(form, field);
    }

    init();
}());
