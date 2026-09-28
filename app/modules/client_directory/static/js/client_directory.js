// Client Directory page, the shared Add Company / Add Contact modals
// (window.ClientDirectoryModals), and the "+ Add new…" options on the
// project create overlay's Client/Contact selects.
// Loaded on the directory page and the project list page; each part checks
// for its own DOM (#directoryList, #client_id) before running.

(function () {
    'use strict';

    // ════════════════════════════════════════════════════════════════════
    // Shared Add Company / Add Contact modals
    // ════════════════════════════════════════════════════════════════════

    // Each caller passes its own onSaved callback (add a list row, or add
    // and select a dropdown option).
    var _addCompanyOnSaved = null;
    var _addContactOnSaved = null;

    function openAddCompanyModal(onSaved) {
        var modal = document.getElementById('add-company-modal');
        if (!modal) return;
        _addCompanyOnSaved = onSaved || null;
        modal.classList.remove('hidden');
        // Pause polling so a reload can't wipe the modal mid-edit.
        if (window.helixPolling) window.helixPolling.pause();
        document.getElementById('addCompanyName').focus();
    }

    function closeAddCompanyModal() {
        var modal = document.getElementById('add-company-modal');
        if (!modal) return;
        modal.classList.add('hidden');
        ['addCompanyName', 'addCompanyAliases', 'addCompanyOfficeLocation', 'addCompanyInstallationLocations']
            .forEach(function (id) { document.getElementById(id).value = ''; });
        if (window.helixPolling) window.helixPolling.resume();
    }

    function submitAddCompanyModal() {
        var btn = document.getElementById('confirmAddCompanyModal');
        var name = document.getElementById('addCompanyName').value.trim();
        if (!name) return;

        btnLoading(btn);
        fetch('/directory/clients/companies', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                aliases: document.getElementById('addCompanyAliases').value.trim(),
                office_location: document.getElementById('addCompanyOfficeLocation').value.trim(),
                installation_locations: document.getElementById('addCompanyInstallationLocations').value.trim()
            })
        })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.success) {
                    var callback = _addCompanyOnSaved;
                    closeAddCompanyModal();
                    if (callback) callback(data.company);
                    btnDone(btn);
                } else {
                    showToast(data.error || 'Could not add company.', 'error');
                    btnDone(btn);
                }
            })
            .catch(function () {
                showToast('Something went wrong. Please try again.', 'error');
                btnDone(btn);
            });
    }

    function openAddContactModal(clientId, onSaved) {
        var modal = document.getElementById('add-contact-modal');
        if (!modal) return;
        _addContactOnSaved = onSaved || null;
        document.getElementById('addContactClientId').value = clientId;
        modal.classList.remove('hidden');
        if (window.helixPolling) window.helixPolling.pause();
        document.getElementById('addContactName').focus();
    }

    function closeAddContactModal() {
        var modal = document.getElementById('add-contact-modal');
        if (!modal) return;
        modal.classList.add('hidden');
        ['addContactName', 'addContactPhone', 'addContactEmail', 'addContactLocation']
            .forEach(function (id) { document.getElementById(id).value = ''; });
        if (window.helixPolling) window.helixPolling.resume();
    }

    function submitAddContactModal() {
        var btn = document.getElementById('confirmAddContactModal');
        var name = document.getElementById('addContactName').value.trim();
        var clientId = document.getElementById('addContactClientId').value;
        if (!name || !clientId) return;

        btnLoading(btn);
        fetch('/directory/clients/contacts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                client_id: clientId,
                phone: document.getElementById('addContactPhone').value.trim(),
                email: document.getElementById('addContactEmail').value.trim(),
                location: document.getElementById('addContactLocation').value.trim()
            })
        })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.success) {
                    var callback = _addContactOnSaved;
                    closeAddContactModal();
                    if (callback) callback(data.contact);
                    btnDone(btn);
                } else {
                    showToast(data.error || 'Could not add contact.', 'error');
                    btnDone(btn);
                }
            })
            .catch(function () {
                showToast('Something went wrong. Please try again.', 'error');
                btnDone(btn);
            });
    }

    // Public API; the modals partial's backdrop onclick and the project
    // create overlay call into this.
    window.ClientDirectoryModals = {
        openAddCompanyModal: openAddCompanyModal,
        closeAddCompanyModal: closeAddCompanyModal,
        openAddContactModal: openAddContactModal,
        closeAddContactModal: closeAddContactModal,
        // project_overlay_create.js re-runs this after it fetches the
        // create fragment, which does not exist when this file first runs.
        initBriefFormIntegration: initBriefFormIntegration
    };

    function wireSharedModalButtons() {
        var cancelCompany = document.getElementById('cancelAddCompanyModal');
        var confirmCompany = document.getElementById('confirmAddCompanyModal');
        var cancelContact = document.getElementById('cancelAddContactModal');
        var confirmContact = document.getElementById('confirmAddContactModal');

        if (cancelCompany) cancelCompany.addEventListener('click', closeAddCompanyModal);
        if (confirmCompany) confirmCompany.addEventListener('click', submitAddCompanyModal);
        if (cancelContact) cancelContact.addEventListener('click', closeAddContactModal);
        if (confirmContact) confirmContact.addEventListener('click', submitAddContactModal);
    }


    // ════════════════════════════════════════════════════════════════════
    // Directory page
    // ════════════════════════════════════════════════════════════════════

    // Working copy of the server data, updated in place after each save.
    var directoryData = (typeof DIRECTORY_DATA !== 'undefined') ? DIRECTORY_DATA : [];
    var canEdit = (typeof CAN_EDIT !== 'undefined') ? CAN_EDIT : false;

    function initDirectoryPage() {
        var listEl = document.getElementById('directoryList');
        if (!listEl) return; // not on the directory page

        renderDirectoryList();
        wireSearch();
        wireAddCompanyButton();
    }

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.textContent = str || '';
        return div.innerHTML;
    }

    // ── Left panel: rendering the grouped list ──────────────────────────

    function renderDirectoryList() {
        var listEl = document.getElementById('directoryList');
        listEl.innerHTML = '';
        directoryData.forEach(function (company) {
            listEl.appendChild(buildCompanyRow(company));
        });
    }

    function buildCompanyRow(company) {
        var wrapper = document.createElement('div');
        wrapper.className = 'directory-company-block';
        wrapper.dataset.companyId = company.id;

        var row = document.createElement('div');
        row.className = 'directory-company-row';
        row.dataset.expand = '1';
        row.innerHTML =
            '<span class="directory-chevron">&#9656;</span>' +
            '<span class="directory-company-name">' + escapeHtml(company.name) + '</span>';

        // Toggled via row.nextElementSibling below, so no per-company IDs are needed.
        var contactList = document.createElement('div');
        contactList.className = 'directory-contact-list hidden';

        company.contacts.forEach(function (contact) {
            contactList.appendChild(buildContactRow(contact));
        });

        if (canEdit) {
            var addContactBtn = document.createElement('button');
            addContactBtn.type = 'button';
            addContactBtn.className = 'btn-secondary btn-sm directory-add-contact-btn';
            addContactBtn.textContent = '+ Add Contact';
            // Defensive: the button sits in contactList, a sibling of row,
            // so the click would not reach row's handler anyway.
            addContactBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                window.ClientDirectoryModals.openAddContactModal(company.id, function (newContact) {
                    company.contacts.push(newContact);
                    // Keep "+ Add Contact" last.
                    contactList.insertBefore(buildContactRow(newContact), addContactBtn);
                    contactList.classList.remove('hidden');
                    row.querySelector('.directory-chevron').classList.add('rotated');
                    selectContact(newContact, company);
                });
            });
            contactList.appendChild(addContactBtn);
        }

        row.addEventListener('click', function () {
            var sibling = row.nextElementSibling;
            sibling.classList.toggle('hidden');
            row.querySelector('.directory-chevron').classList.toggle('rotated');
            selectCompany(company);
        });

        wrapper.appendChild(row);
        wrapper.appendChild(contactList);
        return wrapper;
    }

    function buildContactRow(contact) {
        var row = document.createElement('div');
        row.className = 'directory-contact-row';
        row.textContent = contact.name;
        row.dataset.contactId = contact.id;
        row.addEventListener('click', function (e) {
            e.stopPropagation();
            selectContact(contact, findCompanyByContact(contact.id));
        });
        return row;
    }

    function findCompanyByContact(contactId) {
        for (var i = 0; i < directoryData.length; i++) {
            var match = directoryData[i].contacts.some(function (c) { return c.id === contactId; });
            if (match) return directoryData[i];
        }
        return null;
    }

    // ── Search / filter ──────────────────────────────────────────────────

    function wireSearch() {
        var input = document.getElementById('directorySearchInput');
        if (!input) return;
        input.addEventListener('input', function () {
            applySearchFilter(input.value.trim().toLowerCase());
        });
    }

    function applySearchFilter(query) {
        var listEl = document.getElementById('directoryList');
        var noResultsEl = document.getElementById('directoryNoResults');
        var anyVisible = false;

        var companyBlocks = listEl.querySelectorAll('.directory-company-block');
        companyBlocks.forEach(function (block, index) {
            var company = directoryData[index];
            var companyRow = block.querySelector('.directory-company-row');
            var companyNameEl = companyRow.querySelector('.directory-company-name');
            var contactList = block.querySelector('.directory-contact-list');
            var chevron = companyRow.querySelector('.directory-chevron');
            var contactRows = contactList.querySelectorAll('.directory-contact-row');

            if (!query) {
                // Cleared search: full list, collapsed, no highlights.
                block.classList.remove('hidden');
                companyNameEl.innerHTML = escapeHtml(company.name);
                contactList.classList.add('hidden');
                chevron.classList.remove('rotated');
                contactRows.forEach(function (contactRow, i) {
                    contactRow.innerHTML = escapeHtml(company.contacts[i].name);
                });
                anyVisible = true;
                return;
            }

            // Match company name, each comma-separated alias, and contact names.
            var nameMatch = company.name.toLowerCase().indexOf(query) !== -1;
            var aliasMatch = (company.aliases || '').split(',').some(function (a) {
                return a.trim().toLowerCase().indexOf(query) !== -1;
            });

            var matchedContactIndexes = [];
            company.contacts.forEach(function (contact, i) {
                if (contact.name.toLowerCase().indexOf(query) !== -1) matchedContactIndexes.push(i);
            });

            var companyMatches = nameMatch || aliasMatch;
            var hasMatchingContacts = matchedContactIndexes.length > 0;

            if (!companyMatches && !hasMatchingContacts) {
                block.classList.add('hidden');
                return;
            }

            block.classList.remove('hidden');
            anyVisible = true;

            // Highlight the name only on a name match (alias hits are not visible text).
            companyNameEl.innerHTML = nameMatch ? highlightMatch(company.name, query) : escapeHtml(company.name);

            contactRows.forEach(function (contactRow, i) {
                var contact = company.contacts[i];
                var isMatch = matchedContactIndexes.indexOf(i) !== -1;
                contactRow.innerHTML = isMatch ? highlightMatch(contact.name, query) : escapeHtml(contact.name);
            });

            if (hasMatchingContacts) {
                // Auto-expand so matching contacts are visible.
                contactList.classList.remove('hidden');
                chevron.classList.add('rotated');
            }
        });

        noResultsEl.classList.toggle('hidden', anyVisible);
    }

    function highlightMatch(text, query) {
        var lower = text.toLowerCase();
        var idx = lower.indexOf(query);
        if (idx === -1) return escapeHtml(text);
        return escapeHtml(text.slice(0, idx)) +
            '<span class="directory-highlight">' + escapeHtml(text.slice(idx, idx + query.length)) + '</span>' +
            escapeHtml(text.slice(idx + query.length));
    }

    // ── Right panel: selection + view mode ──────────────────────────────

    function selectCompany(company) {
        markActiveRow(company.id, null);
        renderCompanyDetail(company);
    }

    function selectContact(contact, company) {
        if (!company) return;
        markActiveRow(company.id, contact.id);
        renderContactDetail(contact);
    }

    function markActiveRow(companyId, contactId) {
        document.querySelectorAll('.directory-company-row.active, .directory-contact-row.active')
            .forEach(function (el) { el.classList.remove('active'); });

        var block = document.querySelector('.directory-company-block[data-company-id="' + companyId + '"]');
        if (!block) return;
        if (contactId) {
            var contactRow = block.querySelector('.directory-contact-row[data-contact-id="' + contactId + '"]');
            if (contactRow) contactRow.classList.add('active');
        } else {
            block.querySelector('.directory-company-row').classList.add('active');
        }
    }

    function buildDetailHeader(name) {
        var editButton = canEdit
            ? '<button type="button" class="btn-secondary btn-sm" id="directoryEditBtn">Edit</button>'
            : '';
        return '<div class="directory-detail-header"><h2>' + escapeHtml(name) + '</h2>' + editButton + '</div>';
    }

    function fieldBlock(key, label, value) {
        var hasValue = value && String(value).trim() !== '';
        return '<div class="directory-detail-field" data-field="' + key + '">' +
            '<label>' + label + '</label>' +
            '<div class="directory-detail-value' + (hasValue ? '' : ' empty') + '">' +
            (hasValue ? escapeHtml(value) : 'Not set') +
            '</div></div>';
    }

    function renderCompanyDetail(company) {
        var panel = document.getElementById('directoryRightPanel');
        panel.innerHTML =
            buildDetailHeader(company.name) +
            fieldBlock('name', 'Name', company.name) +
            fieldBlock('aliases', 'Aliases', company.aliases) +
            fieldBlock('office_location', 'Office Location', company.office_location) +
            fieldBlock('installation_locations', 'Installation Locations', company.installation_locations) +
            '<div id="directoryProjectsSection" class="directory-projects-section"></div>';

        wireEditButton('company', company);
        loadLinkedProjects('/api/clients/' + company.id + '/projects');
    }

    function renderContactDetail(contact) {
        var panel = document.getElementById('directoryRightPanel');
        panel.innerHTML =
            buildDetailHeader(contact.name) +
            fieldBlock('name', 'Name', contact.name) +
            fieldBlock('phone', 'Phone', contact.phone) +
            fieldBlock('email', 'Email', contact.email) +
            fieldBlock('location', 'Location', contact.location) +
            '<div id="directoryProjectsSection" class="directory-projects-section"></div>';

        wireEditButton('contact', contact);
        loadLinkedProjects('/api/contacts/' + contact.id + '/projects');
    }

    // ── Right panel: edit mode ──────────────────────────────────────────
    //
    // Keys must match the data-field wrappers built by fieldBlock() in the
    // render*Detail functions above.
    var COMPANY_FIELDS = [
        { key: 'name', label: 'Name', required: true },
        { key: 'aliases', label: 'Aliases' },
        { key: 'office_location', label: 'Office Location' },
        { key: 'installation_locations', label: 'Installation Locations' }
    ];
    var CONTACT_FIELDS = [
        { key: 'name', label: 'Name', required: true },
        { key: 'phone', label: 'Phone' },
        { key: 'email', label: 'Email' },
        { key: 'location', label: 'Location' }
    ];

    function wireEditButton(kind, record) {
        var editBtn = document.getElementById('directoryEditBtn');
        if (!editBtn) return; // read-only user: no Edit button
        editBtn.addEventListener('click', function () {
            enterEditMode(kind, record);
        });
    }

    function enterEditMode(kind, record) {
        var fields = kind === 'company' ? COMPANY_FIELDS : CONTACT_FIELDS;
        var panel = document.getElementById('directoryRightPanel');

        fields.forEach(function (field) {
            var wrapper = panel.querySelector('[data-field="' + field.key + '"]');
            var currentValue = record[field.key] || '';
            wrapper.innerHTML =
                '<label>' + field.label + '</label>' +
                '<input type="text" class="form-input directory-edit-input" value="' + escapeHtml(currentValue) + '">';
        });

        // Swap the Edit button for Cancel/Save.
        var header = panel.querySelector('.directory-detail-header');
        header.querySelector('#directoryEditBtn').outerHTML =
            '<div style="display:flex;gap:0.5rem;">' +
            '<button type="button" class="btn btn--secondary btn--sm" id="directoryCancelBtn">Cancel</button>' +
            '<button type="button" class="btn btn--primary btn--sm" id="directorySaveBtn">Save</button>' +
            '</div>';

        document.getElementById('directoryCancelBtn').addEventListener('click', function () {
            // record is untouched while editing, so re-rendering discards the edits.
            if (kind === 'company') renderCompanyDetail(record); else renderContactDetail(record);
        });
        document.getElementById('directorySaveBtn').addEventListener('click', function () {
            saveEdit(kind, record, fields);
        });
    }

    function saveEdit(kind, record, fields) {
        var panel = document.getElementById('directoryRightPanel');
        var saveBtn = document.getElementById('directorySaveBtn');
        var payload = { id: record.id };
        var valid = true;

        fields.forEach(function (field) {
            var input = panel.querySelector('[data-field="' + field.key + '"] .directory-edit-input');
            var value = input.value.trim();
            if (field.required && !value) valid = false;
            payload[field.key] = value;
        });

        if (!valid) {
            showToast('Name is required.', 'error');
            return;
        }

        var url = kind === 'company' ? '/directory/clients/companies' : '/directory/clients/contacts';
        btnLoading(saveBtn);

        fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (!data.success) {
                    showToast(data.error || 'Could not save changes.', 'error');
                    btnDone(saveBtn);
                    return;
                }

                // Take the server's stored values, then re-render both panels
                // (the name may have changed).
                var updated = kind === 'company' ? data.company : data.contact;
                Object.assign(record, updated);

                renderDirectoryList();
                if (kind === 'company') renderCompanyDetail(record); else renderContactDetail(record);
                btnDone(saveBtn);
            })
            .catch(function () {
                showToast('Something went wrong. Please try again.', 'error');
                btnDone(saveBtn);
            });
    }

    // ── Projects-linked list (read-only for every role) ─────────────────

    function loadLinkedProjects(url) {
        var section = document.getElementById('directoryProjectsSection');
        section.innerHTML = '<h3>Projects</h3><p class="directory-no-projects">Loading...</p>';

        fetch(url)
            .then(function (res) { return res.json(); })
            .then(function (projects) {
                if (!projects.length) {
                    section.innerHTML = '<h3>Projects</h3><p class="directory-no-projects">No projects linked yet.</p>';
                    return;
                }
                var rows = projects.map(function (p) {
                    return '<a class="directory-project-row" href="/projects/' + p.id + '?from=directory">' +
                        '<span class="directory-project-row-name">' + escapeHtml(p.name) + '</span>' +
                        '<span class="status-badge s-' + p.status + '">' + escapeHtml(p.status_label) + '</span>' +
                        '</a>';
                }).join('');
                section.innerHTML = '<h3>Projects</h3>' + rows;
            })
            .catch(function () {
                section.innerHTML = '<h3>Projects</h3><p class="directory-no-projects">Could not load projects.</p>';
            });
    }

    // ── "+ Add Company" button above the left panel ─────────────────────

    function wireAddCompanyButton() {
        var btn = document.getElementById('btnAddCompanyDirectory');
        if (!btn) return; // not rendered for read-only users
        btn.addEventListener('click', function () {
            window.ClientDirectoryModals.openAddCompanyModal(function (newCompany) {
                newCompany.contacts = [];
                directoryData.push(newCompany);
                // Match the server's order_by(Client.name).
                directoryData.sort(function (a, b) { return a.name.localeCompare(b.name); });
                renderDirectoryList();
                selectCompany(newCompany);
            });
        });
    }


    // ════════════════════════════════════════════════════════════════════
    // Project create overlay: "+ Add new company…" / "+ Add new contact…"
    // ════════════════════════════════════════════════════════════════════
    //
    // Option value that opens a modal; must match _details_create.html.
    var ADD_NEW_SENTINEL = '__add_new__';

    function initBriefFormIntegration() {
        var clientSelect = document.getElementById('client_id');
        var contactSelect = document.getElementById('contact_id');
        if (!clientSelect || !contactSelect) return; // create overlay not open

        // Last real selection, restored when "+ Add new…" is picked.
        clientSelect.dataset.previousValue = clientSelect.value;
        contactSelect.dataset.previousValue = contactSelect.value;

        // Capture phase, so the sentinel is caught before the overlay's own
        // change listener (project_overlay_create.js) and never autosaved.
        clientSelect.addEventListener('change', function (e) {
            if (clientSelect.value === ADD_NEW_SENTINEL) {
                e.stopImmediatePropagation();
                clientSelect.value = clientSelect.dataset.previousValue;
                window.ClientDirectoryModals.openAddCompanyModal(function (newCompany) {
                    addOptionBeforeSentinel(clientSelect, newCompany.id, newCompany.name);
                    clientSelect.value = newCompany.id;
                    // A script-set .value fires no 'change'; dispatch one so the
                    // overlay autosaves it and the contact list is refreshed below.
                    clientSelect.dispatchEvent(new Event('change', { bubbles: true }));
                });
                return;
            }

            clientSelect.dataset.previousValue = clientSelect.value;
            refreshContactOptionsForClient(clientSelect.value, contactSelect);
        }, true);

        contactSelect.addEventListener('change', function (e) {
            if (contactSelect.value === ADD_NEW_SENTINEL) {
                e.stopImmediatePropagation();
                contactSelect.value = contactSelect.dataset.previousValue;

                // A Contact needs a Client; the save would 400 without one.
                if (!clientSelect.value) {
                    showToast('Please select a Client first.', 'error');
                    return;
                }

                window.ClientDirectoryModals.openAddContactModal(clientSelect.value, function (newContact) {
                    addOptionBeforeSentinel(contactSelect, newContact.id, newContact.name);
                    contactSelect.value = newContact.id;
                    contactSelect.dispatchEvent(new Event('change', { bubbles: true }));
                });
                return;
            }

            contactSelect.dataset.previousValue = contactSelect.value;
        }, true);
    }

    // Inserts just before the sentinel, which must stay the last option.
    function addOptionBeforeSentinel(select, value, label) {
        var option = document.createElement('option');
        option.value = value;
        option.textContent = label;
        var sentinelOption = select.querySelector('option[value="' + ADD_NEW_SENTINEL + '"]');
        select.insertBefore(option, sentinelOption);
    }

    function rebuildContactOptions(contactSelect, contacts) {
        contactSelect.innerHTML = '<option value="">— Select Contact —</option>';
        contacts.forEach(function (contact) {
            var option = document.createElement('option');
            option.value = contact.id;
            option.textContent = contact.name;
            contactSelect.appendChild(option);
        });
        var sentinel = document.createElement('option');
        sentinel.value = ADD_NEW_SENTINEL;
        sentinel.textContent = '+ Add new contact…';
        contactSelect.appendChild(sentinel);
    }

    function refreshContactOptionsForClient(clientId, contactSelect) {
        if (!clientId) {
            rebuildContactOptions(contactSelect, []);
            return;
        }

        fetch('/api/clients/' + clientId + '/contacts')
            .then(function (res) { return res.json(); })
            .then(function (contacts) {
                rebuildContactOptions(contactSelect, contacts);
            })
            .catch(function (err) {
                console.error('Could not load contacts for client:', err);
            });
    }


    // ════════════════════════════════════════════════════════════════════
    // Run immediately: DOMContentLoaded never fires after SPA navigation, and
    // the page's DOM is already in place when this script runs.
    wireSharedModalButtons();
    initDirectoryPage();
    initBriefFormIntegration();
})();
