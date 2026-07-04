import os, psycopg2
from dotenv import load_dotenv
load_dotenv()

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS nas_url VARCHAR(500)")
conn.commit()
cur.close()
conn.close()
print("Done - nas_url added to User model.")