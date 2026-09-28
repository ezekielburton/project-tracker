"""Admin achievements API: deletes that other rows still point at, the
upload folder, and the 'project_submitted' trigger actually firing."""
import os
from datetime import datetime

from app.modules.core.shared.models import (
    User, Project, ProjectSubmission, ProjectSubmissionFile,
    Achievement, AchievementCategory, AchievementBorder, UserAchievement,
    UserDisplaySettings, UserPinnedAchievement,
)
from app.modules.core.shared.testing import login_as


def _user(db_session, tag, role='admin'):
    u = User(name=f'Ach {tag}', email=f'ach-{tag}@example.com', role=role)
    u.set_password('pw123456')
    db_session.add(u)
    db_session.flush()
    return u


def _achievement(db_session, trigger='user_login', border=None):
    cat = AchievementCategory(name='Test cat')
    db_session.add(cat)
    db_session.flush()
    a = Achievement(category_id=cat.id, name='Test ach', trigger_event=trigger,
                    threshold=1, border_id=border.id if border else None)
    db_session.add(a)
    db_session.flush()
    return a


def test_delete_achievement_clears_pins_and_active_choices(app, client, db_session):
    admin = _user(db_session, 'del-admin')
    holder = _user(db_session, 'del-holder', role='designer')
    ach = _achievement(db_session)
    ua = UserAchievement(user_id=holder.id, achievement_id=ach.id, progress=1, earned_at=datetime.utcnow())
    db_session.add(ua)
    db_session.flush()
    db_session.add(UserPinnedAchievement(user_id=holder.id, user_achievement_id=ua.id, pin_order=1))
    db_session.add(UserDisplaySettings(user_id=holder.id, active_badge_id=ua.id, active_title_id=ua.id))
    db_session.commit()

    login_as(client, app, admin, 'pw123456')
    resp = client.delete(f'/admin/api/achievements/{ach.id}')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True

    assert Achievement.query.get(ach.id) is None
    assert UserPinnedAchievement.query.filter_by(user_id=holder.id).count() == 0
    settings = UserDisplaySettings.query.filter_by(user_id=holder.id).one()
    assert settings.active_badge_id is None
    assert settings.active_title_id is None


def test_delete_border_clears_active_border(app, client, db_session):
    admin = _user(db_session, 'border-admin')
    holder = _user(db_session, 'border-holder', role='designer')
    border = AchievementBorder(name='Gold', css_class='border-gold')
    db_session.add(border)
    db_session.flush()
    db_session.add(UserDisplaySettings(user_id=holder.id, active_border_id=border.id))
    db_session.commit()

    login_as(client, app, admin, 'pw123456')
    resp = client.delete(f'/admin/api/achievement-borders/{border.id}')
    assert resp.status_code == 200
    assert AchievementBorder.query.get(border.id) is None
    assert UserDisplaySettings.query.filter_by(user_id=holder.id).one().active_border_id is None


def test_upload_folder_anchored_to_app_static(app):
    from app.modules.achievements.routes.admin_achievements import ACHIEVEMENT_UPLOAD_FOLDER
    assert ACHIEVEMENT_UPLOAD_FOLDER == os.path.join(app.root_path, 'static', 'achievements')


def test_submit_to_client_fires_project_submitted(app, client, db_session, monkeypatch):
    # Stub the NAS/cache side of the send; the route's DB flow runs for real.
    monkeypatch.setattr('app.modules.core.shared.services.nas.upload_app_file', lambda *a, **kw: None)
    monkeypatch.setattr('app.modules.projects.lib.submission_cache.build_zip_bytes', lambda entries: b'zip')
    monkeypatch.setattr('app.modules.projects.lib.submission_cache.clear_submission_cache', lambda *a: None)
    monkeypatch.setattr('app.modules.core.shared.services.notifications.notify_of_submission_to_client',
                        lambda *a, **kw: None)

    sender = _user(db_session, 'sender')
    ach = _achievement(db_session, trigger='project_submitted')
    project = Project(name='Ach Submit Project', brief_type='standard',
                      cs_lead_id=sender.id, created_by_id=sender.id, project_status='in_design')
    db_session.add(project)
    db_session.flush()
    draft = ProjectSubmission(project_id=project.id, filename='draft', original_filename='draft',
                              file_type='draft', uploaded_by_id=sender.id, is_active=True,
                              workflow_status='internal_review')
    db_session.add(draft)
    db_session.flush()
    db_session.add(ProjectSubmissionFile(submission_id=draft.id, project_id=project.id,
                                         original_filename='deck.pdf', file_type='pdf',
                                         uploaded_by_id=sender.id, storage_location='cache',
                                         local_cache_path='unused', is_main_deck=True))
    db_session.commit()

    login_as(client, app, sender, 'pw123456')
    resp = client.post(f'/projects/{project.id}/overlay/submissions/draft/submit-to-client',
                       json={'scope': 'ckv'})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()['success'] is True

    ua = UserAchievement.query.filter_by(user_id=sender.id, achievement_id=ach.id).one()
    assert ua.earned_at is not None
