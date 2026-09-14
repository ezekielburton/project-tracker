"""Serves the hse module's own static assets (CSS/JS)."""
from flask import Blueprint

hse_assets = Blueprint(
    'hse_assets', __name__,
    static_folder='static', static_url_path='/hse/static',
)
