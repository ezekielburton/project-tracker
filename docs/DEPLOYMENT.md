# Deployment

How OVP runs in production and how a release goes out. Server setup from zero is in [SERVER_SETUP.md](SERVER_SETUP.md). No secrets in this file — real values live in the password manager, and the app reads them from `.env` (start from `.env.example`).

## The server
- Host `vitamine`, deploy user `helixadmin`, repo `/home/helixadmin/project-tracker`.
- Virtualenv `venv/` (no leading dot): `venv/bin/python`, `venv/bin/gunicorn`. The system `python3` doesn't have the app's packages, so every systemd or cron job uses `venv/bin/python`.
- Timezone UTC+04; systemd `OnCalendar` uses local time.
- nginx in front of gunicorn. Public access is through the Cloudflare domain (HTTP/2). The LAN IP is still plain HTTP/1.1 (see *SSE and HTTP/2*).

## The app service
- Unit `helix.service`: `sudo systemctl restart helix`.
- `ExecStart=/home/helixadmin/project-tracker/venv/bin/gunicorn -k gevent -w 9 --worker-connections 1000 --graceful-timeout 5 -b 127.0.0.1:5000 run:app`, working directory the repo.

## Looking at a problem
- App log: `sudo journalctl -u helix -n 200 --no-pager` (add `-f` to follow).
- Database: `sudo -u postgres psql -d project_tracker` — read-only queries only; changes go through a migration.
- Up?: `curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5000/` (200 or 302 = up).

## Releasing — tagged, one-way
Each shipped roadmap item gets its own annotated tag `v<version>` (message = the item's title) and one deploy, after working hours. The server only ever fetches and resets — **never `git pull` on the server**.

Before tagging: the whole test suite passes and the item's wiki articles are written.

### On the laptop — merge `dev` into `main`, tag, push
```
git checkout main
git pull --ff-only origin main
git merge dev
git push origin main
git tag -a v<version> -m "<version> — <title>"
git push origin v<version>
```
If the merge won't fast-forward, stop and check before forcing.

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

## config.py
Reads `.env` from the repo root with `load_dotenv()`. Every setting is `os.environ.get(...)` with a default, so importing `config` never crashes. `SESSION_COOKIE_SECURE` / `REMEMBER_COOKIE_SECURE` are env-gated and stay off until the LAN serves HTTPS. `CLIENT_SERVICING_REVIEW_ONLY` is the Client Servicing lock (off since 2.6). **Never print or commit `.env`.**

## SSE and HTTP/2 (the "navigation hang")
Live updates use SSE: two streams stay open per page (notifications + the page's own; the Chat tray can add a third). Over HTTP/1.1 browsers allow about six connections per host, so pages that fire several `/api/*` calls queue behind the streams and appear to hang.
- It only happens over HTTP/1.1 — `localhost` or the LAN IP on plain HTTP. Over the Cloudflare domain (HTTP/2) it doesn't.
- The fix is HTTP/2 in front of the app, which needs TLS: an nginx `listen 443 ssl; http2 on;` block on the LAN with the internal certificate (`helix-lan.crt` is the public half; the private key never leaves the server), then turn the secure-cookie settings on. Locally, Caddy in front of `python run.py` does the same.

## Git
- Remote `github.com/ezekielburton/project-tracker`. Branches `main` (production) and `dev`. Tags on `main` only.
- A junk remote branch `dev-merged.lock.stale-<nanos>` breaks a full `git fetch` — that's why the runbook fetches single refs. Delete it on GitHub when convenient.

## Coming with production hardening
`/healthz`, `deploy.sh` and `rollback.sh` (snapshot → migrate → restart → health check), a staging service on the same box, error monitoring, LAN TLS + HTTP/2, CSRF protection and a committed `.env.example`. This file is rewritten around `./deploy.sh` when they land.
