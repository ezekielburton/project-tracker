/* Accounts page: fold groups, search the loaded rows, and save the open
   groups per Group by to the server. Runs inline on every SPA visit; every
   listener sits on the page's own elements. */
(function () {
    var TEMPLATE_CONTRACT = {
        'ids': {
            'list': 'cs-acc-list',
            'search': 'cs-acc-search',
            'count': 'cs-acc-count',
            'body': 'cs-acc-body',
            'expandAll': 'cs-acc-expand-all',
            'collapseAll': 'cs-acc-collapse-all'
        },
        'classes': {
            'group': 'cs-acc-group',
            'toggle': 'cs-acc-toggle',
            'row': 'cs-acc-row',
            'scrollBox': 'cs-acc-scrollbox'
        },
        'attributes': {
            'group': 'data-group',
            'state': 'data-state',
            'saveUrl': 'data-save-url',
            'groupKey': 'data-key'
        }
    };
    var ids = TEMPLATE_CONTRACT.ids;
    var cls = TEMPLATE_CONTRACT.classes;
    var attrs = TEMPLATE_CONTRACT.attributes;

    var list = document.getElementById(ids.list);
    if (!list) return;

    // The list panel fills to the footer and scrolls inside.
    if (window.watchFillHeight) {
        window.watchFillHeight('#' + ids.body, '--fill-height');
    }

    // ── Page scroll ───────────────────────────────────────────────────
    // A box holds the wheel only while its content overflows it. Watching
    // the box and its table catches folds, searches and window resizes.
    var scrollBoxes = Array.prototype.slice.call(document.querySelectorAll('.' + cls.scrollBox));

    function markScrollable() {
        scrollBoxes.forEach(function (box) {
            box.classList.toggle('is-scrollable', box.scrollHeight > box.clientHeight + 1);
        });
    }

    if (window.ResizeObserver) {
        var sizeWatch = new ResizeObserver(markScrollable);
        scrollBoxes.forEach(function (box) {
            sizeWatch.observe(box);
            if (box.firstElementChild) sizeWatch.observe(box.firstElementChild);
        });
    }
    markScrollable();

    var search = document.getElementById(ids.search);
    var count = document.getElementById(ids.count);
    var groups = Array.prototype.slice.call(list.querySelectorAll('.' + cls.group));

    // ── Saved view ────────────────────────────────────────────────────
    // state = {group, open: {client: [keys], lead: [keys]}}. Groups hidden
    // by a filter keep their saved state; only what changes is written.
    var view = list.getAttribute(attrs.group);
    var saveUrl = list.getAttribute(attrs.saveUrl);
    var state = null;
    try { state = JSON.parse(list.getAttribute(attrs.state)); } catch (e) { state = null; }
    var saveTimer = null;

    function save() {
        if (!state || !saveUrl) return;
        window.clearTimeout(saveTimer);
        var body = JSON.stringify(state);
        // Batches quick clicks; keepalive lets it finish if the user navigates away.
        saveTimer = window.setTimeout(function () {
            fetch(saveUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: body,
                keepalive: true
            }).catch(function () {
                // Best effort; the next change saves again.
            });
        }, 400);
    }

    function remember(key, open) {
        if (!state) return;
        var keys = state.open[view] || [];
        var at = keys.indexOf(key);
        if (open && at === -1) keys.push(key);
        if (!open && at !== -1) keys.splice(at, 1);
        state.open[view] = keys;
    }

    function setOpen(group, open) {
        group.classList.toggle('is-collapsed', !open);
        var btn = group.querySelector('.' + cls.toggle);
        if (btn) btn.setAttribute('aria-expanded', open ? 'true' : 'false');
        remember(group.getAttribute(attrs.groupKey), open);
    }

    // Opened from a Group by link: remember it as the last view.
    if (state && state.group !== view) {
        state.group = view;
        save();
    }

    // ── Collapse ──────────────────────────────────────────────────────
    list.addEventListener('click', function (e) {
        var btn = e.target.closest ? e.target.closest('.' + cls.toggle) : null;
        if (!btn) return;
        var group = btn.closest('.' + cls.group);
        setOpen(group, group.classList.contains('is-collapsed'));
        save();
    });

    function setAll(open) {
        groups.forEach(function (group) { setOpen(group, open); });
        save();
    }

    var expandAll = document.getElementById(ids.expandAll);
    var collapseAll = document.getElementById(ids.collapseAll);
    if (expandAll) expandAll.addEventListener('click', function () { setAll(true); });
    if (collapseAll) collapseAll.addEventListener('click', function () { setAll(false); });

    // ── Search ────────────────────────────────────────────────────────
    // Matches show even inside a folded group; a group with none hides.
    function applySearch() {
        var term = (search.value || '').trim().toLowerCase();
        var shown = 0;
        list.classList.toggle('is-searching', term !== '');
        groups.forEach(function (group) {
            var visible = 0;
            Array.prototype.forEach.call(group.querySelectorAll('.' + cls.row), function (tr) {
                var hit = !term || (tr.getAttribute('data-search') || '').indexOf(term) !== -1;
                tr.hidden = !hit;
                if (hit) visible += 1;
            });
            group.hidden = visible === 0;
            shown += visible;
        });
        if (count) count.textContent = shown + ' job' + (shown === 1 ? '' : 's');
    }

    if (search) search.addEventListener('input', applySearch);
})();
