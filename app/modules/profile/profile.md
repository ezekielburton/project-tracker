# profile

Viewing and editing user profiles (own and other users'), and the profile page's
achievement display. Also assembles the achievement data that the auth module's
account page renders.

## Structure
```
app/modules/profile/
  routes/profile.py          # the `profile` blueprint (profile_bp)
  templates/profile/profile.html
  tests/test_profile_smoke.py
  profile.md
```

## Routes (the `profile` blueprint)
- `GET /profile` and `GET /profile/<id>` — view own or another user's profile
- `POST /profile/avatar`, `POST /profile/banner` — image uploads
- `POST /profile/details`, `POST /profile/bio` — edit profile fields
- `POST /account/display-settings` — save Active Rewards choices
- `POST /account/pinned-achievements` — save pinned-achievement order

## Models
None of its own. Uses `User`, `RoleTitle`, and the achievement models
(`UserAchievement`, `UserDisplaySettings`, `UserPinnedAchievement`,
`AchievementBorder`, `Achievement`, `AchievementCategory`) from `core/shared`.

## Static
`profile.js`, `profile.css`, and the avatar tools (`avatar-cropper.js`,
`avatar_picker.js`) are **deferred to the shared-static pass** and remain in
`app/static` for now. The avatar tools are shared with `project_list`, so that
pass decides whether they land in core/shared or here.

## Dependencies
core/shared only: `db` (extensions), the models above, `get_actor` (lib/utils).
No reach into any other feature module.

## Exports / consumers
The `profile` blueprint. `_build_account_achievement_context(user)` is imported
by the **auth** module's account view — the one cross-module edge, now wired to
this module's real path.

## Tests
`tests/test_profile_smoke.py` — a profile view requires authentication, and the
renamed template `profile/profile.html` resolves through the module's
`template_folder`.

## Notes
The template was renamed from `auth/profile.html` to `profile/profile.html` so
the module owns its own name.
