"""Each role's sidebar shows only the links it uses. Hiding is tidy-up, not the
gate: the CS and HSE routes still 403 on their own."""
import pytest
from flask import url_for

from app.modules.core.shared.lib.org import DEPARTMENTS, LEGACY_ROLES
from app.modules.core.shared.lib.sidebar import HIDDEN_LINKS, show_link
from app.modules.core.shared.models import User
from app.modules.core.shared.testing import login_as


# The links that change per role.
CHECKED_LINKS = (
    'client-servicing', 'hse', 'digital-innovation',
    'google-slides', 'magnific', 'shutterstock',
    'color-directory', 'production-directory', 'birthday-calendar',
)

_UNBUILT = {'color-directory', 'production-directory', 'birthday-calendar'}
_STOCK = {'magnific', 'shutterstock'}
_DESIGN_SIDE = _UNBUILT | {'client-servicing', 'hse'}
_OPS_SIDE = _UNBUILT | _STOCK | {'google-slides', 'client-servicing', 'hse'}

# What each role must NOT see. Every other checked link must show.
# The HSE officer has its own test (hse/tests/test_hse_sidebar.py).
EXPECTED_HIDDEN = {
    'admin': set(),
    'management': _UNBUILT | _STOCK,
    'cs': _UNBUILT | _STOCK | {'hse'},
    'project_owner': _UNBUILT | _STOCK | {'hse'},
    'finance': _UNBUILT | _STOCK | {'hse', 'google-slides', 'digital-innovation'},
    'designer': _DESIGN_SIDE,
    'team_lead': _DESIGN_SIDE,
    'digital_innovation': _DESIGN_SIDE,
    'hr': _UNBUILT | _STOCK | {'google-slides'},
    'production': _OPS_SIDE,
    'logistics': _OPS_SIDE,
}


def test_every_role_is_covered():
    assert set(EXPECTED_HIDDEN) | {'hse'} == set(LEGACY_ROLES)


def test_hidden_links_are_keyed_by_real_departments():
    assert set(HIDDEN_LINKS) <= set(DEPARTMENTS)


def test_management_in_a_department_gets_the_management_sidebar():
    user = User(department='design', seniority='management', is_admin=False)
    assert show_link('magnific', user) is False
    assert show_link('google-slides', user) is True


@pytest.mark.parametrize('role', sorted(EXPECTED_HIDDEN))
def test_each_role_sees_only_its_links(app, client, db_session, role):
    user = User(name=f'Sidebar {role}', email=f'sidebar-links-{role}@example.com', role=role)
    user.set_password('password123')
    db_session.add(user)
    db_session.flush()
    login_as(client, app, user, 'password123')
    with app.test_request_context():
        url = url_for('wiki.index')

    html = client.get(url).get_data(as_text=True)
    for link in CHECKED_LINKS:
        marker = f'data-link="{link}"'
        if link in EXPECTED_HIDDEN[role]:
            assert marker not in html, f'{role} should not see {link}'
        else:
            assert marker in html, f'{role} should see {link}'
