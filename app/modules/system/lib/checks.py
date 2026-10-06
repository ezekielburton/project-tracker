"""The collector's fixed commands and the parsers that turn their output into
numbers. Commands are tuples written here; the only values from outside are
the LAN cert path and the journal bookmark file, both from .env."""
import json
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


def run(command, cwd=None, timeout=120):
    """stdout of one fixed command, or None when it fails. Takes a tuple, never
    a string, and never uses a shell."""
    if not isinstance(command, tuple):
        raise TypeError('commands are fixed tuples')
    try:
        result = subprocess.run(list(command), cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


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
