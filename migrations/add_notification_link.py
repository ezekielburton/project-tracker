"""
Migration: add `link` column to notifications table.
Run once: python add_notification_link.py
"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS link VARCHAR(500);")
conn.commit()
cur.close()
conn.close()
print("Done — link column added to notifications.")
