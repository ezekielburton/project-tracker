"""Serves the reports module's own static assets (CSS/JS)."""
from flask import Blueprint

reports_assets = Blueprint(
    'reports_assets', __name__,
    static_folder='static', static_url_path='/reports/static',
)
