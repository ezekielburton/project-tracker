# The one blueprint every Client Servicing route file attaches to.
from flask import Blueprint

client_servicing_bp = Blueprint(
    'client_servicing', __name__,
    url_prefix='/client-servicing',
    template_folder='../templates',
)
