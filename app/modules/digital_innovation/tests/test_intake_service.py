"""Tests for services/intake.py, called directly (no HTTP)."""
from app.modules.digital_innovation.models import DiProject, DiIntakeItem
from app.modules.digital_innovation.services.intake import declined_feature_ids


def _marker(db_session, project, source_type, source_ref, status):
    item = DiIntakeItem(
        di_project_id=project.id, source_type=source_type,
        source_ref=source_ref, title='Marker', status=status,
    )
    db_session.add(item)
    db_session.flush()
    return item


def test_declined_feature_ids_returns_only_dismissed_feature_request_refs(app, db_session):
    project = DiProject(name='OVP', lifecycle='active', is_permanent=True)
    db_session.add(project)
    db_session.flush()
    _marker(db_session, project, 'feature_request', '101', 'dismissed')
    _marker(db_session, project, 'feature_request', '102', 'pending')
    _marker(db_session, project, 'slack', '103', 'dismissed')
    _marker(db_session, project, 'feature_request', 'not-a-number', 'dismissed')

    ids = declined_feature_ids()

    assert 101 in ids
    assert not {102, 103} & ids
