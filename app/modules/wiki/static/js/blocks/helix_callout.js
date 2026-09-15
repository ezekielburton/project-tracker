/**
 * Editor.js block for the wiki's two callout styles.
 * Assigned to window rather than declared globally, so it survives SPA re-runs.
 */
(function () {
    'use strict';

    var ICON = '<svg width="17" height="15" viewBox="0 0 17 15" fill="none">' +
        '<rect x="1" y="2" width="15" height="11" rx="2" stroke="currentColor" stroke-width="2"/>' +
        '<path d="M4 5.5h6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';

    class HelixCallout {
        static get toolbox() {
            return { title: 'Callout', icon: ICON };
        }

        static get isReadOnlySupported() {
            return true;
        }

        static get sanitize() {
            return {
                text: { b: {}, strong: {}, i: {}, em: {}, u: {}, s: {}, code: {}, mark: {}, br: {}, a: { href: true } },
                variant: false
            };
        }

        constructor(options) {
            var data = options.data || {};
            this.api = options.api;
            this.readOnly = !!options.readOnly;
            this.data = {
                text: data.text || '',
                variant: data.variant === 'pine' ? 'pine' : 'default'
            };
        }

        render() {
            this.wrapper = document.createElement('div');
            this.wrapper.className = 'wiki-editor-callout';

            this.field = document.createElement('div');
            this.field.className = 'wiki-editor-callout__text';
            this.field.contentEditable = this.readOnly ? 'false' : 'true';
            this.field.dataset.placeholder = 'Callout text';
            this.field.innerHTML = this.data.text;

            this.wrapper.appendChild(this.field);
            this.applyVariant();
            return this.wrapper;
        }

        /** The block's own gear menu: which of the two callout styles this is. */
        renderSettings() {
            var self = this;
            return [
                {
                    icon: ICON,
                    label: 'Note',
                    isActive: this.data.variant === 'default',
                    closeOnActivate: true,
                    onActivate: function () { self.setVariant('default'); }
                },
                {
                    icon: ICON,
                    label: 'Green',
                    isActive: this.data.variant === 'pine',
                    closeOnActivate: true,
                    onActivate: function () { self.setVariant('pine'); }
                }
            ];
        }

        setVariant(variant) {
            this.data.variant = variant;
            this.applyVariant();
        }

        applyVariant() {
            this.wrapper.classList.toggle('wiki-editor-callout--pine', this.data.variant === 'pine');
        }

        save(element) {
            var field = element.querySelector('.wiki-editor-callout__text');
            return {
                text: field ? field.innerHTML.trim() : '',
                variant: this.data.variant
            };
        }

        validate(data) {
            return !!(data.text && data.text.replace(/<br\s*\/?>/gi, '').trim());
        }
    }

    window.HelixCallout = HelixCallout;
}());
