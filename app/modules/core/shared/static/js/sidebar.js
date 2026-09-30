/* sidebar.js — sidebar expand/collapse/pin, active item, click tracking,
   the header theme toggle, and the SPA router (navigateTo).
   Loaded in base.html after main.js. */

(function () {
    'use strict';

    /* ── 1. Elements ──────────────────────────────────────────────────
       Logged-out pages have no #sidebar; only the theme toggle runs there. */
    var sidebar     = document.getElementById('sidebar');
    var expandTab   = document.getElementById('sidebar-expand-tab');
    var pinBtn      = document.getElementById('sidebar-pin-btn');
    var mainContent = document.getElementById('main-content');
    var loadingBar = document.getElementById('header-loading-bar');
    var pageNameEl = document.getElementById('app-header-page-name');
    var themeToggle = document.getElementById('dark-mode-toggle');

    /* Theme toggle. Must stay above the `if (!sidebar) return` below so it
       also works on logged-out pages (login/register).
       helixSetThemeStub is also called by Settings > Appearance; it repaints
       every .theme-toggle on the page, saves to localStorage (no-flash
       reload) and POSTs to the account (401s harmlessly when logged out). */
    window.helixSetThemeStub = function (isDark) {
        var theme = isDark ? 'dark' : 'light';
        document.documentElement.setAttribute('data-theme', theme);
        document.querySelectorAll('.theme-toggle').forEach(function (btn) {
            btn.classList.toggle('theme-toggle--light', !isDark);
            btn.classList.toggle('theme-toggle--dark', isDark);
        });
        try { localStorage.setItem('helix-theme', theme); } catch (e) {}
        fetch('/account/theme-prefs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ theme: theme })
        }).catch(function () {});
    };

    // Paint the toggles to match the data-theme already on <html>.
    // A repaint only: no localStorage write, no POST.
    (function () {
        var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        document.querySelectorAll('.theme-toggle').forEach(function (btn) {
            btn.classList.toggle('theme-toggle--light', !isDark);
            btn.classList.toggle('theme-toggle--dark', isDark);
        });
    })();

    if (themeToggle) {
        themeToggle.addEventListener('click', function () {
            window.helixSetThemeStub(!themeToggle.classList.contains('theme-toggle--dark'));
        });
    }

    if (!sidebar) return;

    /* ── 2. localStorage key ─────────────────────────────────────────
       Pinned state persists across page loads. */
    var PINNED_KEY = 'helix_sidebar_pinned';

    /* ── 3. State helpers ──────────────────────────────────────────── */
    function isPinned()   { return sidebar.classList.contains('sidebar--pinned'); }
    function isExpanded() { return sidebar.classList.contains('sidebar--expanded'); }

    /* ── 4. Expand / Collapse / Pin ──────────────────────────────────
       --expanded is a temporary open; --pinned stays open. They are
       never set together. */
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

    /* ── 5. Restore pin state on page load ─────────────────────────── */
    if (localStorage.getItem(PINNED_KEY) === '1') {
        sidebar.classList.add('sidebar--pinned');
    }

    /* ── 6. Click listeners ──────────────────────────────────────────
       Buttons stop propagation so the sidebar-body and document
       listeners below don't also react. */

    expandTab.addEventListener('click', function (e) {
        e.stopPropagation();
        expand();
    });

    pinBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        setPin(!isPinned());
    });

    // A click on a collapsed sidebar expands it, unless it hit a link,
    // which navigates straight away.
    sidebar.addEventListener('click', function (e) {
        if (isExpanded() || isPinned()) return;
        if (e.target.closest('.sidebar-item--nav, .sidebar-item--external')) return;
        expand();
    });

    // Any click outside an unpinned sidebar collapses it.
    document.addEventListener('click', function (e) {
        if (isPinned()) return;
        if (!sidebar.contains(e.target) && e.target !== expandTab) {
            collapse();
        }
    });

    /* ── 7. Active item highlighting ─────────────────────────────────
       Prefix match, so /projects/123 still highlights /projects. */
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
       Fire-and-forget POST to /sidebar/track; failures are ignored. */
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
       Links with .sidebar-item--nav are intercepted:
         1. Fetch the URL with the X-Nav-Request header.
         2. The server (app/__init__.py) strips the response to the
            inside of #main-content plus the page's extra_js block.
         3. Fade out, swap innerHTML, re-run its scripts, fade in.
         4. Push the URL and fire helix:navigated.
       Any failure falls back to a normal page load. */

    // Scripts set via innerHTML never run; replace each with a fresh copy.
    // One at a time in document order, as on a full load: an external
    // script finishes loading before the next one (often inline code that
    // uses it) runs. The chain stops if a newer swap removed the content.
    function execScripts(container) {
        var scripts = Array.prototype.slice.call(container.querySelectorAll('script'));
        (function next() {
            var old = scripts.shift();
            if (!old || !old.isConnected) return;
            var fresh = document.createElement('script');
            if (old.src) {
                fresh.src = old.src;
                fresh.onload = fresh.onerror = next;
                old.parentNode.replaceChild(fresh, old);
            } else {
                fresh.textContent = old.textContent;
                old.parentNode.replaceChild(fresh, old);
                next();
            }
        })();
    }
    /* One navigation at a time: a new one aborts the previous fetch, so
       quick clicks can't pile up against the browser's connection limit. */
    var _navToken = 0;
    var _navAbort = null;
    var _navSafetyTimer = null;

    function navigateTo(url, push) {
        var myToken = ++_navToken;

        // Cancel the previous navigation's fetch so quick clicks don't stack.
        if (_navAbort) { _navAbort.abort(); }
        _navAbort = (typeof AbortController !== 'undefined') ? new AbortController() : null;

        startLoadingBar();

        // Backstop: never let the bar hang forever, whatever goes wrong.
        if (_navSafetyTimer) { clearTimeout(_navSafetyTimer); }
        _navSafetyTimer = setTimeout(function () {
            if (myToken === _navToken) { finishLoadingBar(); }
        }, 8000);

        fetch(url, {
            headers: { 'X-Nav-Request': '1' },
            signal: _navAbort ? _navAbort.signal : undefined
        })
            .then(function (r) {
                if (!r.ok) throw new Error('nav-failed');
                var pageTitle = r.headers.get('X-Page-Title');
                return r.text().then(function (html) {
                    return { html: html, title: pageTitle };
                });
            })
            .then(function (result) {
                // A newer navigation started while we were fetching — drop this one.
                if (myToken !== _navToken) return;
                mainContent.style.opacity = '0';
                setTimeout(function () {
                    // Re-check: a newer nav may have started during the fade.
                    if (myToken !== _navToken) return;
                    mainContent.innerHTML = result.html;
                    execScripts(mainContent);
                    if (result.title) {
                        var _ta = document.createElement('textarea');
                        _ta.innerHTML = decodeURIComponent(result.title);
                        document.title = _ta.value;
                        setHeaderPageName(_ta.value);
                    }
                    markEntry(push !== false, url);
                    document.dispatchEvent(new CustomEvent('helix:navigated'));
                    mainContent.style.opacity = '1';
                    setActiveItem(url);
                    if (_navSafetyTimer) { clearTimeout(_navSafetyTimer); }
                    finishLoadingBar();
                }, 150);
            })
            .catch(function (err) {
                // A superseded nav stays silent; only a failure of the
                // current one falls back to a full reload.
                if ((err && err.name === 'AbortError') || myToken !== _navToken) return;
                if (_navSafetyTimer) { clearTimeout(_navSafetyTimer); }
                finishLoadingBar();
                window.location.href = url;
            });
    }

    window.navigateTo = navigateTo;
    window.helixExecScripts = execScripts; // used by settings-overlay.js

    document.addEventListener('click', function (e) {
        var item = e.target.closest('.sidebar-item--nav');
        if (!item) return;
        // Modified and non-left clicks keep the browser's new tab/window behaviour.
        if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        e.preventDefault();
        e.stopPropagation();
        var url = item.getAttribute('href');
        if (url) navigateTo(url);
    });

    /* Each render tags its history entry with a key (state.helixNav), so
       Back/Forward can tell the router's entries from ones a page pushed
       itself (project_list.js's overlay and filter states). */
    var _docKey = Date.now().toString(36);
    var _renderSeq = 0;
    var _renderKey = null;
    var _renderedPath = window.location.pathname;

    function markEntry(push, url) {
        _renderKey = _docKey + '-' + (++_renderSeq);
        if (push) {
            history.pushState({ helixNav: _renderKey }, '', url);
        } else {
            var s = history.state;
            history.replaceState(Object.assign({}, (s && typeof s === 'object') ? s : null, { helixNav: _renderKey }), '');
        }
        _renderedPath = window.location.pathname;
    }

    markEntry(false);

    // Back/Forward. The page on screen re-syncs its own entries (this
    // render's, or a same-path one it pushed); anything else loads the
    // entry's full URL, query and hash included.
    window.addEventListener('popstate', function (e) {
        var s = e.state;
        if (s && s.helixNav === _renderKey) return;
        if (s && typeof s === 'object' && !s.helixNav && window.location.pathname === _renderedPath) return;
        navigateTo(window.location.pathname + window.location.search + window.location.hash, false);
    });

    /* ── 10. Header: loading bar and page name ─────────────────────────
   Both live outside #main-content, so they survive SPA swaps. */

    function startLoadingBar() {
        if (!loadingBar) return;
        loadingBar.style.transition = 'none';
        loadingBar.style.width = '0%';
        loadingBar.style.opacity = '1';
        loadingBar.offsetHeight; // force reflow so the reset to 0% applies before animating
        loadingBar.style.transition = '';
        loadingBar.style.width = '80%';
    }

    function finishLoadingBar() {
        if (!loadingBar) return;
        loadingBar.style.width = '100%';
        setTimeout(function () { loadingBar.style.opacity = '0'; }, 150);
    }

    function setHeaderPageName(title) {
        if (pageNameEl && title) pageNameEl.textContent = title;
    }

    // Full page load: mirror the server-rendered <title>. SPA nav sets it in navigateTo.
    setHeaderPageName(document.title);

})();
