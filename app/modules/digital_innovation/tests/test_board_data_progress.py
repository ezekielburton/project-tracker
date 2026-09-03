"""Coverage for board_data.py's _feature_progress — specifically the
current_step_number / progress_pct fields the board card's new progress
bar reads (the bar's width and the "Step N of total" text share this one
number so they can never disagree)."""
from app.modules.digital_innovation.models import DiProject
from app.modules.digital_innovation.lib import step_engine as engine
from app.modules.digital_innovation.lib.board_data import _feature_progress, build_board_context


def _project(db_session, tag):
    project = DiProject(name=f'Test DI Project {tag}')
    db_session.add(project)
    db_session.flush()
    return project


def test_current_step_number_is_done_plus_one_while_a_step_is_open(db_session):
    project = _project(db_session, 'a')
    feature = engine.create_feature(project, 'New thing')
    done_step = engine.add_step(feature, 'First')
    engine.add_step(feature, 'Second')
    engine.add_step(feature, 'Third')
    engine.tick_step(done_step, done=True)

    done, total, active_label, current_step_number, progress_pct = _feature_progress(feature)

    assert done == 1
    assert total == 3
    assert current_step_number == 2
    assert progress_pct == round(100 * 2 / 3)


def test_current_step_number_equals_total_once_every_step_is_done(db_session):
    project = _project(db_session, 'b')
    feature = engine.create_feature(project, 'New thing')
    a = engine.add_step(feature, 'First')
    b = engine.add_step(feature, 'Second')
    engine.tick_step(a, done=True)
    engine.tick_step(b, done=True)

    done, total, active_label, current_step_number, progress_pct = _feature_progress(feature)

    assert current_step_number == total == 2
    assert progress_pct == 100
    assert active_label is None


def test_progress_pct_is_zero_for_an_unconfigured_stage(db_session):
    project = _project(db_session, 'c')
    feature = engine.create_feature(project, 'New thing')
    # Wipe out whatever the template seeded, to exercise the empty case.
    for step in list(feature.steps):
        feature.steps.remove(step)

    done, total, active_label, current_step_number, progress_pct = _feature_progress(feature)

    assert total == 0
    assert current_step_number == 0
    assert progress_pct == 0


def test_build_board_context_exposes_current_step_number_and_progress_pct(db_session):
    project = _project(db_session, 'd')
    feature = engine.create_feature(project, 'New thing')
    step = engine.add_step(feature, 'Only step')
    engine.tick_step(step, done=True)

    ctx = build_board_context(project)
    entry = next(e for e in ctx['columns'][feature.status] if e['feature'].id == feature.id)

    assert entry['current_step_number'] == entry['total']
    assert entry['progress_pct'] == 100
