/**
 * Autosave for the wiki article editor.
 * Parks the working copy in the article's draft every 20 seconds; pressing
 * Save is what makes it live. Only writes when something actually changed.
 */
(function () {
    'use strict';

    var INTERVAL = 20000;

    function Autosave(options) {
        this.editor = options.editor;
        this.form = options.form;
        this.status = options.status;
        this.articleField = options.articleField;
        this.url = options.url;

        this.lastSaved = options.initialContent || '';
        this.savedAt = null;
        this.busy = false;

        this.timer = window.setInterval(this.tick.bind(this), INTERVAL);
        this.clock = window.setInterval(this.showAge.bind(this), 15000);
    }

    Autosave.prototype.destroy = function () {
        window.clearInterval(this.timer);
        window.clearInterval(this.clock);
    };

    Autosave.prototype.field = function (name) {
        var input = this.form.querySelector('[name="' + name + '"]');
        return input ? input.value.trim() : '';
    };

    Autosave.prototype.tick = function () {
        var self = this;
        if (this.busy || !this.editor) { return; }

        this.editor.save().then(function (output) {
            var content = JSON.stringify(output);
            if (content === self.lastSaved) { return; }
            self.send(content);
        }).catch(function () { /* a read that fails is retried on the next tick */ });
    };

    Autosave.prototype.send = function (content) {
        var self = this;
        var body = new FormData();
        body.append('article_id', this.articleField.value);
        body.append('section_id', this.field('section_id'));
        body.append('title', this.field('title'));
        body.append('sections_json', content);

        this.busy = true;
        this.show('Saving…');

        fetch(this.url, { method: 'POST', body: body, credentials: 'same-origin' })
            .then(function (response) { return response.json(); })
            .then(function (result) {
                if (!result.success) { self.show(''); return; }
                if (!self.articleField.value) { self.articleField.value = result.article_id; }
                self.lastSaved = content;
                self.savedAt = Date.now();
                self.showAge();
            })
            .catch(function () { self.show('Could not save the draft'); })
            .then(function () { self.busy = false; });
    };

    /** Called by the editor when a real save has made the draft live. */
    Autosave.prototype.markSaved = function (content) {
        this.lastSaved = content;
        this.savedAt = Date.now();
    };

    Autosave.prototype.showAge = function () {
        if (!this.savedAt) { return; }
        var seconds = Math.round((Date.now() - this.savedAt) / 1000);
        if (seconds < 60) {
            this.show('Draft saved just now');
        } else {
            var minutes = Math.round(seconds / 60);
            this.show('Draft saved ' + minutes + (minutes === 1 ? ' minute ago' : ' minutes ago'));
        }
    };

    Autosave.prototype.show = function (message) {
        if (this.status) { this.status.textContent = message; }
    };

    window.HelixEditorAutosave = {
        start: function (options) { return new Autosave(options); }
    };
}());
