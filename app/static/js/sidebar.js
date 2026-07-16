/* sidebar.js — Vitamin-E v1.3
   All sidebar behaviour: expand/collapse, pin, active state,
   click tracking, and SPA navigation for internal links.
   Loaded in base.html after main.js. No external dependencies. */

(function () {
    'use strict';

    /* ── 1. Elements ──────────────────────────────────────────────────
       Grab every DOM node we'll need. If #sidebar doesn't exist
       (unauthenticated pages), bail out immediately — nothing to do. */
    var sidebar     = document.getElementById('sidebar');
    var expandTab   = document.getElementById('sidebar-expand-tab');
    var toggleBtn   = document.getElementById('sidebar-toggle-btn');
    var pinBtn      = document.getElementById('sidebar-pin-btn');
    var mainContent = document.getElementById('main-content');

    if (!sidebar) return;

    /* ── 2. localStorage key ─────────────────────────────────────────
       We persist the pinned state across page loads so the user's
       preference is remembered between sessions. */
    var PINNED_KEY = 'helix_sidebar_pinned';

    /* ── 3. State helpers ────────────────────────────────────────────
       Two tiny functions so we're never checking classList directly
       throughout the code — easier to read and change later. */
    function isPinned()   { return sidebar.classList.contains('sidebar--pinned'); }
    function isExpanded() { return sidebar.classList.contains('sidebar--expanded'); }

    /* ── 4. Expand / Collapse / Pin ──────────────────────────────────
       expand() and collapse() toggle the --expanded class.
       setPin() handles the --pinned class and saves to localStorage.
       Pinned and expanded are mutually exclusive class names:
       expanded = temporary open; pinned = permanently open. */
    function expand() {
        sidebar.classList.add('sidebar--expanded');
    }

    function collapse() {
        sidebar.classList.remove('sidebar--expanded');
    }

    function setPin(shouldPin) {
        sidebar.classList.toggle('sidebar--pinned', shouldPin);
        sidebar.classList.remove('sidebar--expanded');
        localStorage.setItem(PINNED_KEY, shouldPin ? '1' : '0');
        pinBtn.title = shouldPin ? 'Unpin sidebar' : 'Pin sidebar';
    }

    /* ── 5. Restore pin state on page load ───────────────────────────
       On every page load, check if the user had the sidebar pinned.
       If yes, immediately add --pinned so there's no flash of the
       minimized state before JS runs. */
    if (localStorage.getItem(PINNED_KEY) === '1') {
        sidebar.classList.add('sidebar--pinned');
    }

    /* ── 6. Click listeners ──────────────────────────────────────────
       e.stopPropagation() on buttons prevents the click from also
       bubbling up to the sidebar body or document listeners below. */

    // The tab sticking out from the right edge → expand
    expandTab.addEventListener('click', function (e) {
        e.stopPropagation();
        expand();
    });

    // Chevron toggle button (visible when expanded) → collapse or unpin
    toggleBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        if (isPinned()) {
            setPin(false); // unpin also collapses (CSS handles the transition)
        } else {
            collapse();
        }
    });

    // Pin button → toggle pin state
    pinBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        setPin(!isPinned());
    });

    // Clicking a non-nav area of the sidebar when minimized → expand.
    // Nav link clicks (icons included) navigate directly without expanding first.
    sidebar.addEventListener('click', function (e) {
        if (isExpanded() || isPinned()) return;
        // If the click target is inside a nav or external link, let it navigate — don't expand.
        if (e.target.closest('.sidebar-item--nav, .sidebar-item--external')) return;
        expand();
    });

    // Click anywhere outside the sidebar → collapse (unless pinned)
    document.addEventListener('click', function (e) {
        if (isPinned()) return;
        if (!sidebar.contains(e.target) && e.target !== expandTab) {
            collapse();
        }
    });

    /* ── 7. Active item highlighting ─────────────────────────────────
       On every page load (and after SPA navigation), mark the sidebar
       item whose href matches the current URL path as active.
       We use startsWith so /projects/123 still highlights /projects. */
    function setActiveItem(path) {
        document.querySelectorAll('.sidebar-item--active').forEach(function (el) {
            el.classList.remove('sidebar-item--active');
        });
        document.querySelectorAll('.sidebar-item--nav').forEach(function (item) {
            var href = item.getAttribute('href');
            if (href && path.startsWith(href)) {
                item.classList.add('sidebar-item--active');
            }
        });
    }

    setActiveItem(window.location.pathname);

    /* ── 8. Click tracking ───────────────────────────────────────────
       Fire-and-forget POST to /sidebar/track for every sidebar item
       click. We catch errors silently — analytics should never break
       the UI. The catch(() => {}) swallows network failures. */
    function trackClick(linkName) {
        fetch('/sidebar/track', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ link_name: linkName })
        }).catch(function () {});
    }

    document.querySelectorAll('.sidebar-item[data-link]').forEach(function (item) {
        item.addEventListener('click', function () {
            var linkName = this.getAttribute('data-link');
            if (linkName) trackClick(linkName);
        });
    });

    /* ── 9. SPA navigation ───────────────────────────────────────────
       Internal nav links (class sidebar-item--nav) are intercepted.
       Instead of a full page reload we:
         1. Fetch the URL with the X-Nav-Request header
         2. Flask sees that header and returns only the content block
            (via base_fragment.html) — no full HTML shell
         3. Fade out → swap innerHTML → fade back in
         4. Push the new URL into the browser history bar
       If the fetch fails for any reason we fall back to a normal
       page load so navigation never breaks. */

    function execScripts(container) {
        container.querySelectorAll('script').forEach(function(old) {
            var fresh = document.createElement('script');
            if (old.src) {
                // External script — set src so the browser loads and runs the file
                fresh.src = old.src;
            } else {
                // Inline script — copy the code directly
                fresh.textContent = old.textContent;
            }
            old.parentNode.replaceChild(fresh, old);
        });
    }

    function navigateTo(url, push) {
        fetch(url, {
            headers: { 'X-Nav-Request': '1' }
        })
        .then(function (r) {
            if (!r.ok) throw new Error('nav-failed');
            // Capture the title header before consuming the body
            var pageTitle = r.headers.get('X-Page-Title');
            return r.text().then(function (html) {
                return { html: html, title: pageTitle };
            });
        })
        .then(function (result) {
            mainContent.style.opacity = '0';
            setTimeout(function () {
                mainContent.innerHTML = result.html;
                execScripts(mainContent);
                if (result.title) {
                    // decodeURIComponent undoes the quote() percent-encoding added in __init__.py.
                    // The textarea trick decodes HTML entities (&amp; → &, etc.) because
                    // document.title expects plain text, not HTML — without this, project names
                    // containing & show as &amp; in the browser tab.
                    var _ta = document.createElement('textarea');
                    _ta.innerHTML = decodeURIComponent(result.title);
                    document.title = _ta.value;
                }
                if (push !== false) { history.pushState(null, '', url); }
                document.dispatchEvent(new CustomEvent('helix:navigated'));
                mainContent.style.opacity = '1';
                setActiveItem(url);
            }, 150); // matches the 0.15s CSS transition on .main-content
        })
        .catch(function () {
            window.location.href = url; // graceful fallback
        });
    }

    window.navigateTo = navigateTo;

    document.addEventListener('click', function (e) {
        var item = e.target.closest('.sidebar-item--nav');
        if (!item) return;
        e.preventDefault();
        e.stopPropagation();
        var url = item.getAttribute('href');
        if (url) navigateTo(url);
    });

    // Keep SPA working when the user hits Back/Forward in the browser
    window.addEventListener('popstate', function () {
        navigateTo(window.location.pathname, false);
    });

})();
