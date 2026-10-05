"""Source scans that keep permission logic in the capabilities map: no
role_required imports, no hand-rolled admin gates, no local role sets, and no
unreviewed `.role` literals.
"""
import re

from app.modules.core.shared.tests.role_literals import (
    APP_ROOT,
    BASELINE_PATH,
    _source_files,
    collect_role_literals,
)


def _offenders(needle):
    hits = []
    for path in _source_files():
        text = path.read_text(encoding='utf-8', errors='ignore')
        for lineno, line in enumerate(text.splitlines(), 1):
            if needle in line:
                hits.append(f'{path.relative_to(APP_ROOT)}:{lineno}: {line.strip()}')
    return hits


def _offenders_re(pattern):
    rx = re.compile(pattern)
    hits = []
    for path in _source_files():
        text = path.read_text(encoding='utf-8', errors='ignore')
        for lineno, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                hits.append(f'{path.relative_to(APP_ROOT)}:{lineno}: {line.strip()}')
    return hits


def test_nothing_imports_the_retired_role_decorator():
    """No module imports role_required; gates go through the capabilities map."""
    hits = _offenders('import role_required')
    assert not hits, 'role_required is retired:\n' + '\n'.join(hits)


def test_no_module_hand_rolls_its_own_admin_check():
    """No module defines admin_required(); the existing ones alias
    require_api('...', real_user=True)."""
    hits = _offenders('def admin_required(')
    assert not hits, 'hand-rolled admin gate:\n' + '\n'.join(hits)


# Role-set constants that are allowed because none is a permission gate:
#   _REVIEW_ROLES        who gets in while the CS review lock is on
#   _ROLE_SNAPSHOT_ROLES which people get a tile on the team snapshot
#   LEGACY_ROLES         the role-key bridge onto the org fields (lib/org.py)
_ALLOWED_ROLE_SETS = ('_REVIEW_ROLES', '_ROLE_SNAPSHOT_ROLES', 'LEGACY_ROLES')


def test_no_route_module_declares_its_own_permission_role_set():
    """No `*_ROLES =` constant outside capabilities.py and the allowlist above
    (any spacing matches). A new one needs a capability or an allowlist entry.
    """
    hits = [
        h for h in _offenders_re(r'_ROLES\s*=')
        if 'capabilities.py' not in h
        and 'role_literals.py' not in h
        and not any(name in h for name in _ALLOWED_ROLE_SETS)
    ]
    assert not hits, 'local role set:\n' + '\n'.join(hits)


def test_no_unreviewed_role_literal():
    """Every `.role` comparison matches role_literal_baseline.txt, both ways. A
    new one is either a gate (use can()) or needs a reviewed baseline entry.

    Regenerate after an intentional change:  python generate_role_literal_baseline.py
    """
    assert BASELINE_PATH.exists(), (
        'role-literal baseline missing — run: python generate_role_literal_baseline.py'
    )
    baseline = {
        line.strip()
        for line in BASELINE_PATH.read_text(encoding='utf-8').splitlines()
        if line.strip()
    }
    current = collect_role_literals()

    added = current - baseline
    assert not added, (
        'New role literal(s) not in the baseline. If a gate, use can(); if an '
        'intentional branch/relationship/validation, run '
        'generate_role_literal_baseline.py and commit the baseline:\n'
        + '\n'.join(sorted(added))
    )

    removed = baseline - current
    assert not removed, (
        'Baseline lists role literals that no longer exist — regenerate it:\n'
        + '\n'.join(sorted(removed))
    )

