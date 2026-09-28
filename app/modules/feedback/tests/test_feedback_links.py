"""Notification links into the Signal tray, and who sees comment-delete.

Key rule: every link a feedback notification carries must open with a GET.
"""
from app.modules.core.shared.models import BugReport, BugReportComment, Notification, User
from app.modules.core.shared.testing import login_as


def _user(db_session, tag, role='designer'):
    user = User(name=f'Links {tag}', email=f'links-{tag}@example.com', role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def test_old_feature_link_redirects_to_the_tray(app, client, db_session):
    login_as(client, app, _user(db_session, 'old-fr'), 'password123')
    resp = client.get('/feature-requests')
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith('/dashboard?signal=feature')


def test_old_bug_link_redirects_to_the_tray(app, client, db_session):
    login_as(client, app, _user(db_session, 'old-br'), 'password123')
    resp = client.get('/bug-reports')
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith('/dashboard?signal=bug')


def test_new_feedback_notifies_admin_with_a_tray_link(app, client, db_session):
    _user(db_session, 'admin', role='admin')
    author = _user(db_session, 'author')
    login_as(client, app, author, 'password123')

    feature_id = client.post('/feature-requests', json={
        'title': 'Link me', 'description': '...'}).get_json()['feature']['id']
    bug_id = client.post('/bug-reports', json={
        'title': 'Link me too', 'description': '...'}).get_json()['bug']['id']

    links = {n.link for n in Notification.query.filter_by(triggered_by_id=author.id)}
    assert f'/dashboard?signal=feature:{feature_id}' in links
    assert f'/dashboard?signal=bug:{bug_id}' in links
    for link in links:
        assert client.get(link).status_code == 200


def test_bug_comment_delete_follows_the_real_user_like_the_server(app, client, db_session):
    """An admin viewing as a designer can still delete comments (the route
    checks current_user), so the button must show."""
    admin = _user(db_session, 'emu-admin', role='admin')
    designer = _user(db_session, 'emu-designer')
    bug = BugReport(title='Emulated', description='...', submitted_by_id=designer.id, status='in_queue')
    db_session.add(bug)
    db_session.flush()
    db_session.add(BugReportComment(bug_id=bug.id, user_id=designer.id, body='hi'))
    db_session.flush()

    login_as(client, app, admin, 'password123')
    with client.session_transaction() as sess:
        sess['emulating_user_id'] = designer.id

    html = client.get(f'/bug-reports/{bug.id}').get_data(as_text=True)
    assert 'br-comment-delete' in html
