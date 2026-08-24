# auth

Authentication and account settings: logging in and out, registration,
account preferences, and admin-side user management.

## Structure
```
app/modules/auth/
  routes/auth.py         # the `auth` blueprint
  templates/auth/        # login.html, register.html, account.html, users.html
  tests/test_auth_smoke.py
  auth.md
```

## Routes (the `auth` blueprint)
- `GET/POST /login` — sign in (the app's `login_manager.login_view`)
- `GET/POST /register` — create an account
- `GET /logout` — sign out
- `GET/POST /account` — the current user's account settings page
- `POST /account/notification-prefs` — save per-type email notification opt-outs
- `POST /account/sound-prefs` — save notification-sound preferences
- `GET /admin/users` — admin user list
- `POST /admin/users/<id>/reset-password` — admin password reset

## Models
None of its own. Uses `User` and `NotificationSound` from `core/shared/models`.

## Static
None of its own. Auth pages render through the shared `base.html` layout.

## Dependencies
- **core/shared**: `db` (extensions), `User`/`NotificationSound` (models),
  `role_required` (lib/decorators). Imported directly from core/shared — auth is
  the first module to drop the compatibility shims.
- **Cross-module (explicit, temporary):**
  - `check_achievements` (achievements) — the gamification hook fired on
    login/register.
  - `_build_account_achievement_context` (profile) — supplies the account
    page's rewards data.
  Both are imported from their current `app.*` paths and will repoint when those
  modules migrate. They mark the two seams where auth touches other slices.

## Exports
The `auth` blueprint, registered in the app factory. `login_manager.login_view`
is `auth.login`.

## Tests
`tests/test_auth_smoke.py` — the login page renders, and `/account` requires
authentication. Uses the shared fixtures from `core/shared`.

## Notes
Profile viewing/editing is the **profile** module's responsibility, not auth's.
`profile.html` remains in `app/templates/auth/` and moves with the profile
module.
