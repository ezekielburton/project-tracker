from flask import Blueprint, render_template, redirect, url_for, request, jsonify
from flask_login import login_required, current_user
from datetime import date, timedelta
from app import db
from sqlalchemy import func, nullslast
from app.models import Project, ProjectDesigner, User, ProjectSecondaryCS, Deliverable

main = Blueprint('main', __name__)


@main.route('/')
def index():
    # Default landing page — new role-based dashboard (16 Jul 2026), per
    # Ezekiel: "dashboard is good to go. Make the default page of the app
    # the dashboard." Was main.projects (the old legacy per-role dashboard —
    # cs.html/designer.html/team_lead.html templates); that route/those
    # templates were deleted at M10 cutover (20 Aug 2026) since the sidebar
    # had already been repointed to project_list.index and nothing referenced
    # them anymore. `projects.index` is the NEW dashboard blueprint's endpoint
    # (registered as Blueprint('projects', ..., url_prefix='/dashboard') in
    # dashboard.py — confusingly named after the old system it replaced, not
    # the "Projects" sidebar link) — it already branches internally by
    # layout_role (dashboard_cs.html/_leadership.html/_designer.html), so no
    # role logic is needed here.
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

