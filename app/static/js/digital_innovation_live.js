// Digital Innovation — shared live-refresh connection helper for the
// three screens that show data spanning every project (or, for Edit
// Templates, no project at all): Performance, Edit Templates, Archive.
// Board has its own richer version of this same idea in digital_
// innovation_board.js (it also drives the Incoming badge, and watches a
// single project rather than the whole department) — this file is
// deliberately just the small reusable piece those three simpler screens
// need, kept separate from digital_innovation_shell.js so that file
// stays about exactly one thing (the .di-shell height sync).
//
// Loaded on templates.html/archive.html/performance.html only, not
// board.html.
//
// diWatchDashboardStream(key, markerSelector, onPing) opens ONE
// EventSource to the DI-wide broadcast route (/sse/digital-innovation —
// see sse.py's di_dashboard_stream, and sse_relay.py's
// _di_dashboard_subscribers) for as long as markerSelector is present on
// the page, and closes it the moment that stops being true — same
// "persistent document-level helix:navigated listener, bound once on
// first call, re-checks fresh DOM state every time" shape as board.js's
// _diSyncLiveStream, just parameterized so three screens can each call
// it once for their own marker element without stepping on each other's
// state (that's what `key` is for — it namespaces each screen's
// connection/guard vars on `window` so Performance's watcher doesn't
// clobber Templates' or Archive's).
//
// onPing is only actually wired up on the FIRST call for a given key —
// exactly like board.js's own guarded listener, this relies on every
// later call passing a behaviorally-identical callback (each one should
// just re-read fresh page state itself, never close over anything
// specific to one visit), which is true for all three current callers.
function diWatchDashboardStream(key, markerSelector, onPing) {
    var streamKey = '_diDashStream_' + key;
    var watchKey = '_diDashWatching_' + key;
    var wiredKey = '_diDashWired_' + key;

    function sync() {
        var present = !!document.querySelector(markerSelector);
        if (window[watchKey] === present) return; // already watching (or not watching) the right thing
        if (window[streamKey]) {
            window[streamKey].close();
            window[streamKey] = null;
        }
        window[watchKey] = present;
        if (!present || typeof EventSource === 'undefined') return;

        var source = new EventSource('/sse/digital-innovation');
        source.onmessage = onPing;
        window[streamKey] = source;
    }

    sync();
    if (!window[wiredKey]) {
        window[wiredKey] = true;
        document.addEventListener('helix:navigated', sync);
    }
}
