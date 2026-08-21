"""
M10 cutover — retire the one dead Project.project_status /
ProjectPosmChannel.status literal still sitting in real data:
'internal_review' (a pre-M1 project-level value, superseded by
ProjectSubmission.workflow_status/Deliverable.status's own
'internal_review', which is unrelated and untouched by this script).
Verified 20 Aug 2026: 4 project rows + 1 channel row, no current write
site can ever produce this value anymore. See Projects Redesign
Architecture.md §C. Every other legacy-looking value (draft, briefed,
in_progress, on_hold, submitted_to_client, revision_in_queue, approved)
is still actively written today and intentionally left alone.
"""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

cur.execute("UPDATE projects SET project_status = 'in_progress' WHERE project_status = 'internal_review';")
print(f"projects rows updated: {cur.rowcount}")

cur.execute("UPDATE project_posm_channels SET status = 'in_progress' WHERE status = 'internal_review';")
print(f"project_posm_channels rows updated: {cur.rowcount}")

conn.commit()
cur.close()
conn.close()
print("M10 project_status vocabulary cutover complete.")