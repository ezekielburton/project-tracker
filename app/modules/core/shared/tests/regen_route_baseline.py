"""Regenerate the route-contract baseline from the live app.

Run once from the repo root when routes intentionally change (or to restore a
lost baseline):  python -m app.modules.core.shared.tests.regen_route_baseline

Writes refactor/route_baseline.txt at the repo root — the exact path
test_routes_contract.py's _baseline_path() reads from. Commit it.
"""
import os
from app import create_app


def main():
    app = create_app()
    routes = set()
    for r in app.url_map.iter_rules():
        methods = ','.join(sorted(m for m in r.methods if m not in {'HEAD', 'OPTIONS'}))
        routes.add(f'{r.rule}\t{methods}\t{r.endpoint}')
    out = os.path.join(os.path.dirname(app.root_path), 'refactor', 'route_baseline.txt')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(sorted(routes)) + '\n')
    print(f'wrote {len(routes)} routes -> {out}')


if __name__ == '__main__':
    main()
