"""
Client Servicing's feed for the global Dashboard: the one function it imports
from this module. Relevance and visibility are decided here, so the global side
filters nothing. The logic lives in lib/dashboard.py.
"""
from app.modules.client_servicing.lib.dashboard import feed_items


def feed_for(user):
    """CS items for `user`'s global Dashboard Next Actions, most-urgent first.
    Empty for anyone without CS access; finance items only for finance viewers."""
    return feed_items(user)