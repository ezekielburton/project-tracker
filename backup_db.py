import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timezone, timedelta
from app import create_app
from app.nas import upload_app_file
import subprocess

DUBAI_TZ = timezone(timedelta(hours=4))
now = datetime.now(DUBAI_TZ)

year = now.year
week = now.isocalendar().week
# Leading slash matters — the Synology File Station API requires an absolute
# path rooted at a real DSM Shared Folder name ("Admin" here), not a relative one.
# No trailing slash either — the Upload API's 'path' param rejects it (error 418,
# "Illegal name or path").
folder = f"/Admin/Database/{year}/Week {week}"
filename = now.strftime("%A %d %B") + " Backup.dump"

flask_app = create_app()
with flask_app.app_context():
    db_url =  flask_app.config['SQLALCHEMY_DATABASE_URI']

    result = subprocess.run(
    ['pg_dump', db_url, '-Fc'],
    capture_output=True
    )

    if result.returncode != 0:
        print("pg_dump failed:", result.stderr.decode())
        sys.exit(1)

    upload_app_file(result.stdout, folder, filename)
    print(f"Backup saved to {folder}/{filename}")