# Blueprint shared by every HSE route file.
from flask import Blueprint

hse_bp = Blueprint(
    'hse', __name__,
    url_prefix='/hse',
    template_folder='../templates',
)
