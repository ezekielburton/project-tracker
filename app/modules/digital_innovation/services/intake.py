# Digital Innovation — the intake seam. This is the ONE function any
# other module (the future feedback module, most likely) calls to file an
# approved item onto the OVP board's Incoming tray. Deliberately the
# opposite direction of every other cross-module link in this app: this
# module never imports the feedback module's models, it only ever
# receives plain values through this function — so DI stays buildable and
# testable with zero knowledge of what "feedback" even is.
#
# Doesn't commit — same convention as lib/step_engine.py's create_feature:
# the caller (a route, or another module's own service layer) owns the
# transaction and decides when to commit or roll back.

from app.modules.core.shared.extensions import db
from app.modules.digital_innovation.models import DiIntakeItem
from app.modules.digital_innovation.lib.board_data import permanent_project


def add_feedback_item(source_type, source_ref, title, description=None):
    """Files one pending intake item against the permanent OVP board.
    description is accepted and stored, even though promoting an item
    later drops it (DiFeature has no description field) — it's still
    worth keeping on the intake row itself, for whoever's triaging the
    tray to read before promoting or dismissing.

    Raises ValueError if there's no permanent project to attach to —
    should never happen outside a broken migration, since the seed is
    what creates it."""
    project = permanent_project()
    if project is None:
        raise ValueError('No permanent project exists to attach intake items to.')

    item = DiIntakeItem(
        di_project_id=project.id,
        source_type=source_type,
        source_ref=source_ref,
        title=title,
        description=description,
    )
    db.session.add(item)
    db.session.flush()
    return item
