"""NAS calls from timer scripts. nas.py reads its settings from current_app,
so this gives it a bare Flask app with the config and nothing else."""
from contextlib import contextmanager

from flask import Flask

from config import Config


@contextmanager
def nas_app():
    """An app context that is enough for app.modules.core.shared.services.nas."""
    app = Flask('ovp-jobs')
    app.config.from_object(Config)
    with app.app_context():
        yield
