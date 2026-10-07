# System module

**What it is.** OVP's own health records: request timings, the heartbeat, the job log, deploys and incident notes. Request hooks and timers write them; the admin system pages only read them.

**Who it is for.** Nobody opens it directly. `/healthz` is public and answers only `ok` (200) or `down` (503). Everything else is read by the admin system pages, real admin only.

## How it records
- **Requests.** Each request adds one row to an in-memory buffer — no database work on the request. A background loop in each worker saves the buffer every 10 seconds in one INSERT, on its own connection, and updates that worker's `worker_stats` row (open SSE streams). Static files, SSE streams and `/healthz` are skipped. The user id comes from the login cookie; department is looked up from `users` when a page reads. While an admin views as someone, `emulating_id` holds who. `page` marks a page load (a GET that returns HTML, outside `/api/`). With nginx's `X-Request-Start` header the row also carries the queue wait.
- **Heartbeat.** `collectors/heartbeat.py` runs every minute, calls `/healthz` and saves `{ts, ok, ms}`. A minute with no row is downtime.
- **Jobs.** Every timer runs its work inside `services.jobs.job_run('<name>')`, which saves ok or failed, timing, a message and `details` (sizes, paths, counts, a report list) to `job_runs`. `lib/job_list.py` lists every job with its unit, schedule and command; `deploy/systemd/` must match it (a test reads the unit files). The snapshot reads each timer's last and next run from systemd.
- **Scheduled jobs.** Heartbeat and snapshot every minute · NAS outbox flush every 2 minutes · backup 23:00 (pg_dump to `BACKUP_DIR`, keeping 14 nightly and 8 weekly, then the NAS week folder; a NAS failure keeps the local copy and fails the run) · orphaned-uploads report 02:30 (lists old files in `uploads/` no project file points to; deletes nothing) · VACUUM ANALYZE 03:10 · preview-cache cleanup 03:30 · on Sundays: restore test 04:00 (restores the newest dump, NAS copy first, into `ovp_restore_check` as the `ovp_restore` role, checks key tables hold at least 95% of live rows, all migrations are there and the dump is under 8 days old, then drops it), notifications older than 90 days purged 04:10, retention 04:15 (page views in `request_metrics` 30 days, saved changes 100, `heartbeats` 35, `job_runs` 90).
- **Deploys.** `migrate.py` saves one `deploy_log` row per run: tag, commit, migrations applied, duration, ok. It creates that table itself.
- **Run now.** The Jobs page posts to `/dashboard/api/admin/jobs/<job>/run` (real admin only). It writes a trigger file `RUN_NOW_DIR/<job>` holding the admin's id; a systemd path unit per job starts that job's own service, so a manual and a timed run never overlap. `job_run` takes the file and records who pressed it. Jobs with `run_now` False (the heartbeat) are refused.
- **Live pings.** Each heartbeat, snapshot and job-log save sends `system_changes` (`lib/notify.py`) in its own transaction, so it lands only if the save commits. The relay passes it to `/sse/system` (real admin only), and open admin pages reload their cards.
- **What the pages read.** One service per admin page, read only, every threshold a named constant at its top:
  - `health.py` — Overview (status strip, Needs attention, Today, next jobs), System, and the two rail badges (new error groups in 24h, jobs failed in 7 days).
  - `database.py` — size and growth, connections, cache hits, last backup, largest tables, maintenance. Postgres statistics are read live; history comes from `system_samples`.
  - `slow_queries.py` — the 24-hour slowest queries (below).
  - `performance.py` — response times, error rate, page load by module (7 days), slowest routes, workers.
  - `usage.py` — active now, actions, people, by module and hour (Dubai), recent logins, the emulation log. An action is a saved change (`lib/actions.py`); admins and `USAGE_EXCLUDED_EMAILS` are left out.
  - `errors.py` — errors and warnings grouped by signature, 500s by route, the raw tail.
  - `uptime.py` — 30 days from the heartbeat. A gap of more than 150 seconds, a failed beat, or a latest beat that old is downtime; downtime starting within 15 minutes of a deploy reads as a planned restart.
  - `job_board.py` — every job with its last and next run, the tiles, the latest orphaned-uploads report.
- **Module names.** `lib/modules.py` maps a blueprint to its module (every blueprint lives under `app/modules/<module>/`), labelled as in the sidebar. Performance and Usage group by it.
- **Slowest queries.** `pg_stat_statements` only keeps running totals, so the snapshot saves them to `query_stat_samples` every hour (kept 27 hours), and `slow_queries.py` subtracts the sample nearest to 24 hours ago from the live totals. Off until the extension is loaded on the server (`docs/DEPLOYMENT.md`); the card then says so.
- **Incidents.** Added on the Uptime page (title, date, minutes down, note) through `POST /dashboard/api/admin/incidents`, real admin only, and logged in the activity log.
- **Snapshot.** `collectors/snapshot.py` runs every minute with psutil (`lib/host.py`) and fixed commands only (`lib/checks.py`). It writes the machine's "now" to `snapshot.json` (outside `uploads/`), swapped in whole. NAS space and history (`system_samples`: disk use, network, database size and connections) refresh every 5 minutes, and worker starts are read from the change in gunicorn's worker pids; updates, `origin/main` and certificates every 6 hours. Pages read it through `services.snapshot.read_snapshot()`, which returns `{}` for a missing or broken file.
- **App log.** The same run reads new journald lines for `helix` and saves errors, warnings and worker starts to `app_log_events` (kept 7 days), with a signature that groups repeats (`lib/app_log.py`).

## Tables
`request_metrics` · `heartbeats` · `job_runs` · `worker_stats` · `system_incidents` · `deploy_log` · `system_samples` · `app_log_events` · `query_stat_samples`

## Files
```
app/modules/system/
  models.py                 the tables
  lib/request_metrics.py    the timing hooks, buffer and saving loop
  lib/actions.py            what counts as an action
  lib/notify.py             the system_changes ping
  lib/fmt.py                sizes, ages and Dubai times for the pages
  lib/host.py               psutil readings
  lib/checks.py             the collector's fixed commands and their parsers
  lib/app_log.py            journald lines into events and signatures
  lib/modules.py            blueprint to module, with sidebar labels
  lib/query_stats.py        hourly pg_stat_statements totals
  routes/health.py          /healthz
  lib/job_list.py           every scheduled job: unit, schedule, command, Run now
  lib/nas_access.py         the bare app context NAS calls need from a timer
  jobs/                     backup, restore_test, orphan_uploads, vacuum, purge_notifications, retention
  services/jobs.py          job_run, record_run
  services/health.py        what the Overview and System pages and the badges show
  services/database.py      the Database page
  services/slow_queries.py  the 24-hour slowest queries
  services/performance.py   the Performance page
  services/usage.py         the Usage page
  services/errors.py        the Errors page
  services/uptime.py        the Uptime page and adding incidents
  services/job_board.py     the Jobs page
  services/run_now.py       Run now trigger files: request_run, claim, pending
  services/snapshot.py      read_snapshot, is_stale
  collectors/heartbeat.py   the one-minute heartbeat
  collectors/snapshot.py    the one-minute snapshot and app-log reader
  tests/
```
