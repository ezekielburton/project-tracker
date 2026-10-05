"""
Migration: converts each user's role key into the org fields, seeds the starting
job titles, then renames users.role to legacy_role, which nothing reads; it stays
for rollback. Run via migrate.py after add_org_model.py. Run directly with
--dry-run to print the mapping per user without changing anything.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
from config import Config

# Role key -> (department, seniority, is_admin, starting job title). Frozen here,
# not imported, so the script always does what it did when it ran. Departments
# whose titles differ per person start without one.
MAPPING = {
    'admin':              (None,                 'none',       True,  None),
    'management':         (None,                 'management', False, None),
    'cs':                 ('client_servicing',   'none',       False, 'Account Manager'),
    'project_owner':      ('project_owner',      'none',       False, 'Project Owner'),
    'designer':           ('design',             'none',       False, 'Designer'),
    'team_lead':          ('design',             'manager',    False, 'Team Lead'),
    'finance':            ('finance',            'none',       False, None),
    'digital_innovation': ('digital_innovation', 'none',       False, None),
    'hr':                 ('hr',                 'none',       False, None),
    'production':         ('production',         'none',       False, None),
    'logistics':          ('logistics',          'none',       False, None),
    'hse':                ('hse',                'none',       False, None),
}

dry_run = '--dry-run' in sys.argv
conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
cur = conn.cursor()

cur.execute("""
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'users' AND column_name = 'role'
""")
if cur.fetchone() is None:
    print("Nothing to do: users.role is already converted.")
    sys.exit(0)

cur.execute("SELECT id, name, role, is_active FROM users ORDER BY role, name")
users = cur.fetchall()

unknown = sorted({role for _, _, role, _ in users if role not in MAPPING})
if unknown:
    print(f"Unknown role keys {unknown}: fix those users first. Nothing changed.", file=sys.stderr)
    sys.exit(1)

print(f"{'Name':<30} {'Role':<20} {'Department':<20} {'Seniority':<12} {'Admin':<6} Job title")
for _, name, role, is_active in users:
    department, seniority, is_admin, title = MAPPING[role]
    label = name if is_active else f'{name} (inactive)'
    print(f"{label:<30} {role:<20} {department or '-':<20} {seniority:<12} "
          f"{'yes' if is_admin else '':<6} {title or '-'}")

if dry_run:
    print("\nDry run: nothing changed.")
    sys.exit(0)

title_ids = {}
for sort_order, (department, _, _, title) in enumerate(MAPPING.values()):
    if title:
        cur.execute("""
            INSERT INTO job_roles (department, title, sort_order) VALUES (%s, %s, %s)
            ON CONFLICT (department, title) DO UPDATE SET title = EXCLUDED.title
            RETURNING id
        """, (department, title, sort_order))
        title_ids[(department, title)] = cur.fetchone()[0]

for user_id, _, role, _ in users:
    department, seniority, is_admin, title = MAPPING[role]
    cur.execute("""
        UPDATE users SET department = %s, seniority = %s, is_admin = %s, job_role_id = %s
        WHERE id = %s
    """, (department, seniority, is_admin, title_ids.get((department, title)), user_id))

cur.execute("ALTER TABLE users RENAME COLUMN role TO legacy_role")
cur.execute("ALTER TABLE users ALTER COLUMN legacy_role DROP NOT NULL, ALTER COLUMN legacy_role DROP DEFAULT")

conn.commit()
cur.close()
conn.close()
print(f"\nDone: {len(users)} users converted; users.role renamed to legacy_role.")
