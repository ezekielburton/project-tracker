"""psutil readings: the gunicorn worker count and the mounts list."""
from app.modules.system.lib import host

_GUNICORN = ['/srv/venv/bin/python', '/srv/venv/bin/gunicorn', '-k', 'gevent', '-w', '9', 'run:app']


def test_workers_counts_the_masters_children_against_the_configured_total():
    processes = [{'pid': 10, 'ppid': 1, 'cmdline': _GUNICORN, 'create_time': 1_790_000_000.5}]
    processes += [{'pid': 11 + i, 'ppid': 10, 'cmdline': _GUNICORN, 'create_time': 1_790_000_001} for i in range(8)]
    processes.append({'pid': 99, 'ppid': 1, 'cmdline': ['/usr/sbin/nginx'], 'create_time': 1})
    assert host.workers_from(processes) == {'alive': 8, 'total': 9, 'started_at': 1_790_000_000,
                                            'pids': list(range(11, 19))}


def test_no_gunicorn_means_none():
    assert host.workers_from([{'pid': 1, 'ppid': 0, 'cmdline': None, 'create_time': 0}]) is None


def test_workers_flag_written_with_equals():
    cmd = ['gunicorn', '--workers=4', 'run:app']
    processes = [{'pid': 10, 'ppid': 1, 'cmdline': cmd, 'create_time': 0}]
    assert host.workers_from(processes)['total'] == 4


def test_mounts_skip_system_filesystems_and_list_root_first(monkeypatch):
    from collections import namedtuple
    Part = namedtuple('Part', 'device mountpoint fstype opts')
    Usage = namedtuple('Usage', 'used total')
    monkeypatch.setattr(host.psutil, 'disk_partitions', lambda all=False: [
        Part('/dev/sdb1', '/var/uploads', 'ext4', ''), Part('/dev/sda1', '/', 'ext4', ''),
        Part('/dev/loop0', '/snap/core/1', 'squashfs', ''), Part('/dev/sda2', '/boot/efi', 'vfat', ''),
    ])
    monkeypatch.setattr(host.psutil, 'disk_usage', lambda mount: Usage(10, 20))
    assert host.mounts() == [{'mount': '/', 'used': 10, 'total': 20},
                             {'mount': '/var/uploads', 'used': 10, 'total': 20}]
