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
- App log: `sudo journalctl -u helix -n 200 --no-pager` (add `-f` to follow).
- Database: `sudo -u postgres psql -d project_tracker` — read-only queries only; changes go through a migration.
- Up?: `curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5000/` (200 or 302 = up).

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
venv/bin/python migrate.py                # applies pending migrations
sudo systemctl restart helix
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5000/
```
**Safety gate:** if the diff lists files you don't expect, stop and run `git log --oneline origin/main..HEAD` to check for anything unique on the server before resetting.

After it's live, post the in-app blog update (small patches can share one post).

One-off data scripts with a dry run (e.g. `migrate_wiki_to_editorjs.py`) are run by hand: dry run, read the output, then `--confirm`.

## Migrations
One-off files in `migrations/`, run by `migrate.py` (not Alembic). `migrate.py` records what has run in `schema_migrations`; `--status` lists pending ones. Migrations are additive (`ADD COLUMN IF NOT EXISTS`), which is why running them in name order is safe.

## Scheduled jobs
- `preview-cache-cleanup.timer` + `.service` — daily 03:30, `Persistent=true`, runs `venv/bin/python preview_cache_cleanup.py` as `helixadmin`. Empties `uploads/preview-cache/` (disposable; the NAS is the source of truth).
- The Dashboard update adds more (heartbeat, snapshot, nightly backup, weekly restore test, clean-ups), each a systemd timer recorded in `job_runs`.
- `nas-outbox-flush.timer` + `.service` — every 2 minutes, runs `venv/bin/python nas_outbox_flush.py` as `helixadmin`. Sends files queued in `uploads/nas-outbox/` while the NAS was down. Check the queue: `sudo -u postgres psql -d project_tracker -c "select nas_path, attempts, last_error, created_at from pending_nas_uploads;"` (empty = all sent).

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
`/healthz`, `deploy.sh` and `rollback.sh` (snapshot → migrate → restart → health check), CSRF protection, secure cookies and a committed `.env.example` (Fri 9 Oct); a staging service and error monitoring later (November). This file is rewritten around `./deploy.sh` when they land.
