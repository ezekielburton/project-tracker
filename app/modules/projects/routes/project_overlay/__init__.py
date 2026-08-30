"""
project_overlay — the Project Details Overlay blueprint, split into a package.

project_overlay_bp is defined in _common.py; every route submodule imports it
and decorates its views onto it. That keeps the app factory's
`from ...routes.project_overlay import project_overlay_bp` and every
url_for('project_overlay.*') name unchanged from before the split.

_common.py also holds the shared helpers, re-exported here so imports from
outside the package (e.g. project_preproduction.py's
_build_ccm_deliverable_sections) keep working unchanged.
"""

from ._common import (
    project_overlay_bp,
    _get_actor,
    _can_manage_deliverables,
    _has_edit_access_grant,
    _can_manage_flags,
    _can_resolve_flag,
    _build_ccm_deliverable_sections,
    _recompute_initial_deadline,
    _scoped_deliverables_query,
    _CREATE_REGION_NAMES,
    _CREATE_REGION_ORDER,
    _DELIVERABLE_STATUS_OVERRIDE_OPTIONS,
    _PROJECT_STATUS_OVERRIDE_OPTIONS,
    _parse_edit_date,
    ensure_posm_channels,
)

# Importing each submodule attaches its @project_overlay_bp.route views.
from . import files    # noqa: F401
from . import flags    # noqa: F401
from . import create   # noqa: F401
from . import deliverables  # noqa: F401
from . import submissions   # noqa: F401
from . import details   # noqa: F401
