# Digital Innovation — "brain A": the step-template/advance-status state
# machine (per the build brief). Every rule Ezekiel confirmed lives here,
# in one place, so the board route, the feature-detail route and the future
# Incoming-tray promotion path all move features the same way instead of
# each re-implementing the rules slightly differently.
#
# The rules, as confirmed:
# - A feature's CURRENT stage's steps can be ticked/unticked/added/deleted
#   at any time. Steps from stages already passed are left alone (kept,
#   all done, for history) — only the current stage's steps are editable.
# - Ticking the step that completes a stage does NOT advance by itself —
#   that needs an explicit "Advance" action (see advance_stage below).
# - DELETING a step that leaves the stage's remaining steps all done DOES
#   advance immediately, automatically.
# - A stage with zero steps is never "complete" — there's nothing to
#   finish, so it just sits there (shown on the board as "No steps
#   configured") until a step is added, rather than silently advancing.
# - Implementation is the last stage. Finishing it doesn't advance to
#   anything — the route layer surfaces the "add another step or close
#   this feature" choice instead (is_stage_complete() below is what tells
#   it when to do that); advance_stage() itself refuses to be called from
#   Implementation.

from datetime import datetime

from app.modules.core.shared.extensions import db
from app.modules.digital_innovation.models import DiFeature, DiFeatureStep, DiStepTemplate, DI_STAGES


def create_feature(di_project, name, projected_date=None):
    """New card, placed at the end of its project's list, starting in the
    first stage with that stage's current template steps copied in."""
    sort_order = DiFeature.query.filter_by(di_project_id=di_project.id).count()
    feature = DiFeature(
        di_project_id=di_project.id,
        name=name,
        status=DI_STAGES[0],
        projected_date=projected_date,
        sort_order=sort_order,
    )
    db.session.add(feature)
    db.session.flush()  # need feature.id before its steps can reference it
    _seed_steps_from_template(feature, DI_STAGES[0])
    return feature


def add_step(feature, title, details=None):
    """Adds a step to the feature's CURRENT stage — used both for ordinary
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
    # di_feature_id) so feature.steps — and step.feature, via the backref —
    # are correct immediately in memory, with no flush/re-query needed.
    feature.steps.append(step)
    return step


def tick_step(step, done=True):
    """Ticks or unticks a step. Never advances the stage on its own, even
    if this is the step that completes it — that's what advance_stage is
    for, called explicitly once the UI's "Advance" button is clicked."""
    _assert_current_stage_step(step)
    step.is_done = done


def delete_step(step):
    """Deletes a step from the feature's current stage. If that leaves the
    remaining steps in the stage all done, advances immediately — unless
    the feature is already in Implementation, in which case there's no
    next stage to advance to and the route layer is left to notice (via
    is_stage_complete) and offer the add-step-or-close choice instead.

    Returns True if this call advanced the feature, False otherwise."""
    _assert_current_stage_step(step)
    feature = step.feature
    # Removed through the relationship, same reasoning as add_step above —
    # this also keeps feature.steps in sync immediately. cascade='delete-
    # orphan' on DiFeature.steps (models.py) is what turns "no longer in
    # the collection" into an actual DELETE once this flushes.
    feature.steps.remove(step)
    db.session.flush()

    if feature.status != DI_STAGES[-1] and is_stage_complete(feature):
        advance_stage(feature)
        return True
    return False


def advance_stage(feature):
    """Moves a feature to its next stage, seeding that stage's steps from
    its current template. Refuses if the current stage isn't actually done
    (an empty stage counts as not-done — see is_stage_complete), and
    refuses from Implementation, which has no next stage to advance to."""
    if feature.status == DI_STAGES[-1]:
        raise ValueError(
            "Implementation is the last stage — close the feature or add "
            "another step instead of advancing."
        )
    if not is_stage_complete(feature):
        raise ValueError("Not every step in the current stage is done yet.")

    next_stage = DI_STAGES[DI_STAGES.index(feature.status) + 1]
    feature.status = next_stage
    _seed_steps_from_template(feature, next_stage)


def close_feature(feature):
    """Marks a feature closed — the Implementation-stage "close this
    feature" choice, closing just this card, not its whole project."""
    feature.status = 'closed'
    feature.closed_at = datetime.utcnow()


def is_stage_complete(feature):
    """True when the feature's current stage has at least one step and
    every one of them is done. An unconfigured (zero-step) stage is
    deliberately never "complete" — see the module docstring."""
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
