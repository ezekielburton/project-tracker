"""The collector's fixed commands and the parsers that turn their output into
numbers. Commands are tuples written here; the only values from outside are
the LAN cert path and the journal bookmark file, both from .env."""
import json
import os
import socket
import ssl
import subprocess
import sys
from datetime import datetime

APT_UPGRADABLE = ('apt', 'list', '--upgradable')
GIT_HEAD = ('git', 'rev-parse', 'HEAD')
GIT_TAG = ('git', 'describe', '--tags', '--abbrev=0')
GIT_REMOTE_MAIN = ('git', 'ls-remote', 'origin', 'refs/heads/main')
PIP_OUTDATED = (sys.executable, '-m', 'pip', 'list', '--outdated', '--format=json')
PIP_INSTALLED = (sys.executable, '-m', 'pip', 'list', '--format=json')
# Read at most a day back, so a first run or a long gap stays small.
JOURNAL_SINCE = '-1d'


def cert_end_command(path):
    return ('openssl', 'x509', '-enddate', '-noout', '-in', path)


def journal_command(cursor_file):
    return ('journalctl', '-u', 'helix', '-o', 'json', '--no-pager',
            '--since', JOURNAL_SINCE, '--cursor-file', cursor_file)


def timers_command(units):
    return ('systemctl', 'show', *(f'{unit}.timer' for unit in units),
            '-p', 'Id,LastTriggerUSec,NextElapseUSecRealtime')


def _execute(command, cwd, timeout, utc):
    if not isinstance(command, tuple):
        raise TypeError('commands are fixed tuples')
    # TZ=UTC makes tools like systemctl print times we can read without guessing a zone.
    env = dict(os.environ, TZ='UTC') if utc else None
    return subprocess.run(list(command), cwd=cwd, capture_output=True, text=True,
                          timeout=timeout, env=env)


def run(command, cwd=None, timeout=120, utc=False):
    """stdout of one fixed command, or None when it fails. Takes a tuple, never
    a string, and never uses a shell."""
    try:
        result = _execute(command, cwd, timeout, utc)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def run_status(command, timeout=120):
    """(return code, end of stderr) for a command whose warnings aren't failures
    (pg_restore exits non-zero on harmless notices). Raises if it can't start."""
    try:
        result = _execute(command, None, timeout, False)
    except (OSError, subprocess.SubprocessError) as e:
        raise RuntimeError(f'{command[0]} could not run: {e}')
    return result.returncode, result.stderr.strip()[-2000:]


def run_or_raise(command, cwd=None, timeout=120):
    """Like run(), but a failure raises RuntimeError carrying the end of stderr."""
    try:
        result = _execute(command, cwd, timeout, False)
    except (OSError, subprocess.SubprocessError) as e:
        raise RuntimeError(f'{command[0]} could not run: {e}')
    if result.returncode != 0:
        raise RuntimeError(f'{command[0]} failed: {result.stderr.strip()[-500:]}')
    return result.stdout


def parse_apt(output):
    """(security, total) upgradable packages from `apt list --upgradable`."""
    lines = [line for line in (output or '').splitlines() if '[upgradable from' in line]
    security = sum(1 for line in lines if '-security' in line.split(' ', 1)[0])
    return security, len(lines)


def parse_pip(outdated, installed):
    """(outdated, installed) package counts from two `pip list --format=json` runs."""
    def count(text):
        try:
            return len(json.loads(text))
        except (TypeError, ValueError):
            return None
    return count(outdated), count(installed)


def parse_cert_end(output):
    """The expiry from `openssl x509 -enddate`, as naive UTC, or None."""
    if not output or 'notAfter=' not in output:
        return None
    try:
        return datetime.utcfromtimestamp(ssl.cert_time_to_seconds(output.split('notAfter=', 1)[1].strip()))
    except ValueError:
        return None


def parse_remote_head(output):
    """The commit sha from `git ls-remote`, or None."""
    first = (output or '').split()
    return first[0] if first else None


def first_line(output):
    return output.strip().splitlines()[0] if output and output.strip() else None


def public_cert_end(hostname, timeout=10):
    """When the certificate served for `hostname` expires, as naive UTC, or None."""
    try:
        with socket.create_connection((hostname, 443), timeout=timeout) as sock:
            with ssl.create_default_context().wrap_socket(sock, server_hostname=hostname) as tls:
                not_after = tls.getpeercert()['notAfter']
        return datetime.utcfromtimestamp(ssl.cert_time_to_seconds(not_after))
    except (OSError, ssl.SSLError, KeyError, ValueError):
        return None


def _iso(moment):
    return moment.isoformat(timespec='seconds') if moment else None


def slow_checks(repo_dir, lan_cert_path, public_hostname):
    """Updates, the commit on origin/main and certificate expiries."""
    security, total = parse_apt(run(APT_UPGRADABLE))
    outdated, installed = parse_pip(run(PIP_OUTDATED, timeout=300), run(PIP_INSTALLED))
    lan_end = parse_cert_end(run(cert_end_command(lan_cert_path))) if lan_cert_path else None
    return {
        'os_security': security,
        'os_total': total,
        'pip_outdated': outdated,
        'pip_total': installed,
        'main_commit': parse_remote_head(run(GIT_REMOTE_MAIN, cwd=repo_dir, timeout=30)),
        'certs': [
            {'name': 'LAN', 'expires_at': _iso(lan_end)},
            {'name': 'Cloudflare', 'expires_at': _iso(public_cert_end(public_hostname))},
        ],
    }


def app_version(repo_dir):
    """The release tag and commit the server is running."""
    head = first_line(run(GIT_HEAD, cwd=repo_dir, timeout=10))
    return {'version': first_line(run(GIT_TAG, cwd=repo_dir, timeout=10)),
            'commit': head[:7] if head else None, 'head': head}


def _systemd_time(value):
    try:
        return datetime.strptime(value, '%a %Y-%m-%d %H:%M:%S UTC').isoformat(timespec='seconds')
    except ValueError:
        return None


def parse_timers(output):
    """{unit: {'last', 'next'}} from `systemctl show` of .timer units run with
    TZ=UTC; a time systemd doesn't know is None."""
    timers = {}
    for block in (output or '').strip().split('\n\n'):
        fields = dict(line.split('=', 1) for line in block.splitlines() if '=' in line)
        unit = fields.get('Id', '')
        if unit.endswith('.timer'):
            timers[unit[:-len('.timer')]] = {
                'last': _systemd_time(fields.get('LastTriggerUSec', '')),
                'next': _systemd_time(fields.get('NextElapseUSecRealtime', '')),
            }
    return timers


def timer_states(units):
    """When each job's timer last fired and fires next, straight from systemd."""
    return parse_timers(run(timers_command(tuple(units)), timeout=15, utc=True))
