"""Compatibility shim: this blueprint now lives in core/shared/routes/api.py.
Re-exported here so app/__init__.py keeps importing it unchanged until routing is finalised."""
from app.modules.core.shared.routes.api import api_bp  # noqa: F401
