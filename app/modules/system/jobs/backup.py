"""Nightly backup (ovp-backup.timer, 23:00): pg_dump to a local file, upload it
to the NAS in the same week folders as before, keep 14 nightly and 8 weekly
local copies. If the NAS upload fails the local copy stays and the run fails."""
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone

from config import Config
from app.modules.system.lib import checks
from app.modules.system.lib.nas_access import nas_app
from app.modules.system.services.jobs import job_run

DUBAI = timezone(timedelta(hours=4))
KEEP_NIGHTLY = 14
KEEP_WEEKLY = 8
NAS_ROOT = '/Admin/Database'


def nas_location(local_now):
    """(folder, file name) on the NAS. Same layout as the old cron backup: the
    folder needs a leading slash and no trailing one (Synology rejects both)."""
    return (f'{NAS_ROOT}/{local_now.year}/Week {local_now.isocalendar()[1]}',
            local_now.strftime('%A %d %B') + ' Backup.dump')


def local_paths(backup_dir, local_now):
    """(nightly, weekly) dump paths; weekly only on Sundays, otherwise None."""
    nightly = os.path.join(backup_dir, 'nightly', f'{local_now:%Y-%m-%d}.dump')
    weekly = None
    if local_now.weekday() == 6:
        weekly = os.path.join(backup_dir, 'weekly', f'{local_now:%G-W%V}.dump')
    return nightly, weekly


def prune(folder, keep):
    """Delete all but the newest `keep` dumps in `folder` (the names sort by date); returns bytes freed."""
    if not os.path.isdir(folder):
        return 0
    dumps = sorted(name for name in os.listdir(folder) if name.endswith('.dump'))
    freed = 0
    for name in dumps[:max(len(dumps) - keep, 0)]:
        path = os.path.join(folder, name)
        freed += os.path.getsize(path)
        os.remove(path)
    return freed


def _keep_weekly(nightly, weekly):
    os.makedirs(os.path.dirname(weekly), exist_ok=True)
    try:
        os.link(nightly, weekly)  # same disk: a second name, no second copy
    except OSError:
        shutil.copyfile(nightly, weekly)


def upload(path, folder, filename):
    """Send the dump to the NAS. Raises RuntimeError when the NAS can't take it."""
    from app.modules.core.shared.services import nas
    with open(path, 'rb') as f:
        data = f.read()
    with nas_app():
        nas.upload_app_file(data, folder, filename)


def main():
    with job_run('backup') as run:
        local_now = datetime.now(DUBAI)
        nightly, weekly = local_paths(Config.BACKUP_DIR, local_now)
        os.makedirs(os.path.dirname(nightly), exist_ok=True)
        checks.run_or_raise(('pg_dump', '--format=custom', '--file', nightly,
                             Config.SQLALCHEMY_DATABASE_URI), timeout=3600)
        if weekly:
            _keep_weekly(nightly, weekly)
        freed = (prune(os.path.dirname(nightly), KEEP_NIGHTLY)
                 + prune(os.path.join(Config.BACKUP_DIR, 'weekly'), KEEP_WEEKLY))

        folder, filename = nas_location(local_now)
        size = os.path.getsize(nightly)
        run.bytes_reclaimed = freed or None
        run.details = {'size': size, 'local_path': nightly, 'weekly_path': weekly,
                       'nas_path': f'{folder}/{filename}', 'nas_ok': False}
        upload(nightly, folder, filename)
        run.details['nas_ok'] = True
        run.message = f'{size / 1_048_576:.0f} MB · NAS and local copy'
    return 0


if __name__ == '__main__':
    sys.exit(main())
