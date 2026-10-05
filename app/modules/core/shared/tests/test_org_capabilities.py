"""Each role key converts to the access it must keep, with one deliberate change:
Project Owners also hold Client Servicing's capabilities."""
import pytest

from app.modules.core.shared.lib.capabilities import ALL_CAPABILITIES, can
from app.modules.core.shared.lib.org import LEGACY_ROLES
from app.modules.core.shared.models import User


_READ_ONLY = {'view_workspace', 'view_cs', 'view_finance', 'view_all_projects', 'edit_client_directory'}
_DESIGN = {'view_workspace', 'manage_drafts', 'claim_work', 'raise_flags',
           'complete_preproduction', 'start_projects'}
_CS = {'view_workspace', 'view_cs', 'view_finance', 'edit_finance', 'close_projects',
       'view_all_projects', 'create_projects', 'review_submissions', 'edit_client_directory',
       'raise_flags', 'manage_reference_data', 'manage_project_files'}

# Each role key's access, written out in full rather than read from the map, so
# a change to the department or seniority sets cannot move both sides at once.
ROLE_ACCESS = {
    'admin': set(ALL_CAPABILITIES),
    'management': {
        'view_workspace', 'view_cs', 'view_finance', 'edit_invoicing_thresholds',
        'close_projects', 'view_all_projects', 'manage_projects', 'create_projects',
        'start_projects', 'review_submissions', 'edit_client_directory', 'raise_flags',
        'manage_flags', 'log_site_visits', 'manage_reference_data', 'complete_preproduction',
        'manage_project_files', 'switch_dashboard_scope', 'view_team_snapshot',
        'view_di_performance', 'view_all_di', 'view_hse', 'write_friction_log',
        'view_time_reports',
    },
    'cs': _CS,
    'project_owner': _CS | {'log_site_visits', 'claim_ownership'},
    'finance': {'view_workspace', 'view_cs', 'view_finance', 'edit_finance'},
    'designer': _DESIGN,
    'team_lead': _DESIGN,
    'digital_innovation': {'view_workspace', 'view_all_di'},
    'hse': {'view_hse', 'manage_hse'},
    'hr': _READ_ONLY | {'view_hse'},
    'production': _READ_ONLY - {'view_cs'},
    'logistics': _READ_ONLY - {'view_cs'},
}


def _held(user):
    return {cap for cap in ALL_CAPABILITIES if can(cap, user)}


def test_every_role_key_is_checked():
    assert set(ROLE_ACCESS) == set(LEGACY_ROLES)


@pytest.mark.parametrize('role', sorted(ROLE_ACCESS))
def test_role_key_converts_with_its_access(role):
    held = _held(User(role=role))
    assert held == ROLE_ACCESS[role], (
        f'{role}: gained {sorted(held - ROLE_ACCESS[role])}, '
        f'lost {sorted(ROLE_ACCESS[role] - held)}'
    )


def test_management_inside_a_department_holds_both_sets():
    user = User(department='design', seniority='management', is_admin=False)
    assert _held(user) == ROLE_ACCESS['management'] | _DESIGN


@pytest.mark.parametrize('seniority', ['manager', 'head'])
def test_manager_and_head_add_nothing_yet(seniority):
    base = User(department='finance', seniority='none', is_admin=False)
    senior = User(department='finance', seniority=seniority, is_admin=False)
    assert _held(senior) == _held(base)


def test_the_admin_switch_grants_everything_whatever_the_department():
    assert _held(User(department='hse', seniority='none', is_admin=True)) == set(ALL_CAPABILITIES)
