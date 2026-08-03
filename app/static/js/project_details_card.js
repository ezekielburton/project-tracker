// app/static/js/project_details_card.js
//
// Wires the Project Name card's three avatar pickers (CS Lead, Add
// Secondary CS, Project Owner) plus the Secondary CS remove buttons.
// Each pick/remove POSTs to its existing route, then asks the caller to
// re-fetch the whole overlay content fragment — simpler and more robust
// than hand-patching the DOM three different ways, consistent with the
// fetch-driven render-on-demand approach used everywhere else here.
//
// init() is explicit (not auto-running) — same reasoning as
// ProjectOverlay/AvatarPicker: this markup is injected on open, not
// present at page load.

window.ProjectDetailsCard = (function () {
    function init(rootEl, projectId, onChanged) {
        if (!rootEl) return null;

        var pickerHandles = [];

        function handleResponse(res) {
            return res.json().then(function (data) {
                if (data.success) {
                    onChanged();
                } else {
                    alert(data.error || 'Something went wrong.');
                }
            });
        }

        function postForm(url, body) {
            fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: body,
            }).then(handleResponse);
        }

        function postJson(url, body) {
            fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            }).then(handleResponse);
        }

        var csLeadPicker = rootEl.querySelector('#cs-lead-picker');
        if (csLeadPicker) {
            pickerHandles.push(window.AvatarPicker.init(csLeadPicker, function (userId) {
                postJson(`/projects/${projectId}/reassign-cs-lead`, { new_cs_lead_id: userId });
            }));
        }

        var secondaryCsAddPicker = rootEl.querySelector('#secondary-cs-add-picker');
        if (secondaryCsAddPicker) {
            pickerHandles.push(window.AvatarPicker.init(secondaryCsAddPicker, function (userId) {
                postForm(`/projects/${projectId}/secondary-cs`, `user_id=${userId}`);
            }));
        }

        var ownerPicker = rootEl.querySelector('#project-owner-picker');
        if (ownerPicker) {
            pickerHandles.push(window.AvatarPicker.init(ownerPicker, function (userId) {
                postForm(`/projects/${projectId}/set-project-owner`, `user_id=${userId}`);
            }));
        }

        rootEl.querySelectorAll('.overlay-secondary-cs-remove').forEach(function (btn) {
            btn.addEventListener('click', function () {
                postForm(`/projects/${projectId}/secondary-cs/${btn.dataset.userId}/remove`, '');
            });
        });

        return {
            destroy: function () {
                pickerHandles.forEach(function (handle) {
                    if (handle) handle.destroy();
                });
            }
        };
    }

    return { init: init };
})();