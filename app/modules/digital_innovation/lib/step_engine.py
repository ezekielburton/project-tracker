# Feature and step state machine. Every route that creates or moves a feature
# goes through here.
#
# Rules:
# - Only the CURRENT stage's steps can be ticked, added or deleted.
# - A feature can move to any stage, forward or backward, with no completion gate.
# - Re-entering a stage resumes its old steps as left; a first visit copies the
#   department template. Moving away never deletes steps.
# - Ticking or deleting a step never moves the feature.
# - A stage with zero steps is never "complete".
# - Closing is separate (close_feature); routes/features.py only allows it from
#   the last stage with every step done. reopen_feature puts it back there.

from datetime import datetime

from app.modules.core.shared.extensions import db
from app.modules.digital_innovation.models import DiFeature, DiFeatureStep, DiStepTemplate, DI_STAGES


def create_feature(di_project, name, projected_date=None, starting_stage=None):
    """New card at the end of its project, in starting_stage (default: the
    first stage), with that stage's template steps copied in."""
    if starting_stage is None:
        starting_stage = DI_STAGES[0]
    elif starting_stage not in DI_STAGES:
        raise ValueError(f"'{starting_stage}' isn't a valid starting stage.")

    sort_order = DiFeature.query.filter_by(di_project_id=di_project.id).count()
    feature = DiFeature(
        di_project_id=di_project.id,
        name=name,
        status=starting_stage,
        projected_date=projected_date,
        sort_order=sort_order,
    )
    db.session.add(feature)
    db.session.flush()  # need feature.id before its steps can reference it
    _seed_steps_from_template(feature, starting_stage)
    return feature


def add_step(feature, title, details=None):
    """Adds a step to the feature's current stage. title shows on the board
    card; details only in the detail modal."""
    if feature.status == 'closed':
        raise ValueError("Can't add steps to a closed feature.")
    current = _current_stage_steps(feature)
    next_order = max((s.sort_order for s in current), default=-1) + 1
    step = DiFeatureStep(
        stage=feature.status,
        title=title,
        details=details,
        is_done=False,
        sort_order=next_order,
    )
    # Append through the relationship so feature.steps and step.feature are
    # correct in memory without a flush.
    feature.steps.append(step)
    return step


def tick_step(step, done=True):
    """Ticks or unticks a current-stage step. Never moves the feature."""
    _assert_current_stage_step(step)
    step.is_done = done


def delete_step(step):
    """Deletes a current-stage step. Never moves the feature."""
    _assert_current_stage_step(step)
    feature = step.feature
    # Remove through the relationship to keep feature.steps in sync; the
    # delete-orphan cascade on DiFeature.steps issues the DELETE on flush.
    feature.steps.remove(step)
    db.session.flush()


def move_to_stage(feature, target_stage):
    """Moves a feature to any stage, forward or backward, with no completion
    gate. A stage visited before keeps its old steps as left; only a first
    visit copies the template. A stage with no steps (template or own)
    counts as unvisited, so it re-copies the template."""
    if feature.status == 'closed':
        raise ValueError("Can't move a closed feature - reopen it first.")
    if target_stage not in DI_STAGES:
        raise ValueError(f"'{target_stage}' isn't a valid stage.")
    if target_stage == feature.status:
        return  # already there - nothing to do

    already_visited = any(s.stage == target_stage for s in feature.steps)
    feature.status = target_stage
    if not already_visited:
        _seed_steps_from_template(feature, target_stage)


def close_feature(feature):
    """Marks a feature closed. No stage or completion check here; the route
    enforces that."""
    feature.status = 'closed'
    feature.closed_at = datetime.utcnow()


def reopen_feature(feature):
    """closed -> the last stage, where close_feature_route allows closing
    from. Its steps were never removed, so it resumes as it was left."""
    if feature.status != 'closed':
        raise ValueError("Only a closed feature can be reopened.")
    feature.status = DI_STAGES[-1]
    feature.closed_at = None


def is_stage_complete(feature):
    """True when the current stage has at least one step and all are done.
    Used by the close-feature guard; does not gate movement."""
    steps = _current_stage_steps(feature)
    return bool(steps) and all(s.is_done for s in steps)


def _current_stage_steps(feature):
    return [s for s in feature.steps if s.stage == feature.status]


def _assert_current_stage_step(step):
    if step.stage != step.feature.status:
        raise ValueError("Only steps in the feature's current stage can be edited.")


def _seed_steps_from_template(feature, stage):
    templates = (
        DiStepTemplate.query
        .filter_by(stage=stage)
        .order_by(DiStepTemplate.sort_order)
        .all()
    )
    for template in templates:
        # Append through the relationship, as in add_step.
        feature.steps.append(DiFeatureStep(
            stage=stage,
            title=template.title,
            details=template.details,
            is_done=False,
            sort_order=template.sort_order,
        ))
