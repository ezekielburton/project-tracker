"""Coverage for lib/feature_detail.py's context assembly - the data behind
the read-only feature detail modal, including the move-to-stage
picker's options (stage_options) added alongside the free-movement model
(step_engine.move_to_stage) - next_stage_label doesn't exist any more,
since movement is no longer "the next stage" but "any stage"."""
from app.modules.digital_innovation.models import DiProject, DiCostEntry, DI_STAGES
from app.modules.digital_innovation.lib import step_engine as engine
from app.modules.digital_innovation.lib.feature_detail import build_feature_detail_context


def _project(db_session, tag, track='internal'):
    project = DiProject(name=f'Test DI Project {tag}', track=track)
    db_session.add(project)
    db_session.flush()
    return project


def test_stages_before_current_are_done_current_is_current_rest_are_future(db_session):
    project = _project(db_session, 'a')
    feature = engine.create_feature(project, 'New thing')
    feature.status = DI_STAGES[2]  # coding

    ctx = build_feature_detail_context(feature)

    states = {row['stage']: row['state'] for row in ctx['stage_rows']}
    assert states[DI_STAGES[0]] == 'done'
    assert states[DI_STAGES[1]] == 'done'
    assert states[DI_STAGES[2]] == 'current'
    assert states[DI_STAGES[3]] == 'future'
    assert states[DI_STAGES[-1]] == 'future'
    assert ctx['current_stage_label'] is not None


def test_step_rows_excludes_steps_from_earlier_stages(db_session):
    project = _project(db_session, 'b')
    feature = engine.create_feature(project, 'New thing')
    engine.add_step(feature, 'From researching')
    feature.status = DI_STAGES[1]
    engine.add_step(feature, 'From planning')

    ctx = build_feature_detail_context(feature)

    labels = [row['step'].title for row in ctx['step_rows']]
    assert labels == ['From planning']
    assert ctx['steps_total_count'] == 1


def test_step_row_states_first_unticked_is_active_rest_are_pending(db_session):
    project = _project(db_session, 'h')
    feature = engine.create_feature(project, 'New thing')
    done_step = engine.add_step(feature, 'Done already')
    next_step = engine.add_step(feature, 'Up next')
    later_step = engine.add_step(feature, 'After that')
    engine.tick_step(done_step, done=True)

    ctx = build_feature_detail_context(feature)

    states = {row['step'].id: row['state'] for row in ctx['step_rows']}
    assert states[done_step.id] == 'done'
    assert states[next_step.id] == 'active'
    assert states[later_step.id] == 'pending'


def test_step_row_states_with_nothing_ticked_yet(db_session):
    project = _project(db_session, 'i')
    feature = engine.create_feature(project, 'New thing')
    first_step = engine.add_step(feature, 'First')
    second_step = engine.add_step(feature, 'Second')

    ctx = build_feature_detail_context(feature)

    states = {row['step'].id: row['state'] for row in ctx['step_rows']}
    assert states[first_step.id] == 'active'
    assert states[second_step.id] == 'pending'


def test_steps_done_count_matches_ticked_steps(db_session):
    project = _project(db_session, 'c')
    feature = engine.create_feature(project, 'New thing')
    a = engine.add_step(feature, 'One')
    engine.add_step(feature, 'Two')
    engine.tick_step(a, done=True)

    ctx = build_feature_detail_context(feature)

    assert ctx['steps_done_count'] == 1
    assert ctx['steps_total_count'] == 2


def test_stage_options_lists_every_stage_regardless_of_current_stage(db_session):
    project = _project(db_session, 'd')
    feature = engine.create_feature(project, 'New thing')
    feature.status = DI_STAGES[0]

    ctx = build_feature_detail_context(feature)

    assert [opt['stage'] for opt in ctx['stage_options']] == list(DI_STAGES)
    assert ctx['is_last_stage'] is False


def test_stage_options_are_offered_even_on_the_last_stage(db_session):
    # Free movement (step_engine.move_to_stage) has no completion gate, so
    # the picker still offers every stage - including backward moves -
    # even once the feature is on the last one. is_last_stage still
    # flags this (it drives the Implementation "add step or close" banner
    # in the template), but it no longer implies "no more options".
    project = _project(db_session, 'e')
    feature = engine.create_feature(project, 'New thing')
    feature.status = DI_STAGES[-1]

    ctx = build_feature_detail_context(feature)

    assert ctx['is_last_stage'] is True
    assert [opt['stage'] for opt in ctx['stage_options']] == list(DI_STAGES)


def test_stage_options_use_client_review_label_on_an_external_track_project(db_session):
    project = _project(db_session, 'd2', track='external')
    feature = engine.create_feature(project, 'New thing')

    ctx = build_feature_detail_context(feature)

    labels = {opt['stage']: opt['label'] for opt in ctx['stage_options']}
    assert labels['management_review'] == 'Client Review'


def test_closed_feature_shows_every_stage_done_and_no_current_steps(db_session):
    project = _project(db_session, 'f')
    feature = engine.create_feature(project, 'New thing')
    feature.status = DI_STAGES[-1]
    engine.close_feature(feature)

    ctx = build_feature_detail_context(feature)

    assert ctx['is_closed'] is True
    assert all(row['state'] == 'done' for row in ctx['stage_rows'])
    assert ctx['step_rows'] == []
    assert ctx['current_stage_label'] is None
    # Nowhere left to move a closed feature to.
    assert ctx['stage_options'] == []


def test_logged_hours_sums_dev_time_cost_entries_for_this_feature(db_session):
    project = _project(db_session, 'g')
    feature = engine.create_feature(project, 'New thing')
    db_session.add(DiCostEntry(
        di_project_id=project.id, di_feature_id=feature.id,
        date='2026-08-01', type='dev_time', amount=100, hours=4,
    ))
    db_session.add(DiCostEntry(
        di_project_id=project.id, di_feature_id=feature.id,
        date='2026-08-02', type='dev_time', amount=50, hours=2,
    ))
    # A non-dev-time entry on the same feature shouldn't count as hours.
    db_session.add(DiCostEntry(
        di_project_id=project.id, di_feature_id=feature.id,
        date='2026-08-03', type='claude', amount=20,
    ))
    db_session.flush()

    ctx = build_feature_detail_context(feature)

    assert ctx['logged_hours'] == 6
