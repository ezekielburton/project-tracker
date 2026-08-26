# notifications

The read/manage API for a user's notifications. The **sending** side (creating
notifications and the email fan-out) is a shared service in
`core/shared/services/notifications`; this module is only the endpoints the
front-end calls to read and manage what a user has already received.

## Structure
```
app/modules/notifications/
  routes/notifications.py     # the `notifications` blueprint (notifications_bp)
  tests/test_notifications_smoke.py
  notifications.md
```
No templates — the notification dropdown UI lives in the shared `base.html`
layout and `notifications.js`, driven by the `/notifications/poll` endpoint.

## Routes (the `notifications` blueprint)
`POST /notifications/<id>/read`, `POST /notifications/mark-all-read`,
`POST /notifications/<id>/archive`, `POST /notifications/archive-all`,
`POST /notifications/delete-bulk`, `GET /notifications/poll`,
`POST /notifications/<id>/restore`.

## Models
`Notification`, from `core/shared`.

## Static
`notifications.js` is loaded globally by `base.html`; deferred to the
shared-static pass.

## Dependencies
core/shared only: `db` (extensions) and `Notification` (models). It does not
call the send-side service — that runs from other modules when an event occurs.

## Exports
The `notifications` blueprint. (The notification-count/data injected into every
page's dropdown is assembled by the app factory's context processor, not here.)

## Tests
`tests/test_notifications_smoke.py` — the poll endpoint requires authentication,
and the blueprint's endpoints are registered.
