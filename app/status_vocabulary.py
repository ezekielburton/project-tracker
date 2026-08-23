"""Compatibility shim: this module now lives in core/shared/lib/status_vocabulary.
Re-exported here so existing `from app.status_vocabulary import ...` imports keep
working until each feature module imports from core/shared directly."""
from app.modules.core.shared.lib import status_vocabulary as _src  # noqa: F401
globals().update({k: v for k, v in vars(_src).items() if not k.startswith('__')})
