# System module

**What it is.** OVP's own health records: request timings, the heartbeat, the job log, deploys and incident notes. Request hooks and timers write them; the admin system pages only read them.

**Who it is for.** Nobody opens it directly. `/healthz` is public and answers only `ok` (200) or `down` (503). Everything else is read by the admin system pages, real admin only.

## How it records
- **Requests.** Each request adds one row to an in-memory buffer — no database work on the request. A background loop in each worker saves the buffer every 10 seconds in one INSERT, on its own connection, and updates that worker's `worker_stats` row (open SSE streams). Static files, SSE streams and `/healthz` are skipped. The user id comes from the login cookie; department is looked up from `users` when a page reads. While an admin views as someone, `emulating_id` holds who. With nginx's `X-Request-Start` header the row also carries the queue wait.
- **Heartbeat.** `collectors/heartbeat.py` runs every minute, calls `/healthz` and saves `{ts, ok, ms}`. A minute with no row is downtime.
- **Jobs.** Every timer runs its work inside `services.jobs.job_run('<name>')`, which saves ok or failed, timing and a message to `job_runs`.
- **Deploys.** `migrate.py` saves one `deploy_log` row per run: tag, commit, migrations applied, duration, ok. It creates that table itself.

## Tables
`request_metrics` · `heartbeats` · `job_runs` · `worker_stats` · `system_incidents` · `deploy_log`

## Files
```
app/modules/system/
  models.py                 the tables
  lib/request_metrics.py    the timing hooks, buffer and saving loop
  routes/health.py          /healthz
  services/jobs.py          job_run, record_run
  collectors/heartbeat.py   the one-minute heartbeat
  tests/
```
