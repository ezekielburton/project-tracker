import os, psycopg2
from dotenv import load_dotenv
load_dotenv()

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute("ALTER TABLE deliverable_types ADD COLUMN IF NOT EXISTS reference_image VARCHAR(255)")
conn.commit()
cur.close()
conn.close()
print("Done - reference_image confirmed on DeliverableType (deliverable_types table).")