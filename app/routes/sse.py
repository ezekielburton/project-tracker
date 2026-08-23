"""Compatibility shim: this blueprint now lives in core/shared/routes/sse.py.
Re-exported here so app/__init__.py keeps importing it unchanged until routing is finalised."""
from app.modules.core.shared.routes.sse import sse_bp  # noqa: F401
