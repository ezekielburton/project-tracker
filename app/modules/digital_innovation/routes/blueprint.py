# The one blueprint every Digital Innovation route file attaches to —
# board.py, features.py, templates.py, archive.py, intake.py, performance.py, costs.py, projects.py all import this same
# object rather than each declaring their own, so every DI route sits
# under one clean /digital-innovation prefix (same discipline as the
# projects module's overlay/preproduction/notes split, but with a single
# blueprint instead of several).
from flask import Blueprint

digital_innovation_bp = Blueprint(
    'digital_innovation', __name__,
    url_prefix='/digital-innovation',
    template_folder='../templates',
)