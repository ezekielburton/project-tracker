"""Compatibility shim: this module now lives in core/shared/lib/decorators.
Re-exported here so existing `from app.decorators import ...` imports keep
working until each feature module imports from core/shared directly."""
from app.modules.core.shared.lib import decorators as _src  # noqa: F401
globals().update({k: v for k, v in vars(_src).items() if not k.startswith('__')})
