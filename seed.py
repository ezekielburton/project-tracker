from app import create_app, db
from app.models import Scope

app = create_app()

with app.app_context():
    Scope.query.delete()
    db.session.commit()

    scopes = [
        'Event POSM',
        'POSM',
        'POSM Elements',
        'FSU',
        'Digital',
        'Motion Graphics',
        'Video Production',
        'SBD',
        'App Development',
        'Game Development',
    ]

    for name in scopes:
        db.session.add(Scope(name=name))

    db.session.commit()
    print("Scopes seeded")