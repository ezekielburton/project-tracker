// notifications.js — notification sound, desktop notifications, live inbox
// updates, the bell panel's inbox/archived handlers, and tr[data-href] row links.
// Needs main.js loaded first (showToast, showAchievementToast, btnLoading, btnDone).
// Loaded once from base.html; the panel is outside #main-content, so the
// load-time bindings below survive SPA navigation.

// ── Notification Sound (Web Audio API) ──────────────────────────────────────
// Plays the user's chosen sound file, or a synthesized two-tone chime.
window.helixPlayNotificationSound = function (overrideUrl, overrideVolume) {
    // Any overrideUrl, including '' for the default chime (account.html's "Test
    // Sound"), plays even when sound is off. The no-argument poll call respects the toggle.
    var isExplicitTest = overrideUrl !== undefined;
    var prefs = window.HELIX_SOUND_PREFS || { enabled: true, volume: 1, url: null };

    if (!isExplicitTest && prefs.enabled === false) return;

    var url = isExplicitTest ? overrideUrl : prefs.url;
    var volume = (overrideVolume !== undefined) ? overrideVolume : (prefs.volume != null ? prefs.volume : 1);
    volume = Math.max(0, Math.min(1, volume));

    if (url) {
        var audio = new Audio(url);
        audio.volume = volume;
        audio.play().catch(function () {
            // Autoplay is blocked until the user interacts with the page; ignore.
        });
        return;
    }

    // No file chosen ("Default chime"): synthesize the chime.
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

        // Volume applies to the chime too.
        var peak = 0.25 * volume;
        var now = ctx.currentTime;
        playTone(880, now, 0.4, peak);
        playTone(1108, now + 0.18, 0.5, peak);
    } catch (e) {
        // AudioContext blocked before first user interaction; ignore.
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

// ── Notification Live Updates ────────────────────────────────────────────────
// Fetches /notifications/poll?since=<ISO> whenever /sse/notifications pings
// (a new notification committed). Falls back to a 30s poll while SSE is
// unavailable. The 'since' baseline lives in localStorage (shared by tabs).
(function () {
    // First visit: start the baseline at now so old notifications don't alert.
    if (!localStorage.getItem('helix_last_poll')) {
        localStorage.setItem('helix_last_poll', new Date().toISOString());
    }

    function pollNotifications() {
        // Also tells trays.js to refresh its bubbles.
        document.dispatchEvent(new CustomEvent('helix:user-stream'));
        var since = localStorage.getItem('helix_last_poll') || new Date().toISOString();

        fetch('/notifications/poll?since=' + encodeURIComponent(since))
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.notifications || data.notifications.length === 0) return;

                // Poll returns oldest first; the last one is the new baseline.
                var latest = data.notifications[data.notifications.length - 1];
                localStorage.setItem('helix_last_poll', latest.created_at);

                // One desktop notification + sound per batch, not per item.
                var msg = data.notifications[0].message;
                helixShowBrowserNotification(msg);
                window.helixPlayNotificationSound();

                // Per-item toasts only for types that need attention now.
                data.notifications.forEach(function (n) {
                    if (n.notification_type === 'achievement_earned' && typeof showAchievementToast === 'function') {
                        showAchievementToast(n.message);
                    }
                    if (n.notification_type === 'nas_upload_failed' && typeof showToast === 'function') {
                        showToast(n.message, 'error');
                    }
                });

                var badge = document.getElementById('notif-unread-badge');
                if (badge) {
                    var current = parseInt(badge.textContent, 10) || 0;
                    badge.textContent = current + data.notifications.length;
                } else {
                    // No badge when the count was 0: create it.
                    var bell = document.getElementById('notification-bell');
                    if (bell) {
                        var newBadge = document.createElement('span');
                        newBadge.className = 'bell-badge';
                        newBadge.id = 'notif-unread-badge';
                        newBadge.textContent = data.notifications.length;
                        bell.appendChild(newBadge);
                    }
                }

                // Prepend new items to the bell panel's inbox.
                var inboxView = document.getElementById('notif-inbox-view');
                if (inboxView) {
                    var emptyMsg = inboxView.querySelector('.no-notifications');
                    if (emptyMsg) emptyMsg.remove();

                    // Reverse so the newest ends up on top.
                    data.notifications.slice().reverse().forEach(function (n) {
                        var newItem = buildInboxItem(n.id, n.message, n.time_display || 'Just now');
                        newItem.classList.add('unread');
                        inboxView.prepend(newItem);
                    });
                }
            })
            .catch(function () {
                // Network error: skip this cycle.
            });
    }

    // 30s fallback, only while SSE is unavailable.
    var _fallbackInterval = null;
    function _startFallback() {
        if (_fallbackInterval !== null) return;
        _fallbackInterval = setInterval(pollNotifications, 30000);
    }
    function _stopFallback() {
        if (_fallbackInterval !== null) {
            clearInterval(_fallbackInterval);
            _fallbackInterval = null;
        }
    }

    // Start 5s after load to stay off the initial render.
    setTimeout(function () {
        pollNotifications();

        if (typeof EventSource === 'undefined') {
            _startFallback(); // no SSE in this browser
            return;
        }

        var source = new EventSource('/sse/notifications');
        source.onopen = _stopFallback;
        source.onmessage = function () {
            _stopFallback();
            pollNotifications();
        };
        source.onerror = function () {
            // Poll until SSE recovers.
            _startFallback();
        };
    }, 5000);
})();

// Any tr[data-href] navigates on click. Delegated on document so rows added by
// SPA navigation or JS work too. _clickableRowsWired guards against binding twice.
if (!window._clickableRowsWired) {
    window._clickableRowsWired = true;
    document.addEventListener('click', function (e) {
        // Leave clicks on links, buttons and selects inside the row alone.
        if (e.target.closest('a, button, select')) return;
        var row = e.target.closest('tr[data-href]');
        if (!row) return;
        if (window.navigateTo) {
            window.navigateTo(row.dataset.href);
        } else {
            window.location.href = row.dataset.href;
        }
    });
}

// Bell panel
const bell = document.getElementById('notification-bell');
const panel = document.getElementById('notification-panel');
const closeBtn = document.getElementById('close-notifications');

if (bell && panel) {
    bell.addEventListener('click', function (event) {
        event.stopPropagation();
        panel.classList.toggle('hidden');
    });
}

if (closeBtn && panel) {
    closeBtn.addEventListener('click', function () {
        panel.classList.add('hidden');
    });
}

// A click outside the panel closes it.
document.addEventListener('click', function (event) {
    if (panel && !panel.classList.contains('hidden')) {
        if (!panel.contains(event.target) && event.target !== bell) {
            panel.classList.add('hidden');
        }
    }
});

// Clicking an inbox item marks it read, then navigates. Delegated on the inbox
// so items added later (live poll, restore) open the same way.
var notifInboxEl = document.getElementById('notif-inbox-view');
if (notifInboxEl) {
    notifInboxEl.addEventListener('click', function (e) {
        var item = e.target.closest('.notification-item');
        if (!item || item.classList.contains('notification-item--archived')) return;
        if (e.target.closest('.notification-mark-read-btn')) return;
        // Approve/Deny buttons handle their own click.
        if (e.target.closest('.notification-inline-actions')) return;
        fetch('/notifications/' + item.dataset.id + '/read', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) window.location.href = data.redirect_url;
            });
    });
}

//-----------Notification Helpers------------------------------

// Builds an archived item client-side (after Archive All). `message` and `time`
// go in as text, matching the autoescaped server-rendered items.
function buildArchivedItem(id, message, time) {
    var div = document.createElement('div');
    div.className = 'notification-item notification-item--archived';
    div.dataset.id = id;

    // Must match the server-rendered archived item in base.html.
    div.innerHTML = `
        <input type="checkbox" class="notif-checkbox hidden" value="${id}">
        <div class="notification-content">
            <p class="notification-message"></p>
            <span class="notification-time"></span>
        </div>
        <button type="button" class="notification-restore-btn" data-id="${id}" title="Restore to inbox">↩</button>
    `;
    div.querySelector('.notification-message').textContent = message;
    div.querySelector('.notification-time').textContent = time;

    // Load-time bindings don't cover new nodes, so bind here.
    div.querySelector('.notification-restore-btn').addEventListener('click', handleRestore);

    return div;
}

// Builds an inbox item client-side (after restore or a live poll). `message` and
// `time` go in as text, matching the autoescaped server-rendered items.
function buildInboxItem(id, message, time) {
    var div = document.createElement('div');
    div.className = 'notification-item';
    div.dataset.id = id;

    div.innerHTML = `
        <div class="notification-content">
            <p class="notification-message"></p>
            <span class="notification-time"></span>
        </div>
        <button type="button" class="notification-mark-read-btn" data-id="${id}" title="Mark as read">✓</button>
    `;
    div.querySelector('.notification-message').textContent = message;
    div.querySelector('.notification-time').textContent = time;

    // The item body's click is handled by the inbox's delegated listener.
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

            // Only an unread item lowers the badge count.
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

// Bind server-rendered mark-read buttons.
document.querySelectorAll('.notification-mark-read-btn').forEach(function (btn) {
    btn.addEventListener('click', handleMarkRead);
})

// Approve/Deny buttons on an 'edit_access_requested' notification. Posts to
// project_overlay.py's approve/deny_edit_access(). Success removes only the
// button row (the message stays); failure re-enables the buttons.
function handleEditAccessDecision(e) {
    e.stopPropagation();

    var btn = this;
    var requestId = btn.dataset.requestId;
    var decision = btn.dataset.decision; // 'approve' | 'deny'
    var actionsEl = btn.closest('.notification-inline-actions');
    var buttons = actionsEl ? actionsEl.querySelectorAll('.notification-action-btn') : [];
    buttons.forEach(function (b) { b.disabled = true; });

    fetch('/projects/edit-access-requests/' + requestId + '/' + decision, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (!data.success) {
                buttons.forEach(function (b) { b.disabled = false; });
                var msg = data.error || 'Could not process this request.';
                if (window.showToast) { window.showToast(msg, 'error'); } else { alert(msg); }
                return;
            }
            if (actionsEl) actionsEl.remove();
        })
        .catch(function () {
            buttons.forEach(function (b) { b.disabled = false; });
            var msg = 'Something went wrong. Please try again.';
            if (window.showToast) { window.showToast(msg, 'error'); } else { alert(msg); }
        });
}

document.querySelectorAll('.notification-action-btn').forEach(function (btn) {
    btn.addEventListener('click', handleEditAccessDecision);
});

// Named so buildArchivedItem() can bind it to new restore buttons.
function handleRestore(e) {
    e.stopPropagation();

    var id = this.dataset.id;
    var item = this.closest('.notification-item');

    // Read these before the item is removed.
    var message = item.querySelector('.notification-message').textContent;
    var time = item.querySelector('.notification-time').textContent;

    fetch('/notifications/' + id + '/restore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (!data.success) return;

            item.remove();

            // Drop the inbox's empty-state message, then add the item on top.
            var inboxView = document.getElementById('notif-inbox-view');
            var emptyMsg = inboxView.querySelector('.no-notifications');
            if (emptyMsg) emptyMsg.remove();

            var newItem = buildInboxItem(id, message, time);
            inboxView.prepend(newItem);

            // Archived tab now empty: show its empty state.
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

// Bind server-rendered restore buttons.
document.querySelectorAll('.notification-restore-btn').forEach(function (btn) {
    btn.addEventListener('click', handleRestore);
});


// Inbox / Archived toggle
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

// Archived: select mode + remove selected
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
        if (archivedRemoveBtn) archivedRemoveBtn.classList.toggle('hidden', !selectModeActive);
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
                selectModeActive = false;
                archivedSelectBtn.textContent = 'Select';
                archivedRemoveBtn.classList.add('hidden');
                document.querySelectorAll('#notif-archived-view .notif-checkbox').forEach(function (cb) {
                    cb.classList.add('hidden');
                });
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
                
                // Items stay in the inbox; only the unread highlight goes.
                document.querySelectorAll('#notif-inbox-view .notification-item.unread').forEach(function (el){
                    el.classList.remove('unread');
                });

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

        // Snapshot the items so they can be rebuilt in the Archived tab.
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

                items.forEach(function (el) { el.remove(); });
                var inboxToolbar = inboxView.querySelector('.archived-toolbar');
                if (inboxToolbar) inboxToolbar.remove();
                var emptyInbox = document.createElement('p');
                emptyInbox.className = 'no-notifications';
                emptyInbox.textContent = 'No notifications';
                inboxView.appendChild(emptyInbox);

                var badge = document.getElementById('notif-unread-badge');
                if (badge) badge.remove();

                // Archived tab had no toolbar (it was empty): build one and bind it.
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

                    // Bind the new buttons; same logic as the load-time handlers for these IDs.
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

                // Newest first, above any existing archived items.
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

// Archived: Delete All
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
