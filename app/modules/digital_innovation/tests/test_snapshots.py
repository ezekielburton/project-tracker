"""Coverage for the Digital Innovation Performance rollup + the
month/quarter freeze (lib/snapshots.py, brain C). No routes/HTTP here —
exercises get_period_rollup() directly against the database, same split
test_costs_lib.py/test_periods.py use for their pieces of this module."""
import datetime

from app.modules.digital_innovation.models import DiProject, DiSetting, DiPeriodSnapshot
from app.modules.digital_innovation.lib import costs, periods, snapshots
from app.modules.digital_innovation.lib import step_engine as engine


def _project(db_session, tag, created_at=None, closed_at=None, lifecycle='active', client_charge=None):
    project = DiProject(
        name=f'Test DI Project {tag}',
        lifecycle=lifecycle,
        created_at=created_at or datetime.datetime(2026, 1, 1),
        closed_at=closed_at,
        client_charge=client_charge,
    )
    db_session.add(project)
    db_session.flush()
    return project


def _settings(db_session, rate=100.0, currency='AED'):
    settings = DiSetting(dev_hourly_rate=rate, currency=currency)
    db_session.add(settings)
    db_session.flush()
    return settings


def test_get_period_rollup_week_totals_cost_and_dev_hours(db_session):
    _settings(db_session, rate=100.0)
    project = _project(db_session, 'a', client_charge=1000.0)
    feature = engine.create_feature(project, 'Homepage redesign')
    costs.add_cost_entry(project, datetime.date(2026, 8, 18), 'dev_time', hours=2, feature=feature)
    costs.add_cost_entry(project, datetime.date(2026, 8, 19), 'claude', amount=50)
    # Outside the week — must not count toward this rollup's total_cost.
    costs.add_cost_entry(project, datetime.date(2026, 8, 25), 'claude', amount=999)
    db_session.commit()

    rollup = snapshots.get_period_rollup('week', '2026-W34')

    assert rollup['total_cost'] == 250.0  # 200 (dev_time) + 50 (claude); not the 999 outside the week
    assert len(rollup['projects']) == 1
    row = rollup['projects'][0]
    assert row['dev_hours'] == 2
    assert row['total_cost'] == 999 + 250.0  # lifetime total_cost — unaffected by the period window
    assert row['client_charge'] == 1000.0


def test_get_period_rollup_splits_closed_vs_projected_profit(db_session):
    closed = _project(
        db_session, 'closed', client_charge=1000.0,
        created_at=datetime.datetime(2026, 1, 1),
        closed_at=datetime.datetime(2026, 8, 19), lifecycle='closed',
    )
    costs.add_cost_entry(closed, datetime.date(2026, 8, 1), 'hardware', amount=200)

    active = _project(db_session, 'active', client_charge=500.0, created_at=datetime.datetime(2026, 1, 1))
    costs.add_cost_entry(active, datetime.date(2026, 8, 1), 'hardware', amount=100)
    db_session.commit()

    rollup = snapshots.get_period_rollup('week', '2026-W34')

    assert rollup['closed_profit'] == 800.0  # 1000 - 200
    assert rollup['projected_profit'] == 400.0  # 500 - 100


def test_get_period_rollup_excludes_a_project_with_no_client_charge_from_both_profit_totals(db_session):
    project = _project(db_session, 'g', client_charge=None, created_at=datetime.datetime(2026, 1, 1))
    costs.add_cost_entry(project, datetime.date(2026, 8, 1), 'hardware', amount=50)
    db_session.commit()

    rollup = snapshots.get_period_rollup('week', '2026-W34')

    assert rollup['closed_profit'] == 0.0
    assert rollup['projected_profit'] == 0.0


def test_get_period_rollup_passes_through_the_project_client_label(db_session):
    project = _project(db_session, 'm', created_at=datetime.datetime(2026, 1, 1))
    project.client_label = 'Landing rebuild'
    db_session.commit()

    rollup = snapshots.get_period_rollup('week', '2026-W34')

    assert rollup['projects'][0]['client_label'] == 'Landing rebuild'


def test_get_period_rollup_client_label_is_none_when_unset(db_session):
    _project(db_session, 'n', created_at=datetime.datetime(2026, 1, 1))
    db_session.commit()

    rollup = snapshots.get_period_rollup('week', '2026-W34')

    assert rollup['projects'][0]['client_label'] is None


def test_get_period_rollup_cost_type_labels_only_lists_types_present_in_the_period(db_session):
    project = _project(db_session, 'o', created_at=datetime.datetime(2026, 1, 1))
    costs.add_cost_entry(project, datetime.date(2026, 8, 18), 'claude', amount=50)
    # Outside the week — its type must not show up in the caption either.
    costs.add_cost_entry(project, datetime.date(2026, 8, 25), 'licensing', amount=20)
    db_session.commit()

    rollup = snapshots.get_period_rollup('week', '2026-W34')

    assert rollup['cost_type_labels'] == ['Claude']


def test_get_period_rollup_cost_type_labels_follow_di_cost_types_order(db_session):
    project = _project(db_session, 'p', created_at=datetime.datetime(2026, 1, 1))
    feature = engine.create_feature(project, 'Some feature')
    # Added out of DI_COST_TYPES order (licensing, then dev_time) — the
    # caption should still read in the canonical dev/Claude/hardware/
    # licensing order, not insertion order.
    costs.add_cost_entry(project, datetime.date(2026, 8, 18), 'licensing', amount=20)
    costs.add_cost_entry(project, datetime.date(2026, 8, 19), 'dev_time', hours=1, feature=feature)
    db_session.commit()

    rollup = snapshots.get_period_rollup('week', '2026-W34')

    assert rollup['cost_type_labels'] == ['dev', 'licensing']


def test_get_period_rollup_cost_type_labels_empty_when_no_costs_in_the_period(db_session):
    _project(db_session, 'q', created_at=datetime.datetime(2026, 1, 1))
    db_session.commit()

    rollup = snapshots.get_period_rollup('week', '2026-W34')

    assert rollup['cost_type_labels'] == []


def test_get_period_rollup_closed_project_count_counts_closed_projects_with_profit(db_session):
    closed_a = _project(
        db_session, 'closed-a', client_charge=1000.0,
        created_at=datetime.datetime(2026, 1, 1),
        closed_at=datetime.datetime(2026, 8, 19), lifecycle='closed',
    )
    costs.add_cost_entry(closed_a, datetime.date(2026, 8, 1), 'hardware', amount=100)
    closed_b = _project(
        db_session, 'closed-b', client_charge=500.0,
        created_at=datetime.datetime(2026, 1, 1),
        closed_at=datetime.datetime(2026, 8, 20), lifecycle='closed',
    )
    costs.add_cost_entry(closed_b, datetime.date(2026, 8, 1), 'hardware', amount=50)
    # Still active — must not count even though it's in the period.
    _project(db_session, 'active-c', client_charge=200.0, created_at=datetime.datetime(2026, 1, 1))
    db_session.commit()

    rollup = snapshots.get_period_rollup('week', '2026-W34')

    assert rollup['closed_project_count'] == 2


def test_get_period_rollup_closed_project_count_excludes_a_closed_project_with_no_client_charge(db_session):
    closed = _project(
        db_session, 'closed-d', client_charge=None,
        created_at=datetime.datetime(2026, 1, 1),
        closed_at=datetime.datetime(2026, 8, 19), lifecycle='closed',
    )
    costs.add_cost_entry(closed, datetime.date(2026, 8, 1), 'hardware', amount=100)
    db_session.commit()

    rollup = snapshots.get_period_rollup('week', '2026-W34')

    assert rollup['closed_project_count'] == 0


def test_get_period_rollup_only_lists_active_features_when_expanded(db_session):
    project = _project(db_session, 'h', created_at=datetime.datetime(2026, 1, 1))
    engine.create_feature(project, 'Still going')
    closed_feature = engine.create_feature(project, 'All done')
    closed_feature.status = 'closed'
    db_session.commit()

    rollup = snapshots.get_period_rollup('week', '2026-W34')

    row = rollup['projects'][0]
    assert row['active_feature_count'] == 1
    assert row['closed_feature_count'] == 1
    assert [f['name'] for f in row['features']] == ['Still going']
    assert row['features'][0]['status'] == 'researching'  # DI_STAGES[0], create_feature()'s starting stage


def test_get_period_rollup_current_month_is_never_snapshotted(db_session):
    # The month containing "today" has, by definition, not ended yet —
    # computed live every call, exactly like a week.
    current_month = periods.current_period_key('month')
    start, _ = periods.period_bounds('month', current_month)
    project = _project(db_session, 'i', created_at=datetime.datetime.combine(start, datetime.time()))
    costs.add_cost_entry(project, start, 'hardware', amount=100)
    db_session.commit()

    snapshots.get_period_rollup('month', current_month)

    assert DiPeriodSnapshot.query.filter_by(period_type='month', period_key=current_month).first() is None


def test_get_period_rollup_freezes_an_ended_month_on_first_view(db_session):
    project = _project(db_session, 'j', created_at=datetime.datetime(2020, 1, 1))
    costs.add_cost_entry(project, datetime.date(2020, 1, 15), 'hardware', amount=100)
    db_session.commit()

    rollup = snapshots.get_period_rollup('month', '2020-01')

    snapshot = DiPeriodSnapshot.query.filter_by(period_type='month', period_key='2020-01').first()
    assert snapshot is not None
    assert snapshot.snapshot_data['total_cost'] == rollup['total_cost'] == 100.0


def test_get_period_rollup_reads_the_frozen_snapshot_instead_of_recomputing(db_session):
    project = _project(db_session, 'k', created_at=datetime.datetime(2020, 2, 1))
    costs.add_cost_entry(project, datetime.date(2020, 2, 15), 'hardware', amount=100)
    db_session.commit()

    first = snapshots.get_period_rollup('month', '2020-02')
    assert first['total_cost'] == 100.0

    # A cost entry added AFTER the freeze must not change what's already frozen.
    costs.add_cost_entry(project, datetime.date(2020, 2, 20), 'hardware', amount=5000)
    db_session.commit()

    second = snapshots.get_period_rollup('month', '2020-02')
    assert second['total_cost'] == 100.0  # unchanged — read from the frozen snapshot
    assert DiPeriodSnapshot.query.filter_by(period_type='month', period_key='2020-02').count() == 1


def test_get_period_rollup_quarter_freezes_the_same_way(db_session):
    project = _project(db_session, 'l', created_at=datetime.datetime(2020, 3, 1))
    costs.add_cost_entry(project, datetime.date(2020, 3, 1), 'hardware', amount=300)
    db_session.commit()

    snapshots.get_period_rollup('quarter', '2020-Q1')

    assert DiPeriodSnapshot.query.filter_by(period_type='quarter', period_key='2020-Q1').first() is not None
