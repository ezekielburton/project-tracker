# The one blueprint every HSE route file attaches to.
from flask import Blueprint

hse_bp = Blueprint(
    'hse', __name__,
    url_prefix='/hse',
    template_folder='../templates',
)
