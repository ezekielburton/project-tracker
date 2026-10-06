"""The collector's fixed commands and their parsers."""
import inspect
from datetime import datetime

import pytest

from app.modules.system.collectors import snapshot as collector
from app.modules.system.lib import checks

APT_OUTPUT = """Listing...
openssl/jammy-updates,jammy-security 3.0.2-0ubuntu1.18 amd64 [upgradable from: 3.0.2-0ubuntu1.17]
libaudit1/jammy-updates 1:3.0.7-1ubuntu0.1 amd64 [upgradable from: 1:3.0.7-1build1]
linux-firmware/jammy-security 20220329.git681281e4-0ubuntu3.36 all [upgradable from: 20220329.git681281e4-0ubuntu3.35]
"""


def test_apt_counts_security_and_total():
    assert checks.parse_apt(APT_OUTPUT) == (2, 3)
    assert checks.parse_apt(None) == (0, 0)


def test_pip_counts_outdated_and_installed():
    assert checks.parse_pip('[{"name": "Flask"}]', '[{"name": "Flask"}, {"name": "gevent"}]') == (1, 2)
    assert checks.parse_pip(None, 'not json') == (None, None)


def test_cert_expiry_from_openssl():
    assert checks.parse_cert_end('notAfter=Jan  5 09:34:43 2027 GMT\n') == datetime(2027, 1, 5, 9, 34, 43)
    assert checks.parse_cert_end('') is None
    assert checks.parse_cert_end('notAfter=garbage') is None


def test_remote_head_from_ls_remote():
    assert checks.parse_remote_head('a3f19c2e9b\trefs/heads/main\n') == 'a3f19c2e9b'
    assert checks.parse_remote_head(None) is None


def test_run_refuses_anything_but_a_fixed_tuple():
    with pytest.raises(TypeError):
        checks.run('apt list --upgradable')


def test_a_failing_command_gives_none():
    assert checks.run(('git', 'no-such-git-command')) is None


@pytest.mark.parametrize('module', [checks, collector])
def test_no_shell_and_one_place_that_runs_commands(module):
    source = inspect.getsource(module)
    assert 'shell=True' not in source
    assert 'os.system' not in source and 'os.popen' not in source
    if module is collector:
        assert 'subprocess' not in source
