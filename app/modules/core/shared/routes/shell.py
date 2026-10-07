from flask import Blueprint, redirect, url_for, request, jsonify
from flask_login import login_required, current_user
from app.modules.core.shared.extensions import db
from app.modules.core.shared.lib.capabilities import effective_user
from app.modules.core.shared.lib.home import home_endpoint

main = Blueprint('main', __name__)


@main.route('/')
def index():
    return redirect(url_for(home_endpoint(effective_user())))


@main.route('/sidebar/track', methods=['POST'])
@login_required
def sidebar_track():
    """Fire-and-forget analytics from sidebar.js: which sidebar link was
    clicked, by whom, when. Nothing reads the response."""
    from app.modules.core.shared.models import SidebarClick
    data = request.get_json(silent=True) or {}
    link_name = str(data.get('link_name', ''))[:100]
    if not link_name:
        return jsonify({'ok': False}), 400
    click = SidebarClick(
        link_name=link_name,
        user_id=current_user.id,
        user_role=current_user.role
    )
    db.session.add(click)
    db.session.commit()
    return jsonify({'ok': True})

