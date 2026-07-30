import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    with db.engine.connect() as conn:
        # Add the counter column — default 0 so all existing projects start clean
        conn.execute(text("""
ALTER TABLE project_designers
ADD CONSTRAINT uq_project_designers_project_team
UNIQUE (project_id, team);

"""))
        conn.commit()

    print("Migration complete: fixed db")

