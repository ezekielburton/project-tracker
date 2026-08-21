"""
Migration: create job_number_seq, a Postgres SEQUENCE backing atomic
FOC job-number generation (replaces the racy MAX(job_number)+1 scan in
generate_job_number()). Seeded to continue after the highest existing
FOC number so no collisions with already-issued numbers.
The route itself isn't rewired to use this yet — that lands in M5
alongside the Create mode rebuild; this migration only creates and
correctly seeds the sequence object.
Run via migrate.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    with db.engine.connect() as conn:
        conn.execute(text("""
            CREATE SEQUENCE IF NOT EXISTS job_number_seq;
        """))

        # Seed the sequence to continue after the highest existing FOC-### number,
        # so the first nextval() issued can't collide with an already-used job number.
        max_existing = conn.execute(text("""
            SELECT COALESCE(MAX(CAST(SUBSTRING(job_number FROM 5) AS INTEGER)), 0)
            FROM projects
            WHERE job_number LIKE 'FOC-%' AND SUBSTRING(job_number FROM 5) ~ '^[0-9]+$';
        """)).scalar()

        conn.execute(text("SELECT setval('job_number_seq', :start)"), {"start": max_existing})
        conn.commit()

    print(f"Migration complete: job_number_seq created and seeded past {max_existing}.")