import os
BASE = 'app/modules/core/shared/routes'
os.makedirs(BASE, exist_ok=True)
open(os.path.join(BASE, '__init__.py'), 'a').close()   # empty package marker

# old path -> (new filename, shim import line)
MOVES = {
    'app/routes/__init__.py': ('shell.py', 'from app.modules.core.shared.routes.shell import main  # noqa: F401'),
    'app/routes/sse.py':      ('sse.py',   'from app.modules.core.shared.routes.sse import sse_bp  # noqa: F401'),
    'app/routes/api.py':      ('api.py',   'from app.modules.core.shared.routes.api import api_bp  # noqa: F401'),
}
for old, (newname, shim) in MOVES.items():
    content = open(old, encoding='utf-8').read()
    assert 'core.shared.routes' not in content, old + ' looks already moved'
    open(os.path.join(BASE, newname), 'w', encoding='utf-8').write(content)
    doc = ('"""Compatibility shim: this blueprint now lives in '
           'core/shared/routes/%s.\n'
           'Re-exported here so app/__init__.py keeps importing it unchanged '
           'until routing is finalised."""\n') % newname
    open(old, 'w', encoding='utf-8').write(doc + shim + '\n')
    print('moved', old, '->', BASE + '/' + newname)
print('done')
