"""Serves the roadmap module's own static assets (CSS/JS)."""
from flask import Blueprint

roadmap_assets = Blueprint(
    'roadmap_assets', __name__,
    static_folder='static', static_url_path='/roadmap/static',
)
