"""Compatibility shim: the achievement checker service now lives in
core/shared/services. Kept so code not yet migrated to the modules layout
keeps working; migrated modules import from core/shared directly."""
from app.modules.core.shared.services.achievements import check_achievements  # noqa: F401
