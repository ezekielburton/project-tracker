"""
The live url_map must match the committed refactor/route_baseline.txt; a
dropped, renamed or unexpected route fails. Reads through regen_route_baseline,
the script that writes the file. Regenerate when routes change on purpose:
  python -m app.modules.core.shared.tests.regen_route_baseline
"""

from app.modules.core.shared.tests.regen_route_baseline import (
    baseline_path as _baseline_path,
    current_routes as _current_routes,
)


def test_route_contract_matches_baseline(app):
    with open(_baseline_path(app), encoding='utf-8') as f:
        baseline = {line.rstrip('\n') for line in f if line.strip()}
    current = _current_routes(app)
    missing = baseline - current
    added = current - baseline
    assert not missing, f"Routes in baseline but gone now: {sorted(missing)}"
    assert not added, f"Routes present now but not in baseline: {sorted(added)}"
    print(f"route contract OK — {len(current)} routes match baseline")
