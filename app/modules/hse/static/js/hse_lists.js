// HSE — the officer's own lists.
//
// Adds, renames and deactivates. Every change re-renders the tab from the
// server rather than patching the DOM: the counts and the ordering both
// move, and a half-updated list is worse than a short reload.
//
// IIFE with no DOMContentLoaded gate — page scripts re-run on every SPA
// swap and that event never fires again (spa-navigation.md, trap 1).
(function () {
    function endpointFor(section) {
        var kind = section.getAttribute('data-kind');
        if (kind === 'people') return '/hse/lists/people';
        if (kind === 'assets') return '/hse/lists/assets';
        return '/hse/lists/reference';
    }

    function note(section, text) {
        var slot = section.querySelector('.hse-list-note');
        if (slot) slot.textContent = text || '';
    }

    function refresh() {
        var url = window.location.pathname + window.location.search;
        if (window.navigateTo) {
            window.navigateTo(url);
        } else {
            window.location.reload();
        }
    }

    function send(url, method, body) {
        return fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        }).then(function (res) {
            return res.json().then(function (b) { return { ok: res.ok, body: b }; });
        });
    }

    function payloadFor(section) {
        var kind = section.getAttribute('data-kind');
        var name = section.querySelector('.hse-add-name');
        var value = name ? name.value.trim() : '';
        if (!value) return null;

        if (kind === 'people') {
            return {
                name: value,
                role: (section.querySelector('.hse-add-role') || {}).value || '',
                organisation: (section.querySelector('.hse-add-org') || {}).value || '',
                can_hold_actions: Boolean((section.querySelector('.hse-add-holds') || {}).checked)
            };
        }
        if (kind === 'assets') {
            return {
                kind: section.getAttribute('data-asset-kind'),
                label: value,
                ref: (section.querySelector('.hse-add-ref') || {}).value || ''
            };
        }
        return { kind: kind, label: value };
    }

    function add(section) {
        var payload = payloadFor(section);
        if (!payload) {
            note(section, 'Type a name first.');
            return;
        }
        note(section, 'Saving…');
        send(endpointFor(section), 'POST', payload).then(function (result) {
            if (!result.ok) {
                note(section, result.body.error || 'Could not add that.');
                return;
            }
            refresh();
        }).catch(function () {
            note(section, 'Could not reach the server.');
        });
    }

    function toggle(section, button) {
        var turningOn = button.getAttribute('data-active') === 'no';
        note(section, turningOn ? 'Reactivating…' : 'Deactivating…');
        send(endpointFor(section) + '/' + button.getAttribute('data-row-id'),
             'PATCH', { active: turningOn })
            .then(function (result) {
                if (!result.ok) {
                    note(section, result.body.error || 'Could not change that.');
                    return;
                }
                refresh();
            })
            .catch(function () {
                note(section, 'Could not reach the server.');
            });
    }

    if (window._hseListsWired) return;
    window._hseListsWired = true;

    document.addEventListener('click', function (e) {
        var addBtn = e.target.closest('.hse-list-add-btn');
        if (addBtn) {
            add(addBtn.closest('.hse-list-section'));
            return;
        }
        var toggleBtn = e.target.closest('.hse-list-toggle');
        if (toggleBtn) {
            toggle(toggleBtn.closest('.hse-list-section'), toggleBtn);
        }
    });

    // Enter in an add field is the same as pressing Add.
    document.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter') return;
        var field = e.target.closest('.hse-list-add input[type="text"]');
        if (!field) return;
        e.preventDefault();
        add(field.closest('.hse-list-section'));
    });
})();
