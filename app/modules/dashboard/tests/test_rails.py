"""rail_for follows the "Who gets which rail" table in dashboards_frame.md, one
case per row, reading only the org fields."""
from types import SimpleNamespace

import pytest

from app.modules.dashboard.lib.rails import PAGES, RAILS, rail_for


def _person(department=None, seniority='none', is_admin=False):
    # No `role` attribute: rail_for must never need it.
    return SimpleNamespace(department=department, seniority=seniority, is_admin=is_admin)


@pytest.mark.parametrize('person, rail, landing', [
    (_person(is_admin=True), 'admin', 'overview'),
    (_person('design', 'head', is_admin=True), 'admin', 'overview'),
    (_person(None, 'management'), 'management', 'overview'),
    (_person('client_servicing', 'management'), 'management', 'overview'),
    (_person('design', 'head'), 'design_head', 'design_workload'),
    (_person('design', 'manager'), 'design_lead', 'overview'),
    (_person('design', 'none'), 'designer', 'overview'),
    (_person('client_servicing', 'head'), 'cs_head', 'needs_attention'),
    (_person('client_servicing', 'manager'), 'cs', 'overview'),
    (_person('client_servicing', 'none'), 'cs', 'overview'),
    (_person('project_owner', 'none'), 'project_owner', 'overview'),
    (_person('project_owner', 'head'), 'project_owner', 'overview'),
    (_person('finance'), 'basic', 'overview'),
    (_person('hr'), 'basic', 'overview'),
    (_person('production'), 'basic', 'overview'),
    (_person('logistics'), 'basic', 'overview'),
    (_person('digital_innovation'), 'basic', 'overview'),
    (_person('hse'), 'basic', 'overview'),
    (_person('finance', 'head'), 'basic', 'overview'),
    (_person(None, 'none'), 'basic', 'overview'),
], ids=lambda v: v if isinstance(v, str) else f'{v.department}-{v.seniority}-admin{v.is_admin}')
def test_each_row_of_the_table_gets_its_rail_and_landing(person, rail, landing):
    got = rail_for(person)
    assert (got.key, got.landing) == (rail, landing)


def test_nobody_gets_a_rail_from_nothing():
    assert rail_for(None).key == 'basic'


@pytest.mark.parametrize('key', sorted(RAILS))
def test_every_rail_ends_with_my_hub_and_lists_known_pages_once(key):
    pages = RAILS[key]
    assert pages[-1] == 'my_hub'
    assert set(pages) <= set(PAGES)
    assert len(pages) == len(set(pages))


def test_my_hub_has_no_route():
    assert PAGES['my_hub'].endpoint is None
