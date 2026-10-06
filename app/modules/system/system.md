# System module

**What it is.** OVP's own health records: request timings, the heartbeat, the job log, deploys and incident notes. Request hooks and timers write them; the admin system pages only read them.

**Who it is for.** Nobody opens it directly. `/healthz` is public and answers only `ok` (200) or `down` (503). Everything else is read by the admin system pages, real admin only.

## How it records
- **Requests.** Each request adds one row to an in-memory buffer — no database work on the request. A background loop in each worker saves the buffer every 10 seconds in one INSERT, on its own connection, and updates that worker's `worker_stats` row (open SSE streams). Static files, SSE streams and `/healthz` are skipped. The user id comes from the login cookie; department is looked up from `users` when a page reads. While an admin views as someone, `emulating_id` holds who. With nginx's `X-Request-Start` header the row also carries the queue wait.
- **Heartbeat.** `collectors/heartbeat.py` runs every minute, calls `/healthz` and saves `{ts, ok, ms}`. A minute with no row is downtime.
- **Jobs.** Every timer runs its work inside `services.jobs.job_run('<name>')`, which saves ok or failed, timing and a message to `job_runs`.
- **Deploys.** `migrate.py` saves one `deploy_log` row per run: tag, commit, migrations applied, duration, ok. It creates that table itself.
- **Snapshot.** `collectors/snapshot.py` runs every minute with psutil (`lib/host.py`) and fixed commands only (`lib/checks.py`). It writes the machine's "now" to `snapshot.json` (outside `uploads/`), swapped in whole. NAS space and history (`system_samples`) refresh every 5 minutes; updates, `origin/main` and certificates every 6 hours. Pages read it through `services.snapshot.read_snapshot()`, which returns `{}` for a missing or broken file.
- **App log.** The same run reads new journald lines for `helix` and saves errors, warnings and worker starts to `app_log_events` (kept 7 days), with a signature that groups repeats (`lib/app_log.py`).

## Tables
`request_metrics` · `heartbeats` · `job_runs` · `worker_stats` · `system_incidents` · `deploy_log` · `system_samples` · `app_log_events`

## Files
```
app/modules/system/
  models.py                 the tables
  lib/request_metrics.py    the timing hooks, buffer and saving loop
  lib/host.py               psutil readings
  lib/checks.py             the collector's fixed commands and their parsers
  lib/app_log.py            journald lines into events and signatures
  routes/health.py          /healthz
  services/jobs.py          job_run, record_run
  services/snapshot.py      read_snapshot, is_stale
  collectors/heartbeat.py   the one-minute heartbeat
  collectors/snapshot.py    the one-minute snapshot and app-log reader
  tests/
```
