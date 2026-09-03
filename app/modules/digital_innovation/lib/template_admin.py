# Digital Innovation — department-wide step template management, for the
# admin-only "Edit Templates" screen (routes/templates.py, gated by
# lib/access.py's can_edit_di_templates). Editing a template never
# touches any feature already seeded from it — see step_engine.py's
# module docstring and its
# test_editing_a_later_template_does_not_touch_existing_features — so
# this is plain CRUD plus reordering on DiStepTemplate, no interaction
# with brain A's state machine at all.

from app.modules.core.shared.extensions import db
from app.modules.digital_innovation.models import DiStepTemplate, DI_STAGES


def templates_by_stage():
    """{stage: [DiStepTemplate, ...]} for every stage, each list already
    ordered by sort_order — exactly what the Edit Templates screen
    renders, one section per stage."""
    templates = DiStepTemplate.query.order_by(DiStepTemplate.sort_order).all()
    by_stage = {stage: [] for stage in DI_STAGES}
    for template in templates:
        by_stage.setdefault(template.stage, []).append(template)
    return by_stage


def add_template_step(stage, title, details=None):
    """Adds a step to the end of `stage`'s template list."""
    current = DiStepTemplate.query.filter_by(stage=stage).all()
    next_order = max((t.sort_order for t in current), default=-1) + 1
    template = DiStepTemplate(stage=stage, title=title, details=details, sort_order=next_order)
    db.session.add(template)
    return template


def edit_template_step(template, title, details=None):
    """Updates a template step's title/details in place. Never touches
    stage or sort_order — moving between stages or positions isn't a
    supported action (delete + re-add covers the rare "wrong stage"
    case, and move_template_step below covers reordering)."""
    template.title = title
    template.details = details


def delete_template_step(template):
    db.session.delete(template)


def move_template_step(template, direction):
    """Swaps this template step's sort_order with its neighbour in the
    same stage — 'up' moves it earlier in the list, 'down' moves it
    later. A no-op at either end (already first and moving up, or
    already last and moving down)."""
    siblings = (
        DiStepTemplate.query
        .filter_by(stage=template.stage)
        .order_by(DiStepTemplate.sort_order)
        .all()
    )
    index = siblings.index(template)

    if direction == 'up' and index > 0:
        neighbour = siblings[index - 1]
    elif direction == 'down' and index < len(siblings) - 1:
        neighbour = siblings[index + 1]
    else:
        return

    template.sort_order, neighbour.sort_order = neighbour.sort_order, template.sort_order
