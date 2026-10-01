/* Roadmap page: the month filter and each item's one-line note. SPA nav
   re-runs this file on every visit, so it binds to the fresh page. */
(function () {
    var TEMPLATE_CONTRACT = {
        'ids': {
            'root': 'roadmap'
        },
        'classes': {
            'filter': 'roadmap-seg',
            'group': 'roadmap-group',
            'row': 'roadmap-row',
            'countdown': 'roadmap-countdown',
            'countdownRow': 'roadmap-countdown-row',
            'countdownDue': 'roadmap-countdown-due',
            'countdownDone': 'roadmap-countdown-done'
        },
        'attributes': {
            'month': 'data-month',
            'deadline': 'data-deadline',
            'unit': 'data-unit'
        }
    };

    var ids = TEMPLATE_CONTRACT.ids;
    var cls = TEMPLATE_CONTRACT.classes;
    var attrs = TEMPLATE_CONTRACT.attributes;
    var OPEN = 'roadmap-item--open';
    var FLIPPING = 'roadmap-flip--go';

    var root = document.getElementById(ids.root);
    if (!root) return;

    root.addEventListener('click', function (e) {
        var filterButton = e.target.closest('.' + cls.filter + ' button');
        if (filterButton) { showMonth(filterButton); return; }
        var row = e.target.closest('.' + cls.row);
        if (row) toggleNote(row);
    });

    function showMonth(button) {
        var month = button.getAttribute(attrs.month);
        root.querySelectorAll('.' + cls.filter + ' button').forEach(function (b) {
            b.setAttribute('aria-pressed', String(b === button));
        });
        root.querySelectorAll('.' + cls.group).forEach(function (group) {
            group.hidden = month !== 'all' && group.getAttribute(attrs.month) !== month;
        });
    }

    function toggleNote(row) {
        var item = row.parentNode;
        var open = !item.classList.contains(OPEN);
        item.classList.toggle(OPEN, open);
        row.setAttribute('aria-expanded', String(open));
    }

    // The countdown ticks every second; a card flips only when its value changes.
    var countdown = root.querySelector('.' + cls.countdown);
    if (countdown) startCountdown(countdown);

    function startCountdown(box) {
        var deadline = new Date(box.getAttribute(attrs.deadline)).getTime();
        var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        var cards = {};
        box.querySelectorAll('[' + attrs.unit + ']').forEach(function (card) {
            cards[card.getAttribute(attrs.unit)] = card;
            card.addEventListener('animationend', function (e) {
                if (e.animationName !== 'roadmap-flip-up') return;
                half(card, 'bottom').textContent = card.getAttribute('data-value');
                card.classList.remove(FLIPPING);
            });
        });

        // The interval outlives an SPA swap, so each visit stops the last one.
        if (window.roadmapCountdownTimer) clearInterval(window.roadmapCountdownTimer);
        tick(true);
        window.roadmapCountdownTimer = setInterval(function () {
            if (!document.body.contains(box)) {
                clearInterval(window.roadmapCountdownTimer);
                return;
            }
            tick(false);
        }, 1000);

        function tick(first) {
            var left = Math.max(0, Math.floor((deadline - Date.now()) / 1000));
            if (left === 0) {
                finish();
                return;
            }
            var parts = {
                days: Math.floor(left / 86400),
                hours: Math.floor((left % 86400) / 3600),
                minutes: Math.floor((left % 3600) / 60),
                seconds: left % 60
            };
            Object.keys(parts).forEach(function (unit) {
                if (cards[unit]) setCard(cards[unit], pad(parts[unit]), first || reduce);
            });
        }

        // At zero the cards give way to a plain message; status still changes by hand.
        function finish() {
            clearInterval(window.roadmapCountdownTimer);
            box.querySelector('.' + cls.countdownRow).hidden = true;
            box.querySelector('.' + cls.countdownDue).hidden = true;
            box.querySelector('.' + cls.countdownDone).hidden = false;
        }
    }

    function setCard(card, value, instant) {
        var old = card.getAttribute('data-value');
        if (old === value) return;
        card.setAttribute('data-value', value);
        if (instant || old === null) {
            half(card, 'top').textContent = value;
            half(card, 'bottom').textContent = value;
            return;
        }
        half(card, 'top').textContent = value;
        half(card, 'bottom').textContent = old;
        half(card, 'leaf-top').textContent = old;
        half(card, 'leaf-bottom').textContent = value;
        card.classList.remove(FLIPPING);
        void card.offsetWidth;  // restart the animation
        card.classList.add(FLIPPING);
    }

    function half(card, which) {
        return card.querySelector('.roadmap-flip-' + which + ' span');
    }

    function pad(n) {
        return n < 10 ? '0' + n : String(n);
    }
})();
