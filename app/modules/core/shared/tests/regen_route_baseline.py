"""Regenerate refactor/route_baseline.txt from the live app, then commit it.

Run from the repo root:  python -m app.modules.core.shared.tests.regen_route_baseline

test_routes_contract.py imports current_routes() and baseline_path() from here,
so the writer and the reader always agree.
"""
import os


def current_routes(app):
    """The contract's routes as tab-separated rule, methods, endpoint strings.
    Static routes (the app's and each blueprint's) are left out.
    """
    routes = set()
    for r in app.url_map.iter_rules():
        if r.endpoint == 'static' or r.endpoint.endswith('.static'):
            continue
        methods = ','.join(sorted(m for m in r.methods if m not in {'HEAD', 'OPTIONS'}))
        routes.add(f'{r.rule}\t{methods}\t{r.endpoint}')
    return routes


def baseline_path(app):
    # app.root_path is .../project-tracker/app; the baseline lives one level up.
    return os.path.join(os.path.dirname(app.root_path), 'refactor', 'route_baseline.txt')


def main():
    from app import create_app

    app = create_app()
    routes = current_routes(app)
    out = baseline_path(app)
    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(sorted(routes)) + '\n')
    print(f'wrote {len(routes)} routes -> {out}')


if __name__ == '__main__':
    main()
