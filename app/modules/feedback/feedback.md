# feedback

The Signal tray: a **Bug Report** board, a **Feature Request** board and the
**Friction Log**. Everyone signed in reads and posts to all three. Status
changes and comment deletions are admin-only (`manage_feedback`).

## Structure
```
app/modules/feedback/
  blueprint.py            # feedback_assets: serves this module's static files
  routes/feedback.py      # `feedback` blueprint: detail fragments and writes for both boards
  routes/signal_tray.py   # `signal_tray` blueprint: board lists, Friction Log, launcher bubble
  lib/friction.py         # Friction Log rules: week start, length cap, who may delete
  templates/feedback/     # _bug_content.html, _feature_content.html (detail fragments)
  static/css/             # feedback.css (detail fragments), signal_tray.css
  static/js/signal_tray.js
  tests/
  feedback.md
```

## Routes
`feedback` blueprint:
- `GET /feature-requests`, `GET /bug-reports` — old notification links; redirect into the tray
- `GET /feature-requests/<id>`, `GET /bug-reports/<id>` — one item's detail fragment
- `POST /feature-requests`, `POST /bug-reports` — submit
- `POST /feature-requests/<id>/upvote` — toggle an upvote
- `POST /feature-requests/<id>/comments`, `POST /bug-reports/<id>/comments` — add a comment
- `DELETE /feature-requests/comments/<id>`, `DELETE /bug-reports/comments/<id>` — delete a comment (admin)
- `PATCH /feature-requests/<id>/status`, `PATCH /bug-reports/<id>/status` — change status (admin)
- `DELETE /feature-requests/<id>`, `DELETE /bug-reports/<id>` — delete (admin or submitter)

`signal_tray` blueprint:
- `GET /signal/bugs`, `GET /signal/features` — board rows and chip counts
- `GET /signal/friction` — the latest 500 posts, oldest first, grouped by week
- `POST /signal/friction` — post; anyone signed in, 1–500 characters
- `DELETE /signal/friction/<id>` — delete; the author, or `manage_feedback`
- `GET /signal/unread`, `POST /signal/seen` — the launcher bubble

## Friction Log
- For annoyances only; bugs and ideas have their own tabs. Reviewed every
  Friday; the current week carries a "Review Fri" tag.
- Each post shows Name · Department (`org.department_label`).
- **Emulation exception:** posts and deletes act as the emulated person, as in
  the chat tray (CONVENTIONS.md §4).
- **Live:** adding or deleting a post fires `friction_changes`
  (`core/shared/services/live_events.py`), and `GET /sse/friction` rings every
  open Friction tab, which reloads its list. The stream opens with the tab and
  closes on a tab switch or tray close; the tray outlives page navigation, so
  navigation does not close it.
- A live reload redraws only the list: a half-typed post survives, and the
  list only follows new posts when the reader is already at the bottom.
- Writes go through `fetchJson` in `signal_tray.js` — the one place a CSRF
  token is added.
- The launcher bubble counts new bugs, ideas and friction posts since the tray
  was last opened.

## Models
None of its own. Uses `FeatureRequest`, `FeatureRequestUpvote`,
`FeatureRequestComment`, `BugReport`, `BugReportComment` and
`FrictionLogEntry` from `core/shared/models`.

## Dependencies
- **core/shared:** `db`, the models above, `can` / `effective_user`,
  `org.department_label`, `get_actor` / `log_activity`, the notification
  service, and the live-update stream (`live_events`, `sse_relay`, `polling.js`).
- **Cross-module:** `check_achievements` (on submitting, and on adding an
  upvote — never on removing one); Digital Innovation's
  `services/intake.declined_feature_ids` for the feature board's DI state.

## Tests
- `test_feedback_smoke.py` — logged-out refusals; the detail fragments resolve.
- `test_signal_tray.py` — both boards, every Friction Log gate, emulation,
  ordering, department label, the launcher bubble.
- `test_signal_tray_contract.py` — the fragments still carry every selector
  `signal_tray.js` binds.
- `test_feedback_links.py` — notification links open with a GET; who sees
  comment-delete.
