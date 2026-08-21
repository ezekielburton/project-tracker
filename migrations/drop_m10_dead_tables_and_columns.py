"""
M10 cutover — drop confirmed-dead tables/columns from the Projects rework.
See Projects Redesign Architecture.md §A/§B. project_reviewers verified
empty and project_approvals verified 0 rows before this was written
(20 Aug 2026) — no data loss. needs_artwork/artwork_status added to this
pass (not in the original doc list — postdates it): superseded by the
17 Aug 2026 2D/3D stream split, confirmed unread/unwritten anywhere.
"""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

# Dead tables — superseded, unread/unwritten by any current route.
cur.execute("DROP TABLE IF EXISTS project_reviewers;")
cur.execute("DROP TABLE IF EXISTS project_approvals;")

# Dead columns — superseded, unread/unwritten by any current route/template.
cur.execute("ALTER TABLE deliverables DROP COLUMN IF EXISTS brief_flag;")
cur.execute("ALTER TABLE deliverables DROP COLUMN IF EXISTS brief_flag_resolved;")
cur.execute("ALTER TABLE deliverables DROP COLUMN IF EXISTS needs_artwork;")
cur.execute("ALTER TABLE deliverables DROP COLUMN IF EXISTS artwork_status;")
cur.execute("ALTER TABLE projects DROP COLUMN IF EXISTS hours_accumulated;")
cur.execute("ALTER TABLE projects DROP COLUMN IF EXISTS timer_started_at;")
cur.execute("ALTER TABLE projects DROP COLUMN IF EXISTS status;")

conn.commit()
cur.close()
conn.close()
print("M10 dead tables/columns dropped.")