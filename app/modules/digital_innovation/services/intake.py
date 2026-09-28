# The intake seam: how other modules read back which FeatureRequests DI
# dismissed from its Incoming tray. Only plain values cross it, never
# another module's models.

from app.modules.core.shared.extensions import db
from app.modules.digital_innovation.models import DiIntakeItem


def declined_feature_ids():
    """Ids of FeatureRequests DI has dismissed, as a set of ints. Used by
    the feedback module's signal tray. Non-numeric source_refs are skipped."""
    rows = (db.session.query(DiIntakeItem.source_ref)
            .filter(DiIntakeItem.source_type == 'feature_request',
                    DiIntakeItem.status == 'dismissed')
            .all())
    return {int(ref) for (ref,) in rows if ref and str(ref).isdigit()}
