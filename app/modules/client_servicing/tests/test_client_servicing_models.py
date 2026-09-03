"""Model-level coverage for the Client Servicing module."""
from decimal import Decimal

import pytest

from app.modules.core.shared.models import User, Project
from app.modules.client_servicing.models import ClientServicing, ClientServicingScope


def _project(db_session, tag):
    user = User(name='CS Lead', email=f'cs-model-test-{tag}@example.com', role='cs')
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    project = Project(name=f'Test Project {tag}', cs_lead_id=user.id, created_by_id=user.id)
    db_session.add(project)
    db_session.flush()
    return project


def test_client_servicing_ties_to_one_project(db_session):
    project = _project(db_session, 'a')
    cs = ClientServicing(project_id=project.id, lpo='LPO-1')
    db_session.add(cs)
    db_session.flush()

    assert cs.id is not None
    assert project.client_servicing is cs


def test_project_id_must_be_unique(db_session):
    project = _project(db_session, 'b')
    db_session.add(ClientServicing(project_id=project.id))
    db_session.flush()

    db_session.add(ClientServicing(project_id=project.id))
    with pytest.raises(Exception):
        db_session.flush()


def test_scope_relationship(db_session):
    project = _project(db_session, 'c')
    scope = ClientServicingScope(name='Retail Fit-out')
    db_session.add(scope)
    db_session.flush()

    cs = ClientServicing(project_id=project.id, scope_id=scope.id)
    db_session.add(cs)
    db_session.flush()

    assert cs.scope.name == 'Retail Fit-out'


def test_margin_percent_computes_from_costs(db_session):
    project = _project(db_session, 'd')
    cs = ClientServicing(
        project_id=project.id,
        cost_to_client=Decimal('100.00'),
        inward_cost=Decimal('60.00'),
    )
    assert cs.margin_percent == 40.0


def test_margin_percent_none_when_costs_missing_or_zero(db_session):
    project = _project(db_session, 'e')

    cs_no_costs = ClientServicing(project_id=project.id)
    assert cs_no_costs.margin_percent is None

    cs_only_cost = ClientServicing(project_id=project.id, cost_to_client=Decimal('50.00'))
    assert cs_only_cost.margin_percent is None

    cs_zero_cost = ClientServicing(
        project_id=project.id, cost_to_client=Decimal('0.00'), inward_cost=Decimal('0.00'),
    )
    assert cs_zero_cost.margin_percent is None


def test_days_pending_from_invoice_date_when_invoiced(db_session):
    from datetime import date, timedelta
    project = _project(db_session, 'f')
    cs = ClientServicing(
        project_id=project.id,
        removal_date=date.today() - timedelta(days=30),
        invoice_date=date.today() - timedelta(days=4),
    )
    assert cs.days_pending == 4


def test_days_pending_from_removal_date_when_not_invoiced(db_session):
    from datetime import date, timedelta
    project = _project(db_session, 'g')
    cs = ClientServicing(project_id=project.id, removal_date=date.today() - timedelta(days=7))
    assert cs.days_pending == 7


def test_days_pending_none_when_no_dates(db_session):
    project = _project(db_session, 'h')
    cs = ClientServicing(project_id=project.id)
    assert cs.days_pending is None
