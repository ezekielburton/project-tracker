"""Digital Innovation live refresh: live_events.py's DiStepTemplate sentinel
getter and sse_relay.py's DI dashboard broadcast, called directly (no HTTP)."""
from app.modules.core.shared.services.live_events import _DI_PROJECT_ID_GETTERS, _collect_ids
from app.modules.core.shared.services import sse_relay
from app.modules.digital_innovation.models import DiStepTemplate


# `app` imports every model, so DiStepTemplate's mapper can configure when
# this file runs alone.
def test_di_step_template_getter_returns_the_sentinel(app):
    template = DiStepTemplate(stage='researching', title='Untracked', sort_order=0)
    getter = _DI_PROJECT_ID_GETTERS['DiStepTemplate']
    assert getter(template) == -1


def test_collect_ids_picks_up_the_di_step_template_sentinel(app):
    # _collect_ids skips falsy ids, so the sentinel must be -1, not 0.
    template = DiStepTemplate(stage='researching', title='Untracked', sort_order=0)
    seen = set()
    _collect_ids([template], seen, _DI_PROJECT_ID_GETTERS)
    assert seen == {-1}


def test_collect_ids_ignores_objects_with_no_registered_getter():
    seen = set()
    _collect_ids([object()], seen, _DI_PROJECT_ID_GETTERS)
    assert seen == set()


def test_dashboard_broadcast_receives_every_di_change(monkeypatch):
    # Dashboard subscribers hear every di_project_id, including the -1
    # template sentinel, which no per-project subscriber receives.
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
