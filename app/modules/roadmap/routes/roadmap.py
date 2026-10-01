"""The company roadmap page: what's live, what's in progress and when the next
pieces are delivered."""
from datetime import date

from flask import Blueprint, render_template
from flask_login import login_required

from app.modules.roadmap.lib.items import roadmap_view

roadmap_bp = Blueprint('roadmap', __name__, url_prefix='/roadmap', template_folder='../templates')


@roadmap_bp.route('')
@login_required
def index():
    """GET /roadmap. Login only, no capability: the roadmap is for everyone."""
    return render_template('roadmap/index.html', **roadmap_view(date.today()))
