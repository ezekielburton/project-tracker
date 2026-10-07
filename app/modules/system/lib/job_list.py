"""Every scheduled job: its timer, schedule and what it runs. deploy/systemd/
must match this list (a test reads the unit files), and Run now starts only
jobs listed here with run_now True."""
from collections import namedtuple

# unit: the systemd name without .service/.timer. on_calendar: the timer's
# OnCalendar, word for word. command: what the service's ExecStart runs.
Job = namedtuple('Job', 'key label unit on_calendar schedule command run_now')

JOBS = (
    Job('heartbeat', 'Heartbeat', 'ovp-heartbeat', 'minutely', 'every minute',
        '-m app.modules.system.collectors.heartbeat', False),
    Job('snapshot', 'Snapshot collector', 'ovp-snapshot', 'minutely', 'every minute',
        '-m app.modules.system.collectors.snapshot', True),
    Job('nas-outbox-flush', 'NAS outbox flush', 'nas-outbox-flush', '*:0/2', 'every 2 min',
        'nas_outbox_flush.py', True),
    Job('backup', 'Nightly backup', 'ovp-backup', '*-*-* 23:00:00', 'daily 23:00',
        '-m app.modules.system.jobs.backup', True),
    Job('orphan-uploads', 'Orphaned uploads check', 'ovp-orphan-uploads', '*-*-* 02:30:00', 'daily 02:30',
        '-m app.modules.system.jobs.orphan_uploads', True),
    Job('vacuum-analyze', 'VACUUM ANALYZE', 'ovp-vacuum-analyze', '*-*-* 03:10:00', 'daily 03:10',
        '-m app.modules.system.jobs.vacuum', True),
    Job('preview-cache-cleanup', 'Preview-cache cleanup', 'preview-cache-cleanup', '*-*-* 03:30:00', 'daily 03:30',
        'preview_cache_cleanup.py', True),
    Job('restore-test', 'Weekly restore test', 'ovp-restore-test', 'Sun *-*-* 04:00:00', 'Sun 04:00',
        '-m app.modules.system.jobs.restore_test', True),
    Job('notifications-purge', 'Notifications purge (90 days)', 'ovp-notifications-purge',
        'Sun *-*-* 04:10:00', 'Sun 04:10', '-m app.modules.system.jobs.purge_notifications', True),
    Job('retention', 'Data retention', 'ovp-retention', 'Sun *-*-* 04:15:00', 'Sun 04:15',
        '-m app.modules.system.jobs.retention', True),
)
BY_KEY = {job.key: job for job in JOBS}
