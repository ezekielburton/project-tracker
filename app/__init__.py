from flask import Flask, g, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from config import Config
import os

db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    from app.models import (User, Project, ProjectDesigner, Scope, Client, Customer, DeliverableType, DeliverableTypeDiscipline, ProjectRegion, ProjectCustomer, Deliverable, DeliverableAssignment, ActivityLog, DesignType, DesignDirection, ProjectFile, ProjectSubmission, ProjectSubmissionDeliverable, ProjectRevision, ProjectRevisionDeliverable, BlogPost, BlogComment, FeatureRequest, FeatureRequestUpvote, FeatureRequestComment, BugReport, BugReportComment)
    from app.routes import main
    from app.routes.auth import auth
    from app.routes.projects_brief import brief_bp
    from app.routes.projects_detail import detail_bp
    from app.routes.projects_submission import submission_bp
    from app.routes.projects_approval import approval_bp
    from app.routes.notifications import notifications_bp
    from app.models import Notification
    from flask_login import current_user
    from app.routes.admin import admin_bp
    from app.routes.blog import blog_bp
    from app.routes.feedback import feedback_bp
    from app.routes.wiki import wiki_bp
    from app.routes.api import api_bp  # polling endpoints for live dashboard/detail updates

    app.register_blueprint(notifications_bp)
    app.register_blueprint(main)
    app.register_blueprint(auth)
    app.register_blueprint(brief_bp)
    app.register_blueprint(detail_bp)
    app.register_blueprint(submission_bp)
    app.register_blueprint(approval_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(blog_bp)
    app.register_blueprint(feedback_bp)
    app.register_blueprint(wiki_bp)
    app.register_blueprint(api_bp)  # /api/* poll routes

    from app.utils import calculate_project_hours
    
    @app.context_processor
    def utility_processor():
        return dict(calculate_hours=calculate_project_hours)
    
    @app.context_processor
    def inject_notifications():
        from flask import session
        from flask_login import current_user
        from app.models import Notification

        if current_user.is_authenticated:
            # Use the emulated user's ID when in emulation mode
            emulating_id = session.get('emulating_user_id')
            notif_user_id = emulating_id if (emulating_id and current_user.role == 'admin') else current_user.id

            active_notifications = Notification.query.filter_by(
                recipient_id=notif_user_id,
                is_archived=False
            ).order_by(Notification.created_at.desc()).all()

            archived_notifications = Notification.query.filter_by(
                recipient_id=notif_user_id,
                is_archived=True
            ).order_by(Notification.created_at.desc()).limit(50).all()

            unread_count = sum(1 for n in active_notifications if not n.is_read)

            return {
                'user_notifications': active_notifications,
                'archived_notifications': archived_notifications,
                'unread_count': unread_count
            }
        return {
            'user_notifications': [],
            'archived_notifications': [],
            'unread_count': 0
        }

    @app.context_processor
    def inject_effective_user():
       from flask import session
       if current_user.is_authenticated:
             emulating_id = session.get('emulating_user_id')
             if emulating_id and current_user.role == 'admin':
                 effective_user = User.query.get(emulating_id)
                 is_emulating = True
             else:
                effective_user = current_user
                is_emulating = False
             return {
                 'effective_user': effective_user,
                 'is_emulating': is_emulating
             }
       return {
           'effective_user': current_user,
           'is_emulating': False
       }
    
    from datetime import timezone, timedelta

    def dubai_time(dt):
        if dt is None:
            return '_'
        dubai_tz = timezone(timedelta(hours=4))
        return dt.replace(tzinfo=timezone.utc).astimezone(dubai_tz).strftime('%d %b %Y, %H:%M')
    
    app.jinja_env.filters['dubai_time'] = dubai_time


    # DEV TOOLS — hardcoded True for now. Switch back to env var check before deploying to prod:
    # app.jinja_env.globals['dev_tools_enabled'] = os.environ.get('DEV_TOOLS_ENABLED', '').lower() == 'true'
    app.jinja_env.globals['dev_tools_enabled'] = True

    @app.before_request
    def detect_nav_request():
        # SPA navigation: sidebar.js sends X-Nav-Request: 1 for internal link clicks.
        # Routes render normally; base.html skips the outer shell when this flag is set,
        # returning only the content block so JS can swap it into #main-content.
        g.is_nav_request = request.headers.get('X-Nav-Request') == '1'
    
    @app.after_request
    def spa_strip_response(response):
        if (g.get('is_nav_request') and
            response.content_type.startswith('text/html') and
            response.status_code == 200):
          import re
          html = response.get_data(as_text=True)
          # Send the page title as a header so JS can update document.title.
          # Percent-encode it so non-latin-1 characters (e.g. em dash) don't crash the header.
          title_match = re.search(r'<title>(.*?)</title>', html, re.DOTALL)
          if title_match:
              from urllib.parse import quote
              response.headers['X-Page-Title'] = quote(title_match.group(1).strip())
          m = re.search(
              r'<main[^>]+id=["\']main-content["\'][^>]*>(.*?)</main>',
              html, re.DOTALL
          )
          if m:
              response.set_data(m.group(1))
        return response


    return app