"""Overlay chat drawer and chat attachments: readable by anyone with the
Projects workspace (view_workspace), refused for roles outside it."""
from flask import url_for

from app.modules.core.shared.models import Project, ProjectNote, User
from app.modules.core.shared.testing import login_as


def _user(db_session, tag, role):
    user = User(name=f'Chat Access {tag}', email=f'chat-access-{tag}@example.com', role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    return user


def _project_with_attachment(db_session, cs_lead):
    project = Project(name='Chat Access Project', brief_type='standard',
                      cs_lead_id=cs_lead.id, created_by_id=cs_lead.id,
                      project_status='in_design')
    db_session.add(project)
    db_session.flush()
    note = ProjectNote(project_id=project.id, author_id=cs_lead.id, body='secret plan',
                       attachment_filename='abc.png', attachment_original_filename='plan.png',
                       attachment_type='image')
    db_session.add(note)
    db_session.flush()
    return project, note


def _urls(app, project, note):
    with app.test_request_context():
        return (url_for('project_notes.overlay_chat', project_id=project.id),
                url_for('project_notes.chat_attachment', note_id=note.id))


def _fake_nas(monkeypatch):
    from app.modules.core.shared.services import nas
    monkeypatch.setattr(nas, 'download_app_file', lambda path: b'png-bytes')


def test_role_without_the_workspace_cannot_read_chat_or_attachment(app, client, db_session, monkeypatch):
    _fake_nas(monkeypatch)
    cs_lead = _user(db_session, 'lead', 'cs')
    officer = _user(db_session, 'hse', 'hse')
    project, note = _project_with_attachment(db_session, cs_lead)
    chat_url, attachment_url = _urls(app, project, note)

    login_as(client, app, officer, 'password123')
    chat = client.get(chat_url)
    assert chat.status_code == 403
    assert 'secret plan' not in chat.get_data(as_text=True)
    assert client.get(attachment_url).status_code == 403


def test_designer_not_on_the_project_can_still_read_chat(app, client, db_session, monkeypatch):
    _fake_nas(monkeypatch)
    cs_lead = _user(db_session, 'lead2', 'cs')
    designer = _user(db_session, 'designer', 'designer')
    project, note = _project_with_attachment(db_session, cs_lead)
    chat_url, attachment_url = _urls(app, project, note)

    login_as(client, app, designer, 'password123')
    assert client.get(chat_url).status_code == 200
    assert client.get(attachment_url).status_code == 200


def test_project_cs_lead_can_read_chat_and_attachment(app, client, db_session, monkeypatch):
    _fake_nas(monkeypatch)
    cs_lead = _user(db_session, 'lead3', 'cs')
    project, note = _project_with_attachment(db_session, cs_lead)
    chat_url, attachment_url = _urls(app, project, note)

    login_as(client, app, cs_lead, 'password123')
    chat = client.get(chat_url)
    assert chat.status_code == 200
    assert 'secret plan' in chat.get_data(as_text=True)
    attachment = client.get(attachment_url)
    assert attachment.status_code == 200
    assert attachment.data == b'png-bytes'


def test_management_can_read_any_projects_chat(app, client, db_session, monkeypatch):
    _fake_nas(monkeypatch)
    cs_lead = _user(db_session, 'lead4', 'cs')
    boss = _user(db_session, 'boss', 'management')
    project, note = _project_with_attachment(db_session, cs_lead)
    chat_url, attachment_url = _urls(app, project, note)

    login_as(client, app, boss, 'password123')
    assert client.get(chat_url).status_code == 200
    assert client.get(attachment_url).status_code == 200
