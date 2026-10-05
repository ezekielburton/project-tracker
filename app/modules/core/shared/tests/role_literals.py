"""What counts as a "role literal", shared by the capabilities contract test and
generate_role_literal_baseline.py so the two can never disagree.

A role literal is any `.role`, `.department` or `.seniority` compared or
membership-tested in code (`actor.role == 'cs'`). Branch checks belong in
core/shared/lib/org.py, which reads the fields through getattr. The baseline
records every other one, so a new literal fails the contract test until reviewed.
"""
import re
from pathlib import Path

import app as app_package

APP_ROOT = Path(app_package.__file__).parent
BASELINE_PATH = Path(__file__).parent / 'role_literal_baseline.txt'

# `.role`, `.department` or `.seniority` followed by a comparison or membership
# test. `.role.in_(` (SQLAlchemy) has a dot after the name, so query column
# filters do not match.
_ROLE_LITERAL = re.compile(r'\.(?:role|department|seniority)\s*(?:==|!=|\bin\b|\bnot\s+in\b)')


def _source_files():
    """Every .py and .html under app/, excluding tests and caches."""
    for path in APP_ROOT.rglob('*'):
        if path.suffix not in ('.py', '.html'):
            continue
        parts = path.parts
        if 'tests' in parts or '__pycache__' in parts:
            continue
        yield path


def collect_role_literals():
    """Every role-literal line under app/ as "path :: stripped line". No line
    numbers, so moving a line does not churn the baseline. `#` comment lines are
    skipped; docstrings and trailing comments are not."""
    found = set()
    for path in _source_files():
        text = path.read_text(encoding='utf-8', errors='ignore')
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            if _ROLE_LITERAL.search(line):
                found.add(f'{path.relative_to(APP_ROOT).as_posix()} :: {stripped}')
    return found
