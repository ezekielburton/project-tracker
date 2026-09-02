"""Coverage for lib/template_admin.py — the department-wide step template
CRUD/reordering behind the admin-only Edit Templates screen. No routes/
HTTP here, same split as test_step_engine.py vs test_features_routes.py."""
from app.modules.digital_innovation.models import DiStepTemplate, DI_STAGES
from app.modules.digital_innovation.lib import template_admin


def _template(db_session, stage, title, sort_order=0, details=None):
    template = DiStepTemplate(stage=stage, title=title, details=details, sort_order=sort_order)
    db_session.add(template)
    db_session.flush()
    return template


def test_templates_by_stage_groups_every_stage_and_orders_within_it(db_session):
    _template(db_session, DI_STAGES[0], 'Second', sort_order=1)
    _template(db_session, DI_STAGES[0], 'First', sort_order=0)
    _template(db_session, DI_STAGES[1], 'Only one', sort_order=0)

    by_stage = template_admin.templates_by_stage()

    assert [t.title for t in by_stage[DI_STAGES[0]]] == ['First', 'Second']
    assert [t.title for t in by_stage[DI_STAGES[1]]] == ['Only one']
    assert by_stage[DI_STAGES[2]] == []
    assert set(by_stage.keys()) == set(DI_STAGES)


def test_add_template_step_appends_after_existing_steps_in_the_stage(db_session):
    _template(db_session, DI_STAGES[0], 'First', sort_order=0)

    new_step = template_admin.add_template_step(DI_STAGES[0], 'Second', details='Some detail')

    assert new_step.sort_order == 1
    assert new_step.stage == DI_STAGES[0]
    assert new_step.details == 'Some detail'


def test_add_template_step_details_defaults_to_none(db_session):
    new_step = template_admin.add_template_step(DI_STAGES[0], 'Just a title')
    assert new_step.details is None


def test_edit_template_step_updates_title_and_details(db_session):
    template = _template(db_session, DI_STAGES[0], 'Old title', details='Old details')

    template_admin.edit_template_step(template, 'New title', details='New details')

    assert template.title == 'New title'
    assert template.details == 'New details'


def test_edit_template_step_can_clear_details(db_session):
    template = _template(db_session, DI_STAGES[0], 'Title', details='Had details')

    template_admin.edit_template_step(template, 'Title', details=None)

    assert template.details is None


def test_delete_template_step_removes_it(db_session):
    template = _template(db_session, DI_STAGES[0], 'Doomed')
    template_admin.delete_template_step(template)
    db_session.flush()

    assert DiStepTemplate.query.filter_by(stage=DI_STAGES[0], title='Doomed').first() is None


def test_move_up_swaps_with_the_previous_step(db_session):
    first = _template(db_session, DI_STAGES[0], 'First', sort_order=0)
    second = _template(db_session, DI_STAGES[0], 'Second', sort_order=1)

    template_admin.move_template_step(second, 'up')

    assert second.sort_order == 0
    assert first.sort_order == 1


def test_move_down_swaps_with_the_next_step(db_session):
    first = _template(db_session, DI_STAGES[0], 'First', sort_order=0)
    second = _template(db_session, DI_STAGES[0], 'Second', sort_order=1)

    template_admin.move_template_step(first, 'down')

    assert first.sort_order == 1
    assert second.sort_order == 0


def test_move_up_on_the_first_step_is_a_no_op(db_session):
    first = _template(db_session, DI_STAGES[0], 'First', sort_order=0)
    _template(db_session, DI_STAGES[0], 'Second', sort_order=1)

    template_admin.move_template_step(first, 'up')

    assert first.sort_order == 0


def test_move_down_on_the_last_step_is_a_no_op(db_session):
    _template(db_session, DI_STAGES[0], 'First', sort_order=0)
    second = _template(db_session, DI_STAGES[0], 'Second', sort_order=1)

    template_admin.move_template_step(second, 'down')

    assert second.sort_order == 1


def test_move_never_touches_a_different_stage(db_session):
    first = _template(db_session, DI_STAGES[0], 'Only step here', sort_order=0)
    other_stage_step = _template(db_session, DI_STAGES[1], 'Different stage', sort_order=0)

    template_admin.move_template_step(first, 'down')  # no-op, only step in its stage

    assert first.sort_order == 0
    assert other_stage_step.sort_order == 0
