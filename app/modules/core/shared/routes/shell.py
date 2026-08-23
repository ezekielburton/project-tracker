from flask import Blueprint, render_template, redirect, url_for, request, jsonify
from flask_login import login_required, current_user
from datetime import date, timedelta
from app import db
from sqlalchemy import func, nullslast
from app.models import Project, ProjectDesigner, User, ProjectSecondaryCS, Deliverable

main = Blueprint('main', __name__)


@main.route('/')
def index():
    # Default landing page: redirect to the role-based dashboard. The
    # dashboard's endpoint is `projects.index` — its blueprint is
    # Blueprint('projects', ..., url_prefix='/dashboard') in dashboard.py,
    # named 'projects' for historical reasons, not the "Projects" sidebar
    # link. It branches internally by layout_role
    # (dashboard_cs.html / _leadership.html / _designer.html), so no role
    # logic is needed here.
    return redirect(url_for('projects.index'))


@main.route('/blog-post1-v1.2update')
@login_required
def blog_v12_update():
    return render_template('blog/v12_update.html')


@main.route('/sidebar/track', methods=['POST'])
@login_required
def sidebar_track():
    """
    Fire-and-forget analytics endpoint.
    Records which sidebar link was clicked, who clicked it, and when.
    Called by sidebar.js — no UI depends on the response.
    """
    from app.models import SidebarClick
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

