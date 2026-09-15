/**
 * Drag-to-reorder for Editor.js blocks.
 * Editor.js ships a settings button but no block dragging; this makes that
 * button a handle and reorders with the editor's own blocks.move().
 * Listens in the capture phase, because Editor.js consumes drop events first.
 */
(function () {
    'use strict';

    var DRAG_TYPE = 'application/x-helix-block';
    var HANDLE = '.ce-toolbar__settings-btn';
    var ABOVE = 'ce-block--helix-drop-above';
    var BELOW = 'ce-block--helix-drop-below';
    var DRAGGING = 'wiki-editor--dragging';

    /** Dragging over contenteditable text leaves a highlight behind. */
    function clearSelection() {
        var selection = window.getSelection();
        if (selection && selection.removeAllRanges) { selection.removeAllRanges(); }
    }

    function BlockDrag(editor, holder) {
        this.editor = editor;
        this.holder = holder;
        this.fromIndex = null;
        this.marked = null;

        this.onPointer = this.armHandle.bind(this);
        this.onDragStart = this.dragStart.bind(this);
        this.onDragOver = this.dragOver.bind(this);
        this.onDrop = this.drop.bind(this);
        this.onDragEnd = this.clear.bind(this);

        this.holder.addEventListener('mouseover', this.onPointer);
        this.holder.addEventListener('dragstart', this.onDragStart, true);
        document.addEventListener('dragover', this.onDragOver, true);
        document.addEventListener('drop', this.onDrop, true);
        document.addEventListener('dragend', this.onDragEnd, true);
    }

    BlockDrag.prototype.destroy = function () {
        this.holder.removeEventListener('mouseover', this.onPointer);
        this.holder.removeEventListener('dragstart', this.onDragStart, true);
        document.removeEventListener('dragover', this.onDragOver, true);
        document.removeEventListener('drop', this.onDrop, true);
        document.removeEventListener('dragend', this.onDragEnd, true);
        this.clear();
    };

    /** The toolbar is built on hover, so the handle is marked draggable then. */
    BlockDrag.prototype.armHandle = function () {
        var handle = this.holder.querySelector(HANDLE);
        if (handle && handle.getAttribute('draggable') !== 'true') {
            handle.setAttribute('draggable', 'true');
        }
    };

    BlockDrag.prototype.blocks = function () {
        return Array.prototype.slice.call(this.holder.querySelectorAll('.ce-block'));
    };

    BlockDrag.prototype.blockUnder = function (node) {
        return node && node.closest ? node.closest('.ce-block') : null;
    };

    BlockDrag.prototype.dragStart = function (event) {
        if (!event.target.closest || !event.target.closest(HANDLE)) { return; }
        this.fromIndex = this.editor.blocks.getCurrentBlockIndex();
        if (this.fromIndex < 0) { this.fromIndex = null; return; }
        // A drag with no data is treated as invalid; a private type keeps
        // Editor.js from pasting it back in as content.
        event.dataTransfer.setData(DRAG_TYPE, String(this.fromIndex));
        event.dataTransfer.effectAllowed = 'move';

        this.holder.classList.add(DRAGGING);
        // Deferred so nothing touches the drag while the browser is starting it.
        window.setTimeout(this.closeSettings.bind(this), 0);
    };

    BlockDrag.prototype.closeSettings = function () {
        var toolbar = this.editor.toolbar;
        if (toolbar && typeof toolbar.toggleBlockSettings === 'function') {
            try { toolbar.toggleBlockSettings(false); } catch (error) { /* optional API */ }
        }
    };

    BlockDrag.prototype.dragOver = function (event) {
        if (this.fromIndex === null) { return; }
        var block = this.blockUnder(event.target);
        if (!block || !this.holder.contains(block)) { this.unmark(); return; }

        event.preventDefault();
        event.stopPropagation();
        event.dataTransfer.dropEffect = 'move';
        this.mark(block);
    };

    BlockDrag.prototype.drop = function (event) {
        if (this.fromIndex === null) { return; }
        event.preventDefault();
        event.stopPropagation();

        var block = this.blockUnder(event.target);
        var toIndex = block ? this.blocks().indexOf(block) : -1;
        var fromIndex = this.fromIndex;

        this.clear();
        if (toIndex >= 0 && toIndex !== fromIndex) {
            this.editor.blocks.move(toIndex, fromIndex);
        }
    };

    BlockDrag.prototype.mark = function (block) {
        if (this.marked === block) { return; }
        this.unmark();
        var toIndex = this.blocks().indexOf(block);
        block.classList.add(toIndex < this.fromIndex ? ABOVE : BELOW);
        this.marked = block;
    };

    BlockDrag.prototype.unmark = function () {
        if (this.marked) {
            this.marked.classList.remove(ABOVE, BELOW);
            this.marked = null;
        }
    };

    BlockDrag.prototype.clear = function () {
        this.unmark();
        this.holder.classList.remove(DRAGGING);
        if (this.fromIndex !== null) { clearSelection(); }
        this.fromIndex = null;
    };

    window.HelixBlockDrag = {
        attach: function (editor, holder) { return new BlockDrag(editor, holder); }
    };
}());
