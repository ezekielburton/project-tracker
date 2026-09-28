def assignable_teams_for(team):
    """Teams whose members may be assigned to work on `team`. 2D and Technical
    also include 3D, since 3D designers do the 2D and drawings for their own jobs."""
    t = (team or '').strip().lower()
    if t == '2d':
        return ['2D', '3D']
    if t == 'technical':
        return ['Technical', '3D']
    return [team]
