"""/healthz, the heartbeat's probe. Public on purpose, so it answers only
'ok' or 'down'."""
from flask import Blueprint, Response
from sqlalchemy import text

from app.modules.core.shared.extensions import db

system_bp = Blueprint('system', __name__)


def _answer(body, status):
    return Response(body, status=status, mimetype='text/plain',
                    headers={'Cache-Control': 'no-store'})


@system_bp.route('/healthz')
def healthz():
    """200 'ok' when the database answers SELECT 1, otherwise 503 'down'."""
    try:
        db.session.execute(text('SELECT 1'))
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        return _answer('down', 503)
    return _answer('ok', 200)
