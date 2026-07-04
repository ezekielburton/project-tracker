// notifications.js — Vitamin-E
// Notification sound, polling, inbox/archived DOM handlers, archive-all, delete-all.
// Depends on: showToast(), buildArchivedItem(), buildInboxItem() — all defined here.
// Loaded after main.js.

// ── Notification Sound (Web Audio API) ──────────────────────────────────────
// Generates a two-tone chime without needing any audio file
window.helixPlayNotificationSound = function (overrideUrl, overrideVolume) {
    // Explicit test (account.html's "Test Sound" button) always plays, even
    // if the on/off toggle is currently off — you're deliberately previewing
    // it. The automatic poll-triggered call (no arguments) respects the toggle.
    var isExplicitTest = overrideUrl !== undefined;
    var prefs = window.HELIX_SOUND_PREFS || { enabled: true, volume: 1, url: null };

    if (!isExplicitTest && prefs.enabled === false) return;

    var url = isExplicitTest ? overrideUrl : prefs.url;
    var volume = (overrideVolume !== undefined) ? overrideVolume : (prefs.volume != null ? prefs.volume : 1);
    volume = Math.max(0, Math.min(1, volume));

    if (url) {
        // A real uploaded file has been chosen — play it directly.
        var audio = new Audio(url);
        audio.volume = volume;
        audio.play().catch(function () {
            // Autoplay can be blocked before the user has interacted with the
            // page at all — silent fail, matches the old try/catch behavior.
        });
        return;
    }

    // No file chosen yet (fresh install, or "Default chime" selected) —
    // fall back to the original synthesized two-tone chime so sound still
    // works out of the box with zero admin setup.
    try {
        var ctx = new (window.AudioContext || window.webkitAudioContext)();

        function playTone(freq, startTime, duration, peakGain) {
            var osc = ctx.createOscillator();
            var gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.type = 'sine';
            osc.frequency.value = freq;
            gain.gain.setValueAtTime(0, startTime);
            gain.gain.linearRampToValueAtTime(peakGain, startTime + 0.05);
            gain.gain.exponentialRampToValueAtTime(0.001, startTime + duration);
            osc.start(startTime);
            osc.stop(startTime + duration);
        }

        // Scale the chime's peak volume by the saved slider value too —
        // otherwise volume would only work for uploaded files, not the fallback.
        var peak = 0.25 * volume;
        var now = ctx.currentTime;
        playTone(880, now, 0.4, peak);
        playTone(1108, now + 0.18, 0.5, peak);
    } catch (e) {
        // Audio context blocked (e.g. before first user interaction) — silent fail
    }
};

// ── Desktop (Browser) Notifications ─────────────────────────────────────────
function helixShowBrowserNotification(message) {
    if (localStorage.getItem('helix_browser_notifications') === 'off') return;
    if (!('Notification' in window)) return;
    if (Notification.permission !== 'granted') return;

    new Notification('Vitamin-E', {
        body: message,
        icon: '/static/images/notiftoggle2.png'
    });
}

// ── Notification Polling (every 30 seconds) ──────────────────────────────────
// Polls /notifications/poll?since=<ISO> for new unread notifications.
// On first load, sets the baseline timestamp so we only alert about NEW arrivals.
(function () {
    // Initialise the "last polled" time to now so we don't re-fire existing notifications
    if (!localStorage.getItem('helix_last_poll')) {
        localStorage.setItem('helix_last_poll', new Date().toISOString());
    }

    function pollNotifications() {
        var since = localStorage.getItem('helix_last_poll') || new Date().toISOString();

        fetch('/notifications/poll?since=' + encodeURIComponent(since))
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.notifications || data.notifications.length === 0) return;

                // Update the baseline to the newest notification's timestamp
                var latest = data.notifications[data.notifications.length - 1];
                localStorage.setItem('helix_last_poll', latest.created_at);

                // Fire once per batch (first message) — avoids a flood if many arrive
                var msg = data.notifications[0].message;
                helixShowBrowserNotification(msg);
                window.helixPlayNotificationSound();

                // Achievement toast — show one per achievement in the batch
                data.notifications.forEach(function (n) {
                    if (n.notification_type === 'achievement_earned' && typeof showAchievementToast === 'function') {
                        showAchievementToast(n.message);
                    }
                });

                // Update the unread badge in the nav without a full page reload
                var badge = document.getElementById('notif-unread-badge');
                if (badge) {
                    // Badge already exists — increment the count
                    var current = parseInt(badge.textContent, 10) || 0;
                    badge.textContent = current + data.notifications.length;
                } else {
                    // Badge doesn't exist yet (count was 0) — create and inject it
                    var bell = document.getElementById('notification-bell');
                    if (bell) {
                        var newBadge = document.createElement('span');
                        newBadge.className = 'bell-badge';
                        newBadge.id = 'notif-unread-badge';
                        newBadge.textContent = data.notifications.length;
                        bell.appendChild(newBadge);
                    }
                }
            })
            .catch(function () {
                // Network error — silently skip this poll cycle
            });
    }

    // Start polling 5s after page load (avoid hitting server during initial render)
    setTimeout(function () {
        pollNotifications();
        setInterval(pollNotifications, 30000); // every 30 seconds
    }, 5000);
})();

// Clickable row logic
document.querySelectorAll('.clickable').forEach(row => {
    row.addEventListener('click', function (e) {
        if (e.target.closest('a, button, select')) return;
        if (window.navigateTo) { window.navigateTo(this.dataset.href); } else { window.location.href = this.dataset.href; }
    });
});

// Notification panel elements
const bell = document.getElementById('notification-bell');
const panel = document.getElementById('notification-panel');
const closeBtn = document.getElementById('close-notifications');

// Open and close the panel when bell is clicked
if (bell && panel) {
    bell.addEventListener('click', function (event) {
        event.stopPropagation();
        panel.classList.toggle('hidden');
    });
}

// Close panel when close button is clicked
if (closeBtn && panel) {
    closeBtn.addEventListener('click', function () {
        panel.classList.add('hidden');
    });
}

// Click anywhere outside the panel closes it
document.addEventListener('click', function (event) {
    if (panel && !panel.classList.contains('hidden')) {
        if (!panel.contains(event.target) && event.target !== bell) {
            panel.classList.add('hidden');
        }
    }
});

// Click a notification body — mark as read, then navigate
document.querySelectorAll('.notification-item:not(.notification-item--archived)').forEach(function (item) {
    item.addEventListener('click', function (e) {
        if (e.target.closest('.notification-mark-read-btn')) return;
        var notificationId = this.dataset.id;
        fetch('/notifications/' + notificationId + '/read', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) window.location.href = data.redirect_url;
            });
    });
});

//-----------Notification Helpers------------------------------

// Builds a new archived notification element from existing data
// Called after archiving so the item appears in the Archived tab immediately
function buildArchivedItem(id, message, time) {
    var div = document.createElement('div');
    div.className = 'notification-item notification-item--archived';
    div.dataset.id = id;

    // Inner HTML matches the server rendered archived item structure
    div.innerHTML = `
        <input type="checkbox" class="notif-checkbox hidden" value="${id}">
        <div class="notification-content">
            <p class="notification-message">${message}</p>
            <span class="notification-time">${time}</span>
        </div>
        <button type="button" class="notification-restore-btn" data-id="${id}" title="Restore to inbox">↩</button>
    `;

    // Attach the restore listener on the new button immediately
    // (querySelectorAll only runs on page load, so new elements need manual binding)
    div.querySelector('.notification-restore-btn').addEventListener('click', handleRestore);

    return div;
}

// Builds a new inbox notification element from existing data
// Called after restoring so the item appears in the Inbox tab immediately
function buildInboxItem(id, message, time) {
    var div = document.createElement('div');
    div.className = 'notification-item';
    div.dataset.id = id;

    div.innerHTML = `
        <div class="notification-content">
            <p class="notification-message">${message}</p>
            <span class="notification-time">${time}</span>
        </div>
        <button type="button" class="notification-mark-read-btn" data-id="${id}" title="Mark as read">✓</button>
    `;

    // Attach the mark-read listener to the new button immediately
    div.querySelector('.notification-mark-read-btn').addEventListener('click', handleMarkRead);

    return div;
}

// Mark a notification as read without navigating
function handleMarkRead(e) {
    e.stopPropagation();

    var notificationId = this.dataset.id;
    var item = this.closest('.notification-item');

    fetch('/notifications/' + notificationId + '/read', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (!data.success) return;

            // Decrement the unread badge if this was unread
            if (item.classList.contains('unread')) {
                var badge = document.querySelector('.bell-badge');
                if (badge) {
                    var count = parseInt(badge.textContent) - 1;
                    if (count <= 0) { badge.remove(); } else { badge.textContent = count; }
                }
                item.classList.remove('unread');
            }
        });
}

// Attach to all existing mark-read buttons on page load
document.querySelectorAll('.notification-mark-read-btn').forEach(function (btn) {
    btn.addEventListener('click', handleMarkRead);
})

// Named function so dynamically created restore buttons can reuse the same logic
function handleRestore(e) {
    e.stopPropagation();

    var id = this.dataset.id;
    var item = this.closest('.notification-item');

    // Read message and time before removing from DOM
    var message = item.querySelector('.notification-message').textContent;
    var time = item.querySelector('.notification-time').textContent;

    fetch('/notifications/' + id + '/restore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (!data.success) return;

            // Remove from archived tab
            item.remove();

            // Remove archived empty state if present, then add item to inbox tab
            var inboxView = document.getElementById('notif-inbox-view');
            var emptyMsg = inboxView.querySelector('.no-notifications');
            if (emptyMsg) emptyMsg.remove();

            // Insert restored item at top of inbox
            var newItem = buildInboxItem(id, message, time);
            inboxView.prepend(newItem);

            // Show archived empty state if nothing left in archived tab
            var archivedView = document.getElementById('notif-archived-view');
            if (archivedView && archivedView.querySelectorAll('.notification-item').length === 0) {
                var empty = document.createElement('p');
                empty.className = 'no-notifications';
                empty.textContent = 'No archived notifications';
                archivedView.appendChild(empty);
            }
        })
        .catch(function (err) {
            console.error('Restore failed:', err);
        });
}

// Attach to all existing restore buttons on page load
document.querySelectorAll('.notification-restore-btn').forEach(function (btn) {
    btn.addEventListener('click', handleRestore);
});


// Inbox / Archived Toggle
var btnInbox = document.getElementById('btn-notif-inbox');
var btnArchived = document.getElementById('btn-notif-archived');
var inboxView = document.getElementById('notif-inbox-view');
var archivedView = document.getElementById('notif-archived-view');

if (btnInbox && btnArchived) {
    btnInbox.addEventListener('click', function () {
        btnInbox.classList.add('active');
        btnArchived.classList.remove('active');
        inboxView.classList.remove('hidden');
        archivedView.classList.add('hidden');
    });

    btnArchived.addEventListener('click', function () {
        btnArchived.classList.add('active');
        btnInbox.classList.remove('active');
        archivedView.classList.remove('hidden');
        inboxView.classList.add('hidden');
    });
}

// Archived select / bulk delete
var archivedSelectBtn = document.getElementById('archived-select-btn');
var archivedRemoveBtn = document.getElementById('archived-remove-btn');
var selectModeActive = false;

if (archivedSelectBtn) {
    archivedSelectBtn.addEventListener('click', function () {
        selectModeActive = !selectModeActive;
        var checkboxes = document.querySelectorAll('#notif-archived-view .notif-checkbox');
        checkboxes.forEach(function (cb) {
            cb.classList.toggle('hidden', !selectModeActive);
            if (!selectModeActive) cb.checked = false;
        });
        archivedSelectBtn.textContent = selectModeActive ? 'Cancel' : 'Select';
        archivedRemoveBtn.classList.toggle('hidden', !selectModeActive);
    });
}

if (archivedRemoveBtn) {
    archivedRemoveBtn.addEventListener('click', function () {
        var checked = document.querySelectorAll('#notif-archived-view .notif-checkbox:checked');
        if (checked.length === 0) return;
        var ids = Array.from(checked).map(function (cb) { return parseInt(cb.value); });
        btnLoading(archivedRemoveBtn);
        fetch('/notifications/delete-bulk', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids: ids })
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.success) { btnDone(archivedRemoveBtn); return; }
                ids.forEach(function (id) {
                    var item = document.querySelector('#notif-archived-view .notification-item[data-id="' + id + '"]');
                    if (item) item.remove();
                });
                // Exit select mode
                selectModeActive = false;
                archivedSelectBtn.textContent = 'Select';
                archivedRemoveBtn.classList.add('hidden');
                document.querySelectorAll('#notif-archived-view .notif-checkbox').forEach(function (cb) {
                    cb.classList.add('hidden');
                });
                // Show empty state if nothing left
                var remaining = document.querySelectorAll('#notif-archived-view .notification-item');
                if (remaining.length === 0) {
                    var toolbar = document.getElementById('archived-select-btn').closest('.archived-toolbar');
                    if (toolbar) toolbar.remove();
                    var empty = document.createElement('p');
                    empty.className = 'no-notifications';
                    empty.textContent = 'No archived notifications';
                    document.getElementById('notif-archived-view').appendChild(empty);
                }
            });
    });
}

var inboxMarkAllReadBtn = document.getElementById('inbox-mark-all-read-btn');

if (inboxMarkAllReadBtn) {
    inboxMarkAllReadBtn.addEventListener('click', function () {
        btnLoading(inboxMarkAllReadBtn);
    
        fetch('/notifications/mark-all-read', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        })
            .then(function (r) { return r.json(); })
            .then(function(data) {
                if(!data.success) { btnDone(inboxMarkAllReadBtn); return; }
                
                // Every inbox item stays put, just strip the 'unread' class, so the highlight disappears.
                document.querySelectorAll('#notif-inbox-view .notification-item.unread').forEach(function (el){
                    el.classList.remove('unread');
                });

                // Remove the bell badge
                var badge = document.getElementById('notif-unread-badge');
                if (badge) badge.remove();

                inboxMarkAllReadBtn.remove();
                        
            });
            
     });
}

var inboxArchiveAllBtn = document.getElementById('inbox-archive-all-btn');

if (inboxArchiveAllBtn) {
    inboxArchiveAllBtn.addEventListener('click', function () {
        var inboxView = document.getElementById('notif-inbox-view');
        var archivedView = document.getElementById('notif-archived-view');

        // Snapshot inbox items before removing them
        var items = Array.from(inboxView.querySelectorAll('.notification-item'));
        var snapshots = items.map(function (el) {
            return {
                id: el.dataset.id,
                message: el.querySelector('.notification-message').textContent,
                time: el.querySelector('.notification-time').textContent
            };
        });

        btnLoading(inboxArchiveAllBtn);
        fetch('/notifications/archive-all', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.success) { btnDone(inboxArchiveAllBtn); return; }

                // Clear inbox
                items.forEach(function (el) { el.remove(); });
                var inboxToolbar = inboxView.querySelector('.archived-toolbar');
                if (inboxToolbar) inboxToolbar.remove();
                var emptyInbox = document.createElement('p');
                emptyInbox.className = 'no-notifications';
                emptyInbox.textContent = 'No notifications';
                inboxView.appendChild(emptyInbox);

                // Clear bell badge
                var badge = document.getElementById('notif-unread-badge');
                if (badge) badge.textContent = '0';

                // If archived view has no toolbar yet, inject one
                if (!archivedView.querySelector('.archived-toolbar')) {
                    var emptyMsg = archivedView.querySelector('.no-notifications');
                    if (emptyMsg) emptyMsg.remove();

                    var toolbar = document.createElement('div');
                    toolbar.className = 'archived-toolbar';
                    toolbar.innerHTML = `
                        <button type="button" id="archived-remove-btn" class="archived-remove-btn hidden">Remove</button>
                        <button type="button" id="archived-delete-all-btn" class="archived-remove-btn">Delete All</button>
                        <button type="button" id="archived-select-btn" class="archived-select-btn">Select</button>
                    `;
                    archivedView.prepend(toolbar);

                    // Re-bind toolbar buttons (they didn't exist at page load)
                    var newSelectBtn = toolbar.querySelector('#archived-select-btn');
                    var newRemoveBtn = toolbar.querySelector('#archived-remove-btn');
                    var newDeleteAllBtn = toolbar.querySelector('#archived-delete-all-btn');

                    if (newSelectBtn) {
                        newSelectBtn.addEventListener('click', function () {
                            selectModeActive = !selectModeActive;
                            archivedView.querySelectorAll('.notif-checkbox').forEach(function (cb) {
                                cb.classList.toggle('hidden', !selectModeActive);
                                if (!selectModeActive) cb.checked = false;
                            });
                            newSelectBtn.textContent = selectModeActive ? 'Cancel' : 'Select';
                            newRemoveBtn.classList.toggle('hidden', !selectModeActive);
                        });
                    }
                    if (newRemoveBtn) {
                        newRemoveBtn.addEventListener('click', function () {
                            var checked = archivedView.querySelectorAll('.notif-checkbox:checked');
                            if (checked.length === 0) return;
                            var ids = Array.from(checked).map(function (cb) { return parseInt(cb.value); });
                            btnLoading(newRemoveBtn);
                            fetch('/notifications/delete-bulk', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ ids: ids })
                            }).then(function (r) { return r.json(); }).then(function (d) {
                                if (!d.success) { btnDone(newRemoveBtn); return; }
                                ids.forEach(function (id) {
                                    var el = archivedView.querySelector('.notification-item[data-id="' + id + '"]');
                                    if (el) el.remove();
                                });
                                selectModeActive = false;
                                newSelectBtn.textContent = 'Select';
                                newRemoveBtn.classList.add('hidden');
                                archivedView.querySelectorAll('.notif-checkbox').forEach(function (cb) { cb.classList.add('hidden'); });
                                if (archivedView.querySelectorAll('.notification-item').length === 0) {
                                    toolbar.remove();
                                    var ep = document.createElement('p');
                                    ep.className = 'no-notifications';
                                    ep.textContent = 'No archived notifications';
                                    archivedView.appendChild(ep);
                                }
                            });
                        });
                    }
                    if (newDeleteAllBtn) {
                        newDeleteAllBtn.addEventListener('click', function () {
                            var allItems = archivedView.querySelectorAll('.notification-item');
                            if (allItems.length === 0) return;
                            var ids = Array.from(allItems).map(function (el) { return parseInt(el.dataset.id); });
                            btnLoading(newDeleteAllBtn);
                            fetch('/notifications/delete-bulk', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ ids: ids })
                            }).then(function (r) { return r.json(); }).then(function (d) {
                                if (!d.success) { btnDone(newDeleteAllBtn); return; }
                                allItems.forEach(function (el) { el.remove(); });
                                toolbar.remove();
                                var ep = document.createElement('p');
                                ep.className = 'no-notifications';
                                ep.textContent = 'No archived notifications';
                                archivedView.appendChild(ep);
                            });
                        });
                    }
                }

                // Prepend newly archived items to archived view (most recent first)
                snapshots.reverse().forEach(function (s) {
                    var newItem = buildArchivedItem(s.id, s.message, s.time);
                    var firstItem = archivedView.querySelector('.notification-item');
                    if (firstItem) {
                        archivedView.insertBefore(newItem, firstItem);
                    } else {
                        archivedView.appendChild(newItem);
                    }
                });
            });
    });
}

// Delete All (archived)
var archivedDeleteAllBtn = document.getElementById('archived-delete-all-btn');
if (archivedDeleteAllBtn) {
    archivedDeleteAllBtn.addEventListener('click', function () {
        var items = document.querySelectorAll('#notif-archived-view .notification-item');
        if (items.length === 0) return;
        var ids = Array.from(items).map(function (el) { return parseInt(el.dataset.id); });
        btnLoading(archivedDeleteAllBtn);
        fetch('/notifications/delete-bulk', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids: ids })
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.success) { btnDone(archivedDeleteAllBtn); return; }
                var archivedView = document.getElementById('notif-archived-view');
                archivedView.querySelectorAll('.notification-item').forEach(function (el) { el.remove(); });
                var toolbar = archivedView.querySelector('.archived-toolbar');
                if (toolbar) toolbar.remove();
                var empty = document.createElement('p');
                empty.className = 'no-notifications';
                empty.textContent = 'No archived notifications';
                archivedView.appendChild(empty);
            });
    });
}
