import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv(override=True)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:

    SECRET_KEY = os.environ.get('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    MAX_CONTENT_LENGTH = 900 * 1024 * 1024  # 900 MB file upload limit

    # Session persistence — stay logged in for 30 days unless password changes
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'

    # Email configuration — reads from .env so switching providers requires no code changes
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.resend.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 465))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'false').lower() == 'true'
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'true').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', os.environ.get('MAIL_USERNAME'))
    MAIL_ENABLED = os.environ.get('MAIL_ENABLED', 'false').lower() == 'true'

    # NAS configuration — Synology DS925+ File Station API
    NAS_HOST = os.environ.get('NAS_HOST', '10.101.21.76')
    NAS_PORT = os.environ.get('NAS_PORT', '5001')
    NAS_USERNAME = os.environ.get('NAS_USERNAME')
    NAS_PASSWORD = os.environ.get('NAS_PASSWORD')
    NAS_PROJECT_ROOT = os.environ.get('NAS_PROJECT_ROOT', '/Projects')
    # Base URL for File Station deep links — set to QuickConnect URL for external access.
    # e.g. NAS_WEB_URL=https://quickconnect.to/YOUR_QUICKCONNECT_ID
    # Defaults to LAN IP (https://{NAS_HOST}:{NAS_PORT}) if not set.
    NAS_WEB_URL = os.environ.get('NAS_WEB_URL')

    # Off-LAN fallback for the NAS API itself (not browse links — that's
    # NAS_WEB_URL above). Used only when NAS_HOST is unreachable, e.g. a
    # local dev instance running away from the office network. Points at
    # a Cloudflare Tunnel hostname reverse-proxying straight to the NAS
    # (same tunnel as app.vitamin-e.work / ssh.vitamin-e.work — see
    # SERVER_ACCESS.md), gated by a Cloudflare Access Service Token since
    # this is machine-to-machine, not an interactive login. All three must
    # be set together for the fallback to work — added 20 Aug 2026 after
    # QuickConnect (NAS_WEB_URL's original purpose) turned out to only
    # serve a browser-oriented relay page to plain API clients.
    NAS_TUNNEL_HOST = os.environ.get('NAS_TUNNEL_HOST')
    CF_ACCESS_CLIENT_ID = os.environ.get('CF_ACCESS_CLIENT_ID')
    CF_ACCESS_CLIENT_SECRET = os.environ.get('CF_ACCESS_CLIENT_SECRET')

    # Dev-only tools — set DEV_TOOLS_ENABLED=true in .env on your local machine only.
    # NEVER set this on the production server — it exposes destructive data operations.
    DEV_TOOLS_ENABLED = os.environ.get('DEV_TOOLS_ENABLED', 'false').lower() == 'true'
