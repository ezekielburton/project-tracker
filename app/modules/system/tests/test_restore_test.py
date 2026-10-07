"""The restore test's decisions: which dump it uses, what counts as a failed
restore, and that its database name and URLs are fixed."""
from datetime import timedelta

import pytest

from app.modules.system.jobs import restore_test

LIVE = {'users': 20, 'projects': 400, 'deliverables': 0}


def test_a_complete_recent_restore_passes():
    assert restore_test.problems_with({'users': 20, 'projects': 395, 'deliverables': 0}, LIVE,
                                      ['a.py', 'b.py'], ['a.py', 'b.py'], timedelta(hours=5)) == []


def test_missing_tables_short_tables_missing_migrations_and_old_dumps_fail():
    problems = restore_test.problems_with({'users': 20, 'projects': 300, 'deliverables': None}, LIVE,
                                          ['a.py'], ['a.py', 'b.py'], timedelta(days=9))
    assert problems == ['projects has 300 of 400 live rows', 'deliverables missing',
                        '1 migrations missing: b.py', 'newest dump is 9 days old']


def test_the_local_copy_is_used_when_the_nas_copy_is_missing(tmp_path):
    local = tmp_path / 'nightly.dump'
    local.write_bytes(b'x')
    details = {'nas_ok': False, 'local_path': str(local)}
    assert restore_test.fetch_dump(details, str(tmp_path / 'scratch.dump')) == (str(local), 'local')


def test_no_dump_at_all_fails(tmp_path):
    with pytest.raises(RuntimeError, match='no dump'):
        restore_test.fetch_dump({'nas_ok': False, 'local_path': str(tmp_path / 'gone.dump')},
                                str(tmp_path / 'scratch.dump'))


def test_the_scratch_database_is_fixed_and_swapped_into_the_url():
    assert restore_test.RESTORE_DB == 'ovp_restore_check'
    url = 'postgresql://ovp_restore:secret@localhost:5432/postgres'
    assert restore_test.with_database(url, restore_test.RESTORE_DB) == \
        'postgresql://ovp_restore:secret@localhost:5432/ovp_restore_check'
