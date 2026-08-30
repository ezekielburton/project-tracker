from app import create_app, db
from config import TestingConfig
from app.modules.core.shared.models import Project, User

app = create_app(TestingConfig)
with app.app_context():
    for p in Project.query.filter_by(name='A1 Test Project').all():
        db.session.delete(p)  # cascades to its deliverables/submissions
    for u in User.query.filter(User.email.in_(['a1test2@example.com', 'a1test3@example.com'])).all():
        db.session.delete(u)
    db.session.commit()
    print('cleaned up')