from flask import Flask, g, request
from config import Config
from datetime import timezone, timedelta, datetime
import os

from app.modules.core.shared.extensions import db, login_manager, mail


def _compute_static_version():
    """Cache-busting stamp for STATIC_VERSION — see the long comment in
    create_app() for the git-hash and time.time() history. This is the
    24 Aug 2026 fix for the bug those two attempts left in place: gunicorn
    runs multiple worker processes in production, and time.time() at
    process startup gives EACH worker its own value a few seconds apart
    (whenever they happened to boot). polling.js's init() (fires on every
    page load AND every SPA nav) compares the STATIC_VERSION baked into
    the page against a fresh /api/version fetch, and reloads on any
    mismatch — with requests round-robining across workers, the page-
    render worker and the /api/version-answering worker frequently
    disagreed, so real users saw a "refresh loop" and everything felt
    slow (constant full-page reloads instead of the app's normal SPA
    partial-swap nav). Never showed up locally because `python run.py` is
    a single process — nothing for it to disagree with.

    Fix: derive the stamp from the source tree's own newest file mtime
    instead of wall-clock time at process start. Every worker reads the
    same files off the same disk, so they always compute the identical
    value — no more cross-worker mismatch — and it still changes on the
    next deploy, since `git pull` rewrites the mtime of anything that
    changed. No new env var or GEVENT_WORKER branch needed, so it doesn't
    reintroduce either problem the two earlier attempts ran into.

    Ported onto refactor/vsa 24 Aug 2026 alongside main — this branch's
    own module restructuring (app.modules.core.shared.extensions etc.)
    is untouched by this fix; only the STATIC_VERSION computation itself
    changed.
    """
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
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    from app.live_events import init_live_events
    init_live_events()
    from app.sse_relay import init_sse_relay
    init_sse_relay(app)  # no-op unless GEVENT_WORKER=1 — see sse_relay.py

    # Cache-busting query string for every static <link>/<script> tag in
    # base.html (?v={{ config.STATIC_VERSION }}). Originally the short git
    # commit hash (computed once at process startup) everywhere, gated on
    # whether it could be worth telling "real production" apart from local
    # dev — but that gate was tried with GEVENT_WORKER=1 as the signal (the
    # same flag run.py uses for real prod's gevent monkey-patching) and
    # turned out to be unreliable: Ezekiel also sets GEVENT_WORKER=1 in his
    # LOCAL shell, because run.py's gevent patching is what makes the SSE
    # live-update relay (app/sse_relay.py) work at all, and he wants that
    # locally too. So GEVENT_WORKER=1 does not uniquely mean "real
    # production" — using it as the branch condition just silently kept
    # local dev on the frozen-git-hash path anyway.
    #
    # The git hash was always the wrong signal for local dev regardless:
    # CSS/JS get hand-edited and tested against a locally running server
    # WITHOUT a commit for every change (that's the whole point of
    # iterating locally). Since the hash only moves on a new commit,
    # STATIC_VERSION stayed frozen at whatever commit HEAD was on for an
    # entire editing session, so every static asset URL was byte-identical
    # across dozens of edits — the browser's HTTP cache correctly, and
    # indefinitely, kept serving old CSS/JS, surviving hard refreshes and
    # even brand-new tabs, since the URL genuinely never changed. This is
    # what caused the 16 Jul 2026 "This Week Load has no styling" saga (see
    # CLAUDE.md) — the served bytes and the file on disk were both correct
    # the whole time, only the browser's cached copy of the frozen-URL
    # response was stale. Confirmed via `git status`/`git rev-parse HEAD`
    # directly: dashboard.css showed as modified/uncommitted while
    # STATIC_VERSION matched HEAD exactly — then confirmed AGAIN after a
    # first attempted fix (branching on GEVENT_WORKER) still showed the
    # frozen hash, traced to Ezekiel's local GEVENT_WORKER=1 export.
    #
    # Fix (16 Jul 2026): always use the current timestamp at process
    # startup, everywhere, no GEVENT_WORKER branch at all. Production
    # deploys are always `git pull && systemctl restart` together anyway
    # (see Infrastructure section below), so a restart-time timestamp
    # changes exactly when a deploy happens there too — the git hash's
    # only actual benefit was cosmetic traceability (eyeballing which
    # commit a running instance's assets match), never something anything
    # else in the app depends on, and it's not worth reintroducing a
    # second env-var signal just to get it back. Still requires
    # restarting the local Flask process to pick up new CSS/JS (there's
    # no cheaper fix without moving to per-request computation, which
    # would kill browser caching for stable assets too) — but a restart
    # is something Ezekiel already does periodically, whereas a new git
    # commit is not.
    #
    # Second fix (24 Aug 2026): time.time() at process startup turned out
    # to have the SAME class of bug the git hash fix above was solving
    # for — just triggered by multiple gunicorn workers instead of by
    # git commits. See _compute_static_version() above for the full
    # story; short version is every worker computed its own timestamp a
    # few seconds apart, and polling.js's cross-worker version check
    # treated that disagreement as "the app was redeployed," causing
    # constant spurious full-page reloads in production only (local dev
    # is a single process, so there was nothing to disagree with).
    app.config['STATIC_VERSION'] = _compute_static_version()

    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    from app.models import (User, Project, ProjectDesigner, Scope, Client, Customer, DeliverableType, DeliverableTypeDiscipline, ProjectRegion, ProjectCustomer, Deliverable, DeliverableAssignment, ActivityLog, DesignType, DesignDirection, ProjectFile, ProjectSubmission, ProjectSubmissionDeliverable, ProjectSubmissionFile, ProjectRevision, ProjectRevisionDeliverable, BlogPost, BlogComment, FeatureRequest, FeatureRequestUpvote, FeatureRequestComment, BugReport, BugReportComment)
    from app.modules.core.shared.blueprint import core as core_bp
    from app.routes import main
    from app.modules.auth.routes.auth import auth
    from app.routes.notifications import notifications_bp
    from app.models import Notification
    from flask_login import current_user
    from app.routes.admin import admin_bp
    from app.routes.blog import blog_bp
    from app.routes.feedback import feedback_bp
    from app.routes.wiki import wiki_bp
    from app.routes.api import api_bp  # polling endpoints for live dashboard/detail updates
    from app.routes.profile import profile_bp  # profile view/edit routes (split out of auth.py 3 Jul 2026)
    from app.routes.admin_achievements import admin_achievements_bp  # achievement system admin panel (Phase 7)
    from app.routes.wizard import wizard_bp
    from app.routes.file_templates import file_templates_bp
    from app.routes.sse import sse_bp  # Stage 4 of the SSE redesign — live push routes
    from app.routes.client_directory import client_directory_bp  # Client Directory — companies + contacts
    from app.routes.dashboard import dashboard_bp  # role-based dashboard (backend only for now)
    from app.routes.time_tracking import time_tracking_bp  # project/deliverable business-hours breakdown page
    from app.routes.projects_transfer import transfer_bp  # C&CM deliverable transfer (move / duplicate to new customer)
    from app.routes.project_list import project_list_bp # Projects page list
    from app.routes.project_overlay import project_overlay_bp # Projects detail overlay
    from app.routes.project_preproduction import project_preproduction_bp # Pre-Production phase backend (13 Aug 2026)
    from app.routes.project_notes import project_notes_bp  # Project Notes & Site Visits


    app.register_blueprint(core_bp)  # shared templates (later static) on the Jinja search path
    app.register_blueprint(notifications_bp)
    app.register_blueprint(main)
    app.register_blueprint(auth)
    app.register_blueprint(admin_bp)
    app.register_blueprint(blog_bp)
    app.register_blueprint(feedback_bp)
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

    @app.context_processor
    @app.context_processor
    def inject_notifications():
        import json
        from flask import session, url_for
        from flask_login import current_user
        from app.models import Notification, NotificationSound

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

            # Resolve this user's saved sound prefs (enabled/volume/chosen file)
            # from the same notification_prefs JSON blob used on the account page.
            # Every page needs this — not just /account — because the 30-second
            # poll loop that actually plays the sound runs globally via base.html.
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
        """
        Resolves the given user's active badge image filename, or None.
        Cached on flask.g per request: a dashboard table can easily render
        the same designer 10+ times across different rows, and without this
        cache that would be 10+ identical UserDisplaySettings +
        UserAchievement queries for the exact same answer. g is
        request-scoped, so the cache never leaks between users or requests.

        Registered below as a Jinja GLOBAL (app.jinja_env.globals), NOT a
        @app.context_processor. That distinction matters and caused a real
        bug: context processors only inject into the per-request render
        context, which is visible to directly-rendered templates and to
        {% include %}'d ones (context passes by default there) — but NOT to
        templates pulled in via {% from '_macros.html' import user_avatar %},
        since Jinja's import statement does not pass context unless every
        single call site adds `with context`. The user_avatar()/
        user_avatar_visual() macros in _macros.html are imported this way
        in ~10 templates, so as a context processor this function was
        UndefinedError-ing everywhere it was actually used. A true Jinja
        global is compiled into every template's namespace unconditionally,
        macros included, regardless of how they were imported — so this is
        the fix, not just a workaround for one call site.
        """
        from flask import g
        from app.models import UserDisplaySettings, UserAchievement

        if not hasattr(g, '_active_badge_cache'):
            g._active_badge_cache = {}

        if user.id not in g._active_badge_cache:
            badge_image = None
            settings = UserDisplaySettings.query.filter_by(user_id=user.id).first()
            if settings and settings.active_badge_id:
                ua = UserAchievement.query.get(settings.active_badge_id)
                # Defensive: the achievement itself might not have an
                # uploaded image yet (Phase 7 admin upload didn't exist
                # when this was earned) — in that case there's nothing
                # to overlay, same as the tile fallback trophy elsewhere.
                if ua and ua.achievement.badge_image:
                    badge_image = ua.achievement.badge_image
            g._active_badge_cache[user.id] = badge_image

        return g._active_badge_cache[user.id]

    app.jinja_env.globals['active_badge_image'] = _active_badge_image

    def _nas_deliverable_url(deliverable, project, project_customer=None, region_slug=None):
        """
        Returns the DSM 7 File Station deep-link URL for a deliverable's Design Files folder,
        or None if NAS_WEB_URL is not configured.

        Standard brief:  .../Design Files/{deliverable.name}
        C&CM brief:      .../Design Files/{Region}/{Customer}/{deliverable.name}
        Pass project_customer (ProjectCustomer ORM) + region_slug for C&CM deliverables.

        Uses the same double-encoded launchParam format as get_nas_link() — & in folder
        names survives Synology's internal sub-param parse that way.
        """
        from urllib.parse import quote
        from app.nas import REGION_DISPLAY

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
        """Returns the DSM 7 File Station deep-link URL for a project's root
        folder, or None if NAS_WEB_URL is not configured. Same launchParam
        double-encoding as _nas_deliverable_url()/get_nas_link() — kept as
        its own function rather than calling _nas_deliverable_url with no
        deliverable, since the two produce genuinely different paths (this
        one has no 'Design Files/...' suffix at all).
        """
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
        # Accept an ISO-format string too, not just a real datetime object.
        # Added for dashboard.py's What Changed card: _compute_what_changed()
        # returns 'timestamp' as e.created_at.isoformat() (a plain string)
        # because that same dict is also returned as-is from the JSON API
        # endpoint (jsonify can't serialize a raw datetime). Every OTHER
        # existing caller of this filter passes a real datetime and hits the
        # isinstance check below as False, so their behavior is unchanged —
        # this is purely additive.
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
              # Page-specific scripts (each template's own {% block extra_js %})
              # render AFTER </main> in the full page, so they were never part
              # of the slice above — meaning sidebar.js's execScripts() had
              # nothing to find, and a page whose JS lives in extra_js (rather
              # than loading globally in base.html, like detail.js/polling.js
              # do) got zero of its own JS on an SPA-navigated visit. Markers
              # bound just that one block so this can never accidentally sweep
              # up sidebar.js/polling.js/etc., which already load globally and
              # must NOT be re-executed a second time (duplicate listeners).
              extra_js_match = re.search(
                  r'<!--\s*SPA:EXTRA_JS:START\s*-->(.*?)<!--\s*SPA:EXTRA_JS:END\s*-->',
                  html, re.DOTALL
              )
              if extra_js_match:
                  content += extra_js_match.group(1)
              response.set_data(content)
        return response


    return app