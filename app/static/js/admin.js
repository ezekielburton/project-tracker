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
        fetch('/admin/api/deliverable-types', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                client_id: clientId,
                customer_id: customerId,
                disciplines: disciplines,
                is_custom: isCustom
            })
        })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.success) {
                    ptAddDelForm.classList.add('hidden');
                    ptAddDelForm.reset();
                    ptAllDeliverableTypes.push(data.type);
                    ptAllDeliverableTypes.sort(function (a, b) { return a.name.localeCompare(b.name); });
                    populatePTDelClientFilter(ptAllDeliverableTypes);
                    filterPTDeliverables(); // re-apply current filters instead of showing all rows
                } else {
                    showToast(data.error || 'Could not create deliverable type.', 'error');
                    btnDone(submitBtn);
                }
            })
            .catch(function () { btnDone(submitBtn); });
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
                    '<div class="account-edit-actions">' +
                    '<button type="button" class="btn-primary pt-del-save-btn">Save</button>' +
                    '<button type="button" class="account-cancel-edit-btn">Cancel</button>' +
                    '</div></div>';
                row.querySelector('.account-cancel-edit-btn').addEventListener('click', function () {
                    renderPTDeliverableRows(ptAllDeliverableTypes);
                });
                row.querySelector('.pt-del-save-btn').addEventListener('click', function () {
                    var name = row.querySelector('.pt-del-name-input').value.trim();
                    var disciplines = Array.from(
                        row.querySelectorAll('.pt-discipline-checks input:checked')
                    ).map(function (cb) { return cb.value; });
                    if (!name) { showToast('Name is required.', 'warning'); return; }
                    var saveBtn = this;
                    btnLoading(saveBtn);
                    fetch('/admin/api/deliverable-types/' + id, {
                        method: 'PATCH',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name: name, disciplines: disciplines })
                    })
                        .then(function (res) { return res.json(); })
                        .then(function (data) {
                            if (data.success) {
                                var idx = ptAllDeliverableTypes.findIndex(function (t) { return String(t.id) === String(id); });
                                if (idx !== -1) {
                                    ptAllDeliverableTypes[idx].name = name;
                                    ptAllDeliverableTypes[idx].disciplines = disciplines;
                                }
                                renderPTDeliverableRows(ptAllDeliverableTypes);
                            } else {
                                showToast(data.error || 'Could not save.', 'error');
                                btnDone(saveBtn);
                            }
                        })
                        .catch(function () { btnDone(saveBtn); });
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
