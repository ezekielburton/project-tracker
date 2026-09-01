"""Cross-team assignment rule: 3D people can also be assigned to 2D and
Technical work (they do the companion 2D and technical drawings for their 3D)."""
from app.modules.projects.lib.teams import assignable_teams_for


def test_2d_pool_includes_3d():
    assert set(assignable_teams_for('2D')) == {'2D', '3D'}


def test_technical_pool_includes_3d():
    assert set(assignable_teams_for('Technical')) == {'Technical', '3D'}


def test_3d_stays_3d_only():
    assert assignable_teams_for('3D') == ['3D']


def test_case_insensitive_input():
    assert set(assignable_teams_for('2d')) == {'2D', '3D'}
    assert set(assignable_teams_for('technical')) == {'Technical', '3D'}


def test_unknown_team_unchanged():
    assert assignable_teams_for('Marketing') == ['Marketing']
