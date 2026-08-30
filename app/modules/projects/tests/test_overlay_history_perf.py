"""
Regression test: the overlay Submissions history now loads its files and
included deliverables in bulk. This proves the query count no longer grows with
the number of revisions, and that the rendered history is unchanged.
"""

from datetime import datetime, timedelta

from app.modules.core.shared.models import (
    User, Project, Deliverable, ProjectSubmission,
    ProjectSubmissionFile, ProjectSubmissionDeliverable
)
from app.modules.core.shared.testing import login_as, count_queries
from flask import url_for

def _build_scope(db_session, revision_count):
    """A Standard-brief project with `revision_count` decks sent to the
    client, each with one file and linked to the same two deliverables."""
    user = User(name='CS Lead', email=f'a1test{revision_count}@example.com', role='cs')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()

    project = Project(
        name='A1 Test Project', brief_type='standard',
        cs_lead_id=user.id, created_by_id=user.id,
    )
    db_session.add(project)
    db_session.flush()

    deliverables = []
    for i in range(2):
        d = Deliverable(project_id=project.id, name=f'Delverable {i+1}', created_by_id=user.id)
        db_session.add(d)
        deliverables.append(d)
    db_session.flush()

    base_time = datetime.utcnow()
    for i in range(revision_count):
        label = 'Initial' if i == 0 else f'Revision {i}'
        sub = ProjectSubmission(
            project_id=project.id,
            filename=f'deck-{i}.pptx',
            original_filename=f'A1 Test Project - {label}.pptx',
            file_type='PPTX',
            uploaded_by_id=user.id,
            phase='concept_kv',
            workflow_status='sent_to_client',
            submitted_to_client_at=base_time + timedelta(hours=i),
            submitted_by_id=user.id,
        )
        db_session.add(sub)
        db_session.flush()

        db_session.add(ProjectSubmissionFile(
            submission_id=sub.id, project_id=project.id,
            original_filename=sub.original_filename, file_type='PPTX',
            uploaded_by_id=user.id, is_main_deck=True,
        ))
        for d in deliverables:
            db_session.add(ProjectSubmissionDeliverable(submission_id=sub.id, deliverable_id=d.id))

    db_session.flush()
    return user, project, deliverables

def _get_submissions_page(app, client, user, project):
    login_as(client, app, user, 'password123')
    with app.test_request_context():
        url = url_for('project_overlay.overlay_submissions', project_id=project.id)
    return client.get(url)

def test_overlay_submissions_requires_auth(app, client):
    with app.test_request_context():
        url = url_for('project_overlay.overlay_submissions', project_id=1)
    resp = client.get(url)
    assert resp.status_code in (302, 401)


def test_overlay_submissions_history_renders_all_revisions(app, client, db_session):
    user, project, deliverables = _build_scope(db_session, revision_count=3)
    resp = _get_submissions_page(app, client, user, project)

    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'History (3)' in body
    for d in deliverables:
        assert d.name in body


def test_overlay_submissions_history_query_count_does_not_scale_with_revisions(app, client, db_session):
    user_small, project_small, _ = _build_scope(db_session, revision_count=2)
    with count_queries() as small_count:
        resp = _get_submissions_page(app, client, user_small, project_small)
    assert resp.status_code == 200

    user_big, project_big, _ = _build_scope(db_session, revision_count=6)
    with count_queries() as big_count:
        resp = _get_submissions_page(app, client, user_big, project_big)
    assert resp.status_code == 200

    # Before the A1 fix this scaled with revision count (extra queries per
    # revision for files + included deliverables). After the fix it's flat.
    assert big_count[0] == small_count[0]     