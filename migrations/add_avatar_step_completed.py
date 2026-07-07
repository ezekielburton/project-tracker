import os, psycopg2
from dotenv import load_dotenv
load_dotenv()

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_step_completed BOOLEAN NOT NULL DEFAULT FALSE")
conn.commit()
cur.close()
conn.close()
print("Done - avatar_step_completed added to User model.")