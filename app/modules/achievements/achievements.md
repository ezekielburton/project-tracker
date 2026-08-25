# achievements

The achievements system has two halves, split by responsibility:

- **The checker service** lives in `core/shared/services/achievements.py`. It is
  shared infrastructure, not part of this module — see below.
- **This module** owns the admin-facing management API: the JSON endpoints used
  to create and configure achievements, their categories, and their display
  borders.

## Structure
```
app/modules/achievements/
  routes/admin_achievements.py   # the `admin_achievements` blueprint (JSON API)
  tests/test_achievements_smoke.py
  achievements.md
```

## Routes (the `admin_achievements` blueprint)
A JSON API only — no templates. The management UI that drives it is rendered on
the profile page (`achievements.js`). Endpoints cover CRUD + reordering for:
- `/admin/api/achievement-categories` (GET/POST/PATCH/DELETE, reorder)
- `/admin/api/achievements` (POST/PATCH/DELETE, reorder)
- `/admin/api/achievement-borders` (GET/POST/DELETE)

## Models
None of its own. Uses `Achievement`, `AchievementCategory`, `AchievementBorder`,
`UserAchievement` from `core/shared/models`.

## Static
`css/achievements.css`, `js/achievements.js` — loaded on the profile page,
served from the global `/static` loader; move in the shared-static pass.

## Dependencies
- **core/shared**: `db` (extensions), the four achievement models,
  `log_activity` (lib/utils). All imported directly from core/shared.
- **No cross-module feature seams.** Only the app factory imports this module.

## The checker service (why it is not in this module)
`check_achievements(user, event_type, metadata=None)` lives in
`core/shared/services/achievements.py`, alongside the notification service.
It is called from the tail end of many unrelated routes — logging in, posting a
blog comment, submitting or upvoting feedback, approving a project — to advance
and award achievements. Because it is used by many features (and will track more
as the app grows), it is shared infrastructure, not the private code of the
admin panel. This mirrors how the notification service is shared while the
notifications module owns only its own routes.

A one-line compatibility shim remains at `app/achievements.py` re-exporting
`check_achievements`, so code not yet moved to the modules layout (currently the
project overlay) keeps working. Migrated modules import the service directly
from core/shared.

## Exports
The `admin_achievements` blueprint, registered in the app factory.

## Tests
`tests/test_achievements_smoke.py` — the checker is reachable from both the
shared path and the old shim (same object), and the admin API requires
authentication. Uses the shared fixtures from `core/shared`.
