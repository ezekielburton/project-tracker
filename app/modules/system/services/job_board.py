"""What the admin Jobs page shows: every timer from the job list with its last
run and next run, the totals in the tiles, and the latest orphaned-uploads report."""
from datetime import datetime, timedelta

from sqlalchemy import func

from app.modules.core.shared.extensions import db
from app.modules.system.lib import fmt
from app.modules.system.lib.job_list import JOBS
from app.modules.system.models import Heartbeat, JobRun
from app.modules.system.services import health
from app.modules.system.services.jobs import RESULT_FAILED
from app.modules.system.services.snapshot import parse_time

RECLAIMED_WINDOW = timedelta(days=30)
FAILED_WINDOW = timedelta(days=7)


def _seconds(run):
    return (run.finished_at - run.started_at).total_seconds()


def duration(seconds):
    """0.3 -> '0.3 s', 130 -> '2 m 10 s'."""
    if seconds < 60:
        return f'{seconds:.1f} s' if seconds < 10 else f'{seconds:.0f} s'
    return f'{int(seconds // 60)} m {int(seconds % 60)} s'


def _heartbeat_row(job, beat, due, now):
    # The heartbeat writes its own table rather than a job run: its last beat is its last run.
    return {'key': job.key, 'label': job.label, 'schedule': job.schedule, 'run_now': job.run_now,
            'last': fmt.ago(beat.ts, now), 'duration': fmt.ms(beat.ms) if beat.ms is not None else None,
            'result': 'ok' if beat.ok else RESULT_FAILED, 'failed': not beat.ok, 'message': None, 'due': due}


def rows(snapshot, now=None):
    """One row per job, in job-list order: schedule, last run, result, when it is
    next due (from the snapshot's timers) and whether Run now is allowed."""
    now = now or datetime.utcnow()
    runs = health.latest_runs()
    timers = snapshot.get('timers') or {}
    beat = Heartbeat.query.order_by(Heartbeat.ts.desc()).first()
    result = []
    for job in JOBS:
        run = runs.get(job.key)
        due = parse_time((timers.get(job.unit) or {}).get('next'))
        if job.key == 'heartbeat' and run is None and beat is not None:
            result.append(_heartbeat_row(job, beat, due, now))
            continue
        result.append({
            'key': job.key, 'label': job.label, 'schedule': job.schedule, 'run_now': job.run_now,
            'last': fmt.ago(run.finished_at, now) if run else None,
            'duration': duration(_seconds(run)) if run else None,
            'result': run.result if run else None,
            'failed': bool(run) and run.result == RESULT_FAILED,
            'message': run.message if run else None,
            'due': due,
        })
    return result


def tiles(snapshot, now=None):
    """Jobs scheduled, jobs that failed in 7 days, the next to run, space reclaimed in 30 days."""
    now = now or datetime.utcnow()
    since = now - FAILED_WINDOW
    failed = [row[0] for row in db.session.query(JobRun.job).filter(
        JobRun.result == RESULT_FAILED, JobRun.started_at >= since).distinct()]
    labels = {job.key: job.label for job in JOBS}
    upcoming = health.next_jobs(snapshot, limit=1)
    reclaimed = (db.session.query(func.sum(JobRun.bytes_reclaimed))
                 .filter(JobRun.started_at >= now - RECLAIMED_WINDOW).scalar())
    return {
        'scheduled': len(JOBS),
        'failed': len(failed),
        'failed_names': [labels.get(key, key) for key in sorted(failed)],
        'next': upcoming[0] if upcoming else None,
        'reclaimed': int(reclaimed) if reclaimed else 0,
    }


def orphans(now=None):
    """The latest orphaned-uploads report: {when, count, size, files}, or None before its first run."""
    now = now or datetime.utcnow()
    run = (JobRun.query.filter(JobRun.job == 'orphan-uploads')
           .order_by(JobRun.started_at.desc()).first())
    if run is None:
        return None
    details = run.details or {}
    files = [{'name': item.get('name'), 'size': fmt.size(item.get('size')),
              'modified': fmt.day_time(parse_time(item.get('modified')), now)}
             for item in details.get('files') or []]
    return {'when': fmt.ago(run.finished_at, now), 'failed': run.result == RESULT_FAILED,
            'count': details.get('count', len(files)), 'size': fmt.size(details.get('bytes')),
            'files': files}
