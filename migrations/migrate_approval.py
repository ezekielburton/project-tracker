import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

# Add approval tracking to the projects table.
# approved_at / approved_by_id are set when CS approves the final submitted deck.
# For Standard briefs this happens directly; for C&CM POSM projects it is
# cascaded automatically once every POSM channel has been individually approved.
cur.execute('ALTER TABLE projects ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP')
cur.execute('ALTER TABLE projects ADD COLUMN IF NOT EXISTS approved_by_id INTEGER REFERENCES users(id)')

# Add approval tracking to the POSM channel table.
# Each channel is approved independently; once all channels on a project are
# approved the route auto-cascades to project-level approval.
cur.execute('ALTER TABLE project_posm_channels ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP')
cur.execute('ALTER TABLE project_posm_channels ADD COLUMN IF NOT EXISTS approved_by_id INTEGER REFERENCES users(id)')

conn.commit()
cur.close()
conn.close()

print('Approval migration complete.')
