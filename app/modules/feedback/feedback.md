# feedback

User-facing feedback: a **feature request** board (submit, upvote, comment,
track status) and a **bug report** board (submit, comment, track status). Both
are visible to all signed-in users; status changes and deletions are admin-only.

## Structure
```
app/modules/feedback/
  routes/feedback.py     # the `feedback` blueprint (both boards)
  templates/feedback/    # feature_requests.html, bug_reports.html,
                         # _feature_content.html, _bug_content.html
  tests/test_feedback_smoke.py
  feedback.md
```

## Routes (the `feedback` blueprint)
Feature requests:
- `GET /feature-requests` — the board (list page)
- `GET /feature-requests/<id>` — one request's detail (rendered fragment)
- `POST /feature-requests` — submit a request
- `POST /feature-requests/<id>/upvote` — toggle an upvote
- `POST /feature-requests/<id>/comments` — add a comment
- `DELETE /feature-requests/comments/<id>` — delete a comment (admin)
- `PATCH /feature-requests/<id>/status` — change status (admin)
- `DELETE /feature-requests/<id>` — delete a request (admin or creator)

Bug reports:
- `GET /bug-reports` — the board (list page)
- `GET /bug-reports/<id>` — one bug's detail (rendered fragment)
- `POST /bug-reports` — submit a bug
- `PATCH /bug-reports/<id>/status` — change status (admin)
- `POST /bug-reports/<id>/comments` — add a comment
- `DELETE /bug-reports/comments/<id>` — delete a comment (admin)
- `DELETE /bug-reports/<id>` — delete a bug (admin or creator)

Valid feature statuses: `requested`, `in_progress`, `testing`, `implemented`.

## Models
None of its own. Uses `FeatureRequest`, `FeatureRequestUpvote`,
`FeatureRequestComment`, `BugReport`, `BugReportComment` from
`core/shared/models`.

## Static
Still served from the global `/static` loader (not yet module-owned):
`css/feedback.css`, `js/feedback.js` (feature board), and `js/bug_reports.js`
(bug board). The two boards ship separate scripts — noted here so the eventual
shared-static pass moves all three, not just the one named after the module.

## Dependencies
- **core/shared**: `db` (extensions), the five feedback models,
  `get_actor`/`log_activity` (lib/utils), and the notification service
  (`notify_admin_of_new_feedback`, `create_notification` from
  services/notifications). All imported directly from core/shared.
- **Shared templates**: both detail fragments import `user_avatar` from the
  shared `_macros.html` (on the `core` blueprint's Jinja path).
- **Cross-module (explicit, temporary):** `check_achievements` (achievements) —
  fired on submitting a feature, giving an upvote, and submitting a bug. The
  upvote hook is deliberately guarded to fire only when an upvote is *added*
  (not removed), so toggling can't inflate an "upvote N times" achievement.
  Imported from its current `app.achievements` path; repoints when achievements
  migrates.

## Exports
The `feedback` blueprint, registered in the app factory. The sidebar links to
`feedback.feature_requests` and `feedback.bug_reports`.

## Tests
`tests/test_feedback_smoke.py` — both boards require authentication, and the
board templates resolve. Uses the shared fixtures from `core/shared`.
