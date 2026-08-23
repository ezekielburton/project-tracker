"""Compatibility shim. The models now live in
app/modules/core/shared/models/ as a domain-split package. Every model is
re-exported here so existing `from app.models import X` imports keep working
while feature modules migrate to importing from core/shared directly."""
from app.modules.core.shared.extensions import db, login_manager  # noqa: F401
from app.modules.core.shared.models import *  # noqa: F401,F403
