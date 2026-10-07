"""Orphaned uploads check (ovp-orphan-uploads.timer, 02:30): lists files directly
in uploads/ that no project reference file points to and that are over a week
old. Report only: nothing is deleted; the list is saved with the run."""
import os
import sys
from datetime import datetime, timedelta

import psycopg2

from config import Config
from app.modules.system.services.jobs import job_run

MIN_AGE = timedelta(days=7)
LIST_LIMIT = 200


def find_orphans(folder, referenced, now):
    """[{name, size, modified}] for old files in `folder` (not its subfolders)
    whose names are not in `referenced`, largest first."""
    found = []
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return found
    for entry in entries:
        if not entry.is_file() or entry.name in referenced:
            continue
        stat = entry.stat()
        modified = datetime.utcfromtimestamp(stat.st_mtime)
        if now - modified >= MIN_AGE:
            found.append({'name': entry.name, 'size': stat.st_size,
                          'modified': modified.isoformat(timespec='seconds')})
    return sorted(found, key=lambda f: -f['size'])


def referenced_names(cur):
    cur.execute('SELECT filename FROM project_files')
    return {row[0] for row in cur.fetchall()}


def main():
    with job_run('orphan-uploads') as run:
        conn = psycopg2.connect(Config.SQLALCHEMY_DATABASE_URI)
        try:
            with conn.cursor() as cur:
                referenced = referenced_names(cur)
        finally:
            conn.close()
        orphans = find_orphans(Config.UPLOAD_FOLDER, referenced, datetime.utcnow())
        total = sum(f['size'] for f in orphans)
        run.message = f'{len(orphans)} files · {total / 1_048_576:.1f} MB' if orphans else None
        run.details = {'count': len(orphans), 'bytes': total, 'files': orphans[:LIST_LIMIT]}
    return 0


if __name__ == '__main__':
    sys.exit(main())
