"""Coverage for services/intake.py — the seam other modules call to file
a pending item on the OVP board's Incoming tray. No route/HTTP layer
here; this module is called directly, in-process, by whatever module
ends up owning approved feedback."""
import pytest

from app.modules.digital_innovation.models import DiProject, DiIntakeItem
from app.modules.digital_innovation.services.intake import add_feedback_item


def test_add_feedback_item_attaches_to_the_permanent_project(app, db_session):
    permanent = DiProject(name='OVP', lifecycle='active', is_permanent=True)
    other = DiProject(name='Client - Nexus', lifecycle='active', is_permanent=False)
    db_session.add_all([permanent, other])
    db_session.flush()

    item = add_feedback_item('slack', '#feedback/123', 'Dark mode toggle broken')
    db_session.commit()

    assert item.di_project_id == permanent.id
    assert item.source_type == 'slack'
    assert item.source_ref == '#feedback/123'
    assert item.title == 'Dark mode toggle broken'
    assert item.description is None
    assert item.status == 'pending'


def test_add_feedback_item_stores_an_optional_description(app, db_session):
    permanent = DiProject(name='OVP', lifecycle='active', is_permanent=True)
    db_session.add(permanent)
    db_session.flush()

    item = add_feedback_item(
        'email', 'msg-42', 'Slow report export',
        description="Takes 30s+ for the quarterly report.",
    )
    db_session.commit()

    assert item.description == "Takes 30s+ for the quarterly report."


def test_add_feedback_item_raises_without_a_permanent_project(app, db_session):
    # No is_permanent=True project seeded at all in this test's transaction.
    with pytest.raises(ValueError):
        add_feedback_item('slack', '#feedback/1', 'Some item')


def test_add_feedback_item_is_retrievable_as_a_di_intake_item(app, db_session):
    permanent = DiProject(name='OVP', lifecycle='active', is_permanent=True)
    db_session.add(permanent)
    db_session.flush()

    item = add_feedback_item('slack', None, 'No source ref item')
    db_session.commit()

    fetched = DiIntakeItem.query.get(item.id)
    assert fetched is not None
    assert fetched.source_ref is None
