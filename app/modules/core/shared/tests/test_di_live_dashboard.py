"""Coverage for the DI-wide SSE broadcast infrastructure added 3 Sep 2026
(digital innovation module Performance/Templates/Archive live refresh —
see digital_innovation_module.md's "SPA/SSE readiness" entry). No route
or DB layer here — this exercises live_events.py's DiStepTemplate
sentinel getter and sse_relay.py's dashboard-broadcast dispatch directly,
the same way test_step_engine.py exercises lib/step_engine.py directly
against the database rather than through HTTP. Neither
live_events.py nor sse_relay.py had any test coverage at all before this
(true for the main Projects module's own _dashboard_subscribers/
_dispatch_project_change too) — this file is scoped to just what this
round of work added or changed, not a retroactive sweep of the whole
choke point."""
from app.modules.core.shared.services.live_events import _DI_PROJECT_ID_GETTERS, _collect_ids
from app.modules.core.shared.services import sse_relay
from app.modules.digital_innovation.models import DiStepTemplate


def test_di_step_template_getter_returns_the_sentinel():
    template = DiStepTemplate(stage='researching', title='Untracked', sort_order=0)
    getter = _DI_PROJECT_ID_GETTERS['DiStepTemplate']
    assert getter(template) == -1


def test_collect_ids_picks_up_the_di_step_template_sentinel():
    # The regression this guards against: _collect_ids does
    # `if value: seen.add(value)` — a sentinel of 0 is falsy in Python
    # and would silently never be collected at all. -1 is truthy, so it
    # must actually land in the set.
    template = DiStepTemplate(stage='researching', title='Untracked', sort_order=0)
    seen = set()
    _collect_ids([template], seen, _DI_PROJECT_ID_GETTERS)
    assert seen == {-1}


def test_collect_ids_ignores_objects_with_no_registered_getter():
    seen = set()
    _collect_ids([object()], seen, _DI_PROJECT_ID_GETTERS)
    assert seen == set()


def test_dashboard_broadcast_receives_every_di_change(monkeypatch):
    # A dashboard-style subscriber (Performance/Templates/Archive) must
    # hear about a change to ANY di_project_id — including the -1
    # sentinel a DiStepTemplate edit uses, which never matches a real
    # per-project subscriber.
    sse_relay._di_project_subscribers.clear()
    sse_relay._di_dashboard_subscribers.clear()

    project_q = sse_relay.subscribe_di_project(42)
    dashboard_q = sse_relay.subscribe_di_dashboard()
    try:
        sse_relay._dispatch_di_change('42')
        assert project_q.get_nowait() == 42
        assert dashboard_q.get_nowait() == 42

        sse_relay._dispatch_di_change('-1')
        assert dashboard_q.get_nowait() == -1
        assert project_q.empty()  # the sentinel never reaches project 42's own subscriber
    finally:
        sse_relay.unsubscribe_di_project(42, project_q)
        sse_relay.unsubscribe_di_dashboard(dashboard_q)


def test_dashboard_broadcast_ignores_a_non_integer_payload():
    sse_relay._di_dashboard_subscribers.clear()
    dashboard_q = sse_relay.subscribe_di_dashboard()
    try:
        sse_relay._dispatch_di_change('not-an-id')
        assert dashboard_q.empty()
    finally:
        sse_relay.unsubscribe_di_dashboard(dashboard_q)


def test_unsubscribe_di_dashboard_stops_further_delivery():
    sse_relay._di_dashboard_subscribers.clear()
    dashboard_q = sse_relay.subscribe_di_dashboard()
    sse_relay.unsubscribe_di_dashboard(dashboard_q)

    sse_relay._dispatch_di_change('7')
    assert dashboard_q.empty()
