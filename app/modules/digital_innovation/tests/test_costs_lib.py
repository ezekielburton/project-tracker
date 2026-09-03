"""Coverage for the Digital Innovation cost ledger's business logic
(lib/costs.py). No routes/HTTP here — exercises the rules directly
against the database, the same way test_step_engine.py covers brain A."""
import datetime

import pytest

from app.modules.digital_innovation.models import DiProject, DiSetting, DiCostEntry
from app.modules.digital_innovation.lib import costs
from app.modules.digital_innovation.lib import step_engine as engine


def _project(db_session, tag, client_charge=None):
    project = DiProject(name=f'Test DI Project {tag}', client_charge=client_charge)
    db_session.add(project)
    db_session.flush()
    return project


def _settings(db_session, rate=100.0, currency='AED'):
    settings = DiSetting(dev_hourly_rate=rate, currency=currency)
    db_session.add(settings)
    db_session.flush()
    return settings


def test_get_settings_creates_the_singleton_row_if_missing(db_session):
    settings = costs.get_settings()
    assert settings.id is not None
    assert settings.dev_hourly_rate == 0
    assert settings.currency == 'AED'


def test_get_settings_returns_the_existing_row(db_session):
    existing = _settings(db_session, rate=150.0)
    settings = costs.get_settings()
    assert settings.id == existing.id
    assert settings.dev_hourly_rate == 150.0


def test_add_cost_entry_dev_time_computes_amount_from_the_rate(db_session):
    _settings(db_session, rate=100.0)
    project = _project(db_session, 'a')
    feature = engine.create_feature(project, 'Homepage redesign')

    entry = costs.add_cost_entry(project, datetime.date(2026, 8, 1), 'dev_time', hours=3, feature=feature)

    assert entry.amount == 300.0
    assert entry.hours == 3
    assert entry.di_feature_id == feature.id
    assert entry.di_project_id == project.id


def test_add_cost_entry_dev_time_requires_hours(db_session):
    _settings(db_session, rate=100.0)
    project = _project(db_session, 'b')
    feature = engine.create_feature(project, 'New thing')

    with pytest.raises(ValueError):
        costs.add_cost_entry(project, datetime.date(2026, 8, 1), 'dev_time', feature=feature)


def test_add_cost_entry_dev_time_requires_a_feature(db_session):
    _settings(db_session, rate=100.0)
    project = _project(db_session, 'c')

    with pytest.raises(ValueError):
        costs.add_cost_entry(project, datetime.date(2026, 8, 1), 'dev_time', hours=2)


def test_add_cost_entry_claude_requires_a_positive_amount(db_session):
    project = _project(db_session, 'd')

    with pytest.raises(ValueError):
        costs.add_cost_entry(project, datetime.date(2026, 8, 1), 'claude', amount=0)


def test_add_cost_entry_claude_happy_path_ignores_hours_and_feature(db_session):
    project = _project(db_session, 'e')
    feature = engine.create_feature(project, 'New thing')

    entry = costs.add_cost_entry(
        project, datetime.date(2026, 8, 1), 'claude',
        amount=42.5, hours=99, feature=feature,
    )

    assert entry.amount == 42.5
    assert entry.hours is None
    assert entry.di_feature_id is None


def test_add_cost_entry_rejects_an_unknown_type(db_session):
    project = _project(db_session, 'f')

    with pytest.raises(ValueError):
        costs.add_cost_entry(project, datetime.date(2026, 8, 1), 'not_a_real_type', amount=10)


def test_add_cost_entry_requires_a_date(db_session):
    project = _project(db_session, 'g')

    with pytest.raises(ValueError):
        costs.add_cost_entry(project, None, 'claude', amount=10)


def test_delete_cost_entry_removes_it(db_session):
    project = _project(db_session, 'h')
    entry = costs.add_cost_entry(project, datetime.date(2026, 8, 1), 'hardware', amount=200)
    db_session.commit()
    entry_id = entry.id

    costs.delete_cost_entry(entry)
    db_session.commit()

    assert DiCostEntry.query.get(entry_id) is None


def test_cost_summary_totals_by_type_and_grand_total(db_session):
    _settings(db_session, rate=100.0)
    project = _project(db_session, 'i')
    feature = engine.create_feature(project, 'New thing')
    costs.add_cost_entry(project, datetime.date(2026, 8, 1), 'dev_time', hours=2, feature=feature)
    costs.add_cost_entry(project, datetime.date(2026, 8, 2), 'claude', amount=50)
    costs.add_cost_entry(project, datetime.date(2026, 8, 3), 'claude', amount=25)
    db_session.commit()

    summary = costs.cost_summary(project)

    assert summary['by_type']['dev_time']['total'] == 200.0
    assert summary['by_type']['dev_time']['hours'] == 2
    assert summary['by_type']['claude']['total'] == 75.0
    assert summary['by_type']['claude']['count'] == 2
    assert summary['total_cost'] == 275.0
    # Newest first.
    assert [e.date for e in summary['entries']] == [
        datetime.date(2026, 8, 3), datetime.date(2026, 8, 2), datetime.date(2026, 8, 1),
    ]


def test_cost_summary_projected_profit_is_none_without_a_client_charge(db_session):
    project = _project(db_session, 'j', client_charge=None)
    summary = costs.cost_summary(project)
    assert summary['client_charge'] is None
    assert summary['projected_profit'] is None


def test_cost_summary_projected_profit_is_charge_minus_cost(db_session):
    project = _project(db_session, 'k', client_charge=1000.0)
    costs.add_cost_entry(project, datetime.date(2026, 8, 1), 'hardware', amount=300)
    db_session.commit()

    summary = costs.cost_summary(project)
    assert summary['client_charge'] == 1000.0
    assert summary['projected_profit'] == 700.0
