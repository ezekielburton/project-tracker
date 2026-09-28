"""Project list: the Team filter counts and Team grouping, including rows
with no team or a team outside TEAM_KEYS."""
from app.modules.projects.routes.project_list import _build_filter_counts, _group_rows


def _row(row_id, teams):
    """Minimal row with every field _filter_rows / _build_filter_counts read."""
    return {
        'id': row_id, 'name': f'Row {row_id}', 'client_id': None, 'cs_lead': None,
        'project_owner': None, 'designers': [], 'design_teams': teams,
        'design_type': None, 'brief_type': 'standard', 'blanket_status': 'Briefed',
        'status': 'briefed', 'urgency': 'normal',
    }


def test_team_counts_include_the_undefined_count(app):
    rows = [_row(1, ['2D']), _row(2, []), _row(3, [])]
    with app.test_request_context('/projects-new/'):
        counts = _build_filter_counts(rows)
    assert counts['team'][None] == 2
    assert counts['team']['2D'] == 1


def test_team_grouping_keeps_a_row_with_an_unknown_team():
    rows = [_row(1, ['2D']), _row(2, ['Legacy']), _row(3, [])]
    groups = {g['label']: [r['id'] for r in g['rows']] for g in _group_rows(rows, 'team')}
    assert groups == {'2D': [1], 'Undefined': [2, 3]}


def test_undefined_team_filter_matches_the_undefined_group(app):
    """A row whose only team is outside TEAM_KEYS counts and filters as Undefined."""
    from app.modules.projects.routes.project_list import _filter_rows
    rows = [_row(1, ['2D']), _row(2, ['Legacy']), _row(3, [])]
    with app.test_request_context('/projects-new/'):
        assert _build_filter_counts(rows)['team'][None] == 2
    with app.test_request_context('/projects-new/?team=undefined'):
        assert [r['id'] for r in _filter_rows(rows)] == [2, 3]
