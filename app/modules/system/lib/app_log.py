"""Turns journald's JSON lines for the helix service into events: errors and
warnings (with any traceback that follows) and worker starts. A signature
strips numbers, ids and quoted text so repeats of one problem group together."""
import json
import re
from datetime import datetime

ERROR, WARNING, INFO = 'error', 'warning', 'info'
SIGNATURE_LIMIT = 200
DETAIL_LIMIT = 8000

# Flask's default handler: "[time] ERROR in module: message".
_FLASK = re.compile(r'^\[[^\]]+\] (ERROR|WARNING|CRITICAL) in ([\w.]+): (.*)$')
# Gunicorn: "[time] [pid] [ERROR] message".
_GUNICORN = re.compile(r'^\[[^\]]+\] \[\d+\] \[(ERROR|WARNING|CRITICAL)\] (.*)$')
_WORKER_BOOT = re.compile(r'\[INFO\] Booting worker with pid')
_TRACEBACK = 'Traceback (most recent call last):'
_CHAINED = ('During handling of the above exception', 'The above exception was the direct cause')
_EXCEPTION = re.compile(r'^([A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt|Warning|Timeout))(?::|$)')
_APP_FRAME = re.compile(r'File "[^"]*?[/\\](app[/\\][^"]+)", line \d+, in (\S+)')
_NORMALISE = (
    (re.compile(r"'[^']*'|\"[^\"]*\""), '…'),
    (re.compile(r'\b[0-9a-f]{8}-[0-9a-f-]{27,}\b', re.I), '#'),
    (re.compile(r'\b0x[0-9a-f]+\b', re.I), '#'),
    (re.compile(r'\d+'), '#'),
    (re.compile(r'\s+'), ' '),
)
_LEVELS = {'ERROR': ERROR, 'CRITICAL': ERROR, 'WARNING': WARNING}


def normalise(text):
    """`text` with quoted parts, ids and numbers replaced, so repeats match."""
    for pattern, replacement in _NORMALISE:
        text = pattern.sub(replacement, text)
    return text.strip()


def _message(entry):
    message = entry.get('MESSAGE')
    if isinstance(message, list):
        message = bytes(message).decode('utf-8', 'replace')
    return message if isinstance(message, str) else ''


def _when(entry):
    try:
        return datetime.utcfromtimestamp(int(entry['__REALTIME_TIMESTAMP']) / 1_000_000)
    except (KeyError, TypeError, ValueError):
        return None


def _continues(line):
    return (line.startswith((' ', '\t', _TRACEBACK) + _CHAINED)
            or _EXCEPTION.match(line) is not None or not line.strip())


class _Event:
    def __init__(self, ts, level, source, message):
        self.ts, self.level, self.source, self.message = ts, level, source, message
        self.lines = [message] if message else []

    def finish(self):
        exception, where = None, None
        for line in self.lines:
            frame = _APP_FRAME.search(line)
            if frame:
                where = f"{frame.group(1).replace(chr(92), '/')} · {frame.group(2)}"
            match = _EXCEPTION.match(line)
            if match:
                exception = match.group(1)
        if exception:
            source = where or self.source
            signature = f'{exception} · {source}'
        else:
            source = self.source
            signature = f'{source}: {normalise(self.message)}'
        return {
            'ts': self.ts, 'level': self.level, 'source': source[:120],
            'signature': signature[:SIGNATURE_LIMIT],
            'message': self.message or exception or '',
            'detail': '\n'.join(self.lines)[:DETAIL_LIMIT],
        }


def read_events(json_lines):
    """Events from journald JSON lines, oldest first; other lines are ignored."""
    events, current = [], None
    for raw in json_lines:
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        line, ts = _message(entry), _when(entry)
        flask, gunicorn = _FLASK.match(line), _GUNICORN.match(line)
        if current is not None and not flask and not gunicorn and _continues(line):
            current.lines.append(line)
            continue
        if current is not None:
            events.append(current.finish())
            current = None
        if flask:
            current = _Event(ts, _LEVELS[flask.group(1)], flask.group(2), flask.group(3))
        elif gunicorn:
            current = _Event(ts, _LEVELS[gunicorn.group(1)], 'gunicorn', gunicorn.group(2))
        elif line.startswith(_TRACEBACK):
            current = _Event(ts, ERROR, 'python', '')
            current.lines.append(line)
        elif _WORKER_BOOT.search(line):
            events.append({'ts': ts, 'level': INFO, 'source': 'gunicorn',
                           'signature': 'gunicorn: worker started', 'message': line, 'detail': line})
    if current is not None:
        events.append(current.finish())
    return events
