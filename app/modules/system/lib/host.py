"""Machine readings from psutil: no shell commands, a few milliseconds each."""
import time

import psutil

_SKIP_FSTYPES = frozenset({'squashfs', 'tmpfs', 'devtmpfs', 'overlay', 'proc', 'sysfs', 'vfat'})
_SKIP_PREFIXES = ('/snap', '/boot', '/run', '/sys', '/proc', '/dev', '/var/snap')
_SENSORS = ('coretemp', 'k10temp', 'cpu_thermal', 'acpitz')


def host_reading():
    """Uptime, CPU, load, memory, temperature and network counters. Takes about
    a second: the CPU figure is measured over one idle second."""
    boot = psutil.boot_time()
    memory = psutil.virtual_memory()
    network = psutil.net_io_counters()
    return {
        'boot_at': int(boot),
        'uptime_s': int(time.time() - boot),
        'cpu_pct': psutil.cpu_percent(interval=1),
        'cpus': psutil.cpu_count(),
        'load': [round(x, 2) for x in psutil.getloadavg()],
        'mem_used': memory.total - memory.available,
        'mem_total': memory.total,
        'temp_c': temperature(),
        'net_sent': network.bytes_sent,
        'net_recv': network.bytes_recv,
    }


def temperature():
    """CPU temperature in °C, or None when the machine exposes no sensors."""
    read = getattr(psutil, 'sensors_temperatures', None)
    if read is None:
        return None
    try:
        sensors = read()
    except Exception:
        return None
    for name in _SENSORS:
        for entry in sensors.get(name, []):
            if entry.current:
                return round(entry.current, 1)
    return None


def mounts():
    """Used and total bytes for each real mount, root first."""
    seen, found = set(), []
    for part in psutil.disk_partitions(all=False):
        if (part.fstype in _SKIP_FSTYPES or part.mountpoint.startswith(_SKIP_PREFIXES)
                or part.device in seen):
            continue
        seen.add(part.device)
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except OSError:
            continue
        found.append({'mount': part.mountpoint, 'used': usage.used, 'total': usage.total})
    return sorted(found, key=lambda m: (m['mount'] != '/', m['mount']))


def _configured_workers(cmdline):
    for i, part in enumerate(cmdline):
        if part in ('-w', '--workers') and i + 1 < len(cmdline) and cmdline[i + 1].isdigit():
            return int(cmdline[i + 1])
        if part.startswith('--workers=') and part[10:].isdigit():
            return int(part[10:])
    return None


def workers_from(processes):
    """{alive, total, started_at} for the app's gunicorn from process infos
    (pid, ppid, cmdline, create_time), or None when it isn't running."""
    app = {p['pid']: p for p in processes
           if 'run:app' in (p.get('cmdline') or []) and any('gunicorn' in c for c in p['cmdline'])}
    masters = [p for p in app.values() if p['ppid'] not in app]
    if not masters:
        return None
    master = masters[0]
    alive = sum(1 for p in app.values() if p['ppid'] == master['pid'])
    return {'alive': alive, 'total': _configured_workers(master['cmdline']) or alive,
            'started_at': int(master['create_time'])}


def gunicorn_workers():
    """workers_from() for the processes running now."""
    infos = []
    for proc in psutil.process_iter(['pid', 'ppid', 'cmdline', 'create_time']):
        infos.append(proc.info)
    return workers_from(infos)
