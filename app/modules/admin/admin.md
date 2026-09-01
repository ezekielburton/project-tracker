# admin

The Admin Panel back end: a JSON API for managing the app's reference data and
users — user accounts, clients, customers, deliverable types (and their
disciplines), design types and directions, and notification sounds.

## Structure
```
app/modules/admin/
  routes/admin.py     # the `admin` blueprint (JSON API only)
  tests/test_admin_smoke.py
  admin.md
```

## Routes (the `admin` blueprint)
A JSON API only — no templates. 45 endpoints under `/admin/api/*` covering
list/create/update/delete for users, clients, customers, deliverable types,
design types/directions, and notification sounds, plus a deliverable-type
reference-image upload and an admin password reset. The Admin Panel UI that
drives it lives in the shared `base.html` layout and `admin.js`.

Account deactivation: `POST /admin/api/users/<id>/active` flips a user's
`is_active` flag; the users list endpoint returns `is_active`, and
start-emulation refuses a deactivated target. In the panel, deactivated
accounts collect in a muted "Deactivated" group and are reactivated from there.
Project owners have their own group in the account list. See `core.md` for what
deactivation hides across the rest of the app.

## Models
None of its own. Uses `User`, `Client`, `Customer`, `Project`, `ProjectFile`,
`DeliverableType`, `DeliverableTypeDiscipline`, `DesignType`, `DesignDirection`,
`ActivityLog`, `NotificationSound` from `core/shared/models`.

## Static
`css/admin.css`, `js/admin.js` — served from the global `/static` loader; move in
the shared-static pass.

## Dependencies
- **core/shared**: `db` (extensions), the models above, `log_activity`
  (lib/utils), `role_required` (lib/decorators), `broadcast_update_email`
  (services/notifications), and `template_upload_folder` (lib/paths, for the
  reference-image upload). All imported directly from core/shared.
- **No cross-module feature seams** — only the app factory imports this module.

## Exports
The `admin` blueprint, registered in the app factory.

## Tests
`tests/test_admin_smoke.py` — an admin API endpoint requires authentication.
Uses the shared fixtures from `core/shared`.

## Note
The `achievements` admin API (`admin_achievements`) is a separate module, not
part of this one — it moved out when the achievements system was migrated.
