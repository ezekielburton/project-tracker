# The single blueprint every DI route file registers on, so all DI routes
# share the /digital-innovation prefix.
from flask import Blueprint

digital_innovation_bp = Blueprint(
    'digital_innovation', __name__,
    url_prefix='/digital-innovation',
    template_folder='../templates',
)