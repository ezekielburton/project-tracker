# OVP developer docs

Start here if you're new to the codebase.

| Read | For |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | How the app is laid out: modules, shared code, how modules talk to each other, versioning |
| [CONVENTIONS.md](CONVENTIONS.md) | How we build: definition of done, gating, SPA rules, CSS, layout, testing |
| [CAPABILITIES.md](CAPABILITIES.md) | Who can do what: roles, capabilities, `can()` and the decorators |
| [DEPLOYMENT.md](DEPLOYMENT.md) | The production server and how a release goes out |
| [SERVER_SETUP.md](SERVER_SETUP.md) | Rebuilding the server from zero |
| [wiki_articles/](wiki_articles/README.md) | Source text of every in-app wiki article, one file per wiki section |

Also in the repo:
- Each module's own `app/modules/<name>/<name>.md` — how that module works now.
- `app/modules/core/shared/theming.md` — colour tokens and both themes. Read before any CSS.
- `app/modules/core/shared/spa-navigation.md` — how page swaps work. Read before any page JS.

**Secrets never go in the repo or in these docs.** Real values live in the password manager; the app reads them from `.env`, which is git-ignored.
