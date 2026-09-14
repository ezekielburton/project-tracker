"""
Migration: hse_entries.compliance_item_id — the certificate a compliance
entry is about, as a foreign key to hse_reference, so renaming it keeps its
renewal history instead of splitting it. Converts the free-text `item`
already stored in data into reference rows and links them up.
Run via migrate.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
from config import Config

conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
cur = conn.cursor()

# 1. The column.
cur.execute("""
    ALTER TABLE hse_entries
    ADD COLUMN IF NOT EXISTS compliance_item_id INTEGER
        REFERENCES hse_reference(id) ON DELETE SET NULL;
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_hse_entries_compliance_item "
            "ON hse_entries (compliance_item_id);")

# 2. One reference row per distinct certificate name already entered, case-
#    insensitively deduped, skipping any that already exist.
cur.execute("""
    INSERT INTO hse_reference (kind, label, active, sort_order)
    SELECT DISTINCT ON (lower(trim(e.data->>'item')))
           'compliance_item', trim(e.data->>'item'), true, 0
    FROM hse_entries e
    WHERE e.register = 'compliance_renewal'
      AND coalesce(trim(e.data->>'item'), '') <> ''
      AND NOT EXISTS (
          SELECT 1 FROM hse_reference r
          WHERE r.kind = 'compliance_item'
            AND lower(r.label) = lower(trim(e.data->>'item')))
    ORDER BY lower(trim(e.data->>'item'));
""")

# 3. Link each compliance entry to its reference row.
cur.execute("""
    UPDATE hse_entries e
    SET compliance_item_id = r.id
    FROM hse_reference r
    WHERE e.register = 'compliance_renewal'
      AND r.kind = 'compliance_item'
      AND lower(r.label) = lower(trim(e.data->>'item'))
      AND coalesce(trim(e.data->>'item'), '') <> '';
""")

# 4. Drop the now-migrated key, so there is one home for the value.
cur.execute("""
    UPDATE hse_entries
    SET data = data - 'item'
    WHERE register = 'compliance_renewal' AND data ? 'item';
""")

conn.commit()
cur.close()
conn.close()
print("Done — hse_entries.compliance_item_id added and back-filled.")
