from flask import Flask, g, request
from config import Config
from datetime import timezone, timedelta, datetime
import os

from app.modules.core.shared.extensions import db, login_manager, mail


def _compute_static_version():
    """Cache-busting stamp for STATIC_VERSION: the newest source-file mtime.
    Mtime (not wall-clock) so all gunicorn workers compute the same value —
    otherwise polling.js's version check misreads the drift as a redeploy and
    loops reloads. Changes on deploy, since git rewrites changed files' mtimes."""
    import time
    app_dir = os.path.dirname(os.path.abspath(__file__))
    newest = 0.0
    for root, dirs, files in os.walk(app_dir):
        dirs[:] = [d for d in dirs if d not in ('__pycache__', '.git')]
        for fname in files:
            if fname.endswith('.pyc'):
                continue
            try:
                mtime = os.path.getmtime(os.path.join(root, fname))
            except OSError:
                continue
            if mtime > newest:
                newest = mtime
    # Fallback only if the walk somehow found nothing (shouldn't happen) —
    # keeps STATIC_VERSION from ever being empty/zero.
    return str(int(newest)) if newest else str(int(time.time()))


def create_app(config=Config):
    app = Flask(__name__)
    app.config.from_object(config)

    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    from app.modules.core.shared.services.live_events import init_live_events
    init_live_events()
    from app.modules.core.shared.services.sse_relay import init_sse_relay
    init_sse_relay(app)  # no-op unless GEVENT_WORKER=1 — see sse_relay.py

    # Cache-buster for every static tag in base.html (?v=...). See
    # _compute_static_version — mtime-based so all workers agree.
    app.config['STATIC_VERSION'] = _compute_static_version()

    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    from app.modules.core.shared.models import (User, Project, ProjectDesigner, Scope, Client, Customer, DeliverableType, DeliverableTypeDiscipline, ProjectRegion, ProjectCustomer, Deliverable, DeliverableAssignment, ActivityLog, DesignType, DesignDirection, ProjectFile, ProjectSubmission, ProjectSubmissionDeliverable, ProjectSubmissionFile, ProjectRevision, ProjectRevisionDeliverable, BlogPost, BlogComment, FeatureRequest, FeatureRequestUpvote, FeatureRequestComment, BugReport, BugReportComment)
    from app.modules.core.shared.blueprint import core as core_bp
    from app.modules.core.shared.routes.shell import main
    from app.modules.auth.routes.auth import auth
    from app.modules.notifications.routes.notifications import notifications_bp
    from app.modules.core.shared.models import Notification
    from app.modules.client_servicing.models import ClientServicing, ClientServicingScope  # registers the tables with SQLAlchemy
    from flask_login import current_user
    from app.modules.admin.routes.admin import admin_bp
    from app.modules.blog.routes.blog import blog_bp
    from app.modules.feedback.routes.feedback import feedback_bp
    from app.modules.feedback.routes.signal_tray import signal_tray_bp  # Signal tray boards + Friction Log
    from app.modules.wiki.routes.wiki import wiki_bp
    from app.modules.core.shared.routes.api import api_bp  # polling endpoints for live dashboard/detail updates
    from app.modules.profile.routes.profile import profile_bp  # profile view/edit routes
    from app.modules.achievements.routes.admin_achievements import admin_achievements_bp  # achievement system admin panel
    from app.modules.profile.routes.wizard import wizard_bp
    from app.modules.file_templates.routes.file_templates import file_templates_bp
    from app.modules.core.shared.routes.sse import sse_bp  # SSE live push routes
    from app.modules.client_directory.routes.client_directory import client_directory_bp  # Client Directory — companies + contacts
    from app.modules.dashboard.routes.dashboard import dashboard_bp  # role-based dashboard
    from app.modules.time_tracking.routes.time_tracking import time_tracking_bp  # project/deliverable business-hours breakdown page
    from app.modules.projects.routes.transfer import transfer_bp  # C&CM deliverable transfer (move / duplicate to new customer)
    from app.modules.projects.routes.project_list import project_list_bp # Projects page list
    from app.modules.projects.routes.project_overlay import project_overlay_bp # Projects detail overlay
    from app.modules.projects.routes.project_preproduction import project_preproduction_bp # Pre-Production phase backend
    from app.modules.projects.routes.project_notes import project_notes_bp  # Project Notes & Site Visits
    from app.modules.projects.routes.chat_tray import chat_tray_bp  # Global Chat tray
    from app.modules.projects.blueprint import project_assets  # projects module static assets
    from app.modules.profile.blueprint import profile_assets
    from app.modules.achievements.blueprint import achievements_assets
    from app.modules.admin.blueprint import admin_assets
    from app.modules.blog.blueprint import blog_assets
    from app.modules.feedback.blueprint import feedback_assets
    from app.modules.wiki.blueprint import wiki_assets
    from app.modules.file_templates.blueprint import file_templates_assets
    from app.modules.client_directory.blueprint import client_directory_assets
    from app.modules.dashboard.blueprint import dashboard_assets
    from app.modules.time_tracking.blueprint import time_tracking_assets
    from app.modules.client_servicing.blueprint import client_servicing_assets
    from app.modules.digital_innovation.blueprint import digital_innovation_assets
    from app.modules.hse.blueprint import hse_assets
    from app.modules.digital_innovation.models import DiProject, DiFeature, DiFeatureStep, DiStepTemplate, DiCostEntry, DiSetting, DiPeriodSnapshot, DiIntakeItem  # registers the tables with SQLAlchemy
    from app.modules.hse.models import HseEntry, HseSchedule, HseAsset, HseReference, HsePerson, HseRefCounter, HseAttachment  # registers the tables with SQLAlchemy
    from app.modules.digital_innovation.routes import board as di_board  # registers board routes on digital_innovation_bp
    from app.modules.digital_innovation.routes import projects as di_projects  # registers project-create route on digital_innovation_bp
    from app.modules.digital_innovation.routes import features as di_features  # registers feature routes on digital_innovation_bp
    from app.modules.digital_innovation.routes import templates as di_templates  # registers Edit Templates routes on digital_innovation_bp
    from app.modules.digital_innovation.routes import archive as di_archive  # registers the Archive screen route on digital_innovation_bp
    from app.modules.digital_innovation.routes import intake as di_intake  # registers the Incoming tray's promote/dismiss routes on digital_innovation_bp
    from app.modules.digital_innovation.routes import costs as di_costs  # registers Cost breakdown ledger CRUD + Excel export routes on digital_innovation_bp
    from app.modules.digital_innovation.routes import performance as di_performance  # registers the Performance page (weekly/monthly/quarterly rollups) on digital_innovation_bp
    from app.modules.digital_innovation.routes.blueprint import digital_innovation_bp
    from app.modules.client_servicing.routes import table as client_servicing_table  # registers routes on client_servicing_bp
    from app.modules.client_servicing.routes import edit as client_servicing_edit  # field-update endpoint
    from app.modules.client_servicing.routes import scopes_admin as client_servicing_scopes_admin  # CS Scopes CRUD + quick-add
    from app.modules.client_servicing.routes import layout as client_servicing_layout  # per-user column widths/order
    from app.modules.client_servicing.routes import dashboard as client_servicing_dashboard  # Dashboard landing (first rail entry)
    from app.modules.client_servicing.routes import invoicing as client_servicing_invoicing  # Invoicing sidebar section 
    from app.modules.client_servicing.routes import calendar as client_servicing_calendar  # Calendar sidebar section
    from app.modules.client_servicing.routes import close as client_servicing_close  # close / close-out endpoint
    from app.modules.client_servicing.routes import closed as client_servicing_closed  # Closed Projects sidebar section
    from app.modules.client_servicing.routes.blueprint import client_servicing_bp
    from app.modules.hse.routes import registers as hse_registers  # registers the register surface on hse_bp
    from app.modules.hse.routes import entries as hse_entries  # registers the entry overlay + save endpoints on hse_bp
    from app.modules.hse.routes import attachments as hse_attachments  # registers the NAS attachment endpoints on hse_bp
    from app.modules.hse.routes import lists as hse_lists  # registers the officer's own reference lists on hse_bp
    from app.modules.hse.routes import schedules as hse_schedules  # registers the Schedule tab on hse_bp
    from app.modules.hse.routes import calendar as hse_calendar  # registers the calendar month/agenda/day on hse_bp
    from app.modules.hse.routes import overview as hse_overview  # registers the module's front page on hse_bp
    from app.modules.hse.routes import performance as hse_performance  # registers My performance and its report on hse_bp
    from app.modules.hse.routes.blueprint import hse_bp


    app.register_blueprint(core_bp)  # shared templates + static
    app.register_blueprint(notifications_bp)
    app.register_blueprint(main)
    app.register_blueprint(auth)
    app.register_blueprint(admin_bp)
    app.register_blueprint(blog_bp)
    app.register_blueprint(feedback_bp)
    app.register_blueprint(signal_tray_bp)
    app.register_blueprint(wiki_bp)
    app.register_blueprint(api_bp)  # /api/* poll routes
    app.register_blueprint(profile_bp)
    app.register_blueprint(admin_achievements_bp)
    app.register_blueprint(wizard_bp)
    app.register_blueprint(file_templates_bp)
    app.register_blueprint(sse_bp)
    app.register_blueprint(client_directory_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(time_tracking_bp)
    app.register_blueprint(transfer_bp)
    app.register_blueprint(project_list_bp)
    app.register_blueprint(project_overlay_bp)
    app.register_blueprint(project_preproduction_bp)
    app.register_blueprint(project_notes_bp)
    app.register_blueprint(chat_tray_bp)
    app.register_blueprint(project_assets)
    app.register_blueprint(profile_assets)
    app.register_blueprint(achievements_assets)
    app.register_blueprint(admin_assets)
    app.register_blueprint(blog_assets)
    app.register_blueprint(feedback_assets)
    app.register_blueprint(wiki_assets)
    app.register_blueprint(file_templates_assets)
    app.register_blueprint(client_directory_assets)
    app.register_blueprint(dashboard_assets)
    app.register_blueprint(time_tracking_assets)
    app.register_blueprint(client_servicing_assets)
    app.register_blueprint(digital_innovation_assets)
    app.register_blueprint(digital_innovation_bp)
    app.register_blueprint(client_servicing_bp)
    app.register_blueprint(hse_assets)
    app.register_blueprint(hse_bp)

    @app.context_processor
    def inject_notifications():
        import json
        from flask import url_for
        from flask_login import current_user
        from app.modules.core.shared.models import Notification, NotificationSound
        from app.modules.core.shared.lib.capabilities import effective_user

        if current_user.is_authenticated:
            # Use the emulated user's ID when in emulation mode
            notif_user_id = effective_user().id

            active_notifications = Notification.query.filter_by(
                recipient_id=notif_user_id,
                is_archived=False
            ).order_by(Notification.created_at.desc()).all()

            archived_notifications = Notification.query.filter_by(
                recipient_id=notif_user_id,
                is_archived=True
            ).order_by(Notification.created_at.desc()).limit(50).all()

            unread_count = sum(1 for n in active_notifications if not n.is_read)

            # Attach each pending edit-access request id to its notification
            # so base.html can show inline Approve/Deny buttons. One query total,
            # keyed by (project_id, requester); None means already decided.
            edit_access_notif_ids = [
                n.id for n in active_notifications if n.notification_type == 'edit_access_requested'
            ]
            if edit_access_notif_ids:
                from app.modules.core.shared.models import ProjectEditAccessRequest
                pending_by_key = {
                    (r.project_id, r.user_id): r.id
                    for r in ProjectEditAccessRequest.query.filter_by(status='pending').all()
                }
                for n in active_notifications:
                    if n.notification_type == 'edit_access_requested':
                        n.edit_access_request_id = pending_by_key.get((n.project_id, n.triggered_by_id))

            # Sound prefs from the notification_prefs JSON — needed on every
            # page, since the global poll loop in base.html plays the sound.
            try:
                prefs = json.loads(current_user.notification_prefs or '{}')
            except (ValueError, TypeError):
                prefs = {}

            sound_url = None
            sound = NotificationSound.query.get(prefs['sound_id']) if prefs.get('sound_id') else None
            if sound:
                sound_url = url_for('static', filename=f'sounds/{sound.filename}')

            sound_prefs = {
                'enabled': prefs.get('sound_enabled', True),
                'volume': prefs.get('sound_volume', 1.0),
                'url': sound_url,  # None = no file chosen yet, JS falls back to the synthesized chime
            }

            return {
                'user_notifications': active_notifications,
                'archived_notifications': archived_notifications,
                'unread_count': unread_count,
                'sound_prefs': sound_prefs
            }
        return {
            'user_notifications': [],
            'archived_notifications': [],
            'unread_count': 0,
            'sound_prefs': {'enabled': True, 'volume': 1.0, 'url': None}
        }
    
    def _active_badge_image(user):
        """The user's active badge image filename, or None. Cached on flask.g
        per request (a table can render one designer many times). A Jinja global,
        not a context processor — those don't reach macros imported without
        `with context`, so user_avatar() couldn't see it."""
        from flask import g
        from app.modules.core.shared.models import UserDisplaySettings, UserAchievement

        if not hasattr(g, '_active_badge_cache'):
            g._active_badge_cache = {}

        if user.id not in g._active_badge_cache:
            badge_image = None
            settings = UserDisplaySettings.query.filter_by(user_id=user.id).first()
            if settings and settings.active_badge_id:
                ua = UserAchievement.query.get(settings.active_badge_id)
                # The achievement may have no uploaded image yet — nothing to
                # overlay then, same as the fallback trophy elsewhere.
                if ua and ua.achievement.badge_image:
                    badge_image = ua.achievement.badge_image
            g._active_badge_cache[user.id] = badge_image

        return g._active_badge_cache[user.id]

    app.jinja_env.globals['active_badge_image'] = _active_badge_image

    def _nas_deliverable_url(deliverable, project, project_customer=None, region_slug=None):
        """DSM 7 File Station deep-link to a deliverable's Design Files folder,
        or None if NAS is unconfigured. Standard: .../Design Files/{name};
        C&CM (pass project_customer + region_slug): .../{Region}/{Customer}/{name}.
        launchParam is double-encoded so & in folder names survives Synology's parse."""
        from urllib.parse import quote
        from app.modules.core.shared.services.nas import REGION_DISPLAY

        base = (app.config.get('NAS_WEB_URL') or
                f"https://{app.config.get('NAS_HOST', '')}:{app.config.get('NAS_PORT', '5001')}")

        root        = app.config.get('NAS_PROJECT_ROOT', '/Projects')
        year        = project.created_at.year
        client      = project.client_brand.name if project.client_brand else 'Unknown Client'
        proj_name   = project.name
        design_root = f'{root}/{year}/{client}/{proj_name}/Design Files'

        if project_customer and region_slug:
            region_display = REGION_DISPLAY.get((region_slug or '').lower(), (region_slug or '').title())
            customer_name  = project_customer.customer.name
            folder_path    = f'{design_root}/{region_display}/{customer_name}/{deliverable.name}'
        else:
            folder_path = f'{design_root}/{deliverable.name}'

        # DSM 7 deep-link: double-encode so & in folder names survives launchParam parse
        path_encoded  = quote(folder_path, safe='/')      # & → %26, space → %20
        launch_param  = quote(f'opendir={path_encoded}', safe='/')   # % → %25
        return (f'{base.rstrip("/")}/index.cgi'
                f'?launchApp=SYNO.SDS.App.FileStation3.Instance'
                f'&launchParam={launch_param}')

    app.jinja_env.globals['nas_deliverable_url'] = _nas_deliverable_url

    def _nas_project_url(project):
        """DSM 7 File Station deep-link to a project's root folder, or None if
        NAS is unconfigured. Separate from _nas_deliverable_url — no 'Design
        Files' suffix."""
        from urllib.parse import quote

        base = (app.config.get('NAS_WEB_URL') or
                f"https://{app.config.get('NAS_HOST', '')}:{app.config.get('NAS_PORT', '5001')}")

        root      = app.config.get('NAS_PROJECT_ROOT', '/Projects')
        year      = project.created_at.year
        client    = project.client_brand.name if project.client_brand else 'Unknown Client'
        proj_name = project.name
        folder_path = f'{root}/{year}/{client}/{proj_name}'

        path_encoded = quote(folder_path, safe='/')
        launch_param = quote(f'opendir={path_encoded}', safe='/')
        return (f'{base.rstrip("/")}/index.cgi'
                f'?launchApp=SYNO.SDS.App.FileStation3.Instance'
                f'&launchParam={launch_param}')

    app.jinja_env.globals['nas_project_url'] = _nas_project_url

    # CS sidebar icon gates through the same access check the CS routes use.
    # A Jinja global (not a context processor) so it's reusable anywhere.
    from app.modules.client_servicing.lib.access import can_access_client_servicing
    app.jinja_env.globals['can_access_client_servicing'] = can_access_client_servicing

    # Capability gate. Templates ask can('view_finance') instead of listing
    # roles; role_labels drives every role picker from the same map.
    from app.modules.core.shared.lib.capabilities import can, ROLE_LABELS, role_label
    app.jinja_env.globals['can'] = can
    app.jinja_env.globals['role_labels'] = ROLE_LABELS
    app.jinja_env.globals['role_label'] = role_label

    @app.context_processor
    def inject_effective_user():
        from flask import session
        from app.modules.core.shared.lib.capabilities import effective_user

        is_emulating = bool(session.get('emulating_user_id')) and getattr(current_user, 'role', None) == 'admin'
        return {
            'effective_user': effective_user(),
            'is_emulating': is_emulating,
        }
    

    WIZARD_LAUNCH_DATE = datetime (2026, 7, 5)

    @app.context_processor
    def inject_wizard_state():
        if current_user.is_authenticated and (not current_user.wizard_completed or not current_user.avatar_step_completed):
            return {
                'show_wizard': True,
                'show_name_step': current_user.created_at >= WIZARD_LAUNCH_DATE,
                # True only for accounts that already finished the wizard before
                # the avatar step existed — they should land straight on that one
                # new step, not replay steps 1-3 they've already done.
                'avatar_step_only': current_user.wizard_completed and not current_user.avatar_step_completed,
            }
        return {'show_wizard': False, 'show_name_step': False, 'avatar_step_only': False}
    
    def dubai_time(dt):
        if dt is None:
            return '_'
        # Accept an ISO string too (dashboard's What Changed passes timestamps
        # as isoformat strings for the JSON API); real datetimes are unchanged.
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)
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
          title_match = re.search(r'<title>(.*?)</title>', html, re.DOTALL)
          if title_match:
              from urllib.parse import quote
              response.headers['X-Page-Title'] = quote(title_match.group(1).strip())
          m = re.search(
              r'<main[^>]+id=["\']main-content["\'][^>]*>(.*?)</main>',
              html, re.DOTALL
          )
          if m:
              content = m.group(1)
              # A page's own {% block extra_js %} renders after </main>, so it's
              # outside the sliced content. Markers pull in just that block —
              # never the global scripts, which must not run twice.
              extra_js_match = re.search(
                  r'<!--\s*SPA:EXTRA_JS:START\s*-->(.*?)<!--\s*SPA:EXTRA_JS:END\s*-->',
                  html, re.DOTALL
              )
              if extra_js_match:
                  content += extra_js_match.group(1)
              response.set_data(content)
        return response


    return app