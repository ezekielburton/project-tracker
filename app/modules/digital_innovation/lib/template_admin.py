# CRUD and reordering for department step templates, behind the admin-only
# Edit Templates screen (routes/templates.py). Template edits never touch
# steps already copied onto features.

from app.modules.core.shared.extensions import db
from app.modules.digital_innovation.models import DiStepTemplate, DI_STAGES


def templates_by_stage():
    """{stage: [DiStepTemplate, ...]} for every stage, each ordered by
    sort_order."""
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
    """Updates a template step's title and details. Stage and position are
    unchanged; use move_template_step to reorder."""
    template.title = title
    template.details = details


def delete_template_step(template):
    db.session.delete(template)


def move_template_step(template, direction):
    """Swaps sort_order with the neighbour above ('up') or below ('down')
    in the same stage. No-op at either end."""
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
