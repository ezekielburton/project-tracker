"""Shared fixtures for the Client Servicing tests."""
import pytest

from app.modules.core.shared.lib.capabilities import ROLE_CAPABILITIES


@pytest.fixture
def owner_without_finance(monkeypatch):
    """Every CS role sees finance today; take it from project owners so the
    gate that hides invoicing figures stays tested."""
    monkeypatch.setitem(ROLE_CAPABILITIES, 'project_owner',
                        ROLE_CAPABILITIES['project_owner'] - {'view_finance'})
