# Vitamin-E (Helix)

Internal operations platform for **Vitamin Dubai**. It replaces Monday.com for running creative work end to end — project briefs, deliverables, designer assignments, revision cycles, and approvals across the 2D, 3D, and Technical design teams.

Built and maintained by **Ezekiel Burton** — Digital Systems Pilot Lead.

---

## What it does

Everyone works from a role that fits their job:

- **CS** create briefs (C&CM or Standard), set regions, customers, deliverables and deadlines, review submissions, and approve work.
- **Designers** pick up deliverables, submit work (single or in bulk), and raise flags when something needs clarifying.
- **Team Leads** assign designers and track team progress through revision cycles.
- **Admins** manage users and settings, see everything, give final approval, and lock projects.
- **Management** get a read-only view of project and team status.

**Project types:** *C&CM* (Concept & Campaign Material) runs a concept/KV phase followed by POSM deliverables across the UAE and Gulf regions; *Standard* is a flat list of deliverables with no regional split.

Beyond the core workflow, the platform also includes a role-based **dashboard**, a **client directory**, **time tracking**, a **wiki**, an **achievements** system, reusable **file templates**, an in-app **App Updates blog**, **feature requests + bug reports**, **live updates** (changes appear without a page refresh), **in-app + email notifications**, file storage on the office **Synology NAS**, and an **admin emulation** mode for reproducing any user's exact view.

---

## Architecture

Helix is built in **Vertical Slice Architecture** — every feature is its own self-contained module.

```
app/
  modules/
    <feature>/          # one folder per feature: routes, templates, logic, tests, its own <feature>.md
    core/shared/        # the single home for code shared across features
      models/  lib/  services/  routes/  templates/  extensions.py
  static/               # shared css / js / fonts, cache-busted on each deploy
migrations/             # one-off schema scripts, applied by migrate.py
run.py                  # entry point
```

Feature modules: `achievements`, `admin`, `auth`, `blog`, `client_directory`, `dashboard`, `feedback`, `file_templates`, `notifications`, `profile`, `projects`, `time_tracking`, `wiki`.

The rule is simple: anything one feature needs lives in that feature's folder; anything two or more features share moves to `core/shared`. Features don't reach into each other's internals — they meet in `core/shared`. Want to change one feature? Open its module, change it, done — nothing else has to move. IMPORTANT: Helix doesn't have any tests at the moment. All modules or features must have tests - add to any previous modules if retouching them for overhauls.

---

## Stack

- **Backend:** Python 3.14 · Flask 3.1 · SQLAlchemy 2.0 · Flask-Login
- **Database:** PostgreSQL 18 (`project_tracker`)
- **Frontend:** Jinja2 server-rendered templates · vanilla JS · custom CSS
- **Live updates:** Server-Sent Events (gevent workers in production)
- **Schema changes:** one-off scripts run through a small `migrate.py` runner — no Flask-Migrate

---

## Local setup

Prerequisites: Python 3.14+ and PostgreSQL 18.

```bash
git clone https://github.com/ZeeKzz/project-tracker.git
cd project-tracker

python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt

createdb -U postgres project_tracker

# Create a .env with at least SECRET_KEY and DATABASE_URL
# (add mail / NAS settings if you use those features)

python create_tables.py             # build tables from the models
python migrate.py                   # apply any pending schema scripts
python run.py                       # http://localhost:5000
```

---

## Database migrations

There is no migration framework. Each schema change is a one-off script in `migrations/`, applied through a small runner that records what has already been run:

```bash
python migrate.py --status          # see what's applied vs pending
python migrate.py                   # run all pending scripts
```

---

## Roles

Access is by capability, not by role name: see [docs/CAPABILITIES.md](docs/CAPABILITIES.md) for who can do what.

---

## Deployment

Production runs on-prem (Ubuntu Server) under gunicorn behind nginx, exposed through a Cloudflare Tunnel. Releases are tagged and deployed one-way (fetch + reset, never `git pull` on the server): [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). Rebuilding the server from zero: [docs/SERVER_SETUP.md](docs/SERVER_SETUP.md). No secrets live in version control.

---

## Versioning

`MAJOR.MINOR.PATCH`, numbered in ship order: PATCH is a fix or small addition, MINOR a new page, capability or module, MAJOR a new era (3.0 is the OVP app). Each release is an annotated tag `v<version>`.

---

## Developer docs

Start with [docs/README.md](docs/README.md): architecture, conventions, capabilities, deployment and server setup.
