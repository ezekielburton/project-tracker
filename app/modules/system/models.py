"""OVP's own health records. Request hooks and timers write them; the admin
system pages only read them."""
from datetime import datetime

from app.modules.core.shared.extensions import db


class RequestMetric(db.Model):
    """One served request. user_id has no foreign key so the batched insert
    stays cheap and rows outlive deleted users."""
    __tablename__ = 'request_metrics'
    __table_args__ = (
        db.Index('ix_request_metrics_errors', 'ts', postgresql_where=db.text('status >= 500')),
    )

    id           = db.Column(db.BigInteger, primary_key=True)
    ts           = db.Column(db.DateTime, nullable=False, index=True)
    method       = db.Column(db.String(8), nullable=False)
    route        = db.Column(db.String(200), nullable=False)
    blueprint    = db.Column(db.String(60), nullable=True)
    status       = db.Column(db.SmallInteger, nullable=False)
    duration_ms  = db.Column(db.Integer, nullable=False)
    # Time spent waiting for a worker, from nginx's X-Request-Start; empty without it.
    queue_ms     = db.Column(db.Integer, nullable=True)
    user_id      = db.Column(db.Integer, nullable=True)
    # Who the admin was viewing as, if anyone.
    emulating_id = db.Column(db.Integer, nullable=True)
    # A whole HTML page, not a card, fragment or data call: what "page load" times.
    page         = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())


class Heartbeat(db.Model):
    """One heartbeat check. A minute with no row is downtime."""
    __tablename__ = 'heartbeats'

    id = db.Column(db.Integer, primary_key=True)
    ts = db.Column(db.DateTime, nullable=False, index=True)
    ok = db.Column(db.Boolean, nullable=False)
    ms = db.Column(db.Integer, nullable=True)


class JobRun(db.Model):
    """One run of a scheduled job. run_by_id is set only when an admin pressed Run now."""
    __tablename__ = 'job_runs'
    __table_args__ = (db.Index('ix_job_runs_job_started', 'job', 'started_at'),)

    id              = db.Column(db.Integer, primary_key=True)
    job             = db.Column(db.String(60), nullable=False)
    started_at      = db.Column(db.DateTime, nullable=False)
    finished_at     = db.Column(db.DateTime, nullable=False)
    result          = db.Column(db.String(10), nullable=False)
    message         = db.Column(db.Text, nullable=True)
    bytes_reclaimed = db.Column(db.BigInteger, nullable=True)
    run_by_id       = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    # What the job wants kept with the run: sizes, paths, counts, a report list.
    details         = db.Column(db.JSON, nullable=True)


class WorkerStat(db.Model):
    """Each gunicorn worker's open SSE streams, refreshed by its saving loop."""
    __tablename__ = 'worker_stats'

    pid        = db.Column(db.Integer, primary_key=True, autoincrement=False)
    sse_open   = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.DateTime, nullable=False)


class SystemIncident(db.Model):
    """A note the admin adds on the Uptime page about something that happened."""
    __tablename__ = 'system_incidents'

    id            = db.Column(db.Integer, primary_key=True)
    happened_on   = db.Column(db.Date, nullable=False)
    title         = db.Column(db.String(120), nullable=False, default='', server_default='')
    # How long it lasted, when known.
    minutes       = db.Column(db.Integer, nullable=True)
    note          = db.Column(db.Text, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at    = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class DeployRun(db.Model):
    """One migrate.py run. migrate.py creates this table itself, so the first
    deploy is logged before any migration has run."""
    __tablename__ = 'deploy_log'

    id                 = db.Column(db.Integer, primary_key=True)
    ran_at             = db.Column(db.DateTime, nullable=False)
    tag                = db.Column(db.String(60), nullable=True)
    commit_sha         = db.Column(db.String(40), nullable=True)
    migrations_applied = db.Column(db.Integer, nullable=False, default=0)
    duration_ms        = db.Column(db.Integer, nullable=False)
    ok                 = db.Column(db.Boolean, nullable=False, default=True)


class SystemSample(db.Model):
    """One reading of one metric, saved every 5 minutes for the history charts."""
    __tablename__ = 'system_samples'
    __table_args__ = (db.Index('ix_system_samples_metric_ts', 'metric', 'ts'),)

    id     = db.Column(db.BigInteger, primary_key=True)
    ts     = db.Column(db.DateTime, nullable=False, index=True)
    metric = db.Column(db.String(80), nullable=False)
    value  = db.Column(db.Float, nullable=False)


class AppLogEvent(db.Model):
    """An error, warning or worker start read from the app log; the signature
    groups repeats of one problem."""
    __tablename__ = 'app_log_events'
    __table_args__ = (db.Index('ix_app_log_events_signature_ts', 'signature', 'ts'),)

    id        = db.Column(db.BigInteger, primary_key=True)
    ts        = db.Column(db.DateTime, nullable=False, index=True)
    level     = db.Column(db.String(10), nullable=False)
    source    = db.Column(db.String(120), nullable=False)
    signature = db.Column(db.String(200), nullable=False)
    message   = db.Column(db.Text, nullable=False)
    detail    = db.Column(db.Text, nullable=True)


class QueryStatSample(db.Model):
    """Running totals for one query from pg_stat_statements, saved every hour,
    so the Database page can subtract the totals of 24 hours ago."""
    __tablename__ = 'query_stat_samples'

    id       = db.Column(db.BigInteger, primary_key=True)
    ts       = db.Column(db.DateTime, nullable=False, index=True)
    queryid  = db.Column(db.BigInteger, nullable=False)
    calls    = db.Column(db.BigInteger, nullable=False)
    total_ms = db.Column(db.Float, nullable=False)
