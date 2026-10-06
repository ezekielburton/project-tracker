"""migrate.py saves each deploy run, and a git question it can't answer gives None."""
from datetime import datetime

import migrate
from app.modules.system.models import DeployRun


def test_a_deploy_run_is_saved(db_session):
    cur = db_session.connection().connection.cursor()
    migrate.insert_deploy(cur, datetime(2026, 10, 8, 18, 40), 'v-deploy-test', 'a3f19c2', 2, 48000, True)
    row = DeployRun.query.filter_by(tag='v-deploy-test').one()
    assert (row.commit_sha, row.migrations_applied, row.duration_ms, row.ok) == ('a3f19c2', 2, 48000, True)


def test_git_output_is_none_when_git_cannot_answer():
    assert migrate.git_output('no-such-git-command') is None
