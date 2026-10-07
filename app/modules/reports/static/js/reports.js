// Admin → Reports: Generate, History and Recipients. Re-runs on every SPA
// visit, so document listeners are wired once and read the page they find.
(function () {
    'use strict';

    function urls() { return window.REPORTS_URLS || {}; }

    function post(url, body) {
        return fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body || {})
        }).then(function (res) {
            return res.json().catch(function () { return {}; })
                .then(function (b) { return { ok: res.ok && b.success !== false, body: b }; });
        });
    }

    function toast(message, type) {
        if (window.showToast) window.showToast(message, type);
    }

    function failed(r) {
        toast((r.body && r.body.error) || 'That didn’t work. Try again.', 'error');
    }

    // ── Generate ─────────────────────────────────────────────────────────────
    function generatePage() { return document.getElementById('reports-generate'); }

    function selectedKind(page) {
        var on = page.querySelector('.reports-seg-btn.is-on');
        return on ? on.dataset.kind : 'weekly';
    }

    function form(page) {
        var kind = selectedKind(page);
        var select = page.querySelector('select[data-period-kind="' + kind + '"]');
        var reports = Array.prototype.map.call(
            page.querySelectorAll('input[name="report"]:checked'), function (i) { return i.value; });
        return { kind: kind, start: select ? select.value : '', reports: reports };
    }

    function setKind(page, kind) {
        page.querySelectorAll('.reports-seg-btn').forEach(function (b) {
            var on = b.dataset.kind === kind;
            b.classList.toggle('is-on', on);
            b.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
        page.querySelectorAll('[data-period-kind]').forEach(function (el) {
            el.hidden = el.dataset.periodKind !== kind;
        });
    }

    function busy(page, on) {
        page.querySelectorAll('[data-action]').forEach(function (b) { b.disabled = on; });
    }

    function runAction(page, action) {
        var f = form(page);
        if (!f.reports.length) { toast('Pick at least one report.', 'warning'); return; }
        if (action === 'preview') {
            var q = '?kind=' + f.kind + '&start=' + f.start + '&report=' + f.reports[0];
            window.open(urls().preview + q, '_blank', 'noopener');
            return;
        }
        busy(page, true);
        post(urls().generate, { kind: f.kind, start: f.start, reports: f.reports, send: action === 'send' })
            .then(function (r) {
                busy(page, false);
                if (!r.ok) { failed(r); return; }
                var bad = r.body.runs.filter(function (run) { return run.status === 'failed'; });
                if (bad.length) toast(bad[0].error || 'Some reports were not sent.', 'warning');
                else toast(action === 'send' ? 'Sent.' : 'Saved to History.', 'success');
                window.location.reload();
            })
            .catch(function () { busy(page, false); toast('That didn’t work. Try again.', 'error'); });
    }

    // ── Auto-send switches (Generate and Recipients) ────────────────────────
    function toggleAutoSend(input) {
        post(urls().autoSend, { report: input.dataset.report, kind: input.dataset.kind, enabled: input.checked })
            .then(function (r) { if (!r.ok) { input.checked = !input.checked; failed(r); } });
    }

    // ── Popovers: the ⋯ run menu and the Add recipient picker ───────────────
    var pop = null;

    function closePop() {
        if (!pop) return;
        if (pop.parentNode) pop.parentNode.removeChild(pop);
        pop = null;
    }

    function openPop(el, trigger) {
        closePop();
        pop = el;
        pop._trigger = trigger;
        document.body.appendChild(pop);
        if (window.PopoverPosition) window.PopoverPosition.place(pop, trigger);
    }

    function menuItem(label, onClick) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'reports-menu-item';
        b.textContent = label;
        b.addEventListener('click', function () { closePop(); onClick(); });
        return b;
    }

    function openRunMenu(trigger) {
        var menu = document.createElement('div');
        menu.className = 'reports-menu';
        menu.setAttribute('role', 'menu');
        menu.appendChild(menuItem(trigger.dataset.sendLabel, function () {
            post(trigger.dataset.send).then(function (r) {
                if (!r.ok) { failed(r); return; }
                toast('Sent.', 'success');
                window.location.reload();
            });
        }));
        menu.appendChild(menuItem('Download', function () { window.location.href = trigger.dataset.download; }));
        menu.appendChild(menuItem('Open', function () { window.open(trigger.dataset.open, '_blank', 'noopener'); }));
        openPop(menu, trigger);
        menu.querySelector('button').focus({ preventScroll: true });
    }

    function people() {
        var el = document.getElementById('reports-people');
        try { return el ? JSON.parse(el.textContent) : []; } catch (e) { return []; }
    }

    function ids(value) {
        return (value || '').split(',').filter(Boolean).map(Number);
    }

    function setRecipient(report, userId, add) {
        post(urls().recipients, { report: report, user_id: userId, add: add }).then(function (r) {
            if (!r.ok) { failed(r); return; }
            window.location.reload();
        });
    }

    function openPicker(trigger) {
        var taken = ids(trigger.dataset.taken);
        var suggest = ids(trigger.dataset.suggest);
        var all = people().filter(function (p) { return taken.indexOf(p.id) === -1; });
        var box = document.createElement('div');
        box.className = 'reports-picker';
        var input = document.createElement('input');
        input.type = 'search';
        input.className = 'reports-picker-search';
        input.placeholder = 'Find a person';
        input.setAttribute('aria-label', 'Find a person');
        var list = document.createElement('div');
        list.className = 'reports-picker-list';
        box.appendChild(input);
        box.appendChild(list);

        function row(p) {
            var b = document.createElement('button');
            b.type = 'button';
            b.className = 'reports-picker-row';
            b.innerHTML = '<span class="reports-av"></span><span class="reports-picker-name"></span><span class="reports-muted"></span>';
            b.children[0].textContent = p.initials;
            b.children[1].textContent = p.name;
            b.children[2].textContent = p.meta || '';
            b.addEventListener('click', function () { closePop(); setRecipient(trigger.dataset.report, p.id, true); });
            return b;
        }

        function group(label, items) {
            if (!items.length) return;
            var h = document.createElement('div');
            h.className = 'reports-picker-group';
            h.textContent = label;
            list.appendChild(h);
            items.forEach(function (p) { list.appendChild(row(p)); });
        }

        function render() {
            var q = input.value.trim().toLowerCase();
            var match = all.filter(function (p) { return !q || p.name.toLowerCase().indexOf(q) !== -1; });
            list.innerHTML = '';
            group('Suggested', match.filter(function (p) { return suggest.indexOf(p.id) !== -1; }));
            group('Everyone', match.filter(function (p) { return suggest.indexOf(p.id) === -1; }));
            if (!list.children.length) {
                var none = document.createElement('div');
                none.className = 'reports-picker-group';
                none.textContent = 'No matches';
                list.appendChild(none);
            }
        }

        input.addEventListener('input', render);
        render();
        openPop(box, trigger);
        input.focus({ preventScroll: true });
    }

    // ── Wiring: once per session, delegated ─────────────────────────────────
    // A popover left open by the previous visit goes with it.
    if (window._reportsWired) { window._reportsClosePop(); return; }
    window._reportsWired = true;
    window._reportsClosePop = closePop;

    document.addEventListener('click', function (e) {
        var t = e.target;
        if (pop && !pop.contains(t) && t !== pop._trigger) closePop();

        var seg = t.closest('.reports-seg-btn');
        var action = t.closest('[data-action]');
        var page = generatePage();
        if (seg && page) { setKind(page, seg.dataset.kind); return; }
        if (action && page && page.contains(action)) { runAction(page, action.dataset.action); return; }

        var dots = t.closest('[data-run-menu]');
        if (dots) { pop && pop._trigger === dots ? closePop() : openRunMenu(dots); return; }

        var remove = t.closest('[data-remove-recipient]');
        if (remove) { setRecipient(remove.dataset.report, Number(remove.dataset.user), false); return; }

        var add = t.closest('[data-add-recipient]');
        if (add) { pop && pop._trigger === add ? closePop() : openPicker(add); }
    });

    document.addEventListener('change', function (e) {
        if (e.target.matches && e.target.matches('[data-auto-send]')) toggleAutoSend(e.target);
    });

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') closePop();
    });

    document.addEventListener('scroll', function () {
        if (!pop) return;
        if (pop._trigger.isConnected && window.PopoverPosition) window.PopoverPosition.place(pop, pop._trigger);
        else closePop();
    }, true);
})();
