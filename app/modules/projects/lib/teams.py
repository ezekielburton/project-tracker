def assignable_teams_for(team):
    """Teams whose members may be assigned to a deliverable/stream/lead on `team`.
    3D designers routinely do the 2D companion work AND the technical drawings
    for their own 3D jobs, so the 2D and Technical pools also include 3D people.
    Every other team stays its own."""
    t = (team or '').strip().lower()
    if t == '2d':
        return ['2D', '3D']
    if t == 'technical':
        return ['Technical', '3D']
    return [team]
