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

Accounts: the add form and the inline edit row set name, email, password and
the org fields — department, job title, seniority, Reports to, design team and
the Admin switch. The rules live in `lib/accounts.py` (`apply_org_fields`), not
the routes: fields left out keep their value; unknown department, seniority or
team, a Reports to that is the person or would make a loop, and removing your
own admin are refused with a 400; every access change is logged as
"field: old → new". Job titles are typed freely with the department's titles
suggested; a new one joins that department's list, a hidden one is shown again.
The Job titles panel renames, hides and shows titles (`/admin/api/job-titles`).
The form lists come from `GET /admin/api/org-options`. The list groups people as
Management, then each department, Design split by team.

Account deactivation: `POST /admin/api/users/<id>/active` flips a user's
`is_active` flag; the users list endpoint returns `is_active`, and
start-emulation refuses a deactivated target or an admin account. In the panel,
deactivated accounts collect in a muted "Deactivated" group and are reactivated
from there. See `core.md` for what deactivation hides across the rest of the app.

Help key: `admin.accounts`.

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
