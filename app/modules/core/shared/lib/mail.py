"""The outgoing-email switch. MAIL_ENABLED is off on dev machines so nothing
real is sent by accident."""
from flask import current_app


def mail_enabled():
    return str(current_app.config.get('MAIL_ENABLED', 'false')).lower() == 'true'
