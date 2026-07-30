from app import create_app, db
from app.models import User, Project, ProjectDesigner, Scope, ProjectReviewer, ProjectApproval

app = create_app()

with app.app_context():
    print("Database URL:", app.config['SQLALCHEMY_DATABASE_URI'])
    print("Models known to SQLAlchemy:", db.metadata.tables.keys())
    db.create_all()
    print("Done")