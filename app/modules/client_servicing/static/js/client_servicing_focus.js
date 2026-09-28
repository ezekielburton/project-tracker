/* Scrolls to the row named by ?project=<id> and flashes it. Used by the
   Table, Invoicing and Closed pages, whose rows carry data-project-id.
   Works on a full load and on SPA visits (the router re-runs this script). */
(function () {
    var id = new URLSearchParams(window.location.search).get('project');
    // Project ids are numbers; anything else would break the selector below.
    if (!id || !/^\d+$/.test(id)) return;

    var SELECTOR = 'tr[data-project-id="' + id + '"]';
    var attempts = 0;

    /* The nearest ancestor that scrolls. Scrolling that box directly is
       exact; scrollIntoView can land short while the box is still sizing. */
    function scroller(el) {
        var node = el.parentElement;
        while (node && node !== document.body) {
            var overflowY = window.getComputedStyle(node).overflowY;
            if ((overflowY === 'auto' || overflowY === 'scroll') && node.scrollHeight > node.clientHeight) {
                return node;
            }
            node = node.parentElement;
        }
        return null;
    }

    function focus(row) {
        var box = scroller(row);
        if (box) {
            // Centre vertically; leave horizontal scroll where the user put it.
            var top = row.offsetTop - box.offsetTop - (box.clientHeight / 2) + (row.offsetHeight / 2);
            box.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
        } else {
            row.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'smooth' });
        }
        row.classList.add('cs-focus-flash');
        setTimeout(function () { row.classList.remove('cs-focus-flash'); }, 2400);
    }

    /* The row or its box may not be ready yet, so retry for about a second,
       then give up quietly (the project may not be on this page). */
    function attempt() {
        var row = document.querySelector(SELECTOR);
        if (row) {
            requestAnimationFrame(function () { focus(row); });
            return;
        }
        if (++attempts < 12) { setTimeout(attempt, 100); }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', attempt);
    } else {
        attempt();
    }
})();
