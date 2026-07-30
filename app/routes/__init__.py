from flask import Blueprint, render_template, redirect, url_for, request, jsonify
from flask_login import login_required, current_user
from datetime import date, timedelta
from app import db
from sqlalchemy import func, nullslast
from app.models import Project, ProjectDesigner, User, ProjectSecondaryCS, Deliverable

main = Blueprint('main', __name__)


@main.route('/projects')
@login_required
def projects():
    """
    Role-aware dashboard router.
    Looks at the current user's role and renders the appropriate dashboard.
    """

    from flask import session
    from app.models import User as UserModel
    emulating_id = session.get('emulating_user_id')
    if emulating_id and current_user.role == 'admin':
        effective_role = UserModel.query.get(emulating_id).role
    else:
        effective_role = current_user.role

    if effective_role in ['cs', 'admin', 'management']:
        return cs_dashboard()
    elif effective_role == 'designer':
        return designer_dashboard()
    elif effective_role == 'team_lead':
        return team_lead_dashboard()
    else:
        return redirect(url_for('main.projects'))


def cs_dashboard():
    """Render the CS dashboard - own projects default, all projects toggle."""
    from flask import session
    from app.models import User as UserModel
    
    today = date.today()

    emulating_id = session.get('emulating_user_id')

    if emulating_id and current_user.role == 'admin':
        effective_user = UserModel.query.get(emulating_id)
    else:
        effective_user = current_user
    
    if effective_user.role == 'admin':
        my_projects = Project.query.filter(
            Project.project_status != 'draft',
            Project.project_status != 'approved'
        ).order_by(Project.first_output_deadline.asc()).all()
    else:
        # Include projects where the user is CS lead OR a secondary CS
        secondary_project_ids = db.session.query(ProjectSecondaryCS.project_id).filter_by(
            user_id=effective_user.id
        ).subquery()
        my_projects = Project.query.filter(
            db.or_(
                Project.cs_lead_id == effective_user.id,
                Project.id.in_(secondary_project_ids)
            ),
            Project.project_status != 'draft',
            Project.project_status != 'approved'
        ).order_by(Project.first_output_deadline.asc()).all()

    if effective_user.role == 'admin':
        all_projects = my_projects
    else:
        all_projects = Project.query.filter(
            Project.project_status != 'draft',
            Project.project_status != 'approved'
        ).order_by (
            Project.first_output_deadline.asc()
        ).all()
        

    # All approved projects — shown in the Approved Projects tab, visible to all CS/admin
    approved_projects = Project.query.filter_by(
        project_status='approved'
    ).order_by(Project.approved_at.desc()).all()

    cs_users = User.query.filter(
        User.role.in_(['cs', 'admin'])
    ).order_by(User.name).all()

    # ── Deliverable view — all deliverables across active projects, earliest deadline first
    all_deliverables = (
        Deliverable.query
        .join(Project, Project.id == Deliverable.project_id)
        .filter(
            Project.project_status != 'draft',
            Project.project_status != 'approved'
        )
        .order_by(
            nullslast(Deliverable.design_deadline),
            nullslast(Deliverable.design_deadline_time)
        )
        .all()
    )

    return render_template(
    'dashboards/cs.html',
    projects=my_projects,
    all_projects=all_projects,
    approved_projects=approved_projects,
    cs_users=cs_users,
    today=today,
    effective_role=effective_user.role,
    all_deliverables=all_deliverables
)



def designer_dashboard():
    from flask import session
    from app.models import User as UserModel

    emulating_id = session.get('emulating_user_id')
    if emulating_id and current_user.role == 'admin':
        effective_user = UserModel.query.get(emulating_id)
    else:
        effective_user = current_user

    today = date.today()
    tomorrow = today + timedelta(days=1)

    # ── Personal projects ──
    assigned_subquery = db.session.query(
        ProjectDesigner.project_id
    ).filter_by(user_id=effective_user.id).subquery()

    my_projects = Project.query.filter(
        Project.id.in_(assigned_subquery),
        Project.project_status != 'draft',
        Project.project_status != 'approved'
    ).order_by(Project.first_output_deadline.asc()).all()

    active_count = len(my_projects)
    due_today = sum(1 for p in my_projects if p.design_needed_by == today)
    due_tomorrow = sum(1 for p in my_projects if p.design_needed_by == tomorrow)

    # ── Team overview ──
    team = effective_user.team

    if team:
        team_projects = Project.query.filter(
            Project.design_teams_requested.contains(team),
            Project.project_status != 'draft',
            Project.project_status != 'approved'
        ).order_by(Project.first_output_deadline.asc()).all()

        designers_in_team = User.query.filter(
            User.team == team,
            User.role.in_(['designer', 'team_lead'])
        ).order_by(User.name).all()

    workload_counts = dict(
        db.session.query(
            ProjectDesigner.user_id,
            func.count(ProjectDesigner.project_id)
        ).join(Project)
        .filter(
            ProjectDesigner.user_id.in_([d.id for d in designers_in_team]),
            Project.project_status != 'draft',
            Project.project_status != 'approved'
        ).group_by(ProjectDesigner.user_id).all()
    )

    team_workload = [
        {'name': designer.name, 'count': workload_counts.get(designer.id, 0)}
        for designer in designers_in_team
    ]

    team_active = len(team_projects)
    team_due_today = sum(1 for p in team_projects if p.design_needed_by == today)
    team_due_tomorrow = sum(1 for p in team_projects if p.design_needed_by == tomorrow)

    # All approved projects — shown in the Approved Projects tab
    approved_projects = Project.query.filter_by(
        project_status='approved'
    ).order_by(Project.approved_at.desc()).all()

    # ── Deliverable view — only projects this designer is assigned to ──
    my_deliverables = (
        Deliverable.query
        .join(Project, Project.id == Deliverable.project_id)
        .filter(
            Project.project_status != 'draft',
            Project.project_status != 'approved',
            Project.id.in_(assigned_subquery),
            Deliverable.teams.contains(team)
        )
        .order_by(
            nullslast(Deliverable.design_deadline),
            nullslast(Deliverable.design_deadline_time)
        )
        .all()
    ) if team else []

    return render_template(
        'dashboards/designer.html',
        projects=my_projects,
        active_count=active_count,
        due_today=due_today,
        due_tomorrow=due_tomorrow,
        team_projects=team_projects,
        team_workload=team_workload,
        team_active=team_active,
        team_due_today=team_due_today,
        team_due_tomorrow=team_due_tomorrow,
        approved_projects=approved_projects,
        my_deliverables=my_deliverables,
        today=today
    )


def team_lead_dashboard():
    from flask import session
    from app.models import User as UserModel

    emulating_id = session.get('emulating_user_id')
    if emulating_id and current_user.role == 'admin':
        effective_user = UserModel.query.get(emulating_id)
    else:
        effective_user = current_user

    team = effective_user.team
    today = date.today()
    tomorrow = today + timedelta(days=1)

    if not team:
        return render_template(
            'dashboards/team_lead.html',
            team_projects=[], team_active=0, team_due_today=0,
            team_due_tomorrow=0, team_workload=[],
            personal_projects=[], personal_active=0,
            personal_due_today=0, personal_due_tomorrow=0,
            my_deliverables=[], approved_projects=[],
            today=today
        )

    team_projects = Project.query.filter(
        Project.design_teams_requested.contains(team),
        Project.project_status != 'draft',
        Project.project_status != 'approved'
    ).order_by(Project.first_output_deadline.asc()).all()

    team_active = len(team_projects)
    team_due_today = sum(1 for p in team_projects if p.design_needed_by == today)
    team_due_tomorrow = sum(1 for p in team_projects if p.design_needed_by == tomorrow)

    designers_in_team = User.query.filter(
        User.team == team,
        User.role.in_(['designer', 'team_lead'])
    ).order_by(User.name).all()

    workload_counts = dict(
        db.session.query(
            ProjectDesigner.user_id,
            func.count(ProjectDesigner.project_id)
        ).join(Project)
        .filter(
            ProjectDesigner.user_id.in_([d.id for d in designers_in_team]),
            Project.project_status != 'draft',
            Project.project_status != 'approved'
        ).group_by(ProjectDesigner.user_id).all()
    )

    team_workload = [
        {'name': designer.name, 'count': workload_counts.get(designer.id, 0)}
        for designer in designers_in_team
    ]

    personal_subquery = db.session.query(
       ProjectDesigner.project_id
    ).filter_by(user_id=effective_user.id).subquery()

    personal_projects = Project.query.filter(
        Project.id.in_(personal_subquery),
        Project.project_status != 'draft',
        Project.project_status != 'approved'

    ).order_by(Project.first_output_deadline.asc()).all()


    personal_active = len(personal_projects)
    personal_due_today = sum(1 for p in personal_projects if p.design_needed_by == today)
    personal_due_tomorrow = sum(1 for p in personal_projects if p.design_needed_by == tomorrow)

    # All approved projects — shown in the Approved Projects tab
    approved_projects = Project.query.filter_by(
        project_status='approved'
    ).order_by(Project.approved_at.desc()).all()

    # ── Deliverable view — only projects this team lead is personally assigned to ──
    my_deliverables = (
        Deliverable.query
        .join(Project, Project.id == Deliverable.project_id)
        .filter(
            Project.project_status != 'draft',
            Project.project_status != 'approved',
            Project.id.in_(personal_subquery),
            Deliverable.teams.contains(team)
        )
        .order_by(
            nullslast(Deliverable.design_deadline),
            nullslast(Deliverable.design_deadline_time)
        )
        .all()
    )

    return render_template(
        'dashboards/team_lead.html',
        team_projects=team_projects,
        team_active=team_active,
        team_due_today=team_due_today,
        team_due_tomorrow=team_due_tomorrow,
        team_workload=team_workload,
        personal_projects=personal_projects,
        personal_active=personal_active,
        personal_due_today=personal_due_today,
        personal_due_tomorrow=personal_due_tomorrow,
        approved_projects=approved_projects,
        my_deliverables=my_deliverables,
        today=today
    )

@main.route('/')
def index():
    # Default landing page — new role-based dashboard (16 Jul 2026), per
    # Ezekiel: "dashboard is good to go. Make the default page of the app
    # the dashboard." Was main.projects (the old legacy per-role dashboard
    # — cs.html/designer.html/team_lead.html templates, still reachable via
    # the "Projects" sidebar link, unchanged). `projects.index` is the NEW
    # dashboard blueprint's endpoint (registered as Blueprint('projects', ...,
    # url_prefix='/dashboard') in dashboard.py — confusingly named after the
    # old system it replaced, not the "Projects" sidebar link) — it already
    # branches internally by layout_role (dashboard_cs.html/_leadership.html/
    # _designer.html), so no role logic is needed here.
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

