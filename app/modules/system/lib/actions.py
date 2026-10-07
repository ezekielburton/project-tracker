"""What counts as an action on the Usage and Overview pages: a saved change,
meaning a successful POST, PUT, PATCH or DELETE that isn't housekeeping
(logging in, marking things seen, saving a layout, autosave, previews)."""

ACTION_METHODS = ('POST', 'PUT', 'PATCH', 'DELETE')
# Writes in these blueprints are never someone doing work.
NOT_ACTION_BLUEPRINTS = ('auth', 'sse', 'system', 'notifications')
# Single housekeeping routes, as their url rules.
NOT_ACTION_ROUTES = (
    '/sidebar/track',
    '/signal/seen',
    '/client-servicing/layout',
    '/projects-new/layout',
    '/wiki/editor/article/autosave',
    '/hse/calendar/schedules/preview',
    '/projects/<int:project_id>/overlay/deliverables/apply-multiple/preview',
    '/dashboard/api/admin/jobs/<job_key>/run',
)
