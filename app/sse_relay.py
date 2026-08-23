"""Compatibility shim: this module now lives in core/shared/services/sse_relay.
Re-exported here so existing `from app.sse_relay import ...` imports keep
working until each feature module imports from core/shared directly."""
from app.modules.core.shared.services import sse_relay as _src  # noqa: F401
globals().update({k: v for k, v in vars(_src).items() if not k.startswith('__')})
