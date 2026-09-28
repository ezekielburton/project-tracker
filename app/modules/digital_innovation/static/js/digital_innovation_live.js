// Digital Innovation: live-refresh helper for the department-wide screens
// (Performance, Edit Templates, Archive). The board has its own per-project
// stream in digital_innovation_board.js.
//
// diWatchDashboardStream(key, markerSelector, onPing) keeps one EventSource
// to /sse/digital-innovation open while markerSelector is on the page, and
// closes it on SPA nav away. `key` namespaces each screen's window state.
// Gotcha: the helix:navigated listener is bound on the first call per key,
// so its sync() keeps the first onPing; callbacks must not close over
// per-visit state.
function diWatchDashboardStream(key, markerSelector, onPing) {
    var streamKey = '_diDashStream_' + key;
    var watchKey = '_diDashWatching_' + key;
    var wiredKey = '_diDashWired_' + key;

    function sync() {
        var present = !!document.querySelector(markerSelector);
        if (window[watchKey] === present) return; // already in the right state
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
