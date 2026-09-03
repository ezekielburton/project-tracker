"""Coverage for the Digital Innovation step-advancement state machine
(lib/step_engine.py, "brain A"). No routes/HTTP here - this exercises the
rules directly against the database, the same way
client_servicing/tests/test_client_servicing_models.py covers its models.

move_to_stage() replaced advance_stage() once Ezekiel confirmed he wants
free movement to any stage, forward or backward, with no completion gate
- see step_engine.py's module docstring. Tests below reflect that: there
is no more "refuses when a step is still open" or "auto-advances on
delete" behaviour to cover, and instead there is resume-on-revisit,
seed-on-first-visit, and unconstrained direction to cover."""
import pytest

from app.modules.digital_innovation.models import DiProject, DiStepTemplate, DI_STAGES
from app.modules.digital_innovation.lib import step_engine as engine


def _project(db_session, tag):
    project = DiProject(name=f'Test DI Project {tag}')
    db_session.add(project)
    db_session.flush()
    return project


def _template(db_session, stage, title, sort_order=0):
    template = DiStepTemplate(stage=stage, title=title, sort_order=sort_order)
    db_session.add(template)
    db_session.flush()
    return template


def test_create_feature_starts_in_first_stage_with_no_template(db_session):
    project = _project(db_session, 'a')
    feature = engine.create_feature(project, 'New thing')

    assert feature.id is not None
    assert feature.status == DI_STAGES[0]
    assert feature.steps == []


def test_create_feature_copies_in_the_current_template(db_session):
    project = _project(db_session, 'b')
    _template(db_session, DI_STAGES[0], 'Write the brief', sort_order=0)
    _template(db_session, DI_STAGES[0], 'Talk to Ezekiel', sort_order=1)

    feature = engine.create_feature(project, 'New thing')

    titles = [s.title for s in feature.steps]
    assert titles == ['Write the brief', 'Talk to Ezekiel']
    assert all(s.stage == DI_STAGES[0] and not s.is_done for s in feature.steps)


def test_editing_a_later_template_does_not_touch_existing_features(db_session):
    project = _project(db_session, 'c')
    _template(db_session, DI_STAGES[0], 'Original step')
    feature = engine.create_feature(project, 'New thing')

    _template(db_session, DI_STAGES[0], 'Added later')

    assert [s.title for s in feature.steps] == ['Original step']


def test_create_feature_accepts_a_starting_stage(db_session):
    project = _project(db_session, 'b1')
    _template(db_session, DI_STAGES[3], 'Testing step')

    feature = engine.create_feature(project, 'New thing', starting_stage=DI_STAGES[3])

    assert feature.status == DI_STAGES[3]
    assert [s.title for s in feature.steps] == ['Testing step']


def test_create_feature_refuses_an_invalid_starting_stage(db_session):
    project = _project(db_session, 'b2')

    with pytest.raises(ValueError):
        engine.create_feature(project, 'New thing', starting_stage='not-a-real-stage')


def test_ticking_every_step_does_not_auto_advance(db_session):
    project = _project(db_session, 'd')
    _template(db_session, DI_STAGES[0], 'Only step')
    feature = engine.create_feature(project, 'New thing')

    engine.tick_step(feature.steps[0], done=True)

    assert feature.status == DI_STAGES[0]
    assert engine.is_stage_complete(feature) is True


def test_tick_step_rejects_a_step_from_a_stage_the_feature_has_left(db_session):
    project = _project(db_session, 'e')
    _template(db_session, DI_STAGES[0], 'Only step')
    _template(db_session, DI_STAGES[1], 'Next stage step')
    feature = engine.create_feature(project, 'New thing')
    old_step = feature.steps[0]

    engine.tick_step(old_step, done=True)
    engine.move_to_stage(feature, DI_STAGES[1])

    with pytest.raises(ValueError):
        engine.tick_step(old_step, done=False)


def test_move_to_stage_moves_forward_and_seeds_a_new_stage(db_session):
    project = _project(db_session, 'h')
    _template(db_session, DI_STAGES[0], 'Step one')
    _template(db_session, DI_STAGES[1], 'Planning step')
    feature = engine.create_feature(project, 'New thing')
    # deliberately left unticked - movement is no longer gated on this

    engine.move_to_stage(feature, DI_STAGES[1])

    assert feature.status == DI_STAGES[1]
    assert [s.title for s in feature.steps if s.stage == DI_STAGES[1]] == ['Planning step']
    # the old stage's step is kept, still there, for history
    assert any(s.stage == DI_STAGES[0] for s in feature.steps)


def test_move_to_stage_does_not_gate_on_completion(db_session):
    project = _project(db_session, 'h2')
    _template(db_session, DI_STAGES[0], 'Step one')
    _template(db_session, DI_STAGES[0], 'Step two')
    feature = engine.create_feature(project, 'New thing')
    engine.tick_step(feature.steps[0], done=True)
    # feature.steps[1] left unticked, is_stage_complete() is False

    engine.move_to_stage(feature, DI_STAGES[1])  # must not raise

    assert feature.status == DI_STAGES[1]


def test_move_to_stage_allows_moving_backward(db_session):
    project = _project(db_session, 'i')
    feature = engine.create_feature(project, 'New thing')
    feature.status = DI_STAGES[-1]

    engine.move_to_stage(feature, DI_STAGES[0])

    assert feature.status == DI_STAGES[0]


def test_move_to_stage_is_a_noop_when_target_equals_current(db_session):
    project = _project(db_session, 'i2')
    _template(db_session, DI_STAGES[0], 'Only step')
    feature = engine.create_feature(project, 'New thing')
    step_id_before = feature.steps[0].id

    engine.move_to_stage(feature, DI_STAGES[0])

    assert feature.status == DI_STAGES[0]
    # not reseeded - same single step, not a second copy
    assert [s.id for s in feature.steps] == [step_id_before]


def test_move_to_stage_refuses_an_invalid_stage(db_session):
    project = _project(db_session, 'i3')
    feature = engine.create_feature(project, 'New thing')

    with pytest.raises(ValueError):
        engine.move_to_stage(feature, 'not-a-real-stage')
    assert feature.status == DI_STAGES[0]


def test_move_to_stage_refuses_on_a_closed_feature(db_session):
    project = _project(db_session, 'i4')
    feature = engine.create_feature(project, 'New thing')
    engine.close_feature(feature)

    with pytest.raises(ValueError):
        engine.move_to_stage(feature, DI_STAGES[0])


def test_move_to_stage_resumes_existing_steps_on_revisit(db_session):
    project = _project(db_session, 'i5')
    _template(db_session, DI_STAGES[0], 'Researching step')
    feature = engine.create_feature(project, 'New thing')
    engine.tick_step(feature.steps[0], done=True)

    engine.move_to_stage(feature, DI_STAGES[1])  # leave researching
    # add a template that would seed differently if reseeded
    _template(db_session, DI_STAGES[0], 'Would-be second step')
    engine.move_to_stage(feature, DI_STAGES[0])  # come back

    researching_steps = [s for s in feature.steps if s.stage == DI_STAGES[0]]
    assert len(researching_steps) == 1
    assert researching_steps[0].title == 'Researching step'
    assert researching_steps[0].is_done is True  # exactly as left, not reset


def test_move_to_stage_seeds_fresh_steps_for_a_never_visited_stage(db_session):
    project = _project(db_session, 'i6')
    _template(db_session, DI_STAGES[2], 'Coding step')
    feature = engine.create_feature(project, 'New thing')

    engine.move_to_stage(feature, DI_STAGES[2])

    coding_steps = [s for s in feature.steps if s.stage == DI_STAGES[2]]
    assert [s.title for s in coding_steps] == ['Coding step']
    assert coding_steps[0].is_done is False


def test_delete_step_never_advances_the_feature(db_session):
    project = _project(db_session, 'j')
    _template(db_session, DI_STAGES[0], 'Keep me', sort_order=0)
    _template(db_session, DI_STAGES[0], 'Delete me', sort_order=1)
    feature = engine.create_feature(project, 'New thing')
    keep, remove = feature.steps
    engine.tick_step(keep, done=True)
    # `remove` is left unticked, then deleted - completing the stage

    engine.delete_step(remove)

    # no more auto-advance-on-completion - stage movement is always an
    # explicit move_to_stage() call now
    assert feature.status == DI_STAGES[0]
    assert [s.title for s in feature.steps] == ['Keep me']


def test_deleting_the_last_step_leaves_an_empty_stage(db_session):
    project = _project(db_session, 'l')
    _template(db_session, DI_STAGES[0], 'Only step')
    feature = engine.create_feature(project, 'New thing')
    only_step = feature.steps[0]

    engine.delete_step(only_step)

    assert feature.status == DI_STAGES[0]
    assert feature.steps == []


def test_add_step_appends_after_existing_steps_in_the_current_stage(db_session):
    project = _project(db_session, 'n')
    _template(db_session, DI_STAGES[0], 'First')
    feature = engine.create_feature(project, 'New thing')

    new_step = engine.add_step(feature, 'Second')

    assert new_step.sort_order == 1
    assert new_step.stage == DI_STAGES[0]
    assert [s.title for s in feature.steps] == ['First', 'Second']


def test_add_step_refuses_on_a_closed_feature(db_session):
    project = _project(db_session, 'o')
    feature = engine.create_feature(project, 'New thing')
    engine.close_feature(feature)

    with pytest.raises(ValueError):
        engine.add_step(feature, 'Too late')


def test_close_feature_sets_status_and_timestamp(db_session):
    project = _project(db_session, 'p')
    feature = engine.create_feature(project, 'New thing')

    engine.close_feature(feature)

    assert feature.status == 'closed'
    assert feature.closed_at is not None


def test_second_feature_in_a_project_sorts_after_the_first(db_session):
    project = _project(db_session, 'q')
    first = engine.create_feature(project, 'First')
    second = engine.create_feature(project, 'Second')

    assert first.sort_order == 0
    assert second.sort_order == 1


def test_add_step_stores_optional_details_alongside_the_title(db_session):
    project = _project(db_session, 'r')
    feature = engine.create_feature(project, 'New thing')

    step = engine.add_step(feature, 'Data model', details='Design the wiki_pages full-text index.')

    assert step.title == 'Data model'
    assert step.details == 'Design the wiki_pages full-text index.'


def test_add_step_details_defaults_to_none(db_session):
    project = _project(db_session, 's')
    feature = engine.create_feature(project, 'New thing')

    step = engine.add_step(feature, 'Just a title')

    assert step.details is None


def test_seeding_from_a_template_copies_both_title_and_details(db_session):
    project = _project(db_session, 't')
    template = DiStepTemplate(
        stage=DI_STAGES[0], title='Write the brief',
        details='One page, sent to the client for sign-off.', sort_order=0,
    )
    db_session.add(template)
    db_session.flush()

    feature = engine.create_feature(project, 'New thing')

    assert feature.steps[0].title == 'Write the brief'
    assert feature.steps[0].details == 'One page, sent to the client for sign-off.'
