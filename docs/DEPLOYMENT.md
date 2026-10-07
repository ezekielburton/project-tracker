# Deployment

How OVP runs in production and how a release goes out. Server setup from zero is in [SERVER_SETUP.md](SERVER_SETUP.md). No secrets in this file — real values live in the password manager, and the app reads them from `.env` (start from `.env.example`).

## The server
- Host `vitamine`, deploy user `helixadmin`, repo `/home/helixadmin/project-tracker`.
- Virtualenv `venv/` (no leading dot): `venv/bin/python`, `venv/bin/gunicorn`. The system `python3` doesn't have the app's packages, so every systemd or cron job uses `venv/bin/python`.
- Timezone UTC+04; systemd `OnCalendar` uses local time.
- nginx in front of gunicorn. Public access is through the Cloudflare domain (HTTP/2). The LAN IP serves HTTPS with the internal certificate (`helix-lan.crt`, installed on all company devices); check HTTP/2 is on for it (see *SSE and HTTP/2*).

## The app service
- Unit `helix.service`: `sudo systemctl restart helix`.
- `ExecStart=/home/helixadmin/project-tracker/venv/bin/gunicorn -k gevent -w 9 --worker-connections 1000 --graceful-timeout 5 -b 127.0.0.1:5000 run:app`, working directory the repo.

## Looking at a problem
- First look: Dashboard → Overview (admin only). **Needs attention** lists what is wrong; Errors, Uptime and Jobs have the detail.
- App log: `sudo journalctl -u helix -n 200 --no-pager` (add `-f` to follow).
- Database: `sudo -u postgres psql -d project_tracker` — read-only queries only; changes go through a migration.
- Up?: `curl -sS http://127.0.0.1:5000/healthz` — `ok`, or `down` when the database can't be reached.

## Releasing — tagged, one-way
Each shipped roadmap item gets its own annotated tag `v<version>` (message = the item's title) and one deploy, after working hours. The server only ever fetches and resets — **never `git pull` on the server**.

Before opening the pull request: the whole test suite passes and the item's wiki articles are written.

### On GitHub and the laptop — pull request, merge, tag
Everything reaches `main` through a pull request (PR). Never merge into `main` on the laptop.

1. Finish the feature on `dev`, run `python -m pytest`, then `git push`.
2. On GitHub, open a pull request: **base `main`**, **compare `dev`** (getting these the wrong way round is the common mistake). Title it after the release, e.g. `Release v2.7 — Dashboards`, and paste the build chat's summary into the description.
3. Review the **Files changed** tab — every line that is about to reach production. Look for stray debug lines and files that shouldn't be there.
4. Merge with **Create a merge commit** (from the merge button's dropdown). Never *Squash* or *Rebase* for `dev` → `main`: both leave `main` with commits `dev` doesn't have, and the branches drift apart.
5. On the laptop, tag the release and bring `dev` level with `main`:
```
git checkout main
git pull
git tag -a v<version> -m "<version> — <title>"
git push origin v<version>
git checkout dev
git merge main
git push
```
Commits pushed to `dev` while a PR is open join it automatically. If GitHub says it "can't merge automatically", both branches changed the same lines — stop and resolve on the laptop first.

### On the server — deploy the tag
```
cd /home/helixadmin/project-tracker
git fetch origin main
git fetch origin tag v<version>
git diff --stat origin/main HEAD          # safety gate: only this release's files
git reset --hard origin/main
git describe --tags                       # should print v<version>
venv/bin/pip install -r requirements.txt  # only when requirements.txt changed
venv/bin/python migrate.py                # applies pending migrations, logs the deploy
sudo systemctl restart helix
curl -sS http://127.0.0.1:5000/healthz    # ok
```
If `deploy/systemd/` changed in the release, copy the units again and reload (step 9 of *Admin dashboard: server setup*).
**Safety gate:** if the diff lists files you don't expect, stop and run `git log --oneline origin/main..HEAD` to check for anything unique on the server before resetting.

After it's live, post the in-app blog update (small patches can share one post).

One-off data scripts with a dry run (e.g. `migrate_wiki_to_editorjs.py`) are run by hand: dry run, read the output, then `--confirm`.

## Migrations
One-off files in `migrations/`, run by `migrate.py` (not Alembic). `migrate.py` records what has run in `schema_migrations`; `--status` lists pending ones. Migrations are additive (`ADD COLUMN IF NOT EXISTS`), which is why running them in name order is safe.

## Scheduled jobs
Every job is a systemd timer that runs as `helixadmin` with `venv/bin/python`. The unit files live in `deploy/systemd/` and are copied to `/etc/systemd/system/` (see *Admin dashboard: server setup*). Each run is saved to `job_runs` and shows on Dashboard → Jobs. The list itself is `app/modules/system/lib/job_list.py`; a test checks the unit files match it.

| Timer | When | What it does |
|---|---|---|
| `ovp-heartbeat` | every minute | calls `/healthz` and saves the answer. A minute with no answer is downtime on the Uptime page |
| `ovp-snapshot` | every minute | reads the machine (CPU, memory, disks, network, updates, certificates, timers) into `/var/lib/ovp/snapshot.json`, and new `helix` log lines into `app_log_events` |
| `nas-outbox-flush` | every 2 min | sends files queued in `uploads/nas-outbox/` while the NAS was down |
| `ovp-backup` | daily 23:00 | the nightly backup (see *Backups*) |
| `ovp-orphan-uploads` | daily 02:30 | lists old files in `uploads/` that no project points to. Deletes nothing |
| `ovp-vacuum-analyze` | daily 03:10 | `VACUUM ANALYZE` |
| `preview-cache-cleanup` | daily 03:30 | empties `uploads/preview-cache/` (disposable; the NAS is the source of truth) |
| `ovp-restore-test` | Sun 04:00 | restores the newest backup into a scratch database and checks it (see *Backups*) |
| `ovp-notifications-purge` | Sun 04:10 | deletes notifications older than 90 days |
| `ovp-retention` | Sun 04:15 | trims `request_metrics` (page views 30 days, saved changes 100), `heartbeats` (35) and `job_runs` (90) |

- **Run now.** Every job except the heartbeat has a `.path` unit. The Jobs page writes a trigger file to `/var/lib/ovp/run-now/<job>`; the path unit starts that job's own service, so a manual run never overlaps a timed one.
- **Check them:** `systemctl list-timers 'ovp-*' 'nas-*' 'preview-*'`. One job's output: `sudo journalctl -u ovp-backup -n 50 --no-pager`.
- **NAS queue:** `sudo -u postgres psql -d project_tracker -c "select nas_path, attempts, last_error, created_at from pending_nas_uploads;"` (empty = all sent).
- `reports-weekly.timer` + `.service` — `OnCalendar=Mon *-*-* 08:00:00 Asia/Dubai`, `Persistent=true`, runs `venv/bin/python send_reports.py weekly` as `helixadmin`. Sends last week's report PDFs to their recipients (Admin → Reports). Safe to rerun: a report already sent for that week is skipped.
- `reports-monthly.timer` + `.service` — `OnCalendar=*-*-01 08:00:00 Asia/Dubai`, same, with `monthly`.
- Report PDFs need WeasyPrint's system libraries once: `sudo apt install libpango-1.0-0 libpangoft2-1.0-0`. PDFs are kept in `uploads/reports/` with a copy on the NAS under `NAS_REPORTS_ROOT` (default `/Admin/Reports`). Set `APP_BASE_URL` in `.env` so the email's "Open in OVP" link works.

## Backups
- **Nightly (`ovp-backup`, 23:00).** `pg_dump --format=custom` into `BACKUP_DIR` (default `~/backups`): `nightly/` keeps 14, `weekly/` (Sundays) keeps 8. Then a copy goes to the NAS under `/Admin/Database/<year>/Week <n>/`, the same folders the old cron backup used. If the NAS upload fails, the local copy stays and the run shows as failed.
- **Restore test (`ovp-restore-test`, Sun 04:00).** Takes the newest dump (the NAS copy first, the local one if the NAS is down), restores it into a throwaway `ovp_restore_check` database as the `ovp_restore` role, and checks: key tables hold at least 95% of today's rows, every migration up to the dump is there, and the dump is under 8 days old. Then it drops the database. It never touches `project_tracker`. A `pg_restore` note about the `pg_stat_statements` extension is expected (that role can't create it) and doesn't fail the test.
- **Needs attention** on the Overview shows a backup older than 26 hours and a restore test that failed or is older than 8 days.
- A real restore is a manual `pg_restore` from one of these dumps: [SERVER_SETUP.md](SERVER_SETUP.md) §7.

## Admin dashboard: server setup
Once, in the deploy window of the release that brings the admin pages, after the normal deploy steps (they run its migrations). Real values come from the password manager.

1. **Python packages:** `venv/bin/pip install -r requirements.txt` (brings `psutil`).
2. **Folders** for the snapshot and Run now:
```
sudo mkdir -p /var/lib/ovp/run-now
sudo chown -R helixadmin:helixadmin /var/lib/ovp
```
3. **App log access.** The snapshot reads `journalctl -u helix` as `helixadmin`:
```
sudo usermod -aG systemd-journal helixadmin
```
4. **`pg_stat_statements`** (Slowest queries on the Database page). In `/etc/postgresql/<version>/main/postgresql.conf` set `shared_preload_libraries = 'pg_stat_statements'` (add it to any value already there, comma-separated), then:
```
sudo systemctl restart postgresql
sudo systemctl restart helix
sudo -u postgres psql -d project_tracker -c "CREATE EXTENSION IF NOT EXISTS pg_stat_statements;"
sudo -u postgres psql -c "GRANT pg_read_all_stats TO <app role>;"
```
`<app role>` is the user in the app's `DATABASE_URL`; the grant lets it read the statistics for every query. Until this is done the card reads "pg_stat_statements is off" and nothing else is affected.
5. **Restore-test role.** It can create databases, but owns only the scratch one it makes, so it can't drop anything else:
```
sudo -u postgres psql -c "CREATE ROLE ovp_restore LOGIN CREATEDB PASSWORD '<new password>';"
```
6. **`.env`** — add, then `sudo systemctl restart helix`:
```
RESTORE_DATABASE_URL=postgresql://ovp_restore:<password>@localhost/postgres
LAN_CERT_PATH=<path to helix-lan.crt on the server>
USAGE_EXCLUDED_EMAILS=<test account emails, comma-separated>
```
These have defaults and only need setting to change them: `SYSTEM_SNAPSHOT_PATH` (`/var/lib/ovp/snapshot.json`), `RUN_NOW_DIR` (`/var/lib/ovp/run-now`), `BACKUP_DIR` (`~/backups`), `PUBLIC_HOSTNAME` (`app.vitamin-e.work`).
7. **Queue wait** (Performance page). In every nginx `location` that proxies to `127.0.0.1:5000`, add the line below, then `sudo nginx -t && sudo systemctl reload nginx`. Without it the card reads "No data".
```
proxy_set_header X-Request-Start "t=${msec}";
```
8. **Retire the cron backup.** `crontab -e` and delete the `backup_db.py` line. The timer replaces it; leaving both backs up twice.
9. **Install the timers:**
```
cd /home/helixadmin/project-tracker
sudo cp deploy/systemd/*.service deploy/systemd/*.timer deploy/systemd/*.path /etc/systemd/system/
sudo systemctl daemon-reload
for unit in deploy/systemd/*.timer deploy/systemd/*.path; do sudo systemctl enable --now "$(basename "$unit")"; done
```
10. **Check:**
- `systemctl list-timers 'ovp-*'` — every timer has a next run.
- Dashboard → Overview: the badge reads *Live* within a minute and the status strip is filled.
- Jobs → Run now on *Nightly backup*: ok, a dump in `~/backups/nightly/` and on the NAS.
- Jobs → Run now on *Weekly restore test*: ok.
- Uptime: today's block appears after a few minutes.
11. When the backup and the restore test both pass, `backup_db.py` and `database_restore.py` are deleted from the repo in the next release.

## config.py
Reads `.env` from the repo root with `load_dotenv()`. Every setting is `os.environ.get(...)` with a default, so importing `config` never crashes. `SESSION_COOKIE_SECURE` / `REMEMBER_COOKIE_SECURE` are env-gated; the LAN is HTTPS now, so they can be turned on (with plain HTTP redirected to HTTPS). `CLIENT_SERVICING_REVIEW_ONLY` is the Client Servicing lock (off since 2.6). **Never print or commit `.env`.**

## SSE and HTTP/2 (the "navigation hang")
Live updates use SSE: two streams stay open per page (notifications + the page's own; the Chat tray can add a third). Over HTTP/1.1 browsers allow about six connections per host, so pages that fire several `/api/*` calls queue behind the streams and appear to hang.
- It only happens over HTTP/1.1 — `localhost`, or any HTTPS listener without HTTP/2 switched on. Over the Cloudflare domain (HTTP/2) it doesn't.
- The LAN already serves HTTPS with the internal certificate (`helix-lan.crt` is the public half; the private key never leaves the server). Make sure its nginx block has `http2 on;` (`listen 443 ssl; http2 on;`). Locally, Caddy in front of `python run.py` gives HTTP/2.

## Git
- Remote `github.com/ezekielburton/project-tracker`. Branches `main` (production) and `dev`. Tags on `main` only. `main` only changes through a merged pull request from `dev` (enforced by a branch rule if the plan allows it; otherwise by habit).
- Later: GitHub Actions runs `python -m pytest` on every pull request (needs a Postgres service in the workflow) — planned for the November optimisation pass.
- A junk remote branch `dev-merged.lock.stale-<nanos>` breaks a full `git fetch` — that's why the runbook fetches single refs. Delete it on GitHub when convenient.

## Coming with production hardening
`deploy.sh` and `rollback.sh` (snapshot → migrate → restart → health check), CSRF protection, secure cookies and a committed `.env.example` (Fri 9 Oct); a staging service and error monitoring later (November). This file is rewritten around `./deploy.sh` when they land.
