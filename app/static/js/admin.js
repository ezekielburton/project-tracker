// admin.js — Vitamin-E
// Admin panel trigger/emulation badge (global, header) + all admin panel section
// functions: accounts, clients, customers, projects, deliverable/design types,
// activity log, reference file uploads.
// Depends on: showToast() — defined in main.js.
// Loaded after main.js.

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
            if (sectionName === 'achievements') loadAchievementsSection(); // Phase 7 — see bottom of this file

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
                        allUsers = users;
                        renderUserList(users);
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
                '<span class="emulate-user-name">' + user.name + '</span>' +
                '<span class="emulate-user-role">' + user.role + '</span>' +
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
                return u.name.toLowerCase().includes(query) || u.role.toLowerCase().includes(query);
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
                '<span class="badge-user-name">' + user.name + '</span>' +
                '<span class="badge-user-role">' + user.role + '</span>' +
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
                            badgeUsers = users;
                            renderBadgeUserList(users);
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
                return u.name.toLowerCase().includes(query) || u.role.toLowerCase().includes(query);
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
    var newUserRole = document.getElementById('new-user-role');
    var newUserTeam = document.getElementById('new-user-team');

    function loadAccountsSection() {
        if (!accountsUserList) return;
        fetch('/admin/api/users')
            .then(function (r) { return r.json(); })
            .then(function (users) {
                accountsUserList.innerHTML = '';

                var groups = [
                    { label: 'CS & Admin', filter: function (u) { return u.role === 'cs' || u.role === 'admin'; } },
                    { label: 'Management', filter: function (u) { return u.role === 'management'; } },
                    { label: '2D Team', filter: function (u) { return u.team === '2D'; } },
                    { label: '3D Team', filter: function (u) { return u.team === '3D'; } },
                    { label: 'Technical', filter: function (u) { return u.team === 'Technical'; } }
                ];

                groups.forEach(function (group) {
                    var members = users.filter(group.filter);
                    if (members.length === 0) return;

                    var heading = document.createElement('p');
                    heading.className = 'accounts-group-label';
                    heading.textContent = group.label;
                    accountsUserList.appendChild(heading);

                    members.forEach(function (user) {
                        var row = document.createElement('div');
                        row.className = 'account-user-row';
                        row.dataset.id = user.id;
                        row.innerHTML = renderAccountDisplay(user);
                        accountsUserList.appendChild(row);
                        attachRowActions(row, user);
                    });
                });

                if (accountsUserList.children.length === 0) {
                    accountsUserList.innerHTML = '<p class="no-notifications">No users found</p>';
                }
            });
    }

    function renderAccountDisplay(user) {
        var teamTag = user.team ? '<span class="account-user-team">' + user.team + '</span>' : '';
        return '<div class="account-user-info">' +
            '<span class="account-user-name">' + user.name + '</span>' +
            '<span class="account-user-role">' + user.role + '</span>' +
            teamTag +
            '</div>' +
            '<div class="account-user-actions">' +
            '<button type="button" class="account-edit-btn" data-name="' + user.name + '" data-role="' + user.role + '" data-team="' + (user.team || '') + '">Edit</button>' +
            '<button type="button" class="account-reset-btn" data-name="' + user.name + '">&#8635;</button>' +
            '<button type="button" class="account-delete-btn" data-name="' + user.name + '">&times;</button>' +
            '</div>';
    }

    function renderAccountEdit(user) {
        var roleOptions = ['cs', 'designer', 'team_lead', 'management', 'admin'].map(function (r) {
            return '<option value="' + r + '"' + (user.role === r ? ' selected' : '') + '>' + r + '</option>';
        }).join('');
        var teamOptions = ['2D', '3D', 'Technical'].map(function (t) {
            return '<option value="' + t + '"' + (user.team === t ? ' selected' : '') + '>' + t + '</option>';
        }).join('');
        var teamHidden = (user.role === 'designer' || user.role === 'team_lead') ? '' : ' hidden';
        return '<div class="account-user-edit-form">' +
            '<input type="text" class="form-input edit-name" value="' + user.name + '" placeholder="Full name">' +
            '<input type="email" class="form-input edit-email" value="' + (user.email || '') + '" placeholder="Email">' +
            '<select class="form-input edit-role">' + roleOptions + '</select>' +
            '<select class="form-input edit-team' + teamHidden + '"><option value="">Select team...</option>' + teamOptions + '</select>' +
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
        var editRole = row.querySelector('.edit-role');

        if (editBtn) {
            editBtn.addEventListener('click', function () {
                row.innerHTML = renderAccountEdit(user);
                attachRowActions(row, user);
            });
        }

        if (editRole) {
            editRole.addEventListener('change', function () {
                var teamField = row.querySelector('.edit-team');
                if (this.value === 'designer' || this.value === 'team_lead') {
                    teamField.classList.remove('hidden');
                } else {
                    teamField.classList.add('hidden');
                }
            });
        }

        if (saveBtn) {
            saveBtn.addEventListener('click', function () {
                var name = row.querySelector('.edit-name').value.trim();
                var email = row.querySelector('.edit-email').value.trim();
                var role = row.querySelector('.edit-role').value;
                var team = row.querySelector('.edit-team').value;
                var password = row.querySelector('.edit-password').value.trim();
                btnLoading(saveBtn);
                fetch('/admin/api/users/' + user.id, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: name, email: email, role: role, team: team, password: password })
                })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (data.success) {
                            row.innerHTML = renderAccountDisplay(data.user);
                            attachRowActions(row, data.user);
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
                showConfirm('Reset password for ' + user.name + ' to Vitamin2026!?', function () {
                    fetch('/admin/api/users/' + user.id + '/reset-password', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' }
                    })
                        .then(function (r) { return r.json(); })
                        .then(function (data) {
                            if (data.success) {
                                resetBtn.textContent = '✓';
                                setTimeout(function () { resetBtn.innerHTML = '&#8635;'; }, 2000);
                            }
                        });
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

    if (addUserToggle) {
        addUserToggle.addEventListener('click', function () {
            addUserForm.classList.toggle('hidden');
        });
    }

    if (addUserCancel) {
        addUserCancel.addEventListener('click', function () {
            addUserForm.classList.add('hidden');
            addUserForm.reset();
            newUserTeam.classList.add('hidden');
        });
    }

    if (newUserRole) {
        newUserRole.addEventListener('change', function () {
            if (this.value === 'designer' || this.value === 'team_lead') {
                newUserTeam.classList.remove('hidden');
            } else {
                newUserTeam.classList.add('hidden');
            }
        });
    }

    if (addUserForm) {
        addUserForm.addEventListener('submit', function (e) {
            e.preventDefault();
            var name = document.getElementById('new-user-name').value.trim();
            var email = document.getElementById('new-user-email').value.trim();
            var password = document.getElementById('new-user-password').value.trim();
            var role = newUserRole.value;
            var team = newUserTeam.value;
            var submitBtn = addUserForm.querySelector('button[type="submit"]');
            btnLoading(submitBtn);
            fetch('/admin/api/users', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: name, email: email, password: password, role: role, team: team })
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.success) {
                        addUserForm.reset();
                        newUserTeam.classList.add('hidden');
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
            '<span class="account-user-name">' + sound.name + '</span>' +
            '<audio controls src="' + sound.url + '" style="height:28px;"></audio>' +
            '</div>' +
            '<div class="account-user-actions">' +
            '<button type="button" class="account-delete-btn" data-id="' + sound.id + '" data-name="' + sound.name + '">&times;</button>' +
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

        // multipart/form-data — FormData handles the file automatically,
        // unlike the JSON.stringify() pattern used for other admin forms.
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
                loadSoundsSection(); // simplest way to show the new row in the same sorted order as a fresh page load
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
                        '<span class="account-user-name">' + c.name + '</span>' +
                        '<div class="account-user-actions">' +
                        '<button type="button" class="account-delete-btn" data-id="' + c.id + '" data-name="' + c.name + '">&times;</button>' +
                        '</div></div>';
                }).join('');
                list.querySelectorAll('.account-delete-btn').forEach(function (btn) {
                    btn.addEventListener('click', function () {
                        /* Capture dataset values before the async modal opens — 'this' won't survive the callback. */
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
                    html += '<div class="accounts-group-label">' + region.charAt(0).toUpperCase() + region.slice(1) + '</div>';
                    grouped[region].forEach(function (c) {
                        html += '<div class="account-user-row" id="pt-customer-' + c.id + '">' +
                            '<span class="account-user-name">' + c.name + '</span>' +
                            '<div class="account-user-actions">' +
                            '<button type="button" class="account-delete-btn" data-id="' + c.id + '" data-name="' + c.name + '">&times;</button>' +
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
                    return '<div class="account-user-row" id="pt-project-' + p.id + '">' +
                        '<div class="account-user-info">' +
                        '<span class="account-user-name">' + p.name + '</span>' +
                        '<span class="account-user-role">' + (p.job_number || 'No job #') + ' · ' + p.cs_lead + ' · ' + (statusLabel[p.status] || p.status) + '</span>' +
                        '</div>' +
                        '<div class="account-user-actions">' +
                        '<button type="button" class="account-delete-btn" data-id="' + p.id + '" data-name="' + p.name + '">&times;</button>' +
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
                    return '<div class="account-user-row" id="pt-draft-' + d.id + '">' +
                        '<div class="account-user-info">' +
                        '<span class="account-user-name">' + d.name + '</span>' +
                        '<span class="account-user-role">' + d.cs_lead + '</span>' +
                        '</div>' +
                        '<div class="account-user-actions">' +
                        '<button type="button" class="account-delete-btn" data-id="' + d.id + '" data-name="' + d.name + '">&times;</button>' +
                        '</div></div>';
                }).join('');
                list.querySelectorAll('.account-delete-btn').forEach(function (btn) {
                    btn.addEventListener('click', function () {
                        var name = this.dataset.name;
                        var id   = this.dataset.id;
                        showConfirm('Delete draft "' + name + '"?', function () {
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
                return '<option value="' + c.id + '">' + c.name + '</option>';
            }).join('');
    }

    function populatePTDelFormCustomers(region) {
        var filtered = region
            ? ptFormCustomers.filter(function (c) { return c.region === region; })
            : ptFormCustomers;
        var sel = document.getElementById('pt-new-del-customer');
        sel.innerHTML = '<option value="">Select customer...</option>' +
            filtered.map(function (c) {
                return '<option value="' + c.id + '">' + c.name + '</option>';
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

// Actually creates the deliverable type via the admin API, given
// whatever reference image filename we ended up with (or null). Split
// out so the submit handler can call it either immediately or after
// the upload finishes — same idea as the inline quick-add flow in
// main.js.
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

// Returns a Promise resolving to the uploaded filename, or null if no file
// was chosen at all. Shared by both the reference-image and template-file
// uploads below — same endpoint-agnostic shape, just a different URL.
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

// Three possible outcomes for one of the file fields on an edit save:
//  - a new file was chosen -> upload it, resolve to the new filename
//  - "remove current" was checked -> resolve to null (explicit clear)
//  - neither -> resolve to undefined, meaning "leave alone" — the caller
//    uses that to decide whether to include the key in the PATCH body at
//    all, matching the backend's "only touch the field if present" rule.
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

    // Both uploads (if chosen) run in parallel, then the deliverable type
    // is created once both filenames (or nulls) are known.
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
                            '<span class="account-user-name">' + t.name + '</span>' +
                            '<span class="account-user-role">' + (t.team ? t.team.split(',').join(' + ') : 'No team set') + '</span>' +
                            '</div>' +
                            '<div class="account-user-actions">' +
                            '<button class="account-edit-btn pt-dt-edit" data-id="' + t.id + '" data-name="' + t.name + '" data-team="' + (t.team || '') + '">Edit</button>' +
                            '<button class="account-delete-btn pt-dt-delete" data-id="' + t.id + '" data-name="' + t.name + '">&times;</button>' +
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
                            '<input type="text" class="form-input pt-edit-name" value="' + currentName + '" style="max-width:180px;">' +
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
    });

    function loadPTDesignDirections() {
        fetch('/admin/api/design-directions')
            .then(function (r) { return r.json(); })
            .then(function (dirs) {
                var list = document.getElementById('pt-design-directions-list');
                list.innerHTML = dirs.length === 0 ? '<p class="empty-state">No design directions yet.</p>' :
                    dirs.map(function (d) {
                        return '<div class="account-user-row" id="pt-dd-' + d.id + '">' +
                            '<div class="account-user-info"><span class="account-user-name">' + d.name + '</span></div>' +
                            '<div class="account-user-actions">' +
                            '<button class="account-edit-btn pt-dd-edit" data-id="' + d.id + '" data-name="' + d.name + '">Edit</button>' +
                            '<button class="account-delete-btn pt-dd-delete" data-id="' + d.id + '" data-name="' + d.name + '">&times;</button>' +
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
                            '<input type="text" class="form-input pt-edit-name" value="' + currentName + '" style="max-width:240px;">' +
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
        var prev = sel.value; // Save current selection befoe rebuilding
        sel.innerHTML = '<option value="">All Clients</option>' +
            clients.map(function (c) { return '<option value="' + c + '">' + c + '</option>'; }).join('');
        if (clients.indexOf(prev) !== -1) sel.value = prev; // restore if still valid
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
            customers.map(function (c) { return '<option value="' + c + '">' + c + '</option>'; }).join('');
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
                '<span class="account-user-name">' + t.name + '</span>' +
                '<span class="account-user-role">' + t.client + ' · ' + t.customer + (t.is_custom ? ' · Custom' : '') + '</span>' +
                '</div>' +
                '<div class="account-user-actions">' +
                '<button type="button" class="account-edit-btn" data-id="' + t.id + '">Edit</button>' +
                '<button type="button" class="account-delete-btn" data-id="' + t.id + '" data-name="' + t.name + '">&times;</button>' +
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
                    '<input type="text" class="form-input pt-del-name-input" value="' + type.name + '">' +
                    '<div class="pt-discipline-checks">' +
                    ['2d', '3d', 'technical'].map(function (d) {
                        var checked = type.disciplines.indexOf(d) !== -1 ? 'checked' : '';
                        return '<label><input type="checkbox" value="' + d + '" ' + checked + '> ' + d.toUpperCase() + '</label>';
                    }).join('') +
                    '</div>' +
                    // Shows the current image (if one's set) plus a checkbox
                    // to explicitly remove it, and a file input to replace
                    // it with something new. Three independent choices:
                    // leave it alone, remove it, or swap it.
                    (type.reference_image ?
                        '<img src="/static/deliverable-images/' + type.reference_image + '" class="pt-del-image-preview" style="max-width:80px;max-height:80px;display:block;margin:6px 0;">' +
                        '<label style="font-size:0.85rem;"><input type="checkbox" class="pt-del-remove-image"> Remove current image</label>'
                        : '') +
                    '<label style="font-size:0.85rem;display:block;margin-top:4px;">Replace image: <input type="file" class="pt-del-image-input" accept="image/*"></label>' +
                    (type.template_filename ?
                        '<p style="font-size:0.85rem;margin:6px 0;">Current template: <code>' + type.template_filename + '</code></p>' +
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
        var category = document.getElementById('activity-category').value; // 'all' or a named category

        var params = new URLSearchParams();
        if (search) params.append('search', search);
        if (from) params.append('from', from);
        if (to) params.append('to', to);
        // Only send category param when the user has selected a specific filter —
        // 'all' means no filter and the backend returns everything.
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
                        '<span class="activity-description">' + e.description + '</span>' +
                        '<span class="activity-meta">' + e.user + ' · ' + e.created_at + '</span>' +
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

        // Category dropdown — filter immediately on change, no need to click Search
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

    // ── Reference File Uploads ────────────────────────────────────

    // Only run on pages that have the upload button
    var refFileBtn = document.getElementById('refFileBtn');
    var refFileInput = document.getElementById('refFileInput');

    if (refFileBtn && refFileInput) {

        // Clicking the button triggers the hidden file input
        refFileBtn.addEventListener('click', function () {
            refFileInput.click();
        });

        // When a file is selected, upload it immediately via fetch
        refFileInput.addEventListener('change', function () {
            var file = refFileInput.files[0];
            if (!file) return;

            // Get the project ID from a data attribute we'll add to the button
            var projectId = refFileBtn.dataset.projectId;
            var status = document.getElementById('refFileStatus');

            status.textContent = 'Uploading...';

            // Build a FormData object — this is how we send files via fetch
            var formData = new FormData();
            formData.append('file', file);

            fetch('/projects/' + projectId + '/upload-file', {
                method: 'POST',
                body: formData
                // Note: do NOT set Content-Type header — the browser sets it
                // automatically with the correct multipart boundary when using FormData
            })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (!data.success) {
                        status.textContent = 'Error: ' + data.error;
                        return;
                    }

                    status.textContent = 'Uploaded.';
                    setTimeout(function () { status.textContent = ''; }, 3000);

                    // Reset input so the same file can be re-uploaded if needed
                    refFileInput.value = '';

                    // Build and inject the new file row into the list
                    var list = document.getElementById('reference-files-list');

                    // Remove the "no files" message if present
                    var noFilesMsg = list.querySelector('.no-files-msg');
                    if (noFilesMsg) noFilesMsg.remove();

                    var icons = { jpg: '🖼', jpeg: '🖼', png: '🖼', pdf: '📄', docx: '📝', xlsx: '📊' };
                    var icon = icons[data.file.file_type] || '📎';

                    var item = document.createElement('div');
                    item.className = 'reference-file-item';
                    item.dataset.fileId = data.file.id;
                    item.innerHTML = `
                <span class="reference-file-icon">${icon}</span>
                <span class="reference-file-name">${data.file.original_filename}</span>
                <span class="reference-file-meta">${data.file.uploaded_by}</span>
                <div class="reference-file-actions">
                    <a href="/projects/files/${data.file.id}/download"
                       class="btn-secondary btn-sm">Download</a>
                    <button class="btn-danger btn-sm reference-file-delete-btn"
                            data-file-id="${data.file.id}">Remove</button>
                </div>
            `;

                    // Attach delete handler to the new button
                    item.querySelector('.reference-file-delete-btn').addEventListener('click', handleFileDelete);

                    list.appendChild(item);
                })
                .catch(function (err) {
                    status.textContent = 'Upload failed.';
                    console.error('File upload error:', err);
                });
        });

        // Delete handler — attached to existing buttons on page load and new ones dynamically
        function handleFileDelete(e) {
            /* Capture before the async modal so 'this' is guaranteed in the callback. */
            var fileId = this.dataset.fileId;
            var item = this.closest('.reference-file-item');

            showConfirm('Remove this file?', function () {
                fetch('/projects/files/' + fileId + '/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        if (!data.success) return;
                        item.remove();

                        // Show empty message if no files remain
                        var list = document.getElementById('reference-files-list');
                        if (list.querySelectorAll('.reference-file-item').length === 0) {
                            var msg = document.createElement('p');
                            msg.className = 'no-files-msg';
                            msg.textContent = 'No reference files uploaded yet.';
                            list.appendChild(msg);
                        }
                    });
            });
        }

        // Attach delete handler to all existing delete buttons on page load
        document.querySelectorAll('.reference-file-delete-btn').forEach(function (btn) {
            btn.addEventListener('click', handleFileDelete);
        });
    }

// ═══════════════════════════════════════════════════════════════════════
// ── Achievements admin panel (Phase 7 of the achievement system) ────────
// ═══════════════════════════════════════════════════════════════════════
// Two sub-tabs: Achievements (category accordion, drag-reorderable, with
// an Add/Edit modal per achievement) and Borders (simple list + preview).
// Depends on: btnLoading/btnDone, showConfirm, showToast (all defined
// elsewhere in this file / main.js), and the global `Sortable` constructor
// loaded via CDN in base.html (added for the Pinned Achievements UI on the
// Account page, Phase 5 — reused here rather than loading a second copy).

// achCategoriesData / achBordersData cache the last fetch so the Add/Edit
// modal can populate its category + border <select> options without a
// separate round trip every time it opens.
var achCategoriesData = [];
var achBordersData = [];

// Tracks whether a drag has actually happened since the last save, so the
// "Save Order" button only appears once there's something to save — same
// UX as the Pinned Achievements drag UI reusing the same idea.
var achOrderDirty = false;

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
            achOrderDirty = false;
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
                    ? '<img src="' + a.badge_url + '" class="ach-achievement-badge-thumb" alt="">'
                    : '<span class="ach-achievement-badge-thumb ach-achievement-badge-thumb--empty">🏆</span>') +
                '<div class="ach-achievement-info">' +
                '<span class="ach-achievement-name">' + a.name + '</span>' +
                '<span class="ach-achievement-meta">' + metaBits.join(' · ') + '</span>' +
                '</div>' +
                '<div class="account-user-actions">' +
                '<button type="button" class="account-edit-btn ach-edit-btn" data-id="' + a.id + '">Edit</button>' +
                '<button type="button" class="account-delete-btn ach-delete-btn" data-id="' + a.id + '" data-name="' + a.name + '">&times;</button>' +
                '</div></div>';
        }).join('');

        return '<div class="ach-category-card" data-cat-id="' + cat.id + '">' +
            '<div class="ach-category-header">' +
            '<span class="ach-category-drag-handle" title="Drag to reorder">⠿</span>' +
            '<span class="ach-category-display">' +
            (cat.icon ? '<span class="ach-category-icon">' + cat.icon + '</span>' : '') +
            '<span class="ach-category-name">' + cat.name + '</span>' +
            '</span>' +
            '<span class="ach-category-edit-form hidden">' +
            '<input type="text" class="ach-cat-edit-icon admin-input" placeholder="icon emoji" value="' + (cat.icon || '') + '" maxlength="4" style="width:3.5rem">' +
            '<input type="text" class="ach-cat-edit-name admin-input" placeholder="Category name" value="' + cat.name + '" style="flex:1;min-width:8rem">' +
            '<button type="button" class="accounts-add-btn ach-cat-save-btn" data-id="' + cat.id + '">Save</button>' +
            '<button type="button" class="account-cancel-btn ach-cat-cancel-btn">Cancel</button>' +
            '</span>' +
            '<div class="ach-category-actions">' +
            '<button type="button" class="account-edit-btn ach-category-edit-btn" data-id="' + cat.id + '">Edit</button>' +
            '<button type="button" class="ach-category-toggle-btn" data-cat-id="' + cat.id + '">▾</button>' +
            '<button type="button" class="account-delete-btn ach-category-delete" data-id="' + cat.id + '" data-name="' + cat.name + '">&times;</button>' +
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
    // Collapse/expand — purely visual, no server round trip.
    document.querySelectorAll('.ach-category-toggle-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var body = document.getElementById('ach-category-body-' + this.dataset.catId);
            body.classList.toggle('hidden');
            this.textContent = body.classList.contains('hidden') ? '▸' : '▾';
        });
    });

    // Delete category — blocked server-side if it still has achievements
    // in it (see delete_achievement_category in admin_achievements.py),
    // so the error message from that response is what actually explains
    // why a delete didn't go through.
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

    // Edit category — toggle inline edit form
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
            // Reset inputs to original data
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
                    // Update in-memory data and display
                    var cat = achCategoriesData.find(function (c) { return String(c.id) === String(catId); });
                    if (cat) { cat.name = data.category.name; cat.icon = data.category.icon; }
                    var displayEl = card.querySelector('.ach-category-display');
                    displayEl.innerHTML = (data.category.icon ? '<span class="ach-category-icon">' + data.category.icon + '</span>' : '') +
                        '<span class="ach-category-name">' + data.category.name + '</span>';
                    // Also update the delete button's data-name so confirm dialog shows the right name
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

    // "+ Add Achievement" — opens the shared modal in create mode, pre-scoped to this category.
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

// SortableJS wiring — one Sortable instance for the category list itself
// (reorders categories), plus one PER category for its achievement list
// (reorders achievements within that category only — achievements do NOT
// drag between categories, since that's not something the spec asked for
// and it would need a category_id reassignment on drop, not just a
// display_order change).
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
    achOrderDirty = true;
    document.getElementById('save-ach-order-btn').classList.remove('hidden');
}

// Save Order — reads the CURRENT DOM order (post-drag) for categories and
// for every category's achievement list, and fires one reorder request per
// list. Deliberately reads live DOM order rather than tracking it via drag
// event payloads — simpler, and always correct even if several drags
// happened before Save was clicked.
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
        .then(function () {
            btnDone(saveBtn);
            saveBtn.classList.add('hidden');
            achOrderDirty = false;
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
        return '<option value="' + cat.id + '"' + (String(cat.id) === String(selectedCategoryId) ? ' selected' : '') + '>' + cat.name + '</option>';
    }).join('');
}

function populateAchievementBorderDropdown(selectedBorderId) {
    var sel = document.getElementById('ach-form-border');
    sel.innerHTML = '<option value="">— None —</option>' + achBordersData.map(function (b) {
        return '<option value="' + b.id + '"' + (String(b.id) === String(selectedBorderId) ? ' selected' : '') + '>' + b.name + '</option>';
    }).join('');
}

function openAchievementModal(mode, achievement, categoryId) {
    achievementModal.dataset.mode = mode;
    achievementModal.dataset.editingId = achievement ? achievement.id : '';
    achievementModalTitle.textContent = mode === 'edit' ? 'Edit Achievement' : 'Add Achievement';

    // Borders are needed for the dropdown here even if the admin never
    // visited the Borders tab this session — fetch on demand if we don't
    // have them cached yet, same lazy-load idea as loadPTDelFormData().
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
        if (window.helixPolling) window.helixPolling.pause(); // modal requires input before any server action — see CLAUDE.md polling pattern
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

    // Multipart form, not JSON — a badge image file may be attached.
    // Booleans are appended as literal 'true'/'false' strings rather than
    // relying on checkbox-only-present-when-checked FormData behaviour,
    // matching what admin_achievements.py's create/update routes expect.
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
            // Live preview — applies the actual saved css_class to a small div,
            // so the admin can see immediately whether the class name they typed
            // actually matches something real in achievements.css, rather than
            // discovering a typo only once a user tries to select it as active.
            '<div class="ach-border-preview ' + b.css_class + '"></div>' +
            '<div class="account-user-info">' +
            '<span class="account-user-name">' + b.name + '</span>' +
            '<span class="account-user-role">' + b.css_class + '</span>' +
            '</div>' +
            '<div class="account-user-actions">' +
            '<button type="button" class="account-delete-btn" data-id="' + b.id + '" data-name="' + b.name + '">&times;</button>' +
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
