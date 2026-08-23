import json
import time
import requests
import urllib3
from flask import current_app

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Module-level session with trust_env=False — prevents requests from reading
# Windows system proxy / HTTPS_PROXY env vars, which cause HTTP 407 errors when
# trying to reach the local NAS over LAN. verify=False handles the self-signed cert.
_NAS_SESSION = requests.Session()
_NAS_SESSION.trust_env = False
_NAS_SESSION.verify = False

# Sticky NAS host, set the first time _get_session() successfully connects
# (LAN IP or the NAS_WEB_URL fallback). (host, port) tuple, port is None
# for the fallback path (NAS_WEB_URL is used as a full base URL, not a
# bare host — no port to append). None until the first login. Kept for
# the life of the process, not per-request — Ezekiel's call: a confirmed-
# unreachable LAN IP shouldn't eat a fresh ~10s timeout on every single
# NAS call for the rest of the run when running off the office network.
_NAS_HOST_OVERRIDE = None

from app.models import ProjectRegion, ProjectCustomer, Customer, Deliverable

# Canonical display names for region slugs stored in the DB
REGION_DISPLAY = {
    'uae':     'UAE',
    'ksa':     'KSA',
    'kuwait':  'Kuwait',
    'qatar':   'Qatar',
    'bahrain': 'Bahrain',
    'oman':    'Oman',
}

# --------- Authentication ---------------

def _nas_url(host, port, path):
    """Build a NAS webapi URL from _get_session()'s (host, port). port is
    None when running against NAS_WEB_URL (a QuickConnect base URL already
    carries its own host + ID path segment, e.g. quickconnect.to/vitaminNAS26,
    and never needs an explicit port appended) — port is only appended for
    the LAN-IP case."""
    if port:
        return f'https://{host}:{port}{path}'
    return f'https://{host}{path}'

def _get_session():
    """Login to Synology File Station API, return (sid, host, port).

    Tries NAS_HOST/NAS_PORT (the office LAN IP) first — server and NAS share
    the office LAN in production, so this is the fast, expected path. Falls
    back to NAS_WEB_URL (a Synology QuickConnect URL, e.g.
    https://quickconnect.to/vitaminNAS26) only on a connection-level failure
    (ConnectionError/Timeout) — the real case this covers is the app running
    off the office network (a local dev instance elsewhere), where NAS_HOST
    is simply unreachable. NAS_WEB_URL is used as a full base URL, no port
    appended (Ezekiel's call, M10, 20 Aug 2026) — see _nas_url() above.

    A bad login (wrong credentials) is NOT a connection failure — it still
    raises the existing RuntimeError below without ever trying the fallback,
    since QuickConnect wouldn't fix bad credentials either.

    Whichever host succeeds is cached in _NAS_HOST_OVERRIDE for the rest of
    this process's life (Ezekiel's call) — so a confirmed-unreachable LAN IP
    doesn't eat a fresh ~10s timeout on every single NAS call for the rest
    of the run.
    """
    return _login_with_session('FileStation')


def _login_with_session(session_name):
    """
    Shared LAN-IP/NAS_TUNNEL_HOST fallback + _NAS_HOST_OVERRIDE caching
    logic behind _get_session() — extracted 21 Aug 2026 so
    resolve_drive_file_id() (Synology Drive) can reuse the exact same
    tested fallback path instead of a second inline copy that could drift
    out of sync. session_name is the Synology 'session' login param —
    'FileStation' for _get_session()'s callers, 'SynologyDrive' for Drive
    calls (Synology scopes which app an sid authorizes by this param, so
    a FileStation sid isn't assumed to also work for Drive calls).
    Returns (sid, host, port); raises RuntimeError on failure.
    """
    global _NAS_HOST_OVERRIDE

    if _NAS_HOST_OVERRIDE is not None:
        host, port = _NAS_HOST_OVERRIDE
    else:
        host = current_app.config['NAS_HOST']
        port = current_app.config['NAS_PORT']

    def _attempt_login(host, port):
        return _NAS_SESSION.get(
            _nas_url(host, port, '/webapi/auth.cgi'),
            params={
                'api':     'SYNO.API.Auth',
                'version': '3',
                'method':  'login',
                'account': current_app.config['NAS_USERNAME'],
                'passwd':  current_app.config['NAS_PASSWORD'],
                'session': session_name,
                'format':  'sid',
            },
            timeout=10
        )

    try:
        resp = _attempt_login(host, port)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as conn_exc:
        # Fallback: NAS_TUNNEL_HOST is a Cloudflare Tunnel hostname (e.g.
        # nas.vitamin-e.work) that reverse-proxies straight to the NAS —
        # same tech as app.vitamin-e.work / ssh.vitamin-e.work, gated by a
        # Cloudflare Access Service Token instead of the interactive login
        # those use, since this is a script talking to it, not a browser.
        # (QuickConnect was tried first, 20 Aug 2026 — it only serves a
        # browser-oriented relay landing page to plain HTTP clients, not a
        # usable webapi proxy, so it was replaced with this.)
        tunnel_host = current_app.config.get('NAS_TUNNEL_HOST')
        client_id = current_app.config.get('CF_ACCESS_CLIENT_ID')
        client_secret = current_app.config.get('CF_ACCESS_CLIENT_SECRET')
        # Nothing left to try if there's no fallback configured, or if
        # (host, port) we just failed on WAS already the fallback (cached
        # from _NAS_HOST_OVERRIDE) — don't loop between two dead ends.
        if not tunnel_host or port is None:
            raise RuntimeError(f'NAS unreachable (tried {host}): {conn_exc}')
        if client_id and client_secret:
            _NAS_SESSION.headers.update({
                'CF-Access-Client-Id': client_id,
                'CF-Access-Client-Secret': client_secret,
            })
        host = tunnel_host.split('://', 1)[-1].rstrip('/')
        port = None
        try:
            resp = _attempt_login(host, port)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as conn_exc2:
            raise RuntimeError(f'NAS unreachable on both LAN IP and NAS_TUNNEL_HOST ({host}): {conn_exc2}')

    # A successful connection doesn't guarantee a JSON webapi response — a
    # misconfigured Access policy or bad service token hands back an HTML
    # error page instead of proxying to auth.cgi (see the CF-Access-Client-*
    # env vars above). Surface what came back instead of letting a raw
    # JSONDecodeError bubble up as an unhandled 500 (added 20 Aug 2026).
    try:
        data = resp.json()
    except ValueError:
        raise RuntimeError(
            f'NAS login at {host!r} returned non-JSON (status {resp.status_code}): '
            f'{resp.text[:300]!r}'
        )
    if not data.get('success'):
        raise RuntimeError(f"NAS login failed: {data}")

    _NAS_HOST_OVERRIDE = (host, port)
    return data['data']['sid'], host, port

def _logout(host, port, sid):
    """Logout and invalidate the session token."""
    _NAS_SESSION.get(
        _nas_url(host, port, '/webapi/auth.cgi'),
        params={
            'api':     'SYNO.API.Auth',
            'version': '1',
            'method':  'logout',
            'session': 'FileStation',
            '_sid':    sid,
        },
        timeout=5
    )

# ------ Folder Operations --------

def _rename_folder(host, port, sid, folder_path, new_name):
    """
    Rename a single NAS folder in-place.
    folder_path is the FULL path to the existing folder;
    new_name is just the new folder name (not a full path).
    Logs a warning on failure — never raises.
    """
    resp = _NAS_SESSION.get(
        _nas_url(host, port, '/webapi/entry.cgi'),
        params={
            'api':     'SYNO.FileStation.Rename',
            'version': '2',
            'method':  'rename',
            'path':    json.dumps([folder_path]),
            'name':    json.dumps([new_name]),
            '_sid':    sid,
        },
        timeout=10,
    )
    data = resp.json()
    if not data.get('success'):
        current_app.logger.warning(
            f'NAS rename failed: {folder_path!r} → {new_name!r}: {data}'
        )

def _create_folder(host, port, sid, parent_path, folder_name):
    """
    Create a single folder inside parent_path.
    Silently succeeds if folder already exists (force_parent=true).
    """
    _NAS_SESSION.get(
        _nas_url(host, port, '/webapi/entry.cgi'),
        params={
            'api':          'SYNO.FileStation.CreateFolder',
            'version':      '2',
            'method':       'create',
            'folder_path':  json.dumps([parent_path]),
            'name':         json.dumps([folder_name]),
            'force_parent': 'true',
            '_sid':         sid,
        },
        timeout=10
    )

def _build_folder_tree(host, port, sid, project):
    """
    Build the full folder tree for a project on the NAS.
    Determines structure based on project.brief_type (Standard or C&CM).
    Year folder is auto-created if this is the first project of that year.
    """
    root         = current_app.config['NAS_PROJECT_ROOT']
    year         = project.created_at.year
    year_path    = f'{root}/{year}'
    client_name  = project.client_brand.name if project.client_brand else 'Unknown Client'
    client_path  = f'{year_path}/{client_name}'
    project_path = f'{client_path}/{project.name}'

    _create_folder(host, port, sid, root, str(year))
    _create_folder(host, port, sid, year_path, client_name)
    _create_folder(host, port, sid, client_path, project.name)

    for folder in ['Quotes & Invoices', 'Submissions', 'Reference Files', 'Design Files', 'Close Out Report']:
        _create_folder(host, port, sid, project_path, folder)

    design_path = f'{project_path}/Design Files'

    if project.brief_type == 'ccm':
        _build_ccm_design_folders(host, port, sid, design_path, project)
    else:
        _build_standard_design_folders(host, port, sid, design_path, project)

def _build_standard_design_folders(host, port, sid, design_path, project):
    """
    Standard Brief:
       Design Files/
          {Deliverable}/
              3D Files · Renders · Artwork · DWG · PDF  (based on project teams)
    """
    deliverables = Deliverable.query.filter_by(
        project_id=project.id,
        project_customer_id=None
    ).all()

    teams = [t.strip() for t in (project.design_teams_requested or '').split(',')]

    for d in deliverables:
        _create_folder(host, port, sid, design_path, d.name)
        d_path = f'{design_path}/{d.name}'

        if '3D' in teams:
            _create_folder(host, port, sid, d_path, '3D Files')
            _create_folder(host, port, sid, d_path, 'Renders')
        if '2D' in teams or '3D' in teams:
            _create_folder(host, port, sid, d_path, 'Artwork')
        if 'Technical' in teams or '3D' in teams:
            _create_folder(host, port, sid, d_path, 'DWG')
            _create_folder(host, port, sid, d_path, 'PDF')

def _build_ccm_design_folders(host, port, sid, design_path, project):
    """
    C&CM Brief:
    Design Files/
        Initial KV/
        {Region}/        e.g. UAE, Kuwait
            {Customer}/  customers whose Customer.region matches this region
                {Deliverable}/
    """
    _create_folder(host, port, sid, design_path, 'Initial KV')

    project_regions = ProjectRegion.query.filter_by(project_id=project.id).all()

    for pr in project_regions:
        region_name = REGION_DISPLAY.get((pr.region or '').lower(), (pr.region or '').title())
        _create_folder(host, port, sid, design_path, region_name)
        region_path = f'{design_path}/{region_name}'

        project_customers = (
            ProjectCustomer.query
            .filter_by(project_id=project.id)
            .join(ProjectCustomer.customer)
            .filter(Customer.region == pr.region)
            .all()
        )

        for pc in project_customers:
            customer_name = pc.customer.name
            _create_folder(host, port, sid, region_path, customer_name)
            customer_path = f'{region_path}/{customer_name}'

            for d in pc.deliverables:
                _create_folder(host, port, sid, customer_path, d.name)

# ---- File Upload ----------------

def upload_file_to_nas(project, subfolder, local_file_path, nas_filename):
    """
    Upload a single file into a project subfolder on the NAS.

    Args:
        project:         Project ORM object (needs .created_at, .client_brand, .name)
        subfolder:       Destination subfolder, e.g. 'Reference Files' or 'Submissions'
        local_file_path: Absolute path to the file on the Flask server's local disk
        nas_filename:    Filename to use on the NAS (keeps the original name)

    Failures are logged as warnings and never crash the calling route.
    """
    try:
        sid, host, port = _get_session()
        try:
            root        = current_app.config['NAS_PROJECT_ROOT']
            year        = project.created_at.year
            client_name = project.client_brand.name if project.client_brand else 'Unknown Client'
            dest_path   = f'{root}/{year}/{client_name}/{project.name}/{subfolder}'

            with open(local_file_path, 'rb') as f:
                resp = _NAS_SESSION.post(
                    _nas_url(host, port, '/webapi/entry.cgi'),
                    params={
                        'api':     'SYNO.FileStation.Upload',
                        'version': '2',
                        'method':  'upload',
                        '_sid':    sid,
                    },
                    data={
                        'path':           dest_path,
                        'create_parents': 'true',
                        'overwrite':      'true',
                    },
                    files={'file': (nas_filename, f)},
                    timeout=60,
                )
            data = resp.json()
            if not data.get('success'):
                current_app.logger.warning(
                    f'NAS upload failed for {nas_filename} → {dest_path}: {data}'
                )
        finally:
            _logout(host, port, sid)
    except Exception as e:
        current_app.logger.warning(
            f'NAS upload failed for project {project.id} / {nas_filename}: {e}'
        )

# ---- Background helpers ----------

def _run_in_background(app, fn):
    """Run fn() in a daemon thread with a fresh Flask app context.
    Use this for all NAS calls so they never block the HTTP response."""
    import threading

    def _worker():
        with app.app_context():
            fn()

    threading.Thread(target=_worker, daemon=True).start()

# ---- Project Interface -----------

def create_project_folders(project):
    """
    Main entry point — call this after a project is created or edited.
    Idempotent: safe to call multiple times (force_parent=true on all folders).
    Failures are logged as warnings and never crash the calling route.
    """
    try:
        sid, host, port = _get_session()
        try:
            _build_folder_tree(host, port, sid, project)
        finally:
            _logout(host, port, sid)
    except Exception as e:
        current_app.logger.warning(f'NAS folder creation failed for project {project.id}: {e}')

def rename_project_folder(project, old_name):
    """
    Rename the project's top-level NAS folder when project.name changes.

    Call AFTER db.session.commit() so project reflects the new name.
    old_name is the name the folder currently has on the NAS (captured
    before the DB mutation).

    If the old folder doesn't exist (e.g. was never created), the rename
    is a no-op and create_project_folders will build the correct tree
    under the new name on the next call.

    Failures are logged as warnings and never crash the calling route.
    """
    try:
        sid, host, port = _get_session()
        try:
            root        = current_app.config['NAS_PROJECT_ROOT']
            year        = project.created_at.year
            client_name = project.client_brand.name if project.client_brand else 'Unknown Client'
            old_path    = f'{root}/{year}/{client_name}/{old_name}'
            _rename_folder(host, port, sid, old_path, project.name)
        finally:
            _logout(host, port, sid)
    except Exception as e:
        current_app.logger.warning(
            f'NAS folder rename failed for project {project.id} '
            f'({old_name!r} → {project.name!r}): {e}'
        )

def build_file_path(project, subfolder, filename):
    """
    Build the full NAS path for a project file.
    e.g. /Projects/2026/P&G/Summer 2026/Reference Files/brief.pdf
    """
    root        = current_app.config['NAS_PROJECT_ROOT']
    year        = project.created_at.year
    client_name = project.client_brand.name if project.client_brand else 'Unknown Client'
    return f'{root}/{year}/{client_name}/{project.name}/{subfolder}/{filename}'


def build_chat_file_path(project, filename):
    """Chat attachment NAS path under NAS_CHATS_ROOT, e.g. /Chats/2026/P&G/Summer 2026/9f2a...c1.jpg.
    No provisioning step needed — upload_app_file creates missing folders on upload."""
    root        = current_app.config['NAS_CHATS_ROOT']
    year        = project.created_at.year
    client_name = project.client_brand.name if project.client_brand else 'Unknown Client'
    return f'{root}/{year}/{client_name}/{project.name}/{filename}'

def upload_app_file(file_bytes, nas_folder_path, filename, _max_attempts=3):
    """
    Upload file bytes directly to a NAS folder. Retries up to _max_attempts
    times with exponential back-off on any transient error before raising.

    Args:
        file_bytes:      raw bytes of the file (call file.read() before passing)
        nas_folder_path: destination folder on NAS (not including filename)
        filename:        filename to use on the NAS
    """
    last_exc = None
    for attempt in range(1, _max_attempts + 1):
        try:
            sid, host, port = _get_session()
            try:
                resp = _NAS_SESSION.post(
                    _nas_url(host, port, '/webapi/entry.cgi'),
                    params={
                        'api':     'SYNO.FileStation.Upload',
                        'version': '2',
                        'method':  'upload',
                        '_sid':    sid,
                    },
                    data={
                        'path':           nas_folder_path,
                        'create_parents': 'true',
                        'overwrite':      'true',
                    },
                    files={'file': (filename, file_bytes)},
                    timeout=60,
                )
                data = resp.json()
                if not data.get('success'):
                    raise RuntimeError(f'NAS upload failed: {data}')
                return  # success — exit early
            finally:
                _logout(host, port, sid)
        except Exception as exc:
            last_exc = exc
            if attempt < _max_attempts:
                delay = 2 ** attempt  # 2 s after attempt 1, 4 s after attempt 2
                current_app.logger.warning(
                    f'NAS upload attempt {attempt}/{_max_attempts} failed for '
                    f'"{filename}" — retrying in {delay}s. Error: {exc}'
                )
                time.sleep(delay)

    current_app.logger.error(
        f'NAS upload permanently failed for "{filename}" after '
        f'{_max_attempts} attempts: {last_exc}'
    )
    raise RuntimeError(
        f'NAS upload failed after {_max_attempts} attempts: {last_exc}'
    )

def download_app_file(nas_file_path):
    """
    Fetch a file from the NAS and return its raw bytes.

    Args:
        nas_file_path: full path including filename, e.g.
                       /Projects/2026/P&G/Summer 2026/Reference Files/brief.pdf
    Raises RuntimeError if the NAS returns an error.
    """
    sid, host, port = _get_session()
    try:
        resp = _NAS_SESSION.get(
            _nas_url(host, port, '/webapi/entry.cgi'),
            params={
                'api':     'SYNO.FileStation.Download',
                'version': '2',
                'method':  'download',
                'path':    nas_file_path,
                'mode':    'open',
                '_sid':    sid,
            },
            cookies={'id': sid},
            timeout=60,
        )
        content_type = resp.headers.get('Content-Type', '')

        # Synology FileStation API errors: HTTP 200 but JSON body
        if 'application/json' in content_type:
            err = resp.json()
            current_app.logger.warning(
                f'NAS download API error for {nas_file_path}: {err}'
            )
            raise RuntimeError(f'NAS download failed: {err}')

        # DSM/nginx-level errors (502, 504, etc.) arrive as HTML with a
        # non-200 status — these would otherwise be returned as file bytes,
        # making the downloaded file appear corrupt/unopenable.
        if not resp.ok:
            current_app.logger.warning(
                f'NAS download HTTP {resp.status_code} for {nas_file_path} '
                f'(Content-Type: {content_type})'
            )
            raise RuntimeError(
                f'NAS download HTTP {resp.status_code} for {nas_file_path}'
            )

        # Catch HTML error pages that slipped through with a 200 status
        # (some DSM versions do this for internal errors).
        if 'text/html' in content_type:
            current_app.logger.warning(
                f'NAS returned HTML instead of file bytes for {nas_file_path} '
                f'(HTTP {resp.status_code})'
            )
            raise RuntimeError(
                f'NAS returned an HTML error page for {nas_file_path}'
            )

        return resp.content
    finally:
        _logout(host, port, sid)

def delete_app_file(nas_file_path):
    """
    Delete a single file from the NAS.
    Failures are logged as warnings and never crash the caller.

    Args:
        nas_file_path: full path including filename
    """
    try:
        sid, host, port = _get_session()
        try:
            _NAS_SESSION.get(
                _nas_url(host, port, '/webapi/entry.cgi'),
                params={
                    'api':     'SYNO.FileStation.Delete',
                    'version': '2',
                    'method':  'start',
                    'path':    json.dumps([nas_file_path]),
                    'accurate_progress': 'false',
                    '_sid':    sid,
                },
                timeout=10,
            )
        finally:
            _logout(host, port, sid)
    except Exception as e:
        current_app.logger.warning(f'NAS delete failed for {nas_file_path}: {e}')


# --------- Synology Drive deep-links (M10 NAS migration, 21 Aug 2026) ------
#
# Every user-facing "open this folder" button now points at Synology Drive
# instead of File Station — Ezekiel's call, since Drive is the app people
# actually browse in day to day now. Upload/download/rename/create-folder
# (above) stay on the File Station API untouched; this section only builds
# the clickable "open folder in browser" links.
#
# Drive addresses content by its own opaque internal file_id
# (https://{host}/drive/#file_id={id}), and — confirmed 21 Aug 2026 against
# Ezekiel's real DevTools capture — it has NO API that resolves a path
# string straight to a file_id. Drive's own web client walks an ID tree:
# SYNO.SynologyDrive.TeamFolders.list (method=list, version=1, no `path`
# param — that response IS the root, each item already carries its own
# file_id) gets you the top-level Team Folders (Docs and Templates,
# Projects, etc). From there, SYNO.SynologyDrive.Files.list (method=list,
# version=2) with path="id:{parent_file_id}" lists one folder's contents;
# matching a child by `name` and taking ITS file_id lets you descend one
# more level. Repeat per path segment. This replaces two earlier wrong
# guesses: SYNO.SynologyDrive.Files method=get version=3 (doesn't exist),
# and a '/team-folders/' path-string prefix (Drive doesn't resolve path
# strings at all, so there was nothing for that prefix to fix).

def _path_to_segments(path):
    """Splits a File Station-style path ('/Docs and Templates/Templates/
    Simulation Files') into the ordered list of folder names Drive's
    TeamFolders/Files.list walk needs (see resolve_drive_file_id()).
    Filters out empty segments, so a leading and/or trailing slash is
    harmless."""
    return [seg for seg in path.split('/') if seg]


def resolve_drive_file_id(folder_path):
    """
    Resolves a filesystem-style path to its Synology Drive file_id by
    walking Drive's own ID-based folder tree one segment at a time —
    see the module comment above for why this can't be a single API call.

    Logs in via _login_with_session('SynologyDrive') — the SAME LAN-IP/
    NAS_TUNNEL_HOST fallback _get_session() uses, just a different
    'session' scope (a FileStation sid isn't assumed to also authorize
    Drive calls). Uses whichever (host, port) that login actually
    succeeded on for every walk step too — not the raw config value.

    Returns None on any failure (unreachable NAS, a path segment not
    found, bad auth, unexpected response shape) — callers treat None as
    "no Drive link available," same as the old File Station builders did
    when NAS_WEB_URL wasn't configured. Every failure is logged via
    current_app.logger so a None return isn't a dead end when debugging.
    """
    segments = _path_to_segments(folder_path)
    if not segments:
        current_app.logger.warning('Drive file_id lookup called with an empty path')
        return None

    try:
        sid, host, port = _login_with_session('SynologyDrive')
    except RuntimeError as e:
        current_app.logger.warning(f'Drive login failed resolving {folder_path!r}: {e}')
        return None

    def _list(params):
        # cookies={'id': sid} added 21 Aug 2026 alongside the existing _sid
        # query param — mirrors download_app_file()'s FileStation.Download
        # call elsewhere in this file. Some Synology webapi endpoints (Drive
        # included, it seems) check the session cookie, not just _sid, and
        # silently hand back a limited/empty result instead of a real auth
        # error when it's missing, which is indistinguishable from "this
        # path segment genuinely doesn't exist" without this.
        resp = _NAS_SESSION.get(
            _nas_url(host, port, '/webapi/entry.cgi'),
            params={**params, '_sid': sid},
            cookies={'id': sid},
            timeout=10,
        )
        return resp.json()

    try:
        # Root level: Team Folders (no `path` param — this call IS the root).
        data = _list({
            'api': 'SYNO.SynologyDrive.TeamFolders', 'version': '1', 'method': 'list',
            'offset': '0', 'limit': '1000',
            'sort_by': 'name', 'sort_direction': 'asc',
            'filter': '{"include_transient":true}',
        })
        if not data.get('success'):
            current_app.logger.warning(f'Drive TeamFolders list failed resolving {folder_path!r}: {data}')
            return None
        items = data['data']['items']

        file_id = None
        for depth, segment in enumerate(segments):
            match = next((it for it in items if it['name'] == segment), None)
            if not match:
                # Dumps the actual item names Drive returned at this level —
                # added 21 Aug 2026 so a mismatch (wrong session scope, wrong
                # root, a renamed folder) shows itself in one log line
                # instead of another round of blind guessing.
                current_app.logger.warning(
                    f'Drive path segment {segment!r} not found (resolving {folder_path!r}, '
                    f'matched so far: {segments[:depth]!r}) — items actually returned: '
                    f'{[it.get("name") for it in items]!r}'
                )
                return None
            file_id = match['file_id']
            if depth == len(segments) - 1:
                break  # last segment — file_id above is the answer, no need to list its contents
            data = _list({
                'api': 'SYNO.SynologyDrive.Files', 'version': '2', 'method': 'list',
                'offset': '0', 'limit': '1000',
                'sort_by': 'name', 'sort_direction': 'asc',
                'path': f'id:{file_id}',
                'filter': '{"include_transient":true}',
            })
            if not data.get('success'):
                current_app.logger.warning(f'Drive Files list failed under {segment!r} resolving {folder_path!r}: {data}')
                return None
            items = data['data']['items']

        return file_id
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, ValueError, KeyError) as e:
        current_app.logger.warning(f'Drive file_id lookup errored for {folder_path!r}: {e}')
        return None


def build_drive_folder_url(folder_path):
    """Public entry point for every NAS-open-folder call site — resolves
    folder_path (a plain File Station-style path, e.g. '/Docs and
    Templates/Templates/Simulation Files' or '/Projects/2026/Client/Job')
    to a Drive file_id via resolve_drive_file_id()'s ID-tree walk, and
    returns the web-client deep-link, or None if anything along the way
    failed. Signature unchanged from the earlier (wrong) version, so none
    of file_templates.py / project_overlay.py / project_preproduction.py
    need to change."""
    file_id = resolve_drive_file_id(folder_path)
    if not file_id:
        return None
    base = (current_app.config.get('NAS_WEB_URL') or
            f"https://{current_app.config.get('NAS_HOST', '')}")
    return f'{base.rstrip("/")}/drive/#file_id={file_id}'
