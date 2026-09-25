/**
 * Editor.js setup for the wiki article editor.
 * Runs on both a hard load and an SPA swap, so it tears down any editor left
 * behind by the previous visit before starting a new one.
 */
(function () {
    'use strict';

    // A test reads this list and checks editor_article.html still carries these ids.
    var TEMPLATE_CONTRACT = ['wiki-article-form', 'wiki-editor', 'wiki-sections-json',
        'wiki-article-id', 'wiki-save-status'];

    /** Articles arrive already seeded with their skeleton, chosen when they were created. */
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
        if (window.helixEditorAutosave) {
            window.helixEditorAutosave.destroy();
            window.helixEditorAutosave = null;
        }
        if (window.helixBlockDrag) {
            window.helixBlockDrag.destroy();
            window.helixBlockDrag = null;
        }
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
                if (window.helixEditorAutosave) { window.helixEditorAutosave.markSaved(field.value); }
                form.submit();
            }).catch(function () {
                showToast('Could not read the article content', 'error');
            });
        });
    }

    function startAutosave(editor, form, articleField, status) {
        window.helixEditorAutosave = window.HelixEditorAutosave.start({
            editor: editor,
            form: form,
            status: status,
            articleField: articleField,
            url: window.WIKI_AUTOSAVE_URL,
            initialContent: window.WIKI_ARTICLE_JSON || ''
        });
        if (window.WIKI_DRAFT_RESTORED) {
            status.textContent = 'Restored your unsaved draft — Save makes it live';
        }
    }

    function init() {
        var form = document.getElementById(TEMPLATE_CONTRACT[0]);
        var holder = document.getElementById(TEMPLATE_CONTRACT[1]);
        var field = document.getElementById(TEMPLATE_CONTRACT[2]);
        var articleField = document.getElementById(TEMPLATE_CONTRACT[3]);
        var status = document.getElementById(TEMPLATE_CONTRACT[4]);
        if (!form || !holder || !field || !articleField || !status) { return; }

        teardown();

        var editor = new window.EditorJS({
            holder: holder,
            data: readDocument(),
            tools: tools(),
            placeholder: 'Write the article. Press / to add a block.',
            minHeight: 200,
            onReady: function () {
                window.helixBlockDrag = window.HelixBlockDrag.attach(editor, holder);
                startAutosave(editor, form, articleField, status);
            }
        });

        window.helixWikiEditor = editor;

        wireSubmit(form, field);
    }

    init();
}());
