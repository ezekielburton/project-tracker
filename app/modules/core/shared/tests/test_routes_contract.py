"""
Route contract: the live url_map must match the commited baseline
(refactor/route_baseline.txt). This is the refactor's automated 
safety net - any step that drops, renames or unexpectedly adds a
route fails here.

"""

import os

def _baseline_path(app):
    # app.route_path is .../project-tracker/app; the baseline lives one level up.
    return os.path.join(os.path.dirname(app.root_path), 'refactor', 'route_baseline.txt')

def _current_routes(app):
    routes = set()
    for r in app.url_map.iter_rules():
        methods = ','.join(sorted(m for m in r.methods if m not in {'HEAD', 'OPTIONS'}))
        routes.add(f'{r.rule}\t{methods}\t{r.endpoint}')
    return routes

def test_route_contract_matches_baseline(app):
    with open(_baseline_path(app), encoding='utf-8') as f:
        baseline = {line.rstrip('\n') for line in f if line.strip()}
    current = _current_routes(app)
    missing = baseline - current
    added = current - baseline
    assert not missing, f"Routes in baseline but gone now: {sorted(missing)}"
    assert not added, f"Routes present now but not in baseline: {sorted(added)}"
    print(f"route contract OK \u2014 {len(current)} routes match baseline")
