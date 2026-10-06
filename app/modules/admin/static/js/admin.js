// admin.js — the admin panel and emulation badge in the shell header: emulation,
// accounts, sounds, project tools, activity log, achievements.
// Loaded once by base.html (admins only), after main.js; uses showToast,
// showConfirm and btnLoading/btnDone from there.

// HTML-escapes server text for innerHTML and attribute values ('' for null).
function adminEsc(value) {
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

    // Admin panel open / close
    var adminTrigger = document.getElementById('admin-panel-trigger');
    var adminPanel = document.getElementById('admin-panel');
    var closeAdminBtn = document.getElementById('close-admin-panel');

    if (adminTrigger) {
        adminTrigger.addEventListener('click', function () {
            adminPanel.classList.toggle('hidden');
        });
    }

    if (closeAdminBtn) {
        closeAdminBtn.addEventListener('click', function () {
            adminPanel.classList.add('hidden');
        });
    }

    // Admin section switching
    document.querySelectorAll('.admin-nav-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            document.querySelectorAll('.admin-nav-btn').forEach(function (b) {
                b.classList.remove('active');
            });
            document.querySelectorAll('.admin-section').forEach(function (s) {
                s.classList.add('hidden');
            });
            this.classList.add('active');
            var sectionName = this.dataset.section;
            var section = document.getElementById('admin-section-' + sectionName);
            if (section) section.classList.remove('hidden');
            if (sectionName === 'accounts') loadAccountsSection();
            if (sectionName === 'projects') loadProjectToolsSection();
            if (sectionName === 'activity') loadActivitySection();
            if (sectionName === 'sounds') loadSoundsSection();
            if (sectionName === 'achievements') loadAchievementsSection(); // see bottom of this file

        });
    });

    // ── Emulation ────────────────────────────────────────

    var emulateSearch = document.getElementById('emulate-search');
    var emulateUserList = document.getElementById('emulate-user-list');
    var exitEmulationBtn = document.getElementById('exit-emulation-btn');
    var allUsers = [];

    // Fetch user list when admin panel opens
    if (adminTrigger) {
        adminTrigger.addEventListener('click', function () {
            if (allUsers.length === 0 && emulateUserList) {
                fetch('/admin/api/users')
                    .then(function (r) { return r.json(); })
                    .then(function (users) {
                        allUsers = users.filter(function (u) { return u.is_active; });
                        renderUserList(allUsers);
                    });
            }
        });
    }

    function renderUserList(users) {
        emulateUserList.innerHTML = '';
        if (users.length === 0) {
            emulateUserList.innerHTML = '<p class="no-notifications">No users found</p>';
            return;
        }
        users.forEach(function (user) {
            var row = document.createElement('div');
            row.className = 'emulate-user-row';
            row.innerHTML =
                '<div class="emulate-user-info">' +
                '<span class="emulate-user-name">' + adminEsc(user.name) + '</span>' +
                '<span class="emulate-user-role">' + adminEsc(user.job_title || user.department_label) + '</span>' +
                '</div>' +
                '<button type="button" class="emulate-user-btn" data-id="' + user.id + '">Emulate</button>';
            emulateUserList.appendChild(row);
        });

        emulateUserList.querySelectorAll('.emulate-user-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var self = this;
                btnLoading(self);
                fetch('/admin/emulate/' + this.dataset.id, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (data.success) window.location.reload();
                        else btnDone(self);
                    })
                    .catch(function () { btnDone(self); });
            });
        });
    }

    // Live search filter
    if (emulateSearch) {
        emulateSearch.addEventListener('input', function () {
            var query = this.value.toLowerCase();
            var filtered = allUsers.filter(function (u) {
                return u.name.toLowerCase().includes(query) || (u.job_title + ' ' + u.department_label).toLowerCase().includes(query);
            });
            renderUserList(filtered);
        });
    }

    // Exit emulation
    if (exitEmulationBtn) {
        exitEmulationBtn.addEventListener('click', function () {
            btnLoading(exitEmulationBtn);
            fetch('/admin/emulate/exit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.success) window.location.reload();
                    else btnDone(exitEmulationBtn);
                })
                .catch(function () { btnDone(exitEmulationBtn); });
        });
    }

    // Emulation badge dropdown
    var badgeTrigger = document.getElementById('emulation-badge-trigger');
    var badgeDropdown = document.getElementById('emulation-badge-dropdown');
    var badgeUserSearch = document.getElementById('badge-user-search');
    var badgeUserList = document.getElementById('badge-user-list');
    var badgeUsers = [];

    function renderBadgeUserList(users) {
        badgeUserList.innerHTML = '';
        users.forEach(function (user) {
            var row = document.createElement('div');
            row.className = 'badge-user-row';
            row.innerHTML =
                '<div class="badge-user-info">' +
                '<span class="badge-user-name">' + adminEsc(user.name) + '</span>' +
                '<span class="badge-user-role">' + adminEsc(user.job_title || user.department_label) + '</span>' +
                '</div>';
            row.addEventListener('click', function () {
                fetch('/admin/emulate/' + user.id, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (data.success) window.location.reload();
                    });
            });
            badgeUserList.appendChild(row);
        });
    }

    if (badgeTrigger) {
        badgeTrigger.addEventListener('click', function (e) {
            e.stopPropagation();
            var isHidden = badgeDropdown.classList.contains('hidden');
            badgeDropdown.classList.toggle('hidden');
            if (isHidden) {
                if (badgeUsers.length === 0) {
                    fetch('/admin/api/users')
                        .then(function (r) { return r.json(); })
                        .then(function (users) {
                            badgeUsers = users.filter(function (u) { return u.is_active; });
                            renderBadgeUserList(badgeUsers);
                            if (badgeUserSearch) badgeUserSearch.focus();
                        });
                } else {
                    renderBadgeUserList(badgeUsers);
                    if (badgeUserSearch) badgeUserSearch.focus();
                }
            }
        });
    }

    if (badgeUserSearch) {
        badgeUserSearch.addEventListener('input', function () {
            var query = this.value.toLowerCase();
            var filtered = badgeUsers.filter(function (u) {
                return u.name.toLowerCase().includes(query) || (u.job_title + ' ' + u.department_label).toLowerCase().includes(query);
            });
            renderBadgeUserList(filtered);
        });
    }

    document.addEventListener('click', function (e) {
        if (badgeDropdown && !badgeDropdown.classList.contains('hidden')) {
            if (!badgeDropdown.contains(e.target) && e.target !== badgeTrigger) {
                badgeDropdown.classList.add('hidden');
            }
        }
    });

    // ── Accounts ─────────────────────────────────────────

    var accountsUserList = document.getElementById('accounts-user-list');
    var addUserToggle = document.getElementById('add-user-toggle');
    var addUserForm = document.getElementById('add-user-form');
    var addUserCancel = document.getElementById('add-user-cancel');
    var newUserOrgFields = document.getElementById('new-user-org-fields');

    // The account forms' pick lists and the people for Reports to, refreshed
    // each time the Accounts section loads.
    var orgOptions = { departments: [], seniority: [], titles: {}, teams: [] };
    var accountUsers = [];

    function optionsHtml(items, selected, blankLabel) {
        var html = blankLabel === null ? '' : '<option value="">' + adminEsc(blankLabel) + '</option>';
        return html + items.map(function (item) {
            return '<option value="' + adminEsc(item.key) + '"' +
                (String(item.key) === String(selected) ? ' selected' : '') + '>' + adminEsc(item.label) + '</option>';
        }).join('');
    }

    function titleOptionsHtml(department) {
        return (orgOptions.titles[department || ''] || []).map(function (t) {
            return '<option value="' + adminEsc(t) + '"></option>';
        }).join('');
    }

    // The org fields shared by the add form and the edit row; `key` keeps the
    // title suggestion list's id unique per form.
    function orgFieldsHtml(user, key) {
        var listId = 'job-title-options-' + key;
        var people = accountUsers.filter(function (u) { return u.is_active && u.id !== user.id; })
            .map(function (u) { return { key: u.id, label: u.name }; });
        if (user.reports_to_id && !people.some(function (p) { return p.key === user.reports_to_id; })) {
            people.push({ key: user.reports_to_id, label: user.reports_to_name + ' (deactivated)' });
        }
        var teams = orgOptions.teams.map(function (t) { return { key: t, label: t }; });
        return '<select class="form-input org-department" aria-label="Department">' +
                optionsHtml(orgOptions.departments, user.department || '', 'No department') + '</select>' +
            '<input type="text" class="form-input org-title" list="' + listId + '" maxlength="100"' +
                ' placeholder="Job title" value="' + adminEsc(user.job_title || '') + '">' +
            '<datalist id="' + listId + '">' + titleOptionsHtml(user.department) + '</datalist>' +
            '<select class="form-input org-seniority" aria-label="Seniority">' +
                optionsHtml(orgOptions.seniority, user.seniority || 'none', null) + '</select>' +
            '<select class="form-input org-reports-to" aria-label="Reports to">' +
                optionsHtml(people, user.reports_to_id || '', 'Reports to nobody') + '</select>' +
            '<select class="form-input org-team' + (user.department === 'design' ? '' : ' hidden') + '" aria-label="Team">' +
                optionsHtml(teams, user.team || '', 'No team') + '</select>' +
            '<label class="org-admin-toggle"><input type="checkbox" class="org-is-admin"' +
                (user.is_admin ? ' checked' : '') + '> Admin</label>';
    }

    // Department picks the title suggestions and whether Team shows.
    function wireOrgFields(container) {
        var dept = container.querySelector('.org-department');
        dept.addEventListener('change', function () {
            container.querySelector('datalist').innerHTML = titleOptionsHtml(dept.value);
            container.querySelector('.org-team').classList.toggle('hidden', dept.value !== 'design');
        });
    }

    function readOrgFields(container) {
        return {
            department: container.querySelector('.org-department').value,
            job_title: container.querySelector('.org-title').value.trim(),
            seniority: container.querySelector('.org-seniority').value,
            reports_to_id: container.querySelector('.org-reports-to').value || null,
            team: container.querySelector('.org-team').value,
            is_admin: container.querySelector('.org-is-admin').checked
        };
    }

    function renderNewUserOrgFields() {
        if (!newUserOrgFields) return;
        newUserOrgFields.innerHTML = orgFieldsHtml({}, 'new');
        wireOrgFields(newUserOrgFields);
    }

    function loadAccountsSection() {
        if (!accountsUserList) return;
        Promise.all([
            fetch('/admin/api/users').then(function (r) { return r.json(); }),
            fetch('/admin/api/org-options').then(function (r) { return r.json(); })
        ])
            .then(function (results) {
                var users = results[0];
                orgOptions = results[1];
                accountUsers = users;
                renderNewUserOrgFields();
                accountsUserList.innerHTML = '';

                var activeUsers = users.filter(function (u) { return u.is_active; });
                var deactivatedUsers = users.filter(function (u) { return !u.is_active; });

                // Management first, then each department in order with Design split
                // by team. Built from the department list, so a new one shows up here.
                var groups = [{ label: 'Management', filter: function (u) { return u.seniority === 'management'; } }];
                orgOptions.departments.forEach(function (dept) {
                    if (dept.key === 'design') {
                        orgOptions.teams.forEach(function (team) {
                            groups.push({ label: 'Design · ' + team, filter: function (u) {
                                return u.department === 'design' && u.team === team;
                            } });
                        });
                    }
                    groups.push({ label: dept.label, filter: function (u) { return u.department === dept.key; } });
                });

                function renderGroup(label, members, rowClass) {
                    if (members.length === 0) return;
                    var heading = document.createElement('p');
                    heading.className = 'accounts-group-label';
                    heading.textContent = label;
                    accountsUserList.appendChild(heading);
                    members.forEach(function (user) {
                        var row = document.createElement('div');
                        row.className = rowClass;
                        row.dataset.id = user.id;
                        row.innerHTML = renderAccountDisplay(user);
                        accountsUserList.appendChild(row);
                        attachRowActions(row, user);
                    });
                }

                var rendered = {};
                groups.forEach(function (group) {
                    var members = activeUsers.filter(group.filter);
                    members.forEach(function (u) { rendered[u.id] = true; });
                    renderGroup(group.label, members, 'account-user-row');
                });

                // Catch-all (no department), so no account goes missing.
                renderGroup('No department', activeUsers.filter(function (u) {
                    return !rendered[u.id];
                }), 'account-user-row');

                // Deactivated accounts go in one muted list at the bottom.
                renderGroup('Deactivated', deactivatedUsers, 'account-user-row account-user-row--deactivated');

                if (accountsUserList.children.length === 0) {
                    accountsUserList.innerHTML = '<p class="no-notifications">No users found</p>';
                }
            })
            .catch(function () { showToast('Could not load accounts.', 'error'); });
    }

    // Admin avatar picker: one hidden file input + the shared crop modal,
    // aimed at whichever user's "Replace photo" was clicked.
    var adminAvatarInput = null;
    var adminAvatarTargetId = null;
    var adminAvatarCropper = null; // the HelixAvatarCropper the input is wired to

    function ensureAdminAvatarCropper() {
        // avatar-cropper.js re-runs with a new crop modal on every SPA swap;
        // re-wire when the instance changes so the input never opens a removed modal.
        var cropperApi = window.HelixAvatarCropper;
        if (!cropperApi || (adminAvatarInput && adminAvatarCropper === cropperApi)) return;
        if (adminAvatarInput) adminAvatarInput.remove();
        adminAvatarCropper = cropperApi;
        adminAvatarInput = document.createElement('input');
        adminAvatarInput.type = 'file';
        adminAvatarInput.accept = 'image/jpeg,image/png,image/webp';
        adminAvatarInput.style.display = 'none';
        document.body.appendChild(adminAvatarInput);
        cropperApi.wireFileInput(adminAvatarInput, 'avatar', function (data) {
            var wrap = document.querySelector('.account-user-avatar[data-id="' + adminAvatarTargetId + '"]');
            if (wrap) {
                var btn = wrap.querySelector('.account-avatar-btn');
                wrap.innerHTML = '<img class="user-avatar-img" src="' + adminEsc(data.url) + '" alt="">';
                if (btn) wrap.appendChild(btn);
            }
            if (typeof showToast === 'function') showToast('Photo updated.', 'success');
        }, { uploadUrl: function () { return '/admin/api/users/' + adminAvatarTargetId + '/avatar'; } });
    }

    function openAdminAvatarPicker(userId) {
        ensureAdminAvatarCropper();
        if (!adminAvatarInput || adminAvatarCropper !== window.HelixAvatarCropper) return;
        adminAvatarTargetId = userId;
        adminAvatarInput.value = '';
        adminAvatarInput.click();
    }

    function renderAvatarCell(user) {
        var inner = user.avatar_filename
            ? '<img class="user-avatar-img" src="/static/avatars/' + adminEsc(user.avatar_filename) + '" alt="">'
            : '<span class="user-avatar-initials">' + adminEsc(user.name.charAt(0).toUpperCase()) + '</span>';
        return '<span class="user-avatar-link user-avatar--profile account-user-avatar" data-id="' + user.id + '">' +
            inner +
            '<button type="button" class="account-avatar-btn" title="Replace photo">\uD83D\uDCF7</button>' +
            '</span>';
    }

    function renderAccountDisplay(user) {
        var tags = [user.department_label, user.seniority !== 'none' ? user.seniority_label : '',
                    user.team, user.is_admin ? 'Admin' : ''].filter(Boolean);
        var tagHtml = tags.length ? '<span class="account-user-tags">' + tags.map(function (t) {
            return '<span class="account-user-team">' + adminEsc(t) + '</span>';
        }).join('') + '</span>' : '';
        var activeToggle = user.is_active
            ? '<button type="button" class="account-deactivate-btn" role="menuitem">Deactivate</button>'
            : '<button type="button" class="account-reactivate-btn" role="menuitem">Reactivate</button>';
        return '<div class="account-user-display">' +
            renderAvatarCell(user) +
            '<div class="account-user-info">' +
            '<span class="account-user-name">' + adminEsc(user.name) + '</span>' +
            (user.job_title ? '<span class="account-user-role">' + adminEsc(user.job_title) + '</span>' : '') +
            tagHtml +
            '</div>' +
            '<div class="account-user-actions">' +
            '<button type="button" class="account-menu-btn" aria-haspopup="menu" aria-expanded="false" title="Actions">&#8943;</button>' +
            '<div class="account-row-menu" role="menu" hidden>' +
            '<button type="button" class="account-edit-btn" role="menuitem" data-name="' + adminEsc(user.name) + '">Edit</button>' +
            activeToggle +
            '<button type="button" class="account-reset-btn" role="menuitem" data-name="' + adminEsc(user.name) + '">Reset password</button>' +
            '<button type="button" class="account-delete-btn" role="menuitem" data-name="' + adminEsc(user.name) + '">Delete</button>' +
            '</div>' +
            '</div>' +
            '</div>';
    }

    function renderAccountEdit(user) {
        return '<div class="account-user-edit-form">' +
            '<input type="text" class="form-input edit-name" value="' + adminEsc(user.name) + '" placeholder="Full name">' +
            '<input type="email" class="form-input edit-email" value="' + adminEsc(user.email) + '" placeholder="Email">' +
            orgFieldsHtml(user, user.id) +
            '<input type="password" class="form-input edit-password" placeholder="New password (leave blank to keep)">' +
            '<div class="account-edit-actions">' +
            '<button type="button" class="account-save-btn btn-primary">Save</button>' +
            '<button type="button" class="account-cancel-edit-btn">Cancel</button>' +
            '</div>' +
            '</div>';
    }

    function attachRowActions(row, user) {
        var editBtn = row.querySelector('.account-edit-btn');
        var resetBtn = row.querySelector('.account-reset-btn');
        var deleteBtn = row.querySelector('.account-delete-btn');
        var saveBtn = row.querySelector('.account-save-btn');
        var cancelBtn = row.querySelector('.account-cancel-edit-btn');
        var editForm = row.querySelector('.account-user-edit-form');
        if (editForm) wireOrgFields(editForm);

        var avatarBtn = row.querySelector('.account-avatar-btn');
        if (avatarBtn) {
            avatarBtn.addEventListener('click', function () { openAdminAvatarPicker(user.id); });
        }

        if (editBtn) {
            editBtn.addEventListener('click', function () {
                row.innerHTML = renderAccountEdit(user);
                attachRowActions(row, user);
            });
        }

        if (saveBtn) {
            saveBtn.addEventListener('click', function () {
                var payload = readOrgFields(editForm);
                payload.name = editForm.querySelector('.edit-name').value.trim();
                payload.email = editForm.querySelector('.edit-email').value.trim();
                payload.password = editForm.querySelector('.edit-password').value.trim();
                btnLoading(saveBtn);
                fetch('/admin/api/users/' + user.id, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (data.success) {
                            // A new department or seniority can move the person to another group.
                            loadAccountsSection();
                        } else {
                            showToast(data.error, 'error');
                            btnDone(saveBtn);
                        }
                    })
                    .catch(function () { btnDone(saveBtn); });
            });
        }

        if (cancelBtn) {
            cancelBtn.addEventListener('click', function () {
                row.innerHTML = renderAccountDisplay(user);
                attachRowActions(row, user);
            });
        }

        if (resetBtn) {
            resetBtn.addEventListener('click', function () {
                showConfirm('Reset the password for ' + user.name + ' to a new temporary one?', function () {
                    fetch('/admin/api/users/' + user.id + '/reset-password', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' }
                    })
                        .then(function (r) { return r.json(); })
                        .then(function (data) {
                            if (data.success) {
                                // Shown once only; the server keeps just the hash.
                                showConfirm('New password for ' + user.name + ': ' + data.temp_password +
                                    '\nShare it with them now; it will not be shown again.',
                                    null, 'Password reset');
                            } else {
                                showToast(data.error || 'Could not reset the password.', 'error');
                            }
                        })
                        .catch(function () { showToast('Server error resetting the password.', 'error'); });
                });
            });
        }

        var activeBtn = row.querySelector('.account-deactivate-btn, .account-reactivate-btn');
        if (activeBtn) {
            activeBtn.addEventListener('click', function () {
                var makeActive = !user.is_active;
                var word = makeActive ? 'Reactivate' : 'Deactivate';
                showConfirm(word + ' ' + user.name + '?', function () {
                    fetch('/admin/api/users/' + user.id + '/active', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ active: makeActive })
                    })
                        .then(function (r) { return r.json(); })
                        .then(function (data) {
                            if (data.success) {
                                loadAccountsSection();
                            } else {
                                showToast(data.error || 'Could not update account.', 'error');
                            }
                        })
                        .catch(function () { showToast('Server error updating account.', 'error'); });
                });
            });
        }

        if (deleteBtn) {
            deleteBtn.addEventListener('click', function () {
                showConfirm('Delete ' + user.name + '? This cannot be undone.', function () {
                    fetch('/admin/api/users/' + user.id, {
                        method: 'DELETE',
                        headers: { 'Content-Type': 'application/json' }
                    })
                        .then(function (r) { return r.json(); })
                        .then(function (data) {
                            if (data.success) {
                                row.remove();
                            } else {
                                showToast('Could not delete user: ' + (data.error || 'Unknown error'), 'error');
                            }
                        })
                        .catch(function () {
                            showToast('Server error while deleting user.', 'error');
                        });
                });
            });
        }
    }

    // Account row "⋯" menu — one open at a time. Parked on <body> while open
    // (PopoverPosition): the admin panel's transform would offset a fixed
    // popover. Item buttons keep the listeners attachRowActions bound.
    var openAccountMenu = null;

    function closeAccountMenu() {
        if (!openAccountMenu) return;
        var m = openAccountMenu;
        openAccountMenu = null;
        m.menu.hidden = true;
        m.btn.setAttribute('aria-expanded', 'false');
        window.PopoverPosition.release(m.menu);
    }

    document.addEventListener('click', function (e) {
        var btn = e.target.closest('.account-menu-btn');
        if (btn) {
            var wasOpen = openAccountMenu && openAccountMenu.btn === btn;
            closeAccountMenu();
            if (wasOpen) return;
            var menu = btn.parentNode.querySelector('.account-row-menu');
            if (!menu) return;
            window.PopoverPosition.attach(menu);
            menu.hidden = false;
            window.PopoverPosition.place(menu, btn);
            // Right-align under the button — it sits at the row's right edge.
            var r = btn.getBoundingClientRect();
            menu.style.left = Math.max(8, r.right - menu.offsetWidth) + 'px';
            btn.setAttribute('aria-expanded', 'true');
            openAccountMenu = { btn: btn, menu: menu };
            return;
        }
        // An item or an outside click closes it. Item handlers run first
        // (bound on the buttons), so Edit re-renders before release.
        closeAccountMenu();
    });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') closeAccountMenu();
    });
    document.addEventListener('scroll', closeAccountMenu, true);
    window.addEventListener('resize', closeAccountMenu);

    if (addUserToggle) {
        addUserToggle.addEventListener('click', function () {
            addUserForm.classList.toggle('hidden');
        });
    }

    if (addUserCancel) {
        addUserCancel.addEventListener('click', function () {
            addUserForm.classList.add('hidden');
            addUserForm.reset();
            renderNewUserOrgFields();
        });
    }

    if (addUserForm) {
        addUserForm.addEventListener('submit', function (e) {
            e.preventDefault();
            var payload = readOrgFields(newUserOrgFields);
            payload.name = document.getElementById('new-user-name').value.trim();
            payload.email = document.getElementById('new-user-email').value.trim();
            payload.password = document.getElementById('new-user-password').value.trim();
            var submitBtn = addUserForm.querySelector('button[type="submit"]');
            btnLoading(submitBtn);
            fetch('/admin/api/users', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.success) {
                        btnDone(submitBtn);
                        addUserForm.reset();
                        renderNewUserOrgFields();
                        addUserForm.classList.add('hidden');
                        loadAccountsSection();
                    } else {
                        showToast(data.error, 'error');
                        btnDone(submitBtn);
                    }
                })
                .catch(function () { btnDone(submitBtn); });
        });
    }

    // ── Job titles ─────────────────────────────────────────
    // Titles are added by typing one on a person; here they are renamed,
    // hidden from the pickers, or shown again.
    var jobTitlesToggle = document.getElementById('job-titles-toggle');
    var jobTitlesBlock = document.getElementById('job-titles-block');

    function patchJobTitle(id, body) {
        return fetch('/admin/api/job-titles/' + id, {
            method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
        })
            .then(function (r) { return r.json(); })
            .then(function (d) {
                if (!d.success) { showToast(d.error || 'Could not update the title.', 'error'); return; }
                loadJobTitles();
                loadAccountsSection();
            })
            .catch(function () { showToast('Server error updating the title.', 'error'); });
    }

    function loadJobTitles() {
        var list = document.getElementById('job-titles-list');
        fetch('/admin/api/job-titles')
            .then(function (r) { return r.json(); })
            .then(function (rows) {
                if (!rows.length) { list.innerHTML = '<p class="empty-state">No titles yet</p>'; return; }
                var byId = {};
                var lastGroup = null;
                list.innerHTML = rows.map(function (row) {
                    byId[row.id] = row;
                    var heading = row.department_label !== lastGroup
                        ? '<p class="accounts-group-label">' + adminEsc(row.department_label) + '</p>' : '';
                    lastGroup = row.department_label;
                    return heading +
                        '<div class="account-user-row' + (row.is_active ? '' : ' account-user-row--deactivated') + '" data-id="' + row.id + '">' +
                        '<div class="account-user-info"><span class="account-user-name">' + adminEsc(row.title) + '</span>' +
                        '<span class="account-user-team">' + row.people + (row.people === 1 ? ' person' : ' people') + '</span></div>' +
                        '<div class="account-user-actions">' +
                        '<button type="button" class="account-edit-btn job-title-rename">Rename</button>' +
                        '<button type="button" class="' + (row.is_active ? 'account-deactivate-btn' : 'account-reactivate-btn') +
                            ' job-title-toggle">' + (row.is_active ? 'Hide' : 'Show') + '</button>' +
                        '</div></div>';
                }).join('');

                list.querySelectorAll('.account-user-row').forEach(function (rowEl) {
                    var row = byId[rowEl.dataset.id];
                    rowEl.querySelector('.job-title-toggle').addEventListener('click', function () {
                        patchJobTitle(row.id, { is_active: !row.is_active });
                    });
                    rowEl.querySelector('.job-title-rename').addEventListener('click', function () {
                        rowEl.innerHTML = '<div class="pt-inline-edit">' +
                            '<input type="text" class="form-input job-title-name" maxlength="100" value="' + adminEsc(row.title) + '">' +
                            '<button type="button" class="btn-primary job-title-save">Save</button>' +
                            '<button type="button" class="account-delete-btn job-title-cancel">Cancel</button>' +
                            '</div>';
                        rowEl.querySelector('.job-title-save').addEventListener('click', function () {
                            var title = rowEl.querySelector('.job-title-name').value.trim();
                            if (title) patchJobTitle(row.id, { title: title });
                        });
                        rowEl.querySelector('.job-title-cancel').addEventListener('click', loadJobTitles);
                    });
                });
            })
            .catch(function () { showToast('Could not load job titles.', 'error'); });
    }

    if (jobTitlesToggle) {
        jobTitlesToggle.addEventListener('click', function () {
            var opening = !jobTitlesBlock.classList.toggle('hidden');
            if (opening) loadJobTitles();
        });
    }

// ── Notification Sounds ─────────────────────────────────────────
var addSoundToggle = document.getElementById('add-sound-toggle');
var addSoundForm = document.getElementById('add-sound-form');
var addSoundCancel = document.getElementById('add-sound-cancel');
var soundsList = document.getElementById('sounds-list');

if (addSoundToggle) {
    addSoundToggle.addEventListener('click', function () {
        addSoundForm.classList.toggle('hidden');
    });
}
if (addSoundCancel) {
    addSoundCancel.addEventListener('click', function () {
        addSoundForm.reset();
        addSoundForm.classList.add('hidden');
    });
}

function loadSoundsSection() {
    if (!soundsList) return;
    fetch('/admin/api/sounds')
        .then(function (r) { return r.json(); })
        .then(function (sounds) {
            renderSoundsList(sounds);
        });
}

function renderSoundsList(sounds) {
    soundsList.innerHTML = '';
    if (sounds.length === 0) {
        soundsList.innerHTML = '<p class="no-notifications">No sounds uploaded yet</p>';
        return;
    }
    sounds.forEach(function (sound) {
        var row = document.createElement('div');
        row.className = 'account-user-row';
        row.id = 'sound-' + sound.id;
        row.innerHTML =
            '<div class="account-user-info">' +
            '<span class="account-user-name">' + adminEsc(sound.name) + '</span>' +
            '<audio controls src="' + adminEsc(sound.url) + '" style="height:28px;"></audio>' +
            '</div>' +
            '<div class="account-user-actions">' +
            '<button type="button" class="account-delete-btn" data-id="' + sound.id + '" data-name="' + adminEsc(sound.name) + '">&times;</button>' +
            '</div>';
        soundsList.appendChild(row);

        row.querySelector('.account-delete-btn').addEventListener('click', function () {
            var name = this.dataset.name;
            var id = this.dataset.id;
            showConfirm('Delete sound "' + name + '"? Anyone using it will fall back to the default chime.', function () {
                fetch('/admin/api/sounds/' + id, { method: 'DELETE' })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (data.success) { document.getElementById('sound-' + id).remove(); }
                        else { showToast(data.error || 'Could not delete sound.', 'error'); }
                    });
            });
        });
    });
}

if (addSoundForm) {
    addSoundForm.addEventListener('submit', function (e) {
        e.preventDefault();
        var nameInput = document.getElementById('new-sound-name');
        var fileInput = document.getElementById('new-sound-file');

        if (!nameInput.value.trim() || !fileInput.files[0]) {
            showToast('Please provide a name and a file.', 'error');
            return;
        }

        // Multipart upload, so no JSON Content-Type header.
        var formData = new FormData();
        formData.append('name', nameInput.value.trim());
        formData.append('file', fileInput.files[0]);

        var submitBtn = addSoundForm.querySelector('button[type="submit"]');
        btnLoading(submitBtn);

        fetch('/admin/api/sounds', { method: 'POST', body: formData })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                btnDone(submitBtn);
                if (!data.success) { showToast(data.error || 'Upload failed.', 'error'); return; }
                addSoundForm.reset();
                addSoundForm.classList.add('hidden');
                loadSoundsSection(); // reload keeps the server's sort order
            })
            .catch(function () { btnDone(submitBtn); });
    });
}

    // ── Project Tools ─────────────────────────────────────────────────────────

    document.querySelectorAll('.pt-tab-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            document.querySelectorAll('.pt-tab-btn').forEach(function (b) { b.classList.remove('active'); });
            document.querySelectorAll('.pt-panel').forEach(function (p) { p.classList.add('hidden'); });
            this.classList.add('active');
            var panel = document.getElementById('pt-panel-' + this.dataset.pt);
            if (panel) panel.classList.remove('hidden');
            loadPTPanel(this.dataset.pt);
        });
    });

    function loadProjectToolsSection() {
        var activeTab = document.querySelector('.pt-tab-btn.active');
        if (activeTab) loadPTPanel(activeTab.dataset.pt);
    }

    function loadPTPanel(name) {
        if (name === 'clients') loadPTClients();
        else if (name === 'customers') loadPTCustomers();
        else if (name === 'projects') loadPTProjects();
        else if (name === 'drafts') loadPTDrafts();
        else if (name === 'deliverables') loadPTDeliverables();
        else if (name === 'design-types') loadPTDesignTypes();
        else if (name === 'design-directions') loadPTDesignDirections();
        else if (name === 'job-numbers') loadPTJobNumbers();
        else if (name === 'cs-scopes') loadPTCsScopes();
    }

    // ── Clients ───────────────────────────────────────────────────

    function loadPTClients() {
        fetch('/admin/api/clients')
            .then(function (res) { return res.json(); })
            .then(function (clients) {
                var list = document.getElementById('pt-clients-list');
                if (clients.length === 0) {
                    list.innerHTML = '<p class="empty-state">No clients yet.</p>';
                    return;
                }
                list.innerHTML = clients.map(function (c) {
                    return '<div class="account-user-row" id="pt-client-' + c.id + '">' +
                        '<span class="account-user-name">' + adminEsc(c.name) + '</span>' +
                        '<div class="account-user-actions">' +
                        '<button type="button" class="account-delete-btn" data-id="' + c.id + '" data-name="' + adminEsc(c.name) + '">&times;</button>' +
                        '</div></div>';
                }).join('');
                list.querySelectorAll('.account-delete-btn').forEach(function (btn) {
                    btn.addEventListener('click', function () {
                        /* Read dataset now; 'this' is gone inside the confirm callback. */
                        var name = this.dataset.name;
                        var id   = this.dataset.id;
                        showConfirm('Delete client "' + name + '"? This cannot be undone.', function () {
                            fetch('/admin/api/clients/' + id, { method: 'DELETE' })
                                .then(function (res) { return res.json(); })
                                .then(function (data) {
                                    if (data.success) { document.getElementById('pt-client-' + id).remove(); }
                                    else { showToast(data.error || 'Could not delete client.', 'error'); }
                                });
                        });
                    });
                });
            });
    }

    var ptAddClientToggle = document.getElementById('pt-add-client-toggle');
    var ptAddClientForm = document.getElementById('pt-add-client-form');
    if (ptAddClientToggle) {
        ptAddClientToggle.addEventListener('click', function () {
            ptAddClientForm.classList.toggle('hidden');
        });
    }
    var ptAddClientCancel = document.getElementById('pt-add-client-cancel');
    if (ptAddClientCancel) {
        ptAddClientCancel.addEventListener('click', function () {
            ptAddClientForm.classList.add('hidden');
            document.getElementById('pt-new-client-name').value = '';
        });
    }
    if (ptAddClientForm) ptAddClientForm.addEventListener('submit', function (e) {
        e.preventDefault();
        var name = document.getElementById('pt-new-client-name').value.trim();
        if (!name) return;
        var submitBtn = ptAddClientForm.querySelector('button[type="submit"]');
        btnLoading(submitBtn);
        fetch('/admin/api/clients', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name })
        })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.success) {
                    ptAddClientForm.classList.add('hidden');
                    document.getElementById('pt-new-client-name').value = '';
                    loadPTClients();
                } else {
                    showToast(data.error || 'Could not create client.', 'error');
                    btnDone(submitBtn);
                }
            })
            .catch(function () { btnDone(submitBtn); });
    });

    // ── Customers ─────────────────────────────────────────────────

    function loadPTCustomers() {
        fetch('/admin/api/customers')
            .then(function (res) { return res.json(); })
            .then(function (customers) {
                var list = document.getElementById('pt-customers-list');
                if (customers.length === 0) {
                    list.innerHTML = '<p class="empty-state">No customers yet.</p>';
                    return;
                }
                var grouped = {};
                customers.forEach(function (c) {
                    if (!grouped[c.region]) grouped[c.region] = [];
                    grouped[c.region].push(c);
                });
                var html = '';
                Object.keys(grouped).sort().forEach(function (region) {
                    html += '<div class="accounts-group-label">' + adminEsc(region.charAt(0).toUpperCase() + region.slice(1)) + '</div>';
                    grouped[region].forEach(function (c) {
                        html += '<div class="account-user-row" id="pt-customer-' + c.id + '">' +
                            '<span class="account-user-name">' + adminEsc(c.name) + '</span>' +
                            '<div class="account-user-actions">' +
                            '<button type="button" class="account-delete-btn" data-id="' + c.id + '" data-name="' + adminEsc(c.name) + '">&times;</button>' +
                            '</div></div>';
                    });
                });
                list.innerHTML = html;
                list.querySelectorAll('.account-delete-btn').forEach(function (btn) {
                    btn.addEventListener('click', function () {
                        var name = this.dataset.name;
                        var id   = this.dataset.id;
                        showConfirm('Delete customer "' + name + '"? This cannot be undone.', function () {
                            fetch('/admin/api/customers/' + id, { method: 'DELETE' })
                                .then(function (res) { return res.json(); })
                                .then(function (data) {
                                    if (data.success) { document.getElementById('pt-customer-' + id).remove(); }
                                    else { showToast(data.error || 'Could not delete customer.', 'error'); }
                                });
                        });
                    });
                });
            });
    }

    var ptAddCustomerToggle = document.getElementById('pt-add-customer-toggle');
    var ptAddCustomerForm = document.getElementById('pt-add-customer-form');
    if (ptAddCustomerToggle) {
        ptAddCustomerToggle.addEventListener('click', function () {
            ptAddCustomerForm.classList.toggle('hidden');
        });
    }
    document.getElementById('pt-add-customer-cancel').addEventListener('click', function () {
        ptAddCustomerForm.classList.add('hidden');
        document.getElementById('pt-new-customer-name').value = '';
        document.getElementById('pt-new-customer-region').value = '';
    });
    ptAddCustomerForm.addEventListener('submit', function (e) {
        e.preventDefault();
        var name = document.getElementById('pt-new-customer-name').value.trim();
        var region = document.getElementById('pt-new-customer-region').value;
        if (!name || !region) return;
        var submitBtn = ptAddCustomerForm.querySelector('button[type="submit"]');
        btnLoading(submitBtn);
        fetch('/admin/api/customers', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, region: region })
        })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.success) {
                    ptAddCustomerForm.classList.add('hidden');
                    document.getElementById('pt-new-customer-name').value = '';
                    document.getElementById('pt-new-customer-region').value = '';
                    loadPTCustomers();
                } else {
                    showToast(data.error || 'Could not create customer.', 'error');
                    btnDone(submitBtn);
                }
            })
            .catch(function () { btnDone(submitBtn); });
    });

    // ── Projects ──────────────────────────────────────────────────

    function loadPTProjects() {
        fetch('/admin/api/projects')
            .then(function (res) { return res.json(); })
            .then(function (projects) {
                var list = document.getElementById('pt-projects-list');
                if (projects.length === 0) {
                    list.innerHTML = '<p class="empty-state">No active projects.</p>';
                    return;
                }
                var statusLabel = { briefed: 'Briefed', in_queue: 'In Queue', in_progress: 'In Progress', submitted: 'Submitted', revision_in_queue: 'Revision in Queue', revision_in_progress: 'Revision in Progress', approved: 'Approved', completed: 'Completed' };
                list.innerHTML = projects.map(function (p) {
                    var statusText = statusLabel[p.status] || p.status;
                    return '<div class="account-user-row" id="pt-project-' + p.id + '">' +
                        '<div class="pt-project-row-content">' +
                        '<div class="pt-project-row-info">' +
                        '<span class="pt-project-job-num">' + adminEsc(p.job_number || 'No job #') + '</span>' +
                        '<span class="pt-project-name">' + adminEsc(p.name) + '</span>' +
                        '<span class="pt-project-cs">' + adminEsc(p.cs_lead) + '</span>' +
                        '<span class="pt-project-status">' + adminEsc(statusText) + '</span>' +
                        '</div>' +
                        '<div class="account-user-actions">' +
                        '<button type="button" class="account-delete-btn" data-id="' + p.id + '" data-name="' + adminEsc(p.name) + '">&times;</button>' +
                        '</div>' +
                        '</div></div>';
                }).join('');
                list.querySelectorAll('.account-delete-btn').forEach(function (btn) {
                    btn.addEventListener('click', function () {
                        var name = this.dataset.name;
                        var id   = this.dataset.id;
                        showConfirm('Delete project "' + name + '"? This cannot be undone.', function () {
                            fetch('/admin/api/projects/' + id, { method: 'DELETE' })
                                .then(function (res) { return res.json(); })
                                .then(function (data) {
                                    if (data.success) { document.getElementById('pt-project-' + id).remove(); }
                                    else { showToast(data.error || 'Could not delete project.', 'error'); }
                                });
                        });
                    });
                });
            });
    }

    // ── Drafts ────────────────────────────────────────────────────
    // Deleting a draft deletes the project row, which frees its unique job_number.

    function loadPTDrafts() {
        fetch('/admin/api/drafts')
            .then(function (res) { return res.json(); })
            .then(function (drafts) {
                var list = document.getElementById('pt-drafts-list');
                if (drafts.length === 0) {
                    list.innerHTML = '<p class="empty-state">No drafts.</p>';
                    return;
                }
                list.innerHTML = drafts.map(function (d) {
                    // Job number shown so the admin sees which number a delete frees.
                    var subtitle = d.cs_lead + (d.job_number ? ' · ' + d.job_number : '');
                    return '<div class="account-user-row" id="pt-draft-' + d.id + '">' +
                        '<div class="account-user-info">' +
                        '<span class="account-user-name">' + adminEsc(d.name) + '</span>' +
                        '<span class="account-user-role">' + adminEsc(subtitle) + '</span>' +
                        '</div>' +
                        '<div class="account-user-actions">' +
                        '<button type="button" class="account-delete-btn" data-id="' + d.id + '" data-name="' + adminEsc(d.name) + '">&times;</button>' +
                        '</div></div>';
                }).join('');
                list.querySelectorAll('.account-delete-btn').forEach(function (btn) {
                    btn.addEventListener('click', function () {
                        var name = this.dataset.name;
                        var id   = this.dataset.id;
                        showConfirm('Delete draft "' + name + '"? This also frees its job number.', function () {
                            fetch('/admin/api/drafts/' + id, { method: 'DELETE' })
                                .then(function (res) { return res.json(); })
                                .then(function (data) {
                                    if (data.success) { document.getElementById('pt-draft-' + id).remove(); }
                                    else { showToast(data.error || 'Could not delete draft.', 'error'); }
                                });
                        });
                    });
                });
            });
    }

    // ── Job Numbers ───────────────────────────────────────────────
    // Every project with a job_number. "Clear" sets the number to NULL, freeing
    // it for reuse, and keeps the project.

    function loadPTJobNumbers() {
        fetch('/admin/api/job-numbers')
            .then(function (res) { return res.json(); })
            .then(function (items) {
                var list = document.getElementById('pt-job-numbers-list');
                if (items.length === 0) {
                    list.innerHTML = '<p class="empty-state">No job numbers assigned.</p>';
                    return;
                }

                var statusLabel = {
                    draft:                  'Draft',
                    briefed:                'Briefed',
                    in_queue:               'In Queue',
                    in_progress:            'In Progress',
                    submitted:              'Submitted',
                    awaiting_review:        'Awaiting Review',
                    revision_requested:     'Revision Requested',
                    re_submitted:           'Re-submitted',
                    cs_approved:            'CS Approved',
                    revision_in_queue:      'Rev. in Queue',
                    revision_in_progress:   'Rev. in Progress',
                    on_hold:                'On Hold',
                    awaiting_posm_details:  'Awaiting POSM',
                    approved:               'Approved',
                };

                list.innerHTML = items.map(function (item) {
                    var statusText = statusLabel[item.status] || item.status;
                    return '<div class="account-user-row" id="pt-jobn-' + item.id + '">' +
                        '<div class="pt-project-row-content">' +
                        '<div class="pt-project-row-info">' +
                        '<span class="pt-project-job-num">' + adminEsc(item.job_number) + '</span>' +
                        '<span class="pt-project-name">' + adminEsc(item.name) + '</span>' +
                        '<span class="pt-project-cs">' + adminEsc(item.cs_lead) + '</span>' +
                        '<span class="pt-project-status">' + adminEsc(statusText) + '</span>' +
                        '</div>' +
                        '<div class="account-user-actions">' +
                        '<button type="button" class="account-delete-btn"' +
                        ' data-id="' + item.id + '"' +
                        ' data-name="' + adminEsc(item.job_number) + '"' +
                        ' data-project="' + adminEsc(item.name) + '">' +
                        'Clear</button>' +
                        '</div>' +
                        '</div></div>';
                }).join('');

                list.querySelectorAll('.account-delete-btn').forEach(function (btn) {
                    btn.addEventListener('click', function () {
                        /* Read dataset now; 'this' is gone inside the confirm callback. */
                        var id      = this.dataset.id;
                        var jobn    = this.dataset.name;
                        var project = this.dataset.project;

                        showConfirm(
                            'Clear job number "' + jobn + '" from "' + project + '"?\n' +
                            'The project stays — only the number is freed.',
                            function () {
                                fetch('/admin/api/job-numbers/' + id, { method: 'DELETE' })
                                    .then(function (res) { return res.json(); })
                                    .then(function (data) {
                                        if (data.success) {
                                            var row = document.getElementById('pt-jobn-' + id);
                                            if (row) row.remove();
                                            if (!document.querySelector('[id^="pt-jobn-"]')) {
                                                document.getElementById('pt-job-numbers-list').innerHTML =
                                                    '<p class="empty-state">No job numbers assigned.</p>';
                                            }
                                        } else {
                                            showToast(data.error || 'Could not clear job number.', 'error');
                                        }
                                    })
                                    .catch(function () { showToast('Something went wrong.', 'error'); });
                            },
                            'Clear Job Number'
                        );
                    });
                });
            });
    }

    // ── Deliverable Types ─────────────────────────────────────────
    var ptFormClients = [];
    var ptFormCustomers = [];
    var ptDelFormLoaded = false;

    function loadPTDelFormData(callback) {
        if (ptDelFormLoaded) { callback(); return; }
        Promise.all([
            fetch('/admin/api/clients').then(function (r) { return r.json(); }),
            fetch('/admin/api/customers').then(function (r) { return r.json(); })
        ]).then(function (results) {
            ptFormClients = results[0];
            ptFormCustomers = results[1];
            ptDelFormLoaded = true;
            callback();
        });
    }

    function populatePTDelFormClients() {
        var sel = document.getElementById('pt-new-del-client');
        sel.innerHTML = '<option value="">Select client...</option>' +
            ptFormClients.map(function (c) {
                return '<option value="' + c.id + '">' + adminEsc(c.name) + '</option>';
            }).join('');
    }

    function populatePTDelFormCustomers(region) {
        var filtered = region
            ? ptFormCustomers.filter(function (c) { return c.region === region; })
            : ptFormCustomers;
        var sel = document.getElementById('pt-new-del-customer');
        sel.innerHTML = '<option value="">Select customer...</option>' +
            filtered.map(function (c) {
                return '<option value="' + c.id + '">' + adminEsc(c.name) + '</option>';
            }).join('');
    }

    var ptAddDelToggle = document.getElementById('pt-add-del-toggle');
    var ptAddDelForm = document.getElementById('pt-add-del-form');

    ptAddDelToggle.addEventListener('click', function () {
        var opening = ptAddDelForm.classList.contains('hidden');
        ptAddDelForm.classList.toggle('hidden');
        if (opening) {
            loadPTDelFormData(function () {
                populatePTDelFormClients();
                populatePTDelFormCustomers('');
            });
        }
    });

    document.getElementById('pt-add-del-cancel').addEventListener('click', function () {
        ptAddDelForm.classList.add('hidden');
        ptAddDelForm.reset();
    });

    document.getElementById('pt-new-del-region').addEventListener('change', function () {
        populatePTDelFormCustomers(this.value);
    });

// Creates the deliverable type once any uploads have returned their filenames (or null).
function createPTDeliverableType(name, clientId, customerId, disciplines, isCustom, referenceImage, templateFilename, submitBtn) {
    fetch('/admin/api/deliverable-types', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            name: name,
            client_id: clientId,
            customer_id: customerId,
            disciplines: disciplines,
            is_custom: isCustom,
            reference_image: referenceImage,
            template_filename: templateFilename
        })
    })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (data.success) {
                btnDone(submitBtn);
                ptAddDelForm.classList.add('hidden');
                ptAddDelForm.reset();
                ptAllDeliverableTypes.push(data.type);
                ptAllDeliverableTypes.sort(function (a, b) { return a.name.localeCompare(b.name); });
                populatePTDelClientFilter(ptAllDeliverableTypes);
                filterPTDeliverables();
            } else {
                showToast(data.error || 'Could not create deliverable type.', 'error');
                btnDone(submitBtn);
            }
        })
        .catch(function () { btnDone(submitBtn); });
}

// Uploads a file to `endpoint`; resolves to the saved filename, or null if no file.
function uploadDeliverableFile(file, endpoint) {
    if (!file) return Promise.resolve(null);
    var formData = new FormData();
    formData.append('file', file);
    return fetch(endpoint, { method: 'POST', body: formData })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (!data.success) return Promise.reject(data.error || 'Upload failed.');
            return data.filename;
        });
}

// One file field on an edit save resolves to: the new filename (file chosen),
// null (remove checked), or undefined (leave alone). The caller omits the key
// from the PATCH on undefined; the backend only touches keys that are present.
function resolveFileField(chosenFile, removeChecked, endpoint) {
    if (chosenFile) return uploadDeliverableFile(chosenFile, endpoint);
    if (removeChecked) return Promise.resolve(null);
    return Promise.resolve(undefined);
}

ptAddDelForm.addEventListener('submit', function (e) {
    e.preventDefault();
    var name = document.getElementById('pt-new-del-name').value.trim();
    var clientId = document.getElementById('pt-new-del-client').value;
    var customerId = document.getElementById('pt-new-del-customer').value;
    var disciplines = Array.from(
        ptAddDelForm.querySelectorAll('.pt-discipline-checks input:checked')
    ).map(function (cb) { return cb.value; });
    var isCustom = document.getElementById('pt-new-del-custom').checked;
    if (!name || !clientId || !customerId) {
        showToast('Name, client, and customer are all required.', 'warning');
        return;
    }
    var submitBtn = ptAddDelForm.querySelector('button[type="submit"]');
    btnLoading(submitBtn);

    var imageFile = document.getElementById('pt-new-del-image').files[0];
    var templateFile = document.getElementById('pt-new-del-template').files[0];

    Promise.all([
        uploadDeliverableFile(imageFile, '/projects/deliverable-types/upload-image'),
        uploadDeliverableFile(templateFile, '/admin/api/deliverable-types/upload-template')
    ]).then(function (results) {
        createPTDeliverableType(name, clientId, customerId, disciplines, isCustom, results[0], results[1], submitBtn);
    }).catch(function (err) {
        showToast(typeof err === 'string' ? err : 'Something went wrong uploading a file.', 'error');
        btnDone(submitBtn);
    });
});


    var ptAllDeliverableTypes = [];

    function loadPTDeliverables() {
        fetch('/admin/api/deliverable-types')
            .then(function (res) { return res.json(); })
            .then(function (types) {
                ptAllDeliverableTypes = types;
                populatePTDelClientFilter(types);
                renderPTDeliverableRows(types);
            });
    }

    // ── Design Types ──────────────────────────────────────────────
    function loadPTDesignTypes() {
        fetch('/admin/api/design-types')
            .then(function (r) { return r.json(); })
            .then(function (types) {
                var list = document.getElementById('pt-design-types-list');
                list.innerHTML = types.length === 0 ? '<p class="empty-state">No design types yet.</p>' :
                    types.map(function (t) {
                        return '<div class="account-user-row" id="pt-dt-' + t.id + '">' +
                            '<div class="account-user-info">' +
                            '<span class="account-user-name">' + adminEsc(t.name) + '</span>' +
                            '<span class="account-user-role">' + adminEsc(t.team ? t.team.split(',').join(' + ') : 'No team set') + '</span>' +
                            '</div>' +
                            '<div class="account-user-actions">' +
                            '<button class="account-edit-btn pt-dt-edit" data-id="' + t.id + '" data-name="' + adminEsc(t.name) + '" data-team="' + adminEsc(t.team) + '">Edit</button>' +
                            '<button class="account-delete-btn pt-dt-delete" data-id="' + t.id + '" data-name="' + adminEsc(t.name) + '">&times;</button>' +
                            '</div></div>';
                    }).join('');
                list.querySelectorAll('.pt-dt-delete').forEach(function (btn) {
                    btn.addEventListener('click', function () {
                        var name = this.dataset.name;
                        var id   = this.dataset.id;
                        showConfirm('Delete design type "' + name + '"?', function () {
                            fetch('/admin/api/design-types/' + id, { method: 'DELETE' })
                                .then(function (r) { return r.json(); })
                                .then(function (d) { if (d.success) { document.getElementById('pt-dt-' + id).remove(); } else { showToast(d.error, 'error'); } });
                        });
                    });
                });
                list.querySelectorAll('.pt-dt-edit').forEach(function (btn) {
                    btn.addEventListener('click', function () {
                        var id = this.dataset.id;
                        var row = document.getElementById('pt-dt-' + id);
                        var currentName = this.dataset.name;
                        var currentTeam = this.dataset.team;
                        var currentTeams = currentTeam ? currentTeam.split(',') : [];
                        row.innerHTML =
                            '<div class="pt-inline-edit">' +
                            '<input type="text" class="form-input pt-edit-name" value="' + adminEsc(currentName) + '" style="max-width:180px;">' +
                            '<div class="pt-discipline-checks pt-edit-teams">' +
                            ['2D', '3D', 'Technical'].map(function (t) {
                                return '<label><input type="checkbox" value="' + t + '"' + (currentTeams.indexOf(t) !== -1 ? ' checked' : '') + '> ' + t + '</label>';
                            }).join('') +
                            '</div>' +
                            '<button class="btn-primary pt-dt-save" data-id="' + id + '">Save</button>' +
                            '<button class="account-delete-btn pt-dt-cancel" data-id="' + id + '">Cancel</button>' +
                            '</div>';
                        row.querySelector('.pt-dt-save').addEventListener('click', function () {
                            var newName = row.querySelector('.pt-edit-name').value.trim();
                            var newTeam = Array.from(row.querySelectorAll('.pt-edit-teams input:checked')).map(function (cb) { return cb.value; }).join(',') || null;
                            if (!newName) return;
                            var saveBtn = this;
                            btnLoading(saveBtn);
                            fetch('/admin/api/design-types/' + id, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: newName, team: newTeam }) })
                                .then(function (r) { return r.json(); })
                                .then(function (d) {
                                    if (d.success || !d.error) { loadPTDesignTypes(); }
                                    else { showToast(d.error, 'error'); btnDone(saveBtn); }
                                })
                                .catch(function () { btnDone(saveBtn); });
                        });
                        row.querySelector('.pt-dt-cancel').addEventListener('click', function () { loadPTDesignTypes(); });
                    });
                });
            });
    }

    document.addEventListener('DOMContentLoaded', function () {
        var addDtToggle = document.getElementById('pt-add-dt-toggle');
        var addDtForm = document.getElementById('pt-add-dt-form');
        var addDtCancel = document.getElementById('pt-add-dt-cancel');
        if (addDtToggle) {
            addDtToggle.addEventListener('click', function () { addDtForm.classList.toggle('hidden'); });
            addDtCancel.addEventListener('click', function () { addDtForm.classList.add('hidden'); });
            addDtForm.addEventListener('submit', function (e) {
                e.preventDefault();
                var name = document.getElementById('pt-new-dt-name').value.trim();
                var checked = Array.from(document.querySelectorAll('#pt-new-dt-teams input:checked')).map(function (cb) { return cb.value; });
                var team = checked.join(',') || null;
                if (!name) return;
                var submitBtn = addDtForm.querySelector('button[type="submit"]');
                btnLoading(submitBtn);
                fetch('/admin/api/design-types', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: name, team: team }) })
                    .then(function (r) { return r.json(); })
                    .then(function (d) {
                        if (d.error) { showToast(d.error, 'error'); btnDone(submitBtn); return; }
                        document.getElementById('pt-new-dt-name').value = '';
                        document.querySelectorAll('#pt-new-dt-teams input').forEach(function (cb) { cb.checked = false; });
                        addDtForm.classList.add('hidden');
                        loadPTDesignTypes();
                    })
                    .catch(function () { btnDone(submitBtn); });
            });
        }

        // ── Design Directions ──────────────────────────────────────
        var addDdToggle = document.getElementById('pt-add-dd-toggle');
        var addDdForm = document.getElementById('pt-add-dd-form');
        var addDdCancel = document.getElementById('pt-add-dd-cancel');
        if (addDdToggle) {
            addDdToggle.addEventListener('click', function () { addDdForm.classList.toggle('hidden'); });
            addDdCancel.addEventListener('click', function () { addDdForm.classList.add('hidden'); });
            addDdForm.addEventListener('submit', function (e) {
                e.preventDefault();
                var name = document.getElementById('pt-new-dd-name').value.trim();
                if (!name) return;
                var submitBtn = addDdForm.querySelector('button[type="submit"]');
                btnLoading(submitBtn);
                fetch('/admin/api/design-directions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: name }) })
                    .then(function (r) { return r.json(); })
                    .then(function (d) {
                        if (d.error) { showToast(d.error, 'error'); btnDone(submitBtn); return; }
                        document.getElementById('pt-new-dd-name').value = '';
                        addDdForm.classList.add('hidden');
                        loadPTDesignDirections();
                    })
                    .catch(function () { btnDone(submitBtn); });
            });
        }

        // ── CS Scopes ──────────────────────────────────────
        var addCsScopeToggle = document.getElementById('pt-add-cs-scope-toggle');
        var addCsScopeForm = document.getElementById('pt-add-cs-scope-form');
        var addCsScopeCancel = document.getElementById('pt-add-cs-scope-cancel');
        if (addCsScopeToggle) {
            addCsScopeToggle.addEventListener('click', function () { addCsScopeForm.classList.toggle('hidden'); });
            addCsScopeCancel.addEventListener('click', function () { addCsScopeForm.classList.add('hidden'); });
            addCsScopeForm.addEventListener('submit', function (e) {
                e.preventDefault();
                var name = document.getElementById('pt-new-cs-scope-name').value.trim();
                if (!name) return;
                var submitBtn = addCsScopeForm.querySelector('button[type="submit"]');
                btnLoading(submitBtn);
                fetch('/client-servicing/scopes', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: name }) })
                    .then(function (r) { return r.json(); })
                    .then(function (d) {
                        if (d.error) { showToast(d.error, 'error'); btnDone(submitBtn); return; }
                        document.getElementById('pt-new-cs-scope-name').value = '';
                        addCsScopeForm.classList.add('hidden');
                        loadPTCsScopes();
                    })
                    .catch(function () { btnDone(submitBtn); });
            });
        }
    });

    function loadPTDesignDirections() {
        fetch('/admin/api/design-directions')
            .then(function (r) { return r.json(); })
            .then(function (dirs) {
                var list = document.getElementById('pt-design-directions-list');
                list.innerHTML = dirs.length === 0 ? '<p class="empty-state">No design directions yet.</p>' :
                    dirs.map(function (d) {
                        return '<div class="account-user-row" id="pt-dd-' + d.id + '">' +
                            '<div class="account-user-info"><span class="account-user-name">' + adminEsc(d.name) + '</span></div>' +
                            '<div class="account-user-actions">' +
                            '<button class="account-edit-btn pt-dd-edit" data-id="' + d.id + '" data-name="' + adminEsc(d.name) + '">Edit</button>' +
                            '<button class="account-delete-btn pt-dd-delete" data-id="' + d.id + '" data-name="' + adminEsc(d.name) + '">&times;</button>' +
                            '</div></div>';
                    }).join('');
                list.querySelectorAll('.pt-dd-delete').forEach(function (btn) {
                    btn.addEventListener('click', function () {
                        var name = this.dataset.name;
                        var id   = this.dataset.id;
                        showConfirm('Delete design direction "' + name + '"?', function () {
                            fetch('/admin/api/design-directions/' + id, { method: 'DELETE' })
                                .then(function (r) { return r.json(); })
                                .then(function (d) { if (d.success) { document.getElementById('pt-dd-' + id).remove(); } else { showToast(d.error, 'error'); } });
                        });
                    });
                });
                list.querySelectorAll('.pt-dd-edit').forEach(function (btn) {
                    btn.addEventListener('click', function () {
                        var id = this.dataset.id;
                        var row = document.getElementById('pt-dd-' + id);
                        var currentName = this.dataset.name;
                        row.innerHTML =
                            '<div class="pt-inline-edit">' +
                            '<input type="text" class="form-input pt-edit-name" value="' + adminEsc(currentName) + '" style="max-width:240px;">' +
                            '<button class="btn-primary pt-dd-save" data-id="' + id + '">Save</button>' +
                            '<button class="account-delete-btn pt-dd-cancel">Cancel</button>' +
                            '</div>';
                        row.querySelector('.pt-dd-save').addEventListener('click', function () {
                            var newName = row.querySelector('.pt-edit-name').value.trim();
                            if (!newName) return;
                            var saveBtn = this;
                            btnLoading(saveBtn);
                            fetch('/admin/api/design-directions/' + id, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: newName }) })
                                .then(function (r) { return r.json(); })
                                .then(function (d) {
                                    if (d.success || !d.error) { loadPTDesignDirections(); }
                                    else { showToast(d.error, 'error'); btnDone(saveBtn); }
                                })
                                .catch(function () { btnDone(saveBtn); });
                        });
                        row.querySelector('.pt-dd-cancel').addEventListener('click', function () { loadPTDesignDirections(); });
                    });
                });
            });
    }

    // ── CS Scopes ──
    // Options for the Client Servicing table's Scope dropdown. Deactivating hides
    // a scope from new picks; rows that use it keep its name. Data is owned by
    // the client_servicing module, so these calls use its routes.
    function loadPTCsScopes() {
        fetch('/client-servicing/scopes')
            .then(function (r) { return r.json(); })
            .then(function (scopes) {
                var list = document.getElementById('pt-cs-scopes-list');
                if (scopes.length === 0) {
                    list.innerHTML = '<p class="empty-state">No scopes yet.</p>';
                    return;
                }

                function rowHtml(scope) {
                    var toggleBtn = scope.active
                        ? '<button type="button" class="account-deactivate-btn pt-cs-scope-toggle" data-id="' + scope.id + '" data-active="true">Deactivate</button>'
                        : '<button type="button" class="account-reactivate-btn pt-cs-scope-toggle" data-id="' + scope.id + '" data-active="false">Reactivate</button>';
                    return '<div class="account-user-row' + (scope.active ? '' : ' account-user-row--deactivated') + '" id="pt-cs-scope-' + scope.id + '">' +
                        '<div class="account-user-info"><span class="account-user-name">' + adminEsc(scope.name) + '</span></div>' +
                        '<div class="account-user-actions">' +
                        '<button class="account-edit-btn pt-cs-scope-edit" data-id="' + scope.id + '" data-name="' + adminEsc(scope.name) + '">Edit</button>' +
                        toggleBtn +
                        '</div></div>';
                }

                var active = scopes.filter(function (s) { return s.active; });
                var inactive = scopes.filter(function (s) { return !s.active; });
                var html = active.map(rowHtml).join('');
                if (inactive.length) {
                    html += '<div class="accounts-group-label">Deactivated</div>' + inactive.map(rowHtml).join('');
                }
                list.innerHTML = html;

                list.querySelectorAll('.pt-cs-scope-toggle').forEach(function (btn) {
                    btn.addEventListener('click', function () {
                        var id = this.dataset.id;
                        var makeActive = this.dataset.active !== 'true';
                        fetch('/client-servicing/scopes/' + id, {
                            method: 'PATCH', headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ active: makeActive }),
                        })
                            .then(function (r) { return r.json(); })
                            .then(function (d) { if (!d.error) { loadPTCsScopes(); } else { showToast(d.error, 'error'); } });
                    });
                });

                list.querySelectorAll('.pt-cs-scope-edit').forEach(function (btn) {
                    btn.addEventListener('click', function () {
                        var id = this.dataset.id;
                        var row = document.getElementById('pt-cs-scope-' + id);
                        var currentName = this.dataset.name;
                        row.innerHTML =
                            '<div class="pt-inline-edit">' +
                            '<input type="text" class="form-input pt-edit-name" value="' + adminEsc(currentName) + '" style="max-width:240px;">' +
                            '<button class="btn-primary pt-cs-scope-save" data-id="' + id + '">Save</button>' +
                            '<button class="account-delete-btn pt-cs-scope-cancel">Cancel</button>' +
                            '</div>';
                        row.querySelector('.pt-cs-scope-save').addEventListener('click', function () {
                            var newName = row.querySelector('.pt-edit-name').value.trim();
                            if (!newName) return;
                            var saveBtn = this;
                            btnLoading(saveBtn);
                            fetch('/client-servicing/scopes/' + id, {
                                method: 'PATCH', headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ name: newName }),
                            })
                                .then(function (r) { return r.json(); })
                                .then(function (d) {
                                    if (d.success || !d.error) { loadPTCsScopes(); }
                                    else { showToast(d.error, 'error'); btnDone(saveBtn); }
                                })
                                .catch(function () { btnDone(saveBtn); });
                        });
                        row.querySelector('.pt-cs-scope-cancel').addEventListener('click', function () { loadPTCsScopes(); });
                    });
                });
            });
    }

    function populatePTDelClientFilter(types) {
        var seen = {};
        var clients = [];
        types.forEach(function (t) {
            if (t.client !== '—' && !seen[t.client]) {
                seen[t.client] = true;
                clients.push(t.client);
            }
        });
        clients.sort();
        var sel = document.getElementById('pt-filter-client');
        var prev = sel.value;
        sel.innerHTML = '<option value="">All Clients</option>' +
            clients.map(function (c) { return '<option value="' + adminEsc(c) + '">' + adminEsc(c) + '</option>'; }).join('');
        if (clients.indexOf(prev) !== -1) sel.value = prev; // keep the selection if still valid
    }

    function populatePTDelCustomerFilter(region) {
        var filtered = region
            ? ptAllDeliverableTypes.filter(function (t) { return t.region === region; })
            : ptAllDeliverableTypes;
        var seen = {};
        var customers = [];
        filtered.forEach(function (t) {
            if (t.customer !== '—' && !seen[t.customer]) {
                seen[t.customer] = true;
                customers.push(t.customer);
            }
        });
        customers.sort();
        var sel = document.getElementById('pt-filter-customer');
        var prev = sel.value;
        sel.innerHTML = '<option value="">All Customers</option>' +
            customers.map(function (c) { return '<option value="' + adminEsc(c) + '">' + adminEsc(c) + '</option>'; }).join('');
        if (customers.indexOf(prev) !== -1) sel.value = prev;
    }

    function filterPTDeliverables() {
        var client = document.getElementById('pt-filter-client').value;
        var region = document.getElementById('pt-filter-region').value;
        var customer = document.getElementById('pt-filter-customer').value;
        var filtered = ptAllDeliverableTypes.filter(function (t) {
            if (client && t.client !== client) return false;
            if (region && t.region !== region) return false;
            if (customer && t.customer !== customer) return false;
            return true;
        });
        renderPTDeliverableRows(filtered);
    }

    document.getElementById('pt-filter-client').addEventListener('change', filterPTDeliverables);
    document.getElementById('pt-filter-region').addEventListener('change', function () {
        populatePTDelCustomerFilter(this.value);
        filterPTDeliverables();
    });
    document.getElementById('pt-filter-customer').addEventListener('change', filterPTDeliverables);

    function renderPTDeliverableRows(types) {
        var list = document.getElementById('pt-deliverables-list');
        if (types.length === 0) {
            list.innerHTML = '<p class="empty-state">No deliverable types match.</p>';
            return;
        }
        list.innerHTML = types.map(function (t) {
            return '<div class="account-user-row" id="pt-del-' + t.id + '">' +
                '<div class="account-user-info">' +
                '<span class="account-user-name">' + adminEsc(t.name) + '</span>' +
                '<span class="account-user-role">' + adminEsc(t.client + ' · ' + t.customer + (t.is_custom ? ' · Custom' : '')) + '</span>' +
                '</div>' +
                '<div class="account-user-actions">' +
                '<button type="button" class="account-edit-btn" data-id="' + t.id + '">Edit</button>' +
                '<button type="button" class="account-delete-btn" data-id="' + t.id + '" data-name="' + adminEsc(t.name) + '">&times;</button>' +
                '</div></div>';
        }).join('');

        list.querySelectorAll('.account-delete-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var name = this.dataset.name;
                var id   = this.dataset.id;
                showConfirm('Delete "' + name + '"?', function () {
                    fetch('/admin/api/deliverable-types/' + id, { method: 'DELETE' })
                        .then(function (res) { return res.json(); })
                        .then(function (data) {
                            if (data.success) {
                                ptAllDeliverableTypes = ptAllDeliverableTypes.filter(function (t) { return String(t.id) !== String(id); });
                                document.getElementById('pt-del-' + id).remove();
                            } else { showToast(data.error || 'Could not delete.', 'error'); }
                        });
                });
            });
        });

        list.querySelectorAll('.account-edit-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var id = this.dataset.id;
                var type = ptAllDeliverableTypes.find(function (t) { return String(t.id) === String(id); });
                if (!type) return;
                var row = document.getElementById('pt-del-' + id);
                row.innerHTML =
                    '<div class="account-user-edit-form">' +
                    '<input type="text" class="form-input pt-del-name-input" value="' + adminEsc(type.name) + '">' +
                    '<div class="pt-discipline-checks">' +
                    // Values must match User.team casing exactly: the Deliverables
                    // roster finds designers by exact team string. The
                    // case-insensitive match still ticks lowercase values
                    // already stored, and saving rewrites them in this casing.
                    ['2D', '3D', 'Technical'].map(function (d) {
                        var checked = type.disciplines.some(function (existing) {
                            return existing.toLowerCase() === d.toLowerCase();
                        }) ? 'checked' : '';
                        return '<label><input type="checkbox" value="' + d + '" ' + checked + '> ' + d.toUpperCase() + '</label>';
                    }).join('') +
                    '</div>' +
                    // Per file: leave it, tick "remove", or choose a replacement.
                    (type.reference_image ?
                        '<img src="/static/deliverable-images/' + adminEsc(type.reference_image) + '" class="pt-del-image-preview" style="max-width:80px;max-height:80px;display:block;margin:6px 0;">' +
                        '<label style="font-size:0.85rem;"><input type="checkbox" class="pt-del-remove-image"> Remove current image</label>'
                        : '') +
                    '<label style="font-size:0.85rem;display:block;margin-top:4px;">Replace image: <input type="file" class="pt-del-image-input" accept="image/*"></label>' +
                    (type.template_filename ?
                        '<p style="font-size:0.85rem;margin:6px 0;">Current template: <code>' + adminEsc(type.template_filename) + '</code></p>' +
                        '<label style="font-size:0.85rem;"><input type="checkbox" class="pt-del-remove-template"> Remove current template</label>'
                        : '') +
                    '<label style="font-size:0.85rem;display:block;margin-top:4px;">Replace template (.ai): <input type="file" class="pt-del-template-input" accept=".ai"></label>' +
                    '<div class="account-edit-actions">' +
                    '<button type="button" class="btn-primary pt-del-save-btn">Save</button>' +
                    '<button type="button" class="account-cancel-edit-btn">Cancel</button>' +
                    '</div></div>';
                    
                row.querySelector('.account-cancel-edit-btn').addEventListener('click', function () {
                    filterPTDeliverables();
                });
                row.querySelector('.pt-del-save-btn').addEventListener('click', function () {
                    var name = row.querySelector('.pt-del-name-input').value.trim();
                    var disciplines = Array.from(
                        row.querySelectorAll('.pt-discipline-checks input:checked')
                    ).map(function (cb) { return cb.value; });
                    if (!name) { showToast('Name is required.', 'warning'); return; }
                    var saveBtn = this;
                    btnLoading(saveBtn);

                    function savePTDeliverableType(referenceImage, imageKeyProvided, templateFilename, templateKeyProvided) {
                        var body = { name: name, disciplines: disciplines };
                        if (imageKeyProvided) body.reference_image = referenceImage;
                        if (templateKeyProvided) body.template_filename = templateFilename;

                        fetch('/admin/api/deliverable-types/' + id, {
                            method: 'PATCH',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(body)
                        })
                            .then(function (res) { return res.json(); })
                            .then(function (data) {
                                if (data.success) {
                                    var idx = ptAllDeliverableTypes.findIndex(function (t) { return String(t.id) === String(id); });
                                    if (idx !== -1) {
                                        ptAllDeliverableTypes[idx].name = name;
                                        ptAllDeliverableTypes[idx].disciplines = disciplines;
                                        if (imageKeyProvided) ptAllDeliverableTypes[idx].reference_image = referenceImage;
                                        if (templateKeyProvided) ptAllDeliverableTypes[idx].template_filename = templateFilename;
                                    }
                                    filterPTDeliverables();
                                } else {
                                    showToast(data.error || 'Could not save.', 'error');
                                    btnDone(saveBtn);
                                }
                            })
                            .catch(function () { btnDone(saveBtn); });
                    }

                    var imageFile = row.querySelector('.pt-del-image-input').files[0];
                    var imageRemoveEl = row.querySelector('.pt-del-remove-image');
                    var templateFile = row.querySelector('.pt-del-template-input').files[0];
                    var templateRemoveEl = row.querySelector('.pt-del-remove-template');

                    Promise.all([
                        resolveFileField(imageFile, imageRemoveEl && imageRemoveEl.checked, '/projects/deliverable-types/upload-image'),
                        resolveFileField(templateFile, templateRemoveEl && templateRemoveEl.checked, '/admin/api/deliverable-types/upload-template')
                    ]).then(function (results) {
                        var referenceImage = results[0];
                        var templateFilename = results[1];
                        savePTDeliverableType(referenceImage, referenceImage !== undefined, templateFilename, templateFilename !== undefined);
                    }).catch(function (err) {
                        showToast(typeof err === 'string' ? err : 'Something went wrong uploading a file.', 'error');
                        btnDone(saveBtn);
                    });
                });
            });
        });
    }

    // ── Activity Log ───────────────────────────────────────────────

    function loadActivitySection() {
        var search = document.getElementById('activity-search').value.trim();
        var from = document.getElementById('activity-from').value;
        var to = document.getElementById('activity-to').value;
        var category = document.getElementById('activity-category').value;

        var params = new URLSearchParams();
        if (search) params.append('search', search);
        if (from) params.append('from', from);
        if (to) params.append('to', to);
        // 'all' means no filter, so the param is left off.
        if (category && category !== 'all') params.append('category', category);

        var url = '/admin/api/activity' + (params.toString() ? '?' + params.toString() : '');

        fetch(url)
            .then(function (res) { return res.json(); })
            .then(function (entries) {
                var list = document.getElementById('activity-log-list');
                if (entries.length === 0) {
                    list.innerHTML = '<p class="empty-state">No activity found.</p>';
                    return;
                }
                list.innerHTML = entries.map(function (e) {
                    return '<div class="activity-entry" id="activity-' + e.id + '">' +
                        '<div class="activity-entry-body">' +
                        '<span class="activity-description">' + adminEsc(e.description) + '</span>' +
                        '<span class="activity-meta">' + adminEsc(e.user + ' · ' + e.created_at) + '</span>' +
                        '</div>' +
                        '<button type="button" class="account-delete-btn" data-id="' + e.id + '">&times;</button>' +
                        '</div>';
                }).join('');

                list.querySelectorAll('.account-delete-btn').forEach(function (btn) {
                    btn.addEventListener('click', function () {
                        var id = this.dataset.id;
                        fetch('/admin/api/activity/' + id, { method: 'DELETE' })
                            .then(function (res) { return res.json(); })
                            .then(function (data) {
                                if (data.success) {
                                    document.getElementById('activity-' + id).remove();
                                }
                            });
                    });
                });
            });
    }

    if (document.getElementById('activity-search-btn')) {

        document.getElementById('activity-search-btn').addEventListener('click', function () {
            loadActivitySection();
        });

        document.getElementById('activity-reset-btn').addEventListener('click', function () {
            document.getElementById('activity-search').value = '';
            document.getElementById('activity-from').value = '';
            document.getElementById('activity-to').value = '';
            document.getElementById('activity-category').value = 'all';
            loadActivitySection();
        });

        // Category filters on change, without Search.
        document.getElementById('activity-category').addEventListener('change', function () {
            loadActivitySection();
        });

        document.getElementById('activity-export-btn').addEventListener('click', function () {
            var exportBtn = this;
            btnLoading(exportBtn);
            fetch('/admin/api/activity/export', { method: 'POST' })
                .then(function (res) {
                    if (!res.ok) {
                        return res.json().then(function (d) {
                            showToast(d.error || 'Export failed.', 'error');
                            btnDone(exportBtn);
                        });
                    }
                    var disposition = res.headers.get('Content-Disposition');
                    var filename = 'activity-log.txt';
                    if (disposition) {
                        var match = disposition.match(/filename="(.+)"/);
                        if (match) filename = match[1];
                    }
                    return res.blob().then(function (blob) {
                        var url = URL.createObjectURL(blob);
                        var a = document.createElement('a');
                        a.href = url;
                        a.download = filename;
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                        URL.revokeObjectURL(url);
                        btnDone(exportBtn);
                    });
                })
                .catch(function () { btnDone(exportBtn); });
        });

        document.getElementById('activity-wipe-btn').addEventListener('click', function () {
            showConfirm('Wipe the entire activity log? This cannot be undone.', function () {
                fetch('/admin/api/activity/clear', { method: 'POST' })
                    .then(function (res) { return res.json(); })
                    .then(function (data) {
                        if (data.success) {
                            loadActivitySection();
                        } else {
                            showToast('Could not wipe log.', 'error');
                        }
                    });
            });
        });

    }

// ═══════════════════════════════════════════════════════════════════════
// ── Achievements admin panel ────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════
// Two sub-tabs: Achievements (drag-reorderable category accordion + Add/Edit
// modal) and Borders (list + preview). Needs the global `Sortable`, loaded
// from a CDN in base.html.

// Last fetch, cached so the Add/Edit modal can fill its selects without a round trip.
var achCategoriesData = [];
var achBordersData = [];

function loadAchievementsSection() {
    var activeAchTab = document.querySelector('.ach-tab-btn.active');
    var tab = activeAchTab ? activeAchTab.dataset.ach : 'categories';
    if (tab === 'categories') loadAchievementCategories();
    else loadAchievementBorders();
}

// ── Achievements / Borders sub-tab toggle ───────────────────────────────
document.querySelectorAll('.ach-tab-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
        document.querySelectorAll('.ach-tab-btn').forEach(function (b) { b.classList.remove('active'); });
        document.querySelectorAll('.ach-panel').forEach(function (p) { p.classList.add('hidden'); });
        this.classList.add('active');
        var panel = document.getElementById('ach-panel-' + this.dataset.ach);
        if (panel) panel.classList.remove('hidden');
        if (this.dataset.ach === 'categories') loadAchievementCategories();
        else loadAchievementBorders();
    });
});

// ─────────────────────────── Categories + Achievements ──────────────────

function loadAchievementCategories() {
    var list = document.getElementById('ach-categories-list');
    if (!list) return;
    fetch('/admin/api/achievement-categories')
        .then(function (r) { return r.json(); })
        .then(function (categories) {
            achCategoriesData = categories;
            document.getElementById('save-ach-order-btn').classList.add('hidden');
            renderAchievementCategories(categories);
        });
}

var TRIGGER_EVENT_LABELS = {
    project_submitted: 'Project Submitted',
    project_approved: 'Project Approved',
    bug_submitted: 'Bug Report Submitted',
    feature_submitted: 'Feature Request Submitted',
    blog_comment: 'Blog Comment Posted',
    upvote_given: 'Feature Upvote Given',
    user_login: 'User Logged In'
};

function renderAchievementCategories(categories) {
    var list = document.getElementById('ach-categories-list');

    if (categories.length === 0) {
        list.innerHTML = '<p class="empty-state">No categories yet — add one above to get started.</p>';
        return;
    }

    list.innerHTML = categories.map(function (cat) {
        var achievementRows = cat.achievements.map(function (a) {
            var metaBits = [TRIGGER_EVENT_LABELS[a.trigger_event] || a.trigger_event, 'threshold ' + a.threshold];
            if (a.is_hidden) metaBits.push('hidden');
            if (a.reward_title) metaBits.push('title: ' + a.reward_title);
            return '<div class="ach-achievement-row" data-id="' + a.id + '">' +
                '<span class="ach-drag-handle" title="Drag to reorder">⠿</span>' +
                (a.badge_url
                    ? '<img src="' + adminEsc(a.badge_url) + '" class="ach-achievement-badge-thumb" alt="">'
                    : '<span class="ach-achievement-badge-thumb ach-achievement-badge-thumb--empty">🏆</span>') +
                '<div class="ach-achievement-info">' +
                '<span class="ach-achievement-name">' + adminEsc(a.name) + '</span>' +
                '<span class="ach-achievement-meta">' + adminEsc(metaBits.join(' · ')) + '</span>' +
                '</div>' +
                '<div class="account-user-actions">' +
                '<button type="button" class="account-edit-btn ach-edit-btn" data-id="' + a.id + '">Edit</button>' +
                '<button type="button" class="account-delete-btn ach-delete-btn" data-id="' + a.id + '" data-name="' + adminEsc(a.name) + '">&times;</button>' +
                '</div></div>';
        }).join('');

        return '<div class="ach-category-card" data-cat-id="' + cat.id + '">' +
            '<div class="ach-category-header">' +
            '<span class="ach-category-drag-handle" title="Drag to reorder">⠿</span>' +
            '<span class="ach-category-display">' +
            (cat.icon ? '<span class="ach-category-icon">' + adminEsc(cat.icon) + '</span>' : '') +
            '<span class="ach-category-name">' + adminEsc(cat.name) + '</span>' +
            '</span>' +
            '<span class="ach-category-edit-form hidden">' +
            '<input type="text" class="ach-cat-edit-icon admin-input" placeholder="icon emoji" value="' + adminEsc(cat.icon) + '" maxlength="4" style="width:3.5rem">' +
            '<input type="text" class="ach-cat-edit-name admin-input" placeholder="Category name" value="' + adminEsc(cat.name) + '" style="flex:1;min-width:8rem">' +
            '<button type="button" class="accounts-add-btn ach-cat-save-btn" data-id="' + cat.id + '">Save</button>' +
            '<button type="button" class="account-cancel-btn ach-cat-cancel-btn">Cancel</button>' +
            '</span>' +
            '<div class="ach-category-actions">' +
            '<button type="button" class="account-edit-btn ach-category-edit-btn" data-id="' + cat.id + '">Edit</button>' +
            '<button type="button" class="ach-category-toggle-btn" data-cat-id="' + cat.id + '">▾</button>' +
            '<button type="button" class="account-delete-btn ach-category-delete" data-id="' + cat.id + '" data-name="' + adminEsc(cat.name) + '">&times;</button>' +
            '</div>' +
            '</div>' +
            '<div class="ach-category-body" id="ach-category-body-' + cat.id + '">' +
            '<button type="button" class="accounts-add-btn ach-add-achievement-btn" data-cat-id="' + cat.id + '">+ Add Achievement</button>' +
            '<div class="ach-achievement-list" data-cat-id="' + cat.id + '">' + (achievementRows || '<p class="empty-state">No achievements in this category yet.</p>') + '</div>' +
            '</div></div>';
    }).join('');

    attachAchievementCategoryHandlers();
    initAchievementSortables();
}

function attachAchievementCategoryHandlers() {
    // Collapse/expand is client-only.
    document.querySelectorAll('.ach-category-toggle-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var body = document.getElementById('ach-category-body-' + this.dataset.catId);
            body.classList.toggle('hidden');
            this.textContent = body.classList.contains('hidden') ? '▸' : '▾';
        });
    });

    // The server refuses to delete a category that still has achievements
    // (admin_achievements.py); its error message is shown as the reason.
    document.querySelectorAll('.ach-category-delete').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var name = this.dataset.name;
            var id = this.dataset.id;
            showConfirm('Delete category "' + name + '"?', function () {
                fetch('/admin/api/achievement-categories/' + id, { method: 'DELETE' })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (data.success) loadAchievementCategories();
                        else showToast(data.error || 'Could not delete category.', 'error');
                    });
            });
        });
    });

    // Edit category (inline form)
    document.querySelectorAll('.ach-category-edit-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var card = this.closest('.ach-category-card');
            card.querySelector('.ach-category-display').classList.add('hidden');
            card.querySelector('.ach-category-actions').classList.add('hidden');
            card.querySelector('.ach-category-edit-form').classList.remove('hidden');
            card.querySelector('.ach-cat-edit-name').focus();
        });
    });

    // Cancel edit
    document.querySelectorAll('.ach-cat-cancel-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var card = this.closest('.ach-category-card');
            var catId = card.dataset.catId;
            var cat = achCategoriesData.find(function (c) { return String(c.id) === String(catId); });
            if (cat) {
                card.querySelector('.ach-cat-edit-name').value = cat.name;
                card.querySelector('.ach-cat-edit-icon').value = cat.icon || '';
            }
            card.querySelector('.ach-category-edit-form').classList.add('hidden');
            card.querySelector('.ach-category-display').classList.remove('hidden');
            card.querySelector('.ach-category-actions').classList.remove('hidden');
        });
    });

    // Save category edit
    document.querySelectorAll('.ach-cat-save-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var card = this.closest('.ach-category-card');
            var catId = this.dataset.id;
            var newName = card.querySelector('.ach-cat-edit-name').value.trim();
            var newIcon = card.querySelector('.ach-cat-edit-icon').value.trim();
            if (!newName) { showToast('Category name cannot be empty.', 'error'); return; }
            btnLoading(btn);
            fetch('/admin/api/achievement-categories/' + catId, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: newName, icon: newIcon })
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.success) { showToast(data.error || 'Could not save.', 'error'); btnDone(btn); return; }
                    var cat = achCategoriesData.find(function (c) { return String(c.id) === String(catId); });
                    if (cat) { cat.name = data.category.name; cat.icon = data.category.icon; }
                    var displayEl = card.querySelector('.ach-category-display');
                    displayEl.innerHTML = (data.category.icon ? '<span class="ach-category-icon">' + adminEsc(data.category.icon) + '</span>' : '') +
                        '<span class="ach-category-name">' + adminEsc(data.category.name) + '</span>';
                    // Keep the delete confirm's name in step with the rename.
                    var deleteBtn = card.querySelector('.ach-category-delete');
                    if (deleteBtn) deleteBtn.dataset.name = data.category.name;
                    card.querySelector('.ach-category-edit-form').classList.add('hidden');
                    card.querySelector('.ach-category-display').classList.remove('hidden');
                    card.querySelector('.ach-category-actions').classList.remove('hidden');
                    btnDone(btn);
                    showToast('Category updated.', 'success');
                })
                .catch(function () { btnDone(btn); showToast('Network error.', 'error'); });
        });
    });

    // "+ Add Achievement" opens the modal in create mode, preset to this category.
    document.querySelectorAll('.ach-add-achievement-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            openAchievementModal('create', null, this.dataset.catId);
        });
    });

    document.querySelectorAll('.ach-edit-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var id = btn.dataset.id;
            var achievement = null;
            achCategoriesData.forEach(function (cat) {
                cat.achievements.forEach(function (a) { if (String(a.id) === String(id)) achievement = a; });
            });
            if (achievement) openAchievementModal('edit', achievement, achievement.category_id);
        });
    });

    document.querySelectorAll('.ach-delete-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var name = this.dataset.name;
            var id = this.dataset.id;
            showConfirm('Delete achievement "' + name + '"? Everyone\'s progress toward it will be lost too.', function () {
                fetch('/admin/api/achievements/' + id, { method: 'DELETE' })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (data.success) loadAchievementCategories();
                        else showToast(data.error || 'Could not delete achievement.', 'error');
                    });
            });
        });
    });
}

// One Sortable for the category list, plus one per category's achievement
// list. Achievements cannot move between categories: that would need a
// category_id change, and the reorder routes only set display_order.
function initAchievementSortables() {
    var categoriesList = document.getElementById('ach-categories-list');
    new Sortable(categoriesList, {
        handle: '.ach-category-drag-handle',
        animation: 150,
        onEnd: function () { markAchOrderDirty(); }
    });

    document.querySelectorAll('.ach-achievement-list').forEach(function (list) {
        new Sortable(list, {
            handle: '.ach-drag-handle',
            animation: 150,
            onEnd: function () { markAchOrderDirty(); }
        });
    });
}

function markAchOrderDirty() {
    document.getElementById('save-ach-order-btn').classList.remove('hidden');
}

// Save Order: reads the live DOM order and sends one reorder request for the
// categories plus one per achievement list.
document.getElementById('save-ach-order-btn').addEventListener('click', function () {
    var saveBtn = this;
    btnLoading(saveBtn);

    var categoryIds = Array.from(document.querySelectorAll('.ach-category-card')).map(function (card) {
        return card.dataset.catId;
    });

    var achievementReorders = Array.from(document.querySelectorAll('.ach-achievement-list')).map(function (list) {
        var ids = Array.from(list.querySelectorAll('.ach-achievement-row')).map(function (row) { return row.dataset.id; });
        return { achievement_ids: ids };
    }).filter(function (payload) { return payload.achievement_ids.length > 0; });

    var requests = [
        fetch('/admin/api/achievement-categories/reorder', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ category_ids: categoryIds })
        })
    ].concat(achievementReorders.map(function (payload) {
        return fetch('/admin/api/achievements/reorder', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
    }));

    Promise.all(requests)
        .then(function (responses) {
            // fetch only rejects on network errors; an HTTP error must fail the save too.
            if (!responses.every(function (r) { return r.ok; })) throw new Error('reorder failed');
            btnDone(saveBtn);
            saveBtn.classList.add('hidden');
        })
        .catch(function () {
            btnDone(saveBtn);
            showToast('Could not save order — please try again.', 'error');
        });
});

// ── Add Category form ────────────────────────────────────────────────────
var addAchCategoryToggle = document.getElementById('add-ach-category-toggle');
var addAchCategoryForm = document.getElementById('add-ach-category-form');
if (addAchCategoryToggle) {
    addAchCategoryToggle.addEventListener('click', function () {
        addAchCategoryForm.classList.toggle('hidden');
    });
    document.getElementById('add-ach-category-cancel').addEventListener('click', function () {
        addAchCategoryForm.classList.add('hidden');
        addAchCategoryForm.reset();
    });
    addAchCategoryForm.addEventListener('submit', function (e) {
        e.preventDefault();
        var name = document.getElementById('new-ach-category-name').value.trim();
        var icon = document.getElementById('new-ach-category-icon').value.trim();
        if (!name) return;
        var submitBtn = addAchCategoryForm.querySelector('button[type="submit"]');
        btnLoading(submitBtn);
        fetch('/admin/api/achievement-categories', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, icon: icon })
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    addAchCategoryForm.reset();
                    addAchCategoryForm.classList.add('hidden');
                    loadAchievementCategories();
                } else {
                    showToast(data.error || 'Could not create category.', 'error');
                    btnDone(submitBtn);
                }
            })
            .catch(function () { btnDone(submitBtn); });
    });
}

// ── Add/Edit Achievement modal ──────────────────────────────────────────
var achievementModal = document.getElementById('achievement-modal');
var achievementModalTitle = document.getElementById('achievement-modal-title');
var achFormBadgeFile = document.getElementById('ach-form-badge-file');
var achFormBadgePreview = document.getElementById('ach-form-badge-preview');

function populateAchievementCategoryDropdown(selectedCategoryId) {
    var sel = document.getElementById('ach-form-category');
    sel.innerHTML = achCategoriesData.map(function (cat) {
        return '<option value="' + cat.id + '"' + (String(cat.id) === String(selectedCategoryId) ? ' selected' : '') + '>' + adminEsc(cat.name) + '</option>';
    }).join('');
}

function populateAchievementBorderDropdown(selectedBorderId) {
    var sel = document.getElementById('ach-form-border');
    sel.innerHTML = '<option value="">— None —</option>' + achBordersData.map(function (b) {
        return '<option value="' + b.id + '"' + (String(b.id) === String(selectedBorderId) ? ' selected' : '') + '>' + adminEsc(b.name) + '</option>';
    }).join('');
}

function openAchievementModal(mode, achievement, categoryId) {
    achievementModal.dataset.mode = mode;
    achievementModal.dataset.editingId = achievement ? achievement.id : '';
    achievementModalTitle.textContent = mode === 'edit' ? 'Edit Achievement' : 'Add Achievement';

    // Borders load lazily; the Borders tab may not have been opened yet.
    var ensureBorders = achBordersData.length > 0
        ? Promise.resolve()
        : fetch('/admin/api/achievement-borders').then(function (r) { return r.json(); }).then(function (b) { achBordersData = b; });

    ensureBorders.then(function () {
        populateAchievementCategoryDropdown(categoryId);
        populateAchievementBorderDropdown(achievement ? achievement.border_id : '');

        document.getElementById('ach-form-name').value = achievement ? achievement.name : '';
        document.getElementById('ach-form-description').value = achievement ? (achievement.description || '') : '';
        document.getElementById('ach-form-trigger').value = achievement ? achievement.trigger_event : 'project_submitted';
        document.getElementById('ach-form-threshold').value = achievement ? achievement.threshold : 1;
        document.getElementById('ach-form-hidden').checked = achievement ? achievement.is_hidden : false;
        document.getElementById('ach-form-animated').checked = achievement ? achievement.badge_type === 'animated' : false;
        document.getElementById('ach-form-reward-title').value = achievement ? (achievement.reward_title || '') : '';
        document.getElementById('ach-form-title-animated').checked = achievement ? achievement.title_animated : false;
        achFormBadgeFile.value = '';

        if (achievement && achievement.badge_url) {
            achFormBadgePreview.src = achievement.badge_url;
            achFormBadgePreview.classList.remove('hidden');
        } else {
            achFormBadgePreview.classList.add('hidden');
        }

        achievementModal.classList.remove('hidden');
        if (window.helixPolling) window.helixPolling.pause(); // no polling refresh while the modal is open
    });
}

function closeAchievementModal() {
    achievementModal.classList.add('hidden');
    if (window.helixPolling) window.helixPolling.resume();
}

document.getElementById('achievement-modal-cancel-btn').addEventListener('click', closeAchievementModal);

document.getElementById('achievement-modal-save-btn').addEventListener('click', function () {
    var saveBtn = this;
    var mode = achievementModal.dataset.mode;
    var editingId = achievementModal.dataset.editingId;

    var name = document.getElementById('ach-form-name').value.trim();
    var categoryId = document.getElementById('ach-form-category').value;
    var threshold = document.getElementById('ach-form-threshold').value;

    if (!name || !categoryId || !threshold) {
        showToast('Name, category, and threshold are required.', 'warning');
        return;
    }

    // Multipart, since a badge file may be attached. Booleans go as
    // 'true'/'false' strings; admin_achievements.py compares against 'true'.
    var formData = new FormData();
    formData.append('name', name);
    formData.append('description', document.getElementById('ach-form-description').value.trim());
    formData.append('category_id', categoryId);
    formData.append('trigger_event', document.getElementById('ach-form-trigger').value);
    formData.append('threshold', threshold);
    formData.append('is_hidden', document.getElementById('ach-form-hidden').checked ? 'true' : 'false');
    formData.append('badge_type', document.getElementById('ach-form-animated').checked ? 'animated' : 'static');
    formData.append('reward_title', document.getElementById('ach-form-reward-title').value.trim());
    formData.append('title_animated', document.getElementById('ach-form-title-animated').checked ? 'true' : 'false');
    formData.append('border_id', document.getElementById('ach-form-border').value);
    if (achFormBadgeFile.files[0]) formData.append('badge_file', achFormBadgeFile.files[0]);

    var url = mode === 'edit' ? '/admin/api/achievements/' + editingId : '/admin/api/achievements';
    var method = mode === 'edit' ? 'PATCH' : 'POST';

    btnLoading(saveBtn);
    fetch(url, { method: method, body: formData })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            btnDone(saveBtn);
            if (!data.success) { showToast(data.error || 'Could not save achievement.', 'error'); return; }
            closeAchievementModal();
            loadAchievementCategories();
        })
        .catch(function () { btnDone(saveBtn); });
});

// ─────────────────────────── Borders tab ────────────────────────────────

function loadAchievementBorders() {
    var list = document.getElementById('ach-borders-list');
    if (!list) return;
    fetch('/admin/api/achievement-borders')
        .then(function (r) { return r.json(); })
        .then(function (borders) {
            achBordersData = borders;
            renderAchievementBorders(borders);
        });
}

function renderAchievementBorders(borders) {
    var list = document.getElementById('ach-borders-list');
    if (borders.length === 0) {
        list.innerHTML = '<p class="empty-state">No borders yet — add one above.</p>';
        return;
    }
    list.innerHTML = borders.map(function (b) {
        return '<div class="account-user-row" id="ach-border-' + b.id + '">' +
            // Preview applies the saved css_class, so a mistyped class is visible at once.
            '<div class="ach-border-preview ' + adminEsc(b.css_class) + '"></div>' +
            '<div class="account-user-info">' +
            '<span class="account-user-name">' + adminEsc(b.name) + '</span>' +
            '<span class="account-user-role">' + adminEsc(b.css_class) + '</span>' +
            '</div>' +
            '<div class="account-user-actions">' +
            '<button type="button" class="account-delete-btn" data-id="' + b.id + '" data-name="' + adminEsc(b.name) + '">&times;</button>' +
            '</div></div>';
    }).join('');

    list.querySelectorAll('.account-delete-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var name = this.dataset.name;
            var id = this.dataset.id;
            showConfirm('Delete border "' + name + '"?', function () {
                fetch('/admin/api/achievement-borders/' + id, { method: 'DELETE' })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (data.success) document.getElementById('ach-border-' + id).remove();
                        else showToast(data.error || 'Could not delete border.', 'error');
                    });
            });
        });
    });
}

var addAchBorderToggle = document.getElementById('add-ach-border-toggle');
var addAchBorderForm = document.getElementById('add-ach-border-form');
if (addAchBorderToggle) {
    addAchBorderToggle.addEventListener('click', function () {
        addAchBorderForm.classList.toggle('hidden');
    });
    document.getElementById('add-ach-border-cancel').addEventListener('click', function () {
        addAchBorderForm.classList.add('hidden');
        addAchBorderForm.reset();
    });
    addAchBorderForm.addEventListener('submit', function (e) {
        e.preventDefault();
        var name = document.getElementById('new-ach-border-name').value.trim();
        var cssClass = document.getElementById('new-ach-border-class').value.trim();
        if (!name || !cssClass) return;
        var submitBtn = addAchBorderForm.querySelector('button[type="submit"]');
        btnLoading(submitBtn);
        fetch('/admin/api/achievement-borders', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, css_class: cssClass })
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    addAchBorderForm.reset();
                    addAchBorderForm.classList.add('hidden');
                    loadAchievementBorders();
                } else {
                    showToast(data.error || 'Could not create border.', 'error');
                    btnDone(submitBtn);
                }
            })
            .catch(function () { btnDone(submitBtn); });
    });
}
