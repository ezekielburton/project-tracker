def assignable_teams_for(team):
    """Teams whose members may be assigned to a deliverable/stream on `team`.
    3D designers routinely do the 2D companion work for their own 3D jobs, so
    the 2D pool also includes 3D people. Every other team stays its own."""
    if (team or '').strip().lower() == '2d':
        return ['2D', '3D']
    return [team]
