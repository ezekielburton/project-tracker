// app/static/js/client_directory.js
//
// Powers three things:
//   1. The Client Directory page itself (client_directory/index.html):
//      renders DIRECTORY_DATA into the left-panel list, live search
//      filtering, expand/collapse, the right-panel view/edit detail, and
//      the Projects-linked list.
//   2. The shared Add Company / Add Contact modals - also included on the
//      brief form (projects/create.html) via the same modal partial, so
//      the open/close/save logic for those modals lives here once and is
//      exposed as window.ClientDirectoryModals, callable from both pages.
//   3. The brief form's "+ Add new company…" / "+ Add new contact…"
//      dropdown-option wiring (initBriefFormIntegration) - this is what
//      replaced the old per-page button + inline reveal-form that used to
//      live in main.js (setupAddClient/setupAddContact), now that both
//      pages share one modal instead of each having their own inline form.
//
// Every directory-page-specific function checks for #directoryList (and the
// brief-form section checks for #client_id) before doing anything, so this
// one file is safe to include on either page even though neither has the
// other's DOM.

(function () {
    'use strict';

    // ════════════════════════════════════════════════════════════════════
    // Shared Add Company / Add Contact modals
    // ════════════════════════════════════════════════════════════════════

    // onSaved callbacks let each call site (directory page vs. brief form)
    // decide what happens after a successful save - insert a list row vs.
    // populate + select a dropdown option - without either modal needing
    // to know which page it's running on.
    var _addCompanyOnSaved = null;
    var _addContactOnSaved = null;

    function openAddCompanyModal(onSaved) {
        var modal = document.getElementById('add-company-modal');
        if (!modal) return;
        _addCompanyOnSaved = onSaved || null;
        modal.classList.remove('hidden');
        // Pause polling while the modal is open, per the "Polling —
        // pause during modals" pattern - without this, the interval reload
        // could yank the page out from under the user mid-edit. Guarded
        // (window.helixPolling &&) because not every page that loads this
        // file has polling running - the directory page itself doesn't.
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

    // Exposed globally so both this file's own directory-page code AND
    // create.html's brief-form-specific JS can open these modals and
    // register their own onSaved callback, without either needing to know
    // the other's internals - this is the one shared surface between the
    // two pages the spec asked for.
    window.ClientDirectoryModals = {
        openAddCompanyModal: openAddCompanyModal,
        closeAddCompanyModal: closeAddCompanyModal,
        openAddContactModal: openAddContactModal,
        closeAddContactModal: closeAddContactModal,
        // Exposed so the create-mode overlay (project_overlay_create.js,
        // task #61) can re-run this against #client_id/#contact_id after
        // fetching that fragment in dynamically — this file's own call at
        // the bottom only ever sees the DOM present at real page load,
        // before that fragment exists.
        initBriefFormIntegration: initBriefFormIntegration
    };

    function wireSharedModalButtons() {
        var cancelCompany = document.getElementById('cancelAddCompanyModal');
        var confirmCompany = document.getElementById('confirmAddCompanyModal');
        var cancelContact = document.getElementById('cancelAddContactModal');
        var confirmContact = document.getElementById('confirmAddContactModal');

        // Each guarded individually rather than bailing out of the whole
        // function on the first missing element - harmless if a future
        // page includes the modals partial but only ends up using one of
        // the two modals.
        if (cancelCompany) cancelCompany.addEventListener('click', closeAddCompanyModal);
        if (confirmCompany) confirmCompany.addEventListener('click', submitAddCompanyModal);
        if (cancelContact) cancelContact.addEventListener('click', closeAddContactModal);
        if (confirmContact) confirmContact.addEventListener('click', submitAddContactModal);
    }


    // ════════════════════════════════════════════════════════════════════
    // Directory page
    // ════════════════════════════════════════════════════════════════════

    // Working copy of the server data - mutated in place as companies/
    // contacts are added or edited, so the list and detail views never
    // need a full page reload or a re-fetch to reflect a change just saved.
    var directoryData = (typeof DIRECTORY_DATA !== 'undefined') ? DIRECTORY_DATA : [];
    var canEdit = (typeof CAN_EDIT !== 'undefined') ? CAN_EDIT : false;

    function initDirectoryPage() {
        var listEl = document.getElementById('directoryList');
        if (!listEl) return; // not on the directory page - the brief form only has the modals

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

        // This is the sibling that gets its "hidden" class toggled by the
        // row's click handler below - same this.nextElementSibling
        // mechanic used for the project table's expansion
        // rows, so a company's contacts are always looked up structurally
        // (via the sibling relationship) rather than by ID, avoiding any
        // duplicate-ID collision between company blocks.
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
            // stopPropagation here is a no-op today (this button lives
            // inside contactList, a SIBLING of row, not a descendant of it -
            // so a click here was never going to bubble into row's own
            // listener). Left in defensively in case that nesting changes.
            addContactBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                window.ClientDirectoryModals.openAddContactModal(company.id, function (newContact) {
                    company.contacts.push(newContact);
                    // Insert before the button itself, not appendChild,
                    // so "+ Add Contact" stays the last element in the list.
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
                // Cleared search - restore the full list, collapsed, no
                // highlights, per "Clearing the search restores the full list."
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

            // Match against company name, each comma-separated alias, and
            // every contact name under this company - the three match
            // targets called for in the spec.
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
                // No match anywhere in this company - collapse it out of
                // view entirely, per "Companies with no matching results collapse."
                block.classList.add('hidden');
                return;
            }

            block.classList.remove('hidden');
            anyVisible = true;

            // Only highlight the company name itself if the match was
            // actually in the name/alias - a contact-only match still
            // shows the plain company name, since that's not where it hit.
            companyNameEl.innerHTML = nameMatch ? highlightMatch(company.name, query) : escapeHtml(company.name);

            contactRows.forEach(function (contactRow, i) {
                var contact = company.contacts[i];
                var isMatch = matchedContactIndexes.indexOf(i) !== -1;
                contactRow.innerHTML = isMatch ? highlightMatch(contact.name, query) : escapeHtml(contact.name);
            });

            if (hasMatchingContacts) {
                // Auto-expand so the match is visible without an extra
                // click, per "expand automatically and highlight the matched text."
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
    // COMPANY_FIELDS / CONTACT_FIELDS describe each editable field once -
    // its data-field key (matching the wrapper built by fieldBlock above),
    // display label, and whether it's required. Driving edit mode from the
    // same key list used to render view mode means the two can't drift out
    // of sync with each other (a field added to one but forgotten in the
    // other).
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
        if (!editBtn) return; // canEdit is false - no Edit button exists for a Designer
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

        // Swap the header's Edit button for Cancel/Save - "clicking Edit
        // switches text fields to inputs in place" from the spec, done here
        // by replacing the button itself since Cancel/Save need different
        // click handlers than Edit did, not just a different label.
        var header = panel.querySelector('.directory-detail-header');
        header.querySelector('#directoryEditBtn').outerHTML =
            '<div style="display:flex;gap:0.5rem;">' +
            '<button type="button" class="btn btn--secondary btn--sm" id="directoryCancelBtn">Cancel</button>' +
            '<button type="button" class="btn btn--primary btn--sm" id="directorySaveBtn">Save</button>' +
            '</div>';

        document.getElementById('directoryCancelBtn').addEventListener('click', function () {
            // record was never mutated during edit mode (only the <input>
            // elements held the in-progress values) - re-rendering the
            // view straight from record is what makes Cancel "restore the
            // previous values without saving" for free.
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

                // Mutate the in-memory record in place with whatever the
                // server actually stored, then re-render both the left
                // panel (name may have changed) and the right panel detail
                // from that same object - no page reload, no re-fetch.
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
        if (!btn) return; // not rendered at all when canEdit is false
        btn.addEventListener('click', function () {
            window.ClientDirectoryModals.openAddCompanyModal(function (newCompany) {
                newCompany.contacts = [];
                directoryData.push(newCompany);
                // Keep the in-memory list sorted the same way the server
                // originally sent it (Client.query.order_by(Client.name)),
                // so the new company lands in alphabetical position instead
                // of always at the bottom of the list.
                directoryData.sort(function (a, b) { return a.name.localeCompare(b.name); });
                renderDirectoryList();
                selectCompany(newCompany);
            });
        });
    }


    // ════════════════════════════════════════════════════════════════════
    // Brief form integration: "+ Add new company…" / "+ Add new contact…"
    // ════════════════════════════════════════════════════════════════════
    //
    // The sentinel option value used by both selects to trigger a modal
    // instead of being treated as a real selection.
    var ADD_NEW_SENTINEL = '__add_new__';

    function initBriefFormIntegration() {
        var clientSelect = document.getElementById('client_id');
        var contactSelect = document.getElementById('contact_id');
        if (!clientSelect || !contactSelect) return; // not on the brief form

        // Remember the last real (non-sentinel) selection on each select, so
        // choosing "+ Add new..." can be reverted to whatever was actually
        // selected before, both while the modal is open and if the user
        // cancels out of it without saving.
        clientSelect.dataset.previousValue = clientSelect.value;
        contactSelect.dataset.previousValue = contactSelect.value;

        clientSelect.addEventListener('change', function () {
            if (clientSelect.value === ADD_NEW_SENTINEL) {
                clientSelect.value = clientSelect.dataset.previousValue;
                window.ClientDirectoryModals.openAddCompanyModal(function (newCompany) {
                    addOptionBeforeSentinel(clientSelect, newCompany.id, newCompany.name);
                    clientSelect.value = newCompany.id;
                    clientSelect.dataset.previousValue = newCompany.id;
                    // A brand new company has zero contacts - reset the
                    // Contact select to just the placeholder + sentinel
                    // rather than firing a fetch that would just come back
                    // empty anyway.
                    rebuildContactOptions(contactSelect, []);
                    contactSelect.dataset.previousValue = '';
                    // client_id changing is exactly the kind of thing the
                    // completion bar / autosave need to know about, but a
                    // script-set .value never fires a native 'change' event
                    // on its own - these two are exposed on window by
                    // main.js specifically so this callback can call them
                    // directly, same as the old setupAddClient() used to.
                    if (window.calculateCompletion) window.calculateCompletion();
                    if (window.scheduleAutosave) window.scheduleAutosave();
                });
                return;
            }

            clientSelect.dataset.previousValue = clientSelect.value;
            refreshContactOptionsForClient(clientSelect.value, contactSelect);
        });

        contactSelect.addEventListener('change', function () {
            if (contactSelect.value === ADD_NEW_SENTINEL) {
                contactSelect.value = contactSelect.dataset.previousValue;

                // A Contact must belong to a Client (Contact.client_id is
                // required at the model level) - if none is picked yet,
                // don't even open the modal, since saving would just come
                // back as a 400. Same guard the old setupAddContact() had.
                if (!clientSelect.value) {
                    showToast('Please select a Client first.', 'error');
                    return;
                }

                window.ClientDirectoryModals.openAddContactModal(clientSelect.value, function (newContact) {
                    addOptionBeforeSentinel(contactSelect, newContact.id, newContact.name);
                    contactSelect.value = newContact.id;
                    contactSelect.dataset.previousValue = newContact.id;
                    if (window.calculateCompletion) window.calculateCompletion();
                    if (window.scheduleAutosave) window.scheduleAutosave();
                });
                return;
            }

            contactSelect.dataset.previousValue = contactSelect.value;
            // No extra handling needed for a normal selection - #contact_id
            // lives inside #sectionBasics, so the generic
            // "#sectionBasics input, #sectionBasics select" change listener
            // in main.js already calls calculateCompletion()/scheduleAutosave()
            // for real, user-driven selections like this one.
        });
    }

    // Inserts a new <option> as the second-to-last child (i.e. right before
    // the "+ Add new..." sentinel, which must always stay last) rather than
    // a plain appendChild - otherwise every newly added company/contact
    // would end up sorted after the sentinel instead of among the real options.
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

        // Same GET /api/clients/<id>/contacts endpoint the old
        // fetchContactsForClient() in main.js used to call - just rebuilt
        // here with the sentinel option appended afterward every time,
        // since a full rebuild (same approach showDeliverableSelector()
        // uses elsewhere in this app) always needs that last option re-added.
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
    // Run immediately - NOT gated behind DOMContentLoaded. This file is
    // loaded two ways: a real page load (DOMContentLoaded fires normally,
    // and by the time it does, this script tag - placed at the very end of
    // the content block - has already executed anyway) and an SPA
    // navigation via sidebar.js's execScripts(), which recreates and
    // re-executes this exact <script> tag after the new HTML is already
    // sitting in the DOM. DOMContentLoaded only ever fires once per real
    // page load, so on the SPA path it would never fire again and none of
    // this would run - same reasoning already documented in achievements.js
    // for the same navigation mechanism. Calling these directly works for
    // both cases because the relevant DOM (list, modals, selects) is always
    // already present by the time THIS script runs, on either path.
    wireSharedModalButtons();
    initDirectoryPage();
    initBriefFormIntegration();
})();
