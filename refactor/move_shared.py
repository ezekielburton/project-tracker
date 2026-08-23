import os
BASE = 'app/modules/core/shared'
MOVES = {
    'app/decorators.py':        ('lib', 'decorators'),
    'app/utils.py':             ('lib', 'utils'),
    'app/zip_utils.py':         ('lib', 'zip_utils'),
    'app/status_vocabulary.py': ('lib', 'status_vocabulary'),
    'app/notifications.py':     ('services', 'notifications'),
    'app/status_tracking.py':   ('services', 'status_tracking'),
    'app/nas.py':               ('services', 'nas'),
    'app/live_events.py':       ('services', 'live_events'),
    'app/sse_relay.py':         ('services', 'sse_relay'),
}
for sub in ('lib', 'services'):
    d = os.path.join(BASE, sub)
    os.makedirs(d, exist_ok=True)
    ip = os.path.join(d, '__init__.py')
    if not os.path.exists(ip):
        open(ip, 'w').close()
for old, (sub, name) in MOVES.items():
    content = open(old, encoding='utf-8').read()
    assert 'core.shared' not in content[:300], old + ' looks already moved'
    open(os.path.join(BASE, sub, name + '.py'), 'w', encoding='utf-8').write(content)
    shim = (
        '"""Compatibility shim: this module now lives in '
        'core/shared/%s/%s.\n'
        'Re-exported here so existing `from app.%s import ...` imports keep\n'
        'working until each feature module imports from core/shared directly."""\n'
        'from app.modules.core.shared.%s import %s as _src  # noqa: F401\n'
        "globals().update({k: v for k, v in vars(_src).items() if not k.startswith('__')})\n"
        % (sub, name, name, sub, name)
    )
    open(old, 'w', encoding='utf-8').write(shim)
    print('moved', old, '->', sub + '/' + name + '.py')
print('done', len(MOVES), 'files')
