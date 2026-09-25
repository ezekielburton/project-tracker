// Global trays — the dock launchers, the shared panel shell, and the
// unread-bubble hook B2/B3 feed. Lives outside #main-content, so this binds
// once per session and SPA page swaps never touch it.
(function () {
    var STORAGE_KEY = 'helix.openTray';

    var dock = document.getElementById('tray-dock');
    var panel = document.getElementById('tray-panel');
    if (!dock || !panel) return;

    var titleEl = document.getElementById('tray-panel-title');
    var actionsEl = document.getElementById('tray-panel-actions');
    var bodyEl = document.getElementById('tray-panel-body');
    var closeBtn = document.getElementById('tray-panel-close');

    var launchers = {};
    dock.querySelectorAll('.tray-launcher').forEach(function (btn) {
        launchers[btn.dataset.tray] = btn;
    });

    // ── Reveal / collapse ────────────────────────────────
    // The dock is a tab at the edge; the launchers slide out on hover and go
    // back 5s after you leave, unless something is holding them out.
    var REVEAL_HOLD_MS = 5000;
    var tab = document.getElementById('tray-dock-tab');
    var tabBubble = document.getElementById('tray-dock-bubble');
    var unreadCounts = {};
    var collapseTimer = null;
    var pinned = false;

    // An open tray, or a click on the tab, holds the launchers out.
    function isHeldOut() { return pinned || openTray !== null; }

    function clearCollapse() {
        if (collapseTimer) {
            clearTimeout(collapseTimer);
            collapseTimer = null;
        }
    }

    function reveal() {
        clearCollapse();
        dock.classList.add('is-revealed');
        if (tab) tab.setAttribute('aria-expanded', 'true');
    }

    function collapse() {
        clearCollapse();
        if (isHeldOut()) return;
        dock.classList.remove('is-revealed');
        if (tab) tab.setAttribute('aria-expanded', 'false');
    }

    function scheduleCollapse() {
        clearCollapse();
        if (isHeldOut()) return;
        collapseTimer = setTimeout(collapse, REVEAL_HOLD_MS);
    }

    // The tab shows what all the trays add up to, so a shut dock still says
    // something is waiting. New arrivals never slide it open on their own.
    function paintTabBubble() {
        if (!tabBubble) return;
        var total = 0;
        Object.keys(unreadCounts).forEach(function (key) { total += unreadCounts[key]; });
        tabBubble.textContent = total > 99 ? '99+' : String(total);
        tabBubble.hidden = total <= 0;
    }

    dock.addEventListener('mouseenter', reveal);
    dock.addEventListener('mouseleave', scheduleCollapse);
    // Keyboard focus counts as hover, so the dock is still reachable by tabbing.
    dock.addEventListener('focusin', reveal);
    dock.addEventListener('focusout', function (e) {
        if (!dock.contains(e.relatedTarget)) scheduleCollapse();
    });

    if (tab) {
        tab.addEventListener('click', function () {
            // The tap path — touch has no hover, so the tab toggles and holds.
            pinned = !(pinned && dock.classList.contains('is-revealed'));
            if (pinned) reveal();
            else collapse();
        });
    }

    var openTray = null;
    // name -> { onOpen, onClose, onSignal } — filled by each tray's own script.
    var registry = {};

    function remember(name) {
        try {
            if (name) localStorage.setItem(STORAGE_KEY, name);
            else localStorage.removeItem(STORAGE_KEY);
        } catch (e) {
            // Private mode or blocked storage — the dock still works, it just forgets.
        }
    }

    function close() {
        if (!openTray) return;
        var previous = openTray;
        openTray = null;
        panel.classList.add('hidden');
        panel.setAttribute('aria-hidden', 'true');
        launchers[previous].classList.remove('is-open');
        launchers[previous].setAttribute('aria-expanded', 'false');
        remember(null);
        var entry = registry[previous];
        if (entry && entry.onClose) entry.onClose(bodyEl, actionsEl);
        // Nothing holding it out any more — start the 5s countdown.
        scheduleCollapse();
    }

    function open(name) {
        var btn = launchers[name];
        if (!btn) return;
        if (openTray === name) { close(); return; }
        if (openTray) close();

        openTray = name;
        // The launcher's own icon doubles as the panel's, so there is one copy of it.
        var icon = btn.querySelector('svg');
        titleEl.innerHTML = '';
        if (icon) titleEl.appendChild(icon.cloneNode(true));
        titleEl.appendChild(document.createTextNode(btn.dataset.title || name));

        // The shell hands each tray a clean body and header slot on every open.
        actionsEl.innerHTML = '';
        bodyEl.innerHTML = '';

        panel.classList.remove('hidden');
        panel.setAttribute('aria-hidden', 'false');
        btn.classList.add('is-open');
        btn.setAttribute('aria-expanded', 'true');
        reveal();
        remember(name);

        var entry = registry[name];
        if (entry && entry.onOpen) entry.onOpen(bodyEl, actionsEl);
    }

    // The public hook B2/B3 use. 0 or less hides the bubble entirely.
    function setUnread(name, count) {
        var btn = launchers[name];
        if (!btn) return;
        var n = parseInt(count, 10) || 0;
        unreadCounts[name] = n;
        var bubble = btn.querySelector('.tray-launcher__bubble');
        if (bubble) {
            bubble.textContent = n > 99 ? '99+' : String(n);
            bubble.hidden = n <= 0;
        }
        paintTabBubble();
    }

    function register(name, options) {
        registry[name] = options || {};
        // A tray restored on page load can register after the shell already
        // reopened it — give it its turn rather than leaving the panel empty.
        if (openTray === name && registry[name].onOpen) {
            registry[name].onOpen(bodyEl, actionsEl);
        }
    }

    Object.keys(launchers).forEach(function (name) {
        launchers[name].addEventListener('click', function () { open(name); });
    });
    closeBtn.addEventListener('click', close);

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && openTray) close();
    });

    // The per-user live stream notifications.js already holds. Each tray
    // refetches its own count from here; B1 ships no counts of its own.
    document.addEventListener('helix:user-stream', function () {
        Object.keys(registry).forEach(function (name) {
            var entry = registry[name];
            if (entry && entry.onSignal) entry.onSignal();
        });
    });

    window.HelixTrays = {
        open: open,
        close: close,
        setUnread: setUnread,
        register: register,
        isOpen: function (name) { return name ? openTray === name : openTray !== null; },
        body: function () { return bodyEl; }
    };

    // Keep the dock clear of the page footer as it scrolls into view. Drives
    // one variable the panel and both toast stacks follow.
    var footer = document.querySelector('.footer');
    var BASE_OFFSET = 20;
    var offsetQueued = false;

    function applyDockOffset() {
        offsetQueued = false;
        var offset = BASE_OFFSET;
        if (footer) {
            var visible = window.innerHeight - footer.getBoundingClientRect().top;
            if (visible > 0) offset = BASE_OFFSET + visible;
        }
        document.documentElement.style.setProperty('--tray-dock-bottom', offset + 'px');
    }

    function queueDockOffset() {
        if (offsetQueued) return;
        offsetQueued = true;
        window.requestAnimationFrame(applyDockOffset);
    }

    window.addEventListener('scroll', queueDockOffset, { passive: true });
    window.addEventListener('resize', queueDockOffset);
    // Page swaps change the document height without a scroll event.
    if (typeof ResizeObserver !== 'undefined') {
        new ResizeObserver(queueDockOffset).observe(document.body);
    }
    applyDockOffset();

    // Reopen whatever was open before a full page load.
    try {
        var saved = localStorage.getItem(STORAGE_KEY);
        if (saved && launchers[saved]) open(saved);
    } catch (e) {
        // Storage unavailable — start closed.
    }
})();
