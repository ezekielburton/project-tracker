# Digital Innovation - "brain A": the step-template/stage-movement state
# machine (per the build brief). Every rule Ezekiel confirmed lives here,
# in one place, so the board route, the feature-detail route and the future
# Incoming-tray promotion path all move features the same way instead of
# each re-implementing the rules slightly differently.
#
# The rules, as confirmed:
# - A feature's CURRENT stage's steps can be ticked/unticked/added/deleted
#   at any time. Steps from stages already passed (or not yet reached) are
#   left alone - only the current stage's steps are editable.
# - A feature can be moved to ANY stage, forward or backward, at any time,
#   via move_to_stage() below - there's no completion gate. This replaced
#   an earlier single-gated-step "Advance" action once Ezekiel confirmed
#   he wants free movement, including backwards, not a locked pipeline.
# - Moving into a stage the feature has already visited before RESUMES
#   that stage's existing steps (ticked or not, exactly as left) rather
#   than reseeding them - a feature's steps are never deleted just for
#   having moved away from their stage. Moving into a stage for the first
#   time seeds it fresh from the department's current template, as before.
# - Because movement is no longer gated on completion, deleting a step no
#   longer auto-advances anything - it just deletes the step.
# - A stage with zero steps is never "complete" - there's nothing to
#   finish, so it just sits there (shown on the board as "No steps
#   configured") until a step is added.
# - Implementation is the last stage in DI_STAGES, but that no longer
#   means anything special to move_to_stage() itself - a feature can be
#   moved OUT of Implementation backward like any other stage. Closing a
#   feature (leaving the stage list entirely) is a separate action -
#   close_feature() below - still gated on being in the last stage with
#   that stage complete (see routes/features.py's close route).

from datetime import datetime

from app.modules.core.shared.extensions import db
from app.modules.digital_innovation.models import DiFeature, DiFeatureStep, DiStepTemplate, DI_STAGES


def create_feature(di_project, name, projected_date=None, starting_stage=None):
    """New card, placed at the end of its project's list, starting in
    starting_stage (validated against DI_STAGES) if given, else the
    pipeline's first stage - with that stage's current template steps
    copied in either way."""
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
    """Adds a step to the feature's CURRENT stage - used both for ordinary
    checklist editing and for the Implementation-stage "add another step"
    choice (they're the same action). title is the short "at a glance"
    text the board card shows; details is optional longer elaboration,
    shown only in the feature detail checklist."""
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
    # Appended through the relationship (not db.session.add() with a raw
    # di_feature_id) so feature.steps - and step.feature, via the backref -
    # are correct immediately in memory, with no flush/re-query needed.
    feature.steps.append(step)
    return step


def tick_step(step, done=True):
    """Ticks or unticks a step. Never moves the feature's stage on its
    own, even if this is the step that completes it - stage movement is
    always a separate, explicit move_to_stage() call from the UI's stage
    picker."""
    _assert_current_stage_step(step)
    step.is_done = done


def delete_step(step):
    """Deletes a step from the feature's current stage. Movement between
    stages is unconstrained (see move_to_stage), so deleting a step never
    triggers a stage change of its own anymore - it just deletes the
    step."""
    _assert_current_stage_step(step)
    feature = step.feature
    # Removed through the relationship, same reasoning as add_step above -
    # this also keeps feature.steps in sync immediately. cascade='delete-
    # orphan' on DiFeature.steps (models.py) is what turns "no longer in
    # the collection" into an actual DELETE once this flushes.
    feature.steps.remove(step)
    db.session.flush()


def move_to_stage(feature, target_stage):
    """Moves a feature directly to any stage, forward or backward, at any
    time - no completion gate, per Ezekiel's confirmed free-movement
    model. This is the sole way a feature's status changes (besides
    creation and closing).

    Resume-on-revisit: a feature's steps are stage-scoped but never
    deleted just because the feature moved to a different stage, so if
    target_stage is one the feature has been in before, its steps from
    that earlier visit are still sitting in feature.steps - this resumes
    them exactly as they were left (ticked or not) rather than reseeding.
    Only a stage the feature has genuinely never entered gets fresh
    steps copied from the department's current template.
    """
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
    """Marks a feature closed - the Implementation-stage "close this
    feature" choice, closing just this card, not its whole project."""
    feature.status = 'closed'
    feature.closed_at = datetime.utcnow()


def is_stage_complete(feature):
    """True when the feature's current stage has at least one step and
    every one of them is done. An unconfigured (zero-step) stage is
    deliberately never "complete" - see the module docstring. No longer
    gates stage movement (see move_to_stage), but still drives the
    Implementation-stage "add step or close" choice and the close-feature
    route's guard."""
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
        # Same append-through-the-relationship reasoning as add_step above.
        feature.steps.append(DiFeatureStep(
            stage=stage,
            title=template.title,
            details=template.details,
            is_done=False,
            sort_order=template.sort_order,
        ))
