import json
import time
import requests
import urllib3
from flask import current_app

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# trust_env=False: ignore system/env proxies (they cause HTTP 407 reaching the
# NAS on the LAN). verify=False: the NAS has a self-signed cert.
_NAS_SESSION = requests.Session()
_NAS_SESSION.trust_env = False
_NAS_SESSION.verify = False

# (host, port) of the last NAS login that worked; port is None for
# NAS_TUNNEL_HOST. Kept for the process life so an unreachable LAN IP
# doesn't cost a ~10s timeout on every call.
_NAS_HOST_OVERRIDE = None

from app.modules.core.shared.models import ProjectRegion, ProjectCustomer, Customer, Deliverable

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
    """Build a NAS webapi URL. port is None for the NAS_TUNNEL_HOST
    fallback (a bare hostname)."""
    if port:
        return f'https://{host}:{port}{path}'
    return f'https://{host}{path}'

def _get_session():
    """Log in to File Station; returns (sid, host, port). See
    _login_with_session for the LAN / tunnel fallback."""
    return _login_with_session('FileStation')


def _login_with_session(session_name):
    """Log in to the NAS webapi; returns (sid, host, port), raises
    RuntimeError. Tries NAS_HOST/NAS_PORT (office LAN) first, then
    NAS_TUNNEL_HOST on a connection failure only (bad credentials never fall
    back). The working host is cached in _NAS_HOST_OVERRIDE. session_name
    scopes the sid to an app: 'FileStation' or 'SynologyDrive'."""
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
        # Fallback: NAS_TUNNEL_HOST is a Cloudflare Tunnel to the NAS, gated
        # by a Cloudflare Access service token. (QuickConnect has no webapi
        # proxy usable from a script.)
        tunnel_host = current_app.config.get('NAS_TUNNEL_HOST')
        client_id = current_app.config.get('CF_ACCESS_CLIENT_ID')
        client_secret = current_app.config.get('CF_ACCESS_CLIENT_SECRET')
        # Give up if no fallback is configured or we just failed on the
        # (cached) fallback itself.
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

    # A bad Access policy or service token returns an HTML page; raise a
    # clear error instead of a JSONDecodeError 500.
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

def _logout(host, port, sid, session_name='FileStation'):
    """Log out a sid; session_name must match the one it logged in with."""
    _NAS_SESSION.get(
        _nas_url(host, port, '/webapi/auth.cgi'),
        params={
            'api':     'SYNO.API.Auth',
            'version': '1',
            'method':  'logout',
            'session': session_name,
            '_sid':    sid,
        },
        timeout=5
    )

# ------ Folder Operations --------

def _create_folder(host, port, sid, parent_path, folder_name):
    """Create one folder in parent_path; no error if it already exists."""
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
    """Create a project's NAS folder tree: year / client / project, the
    standard subfolders, then Design Files by brief type (Standard or C&CM)."""
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

# ---- Background helpers ----------

def _run_in_background(app, fn):
    """Run fn() in a daemon thread inside a fresh app context, so NAS calls
    never block the response. fn must not push its own app_context(): tests
    run fn inline, and a new context would hide the test's transaction."""
    import threading

    def _worker():
        with app.app_context():
            fn()

    threading.Thread(target=_worker, daemon=True).start()

# ---- Project Interface -----------

def create_project_folders(project):
    """Build the project's NAS folders; call after a project is created or
    edited. Idempotent. Failures are logged, never raised."""
    try:
        sid, host, port = _get_session()
        try:
            _build_folder_tree(host, port, sid, project)
        finally:
            _logout(host, port, sid)
    except Exception as e:
        current_app.logger.warning(f'NAS folder creation failed for project {project.id}: {e}')

def build_file_path(project, subfolder, filename):
    """Full NAS path for a project file, e.g.
    /Projects/2026/P&G/Summer 2026/Reference Files/brief.pdf"""
    root        = current_app.config['NAS_PROJECT_ROOT']
    year        = project.created_at.year
    client_name = project.client_brand.name if project.client_brand else 'Unknown Client'
    return f'{root}/{year}/{client_name}/{project.name}/{subfolder}/{filename}'


def build_chat_file_path(project, filename):
    """Chat attachment NAS path under NAS_CHATS_ROOT, e.g. /Chats/2026/P&G/Summer 2026/9f2a...c1.jpg.
    upload_app_file creates missing folders."""
    root        = current_app.config['NAS_CHATS_ROOT']
    year        = project.created_at.year
    client_name = project.client_brand.name if project.client_brand else 'Unknown Client'
    return f'{root}/{year}/{client_name}/{project.name}/{filename}'

def is_reachable():
    """True if a File Station login works right now (LAN or tunnel)."""
    try:
        sid, host, port = _get_session()
    except Exception:
        return False
    try:
        _logout(host, port, sid)
    except requests.exceptions.RequestException:
        pass
    return True

def share_space(share_path):
    """{'free', 'total'} bytes of the volume holding a shared folder such as
    '/Projects', or None when the NAS doesn't list it. Raises RuntimeError if unreachable."""
    sid, host, port = _get_session()
    try:
        resp = _NAS_SESSION.get(
            _nas_url(host, port, '/webapi/entry.cgi'),
            params={
                'api':        'SYNO.FileStation.List',
                'version':    '2',
                'method':     'list_share',
                'additional': '["volume_status"]',
                '_sid':       sid,
            },
            timeout=10
        )
        data = resp.json()
    except (requests.exceptions.RequestException, ValueError) as e:
        raise RuntimeError(f'NAS share list failed: {e}')
    finally:
        try:
            _logout(host, port, sid)
        except requests.exceptions.RequestException:
            pass
    if not data.get('success'):
        return None
    for share in data.get('data', {}).get('shares', []):
        status = (share.get('additional') or {}).get('volume_status') or {}
        if share.get('path') == share_path and 'totalspace' in status:
            return {'free': int(status['freespace']), 'total': int(status['totalspace'])}
    return None


def upload_app_file(file_bytes, nas_folder_path, filename, _max_attempts=3):
    """
    Upload bytes to a NAS folder. Retries with exponential back-off, then
    raises RuntimeError.

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
                return
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
    # Queued on the server while the NAS was down? Serve that copy.
    from app.modules.core.shared.services.nas_outbox import pending_bytes
    queued = pending_bytes(nas_file_path)
    if queued is not None:
        return queued

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
    Delete one file from the NAS. Failures are logged, never raised.

    Args:
        nas_file_path: full path including filename
    """
    # Drop any queued copy so the flush never uploads a deleted file. Still
    # delete on the NAS below, in case an older version is already there.
    from app.modules.core.shared.services.nas_outbox import discard
    discard(nas_file_path)

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


# --------- Synology Drive deep-links ------
#
# User-facing "open folder" links go to Synology Drive (the app people
# browse); file operations above use the File Station API.
#
# Drive links need an opaque file_id (https://{host}/drive/#file_id={id})
# and no API maps a path to one. So we walk the tree like Drive's web client:
# TeamFolders.list (no `path`) returns the root items with their file_ids,
# then Files.list with path="id:{parent_file_id}" lists one level; match
# each path segment by name.

def _path_to_segments(path):
    """Split a path ('/Docs and Templates/Templates/Simulation Files') into
    folder names for the Drive walk; leading/trailing slashes are ignored."""
    return [seg for seg in path.split('/') if seg]


def resolve_drive_file_id(folder_path):
    """Resolve a path to its Synology Drive file_id by walking the tree one
    segment at a time (see the section comment). Logs in with the
    'SynologyDrive' session scope. Returns None on any failure, and logs why."""
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
        # Send the sid cookie too: without it some endpoints (Drive included)
        # silently return an empty list instead of an auth error.
        resp = _NAS_SESSION.get(
            _nas_url(host, port, '/webapi/entry.cgi'),
            params={**params, '_sid': sid},
            cookies={'id': sid},
            timeout=10,
        )
        return resp.json()

    try:
        # Root level: Team Folders (no `path` param).
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
                # Log the names Drive returned, so a mismatch shows in one line.
                current_app.logger.warning(
                    f'Drive path segment {segment!r} not found (resolving {folder_path!r}, '
                    f'matched so far: {segments[:depth]!r}) — items actually returned: '
                    f'{[it.get("name") for it in items]!r}'
                )
                return None
            file_id = match['file_id']
            if depth == len(segments) - 1:
                break  # last segment: no need to list its contents
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
    finally:
        # A failed logout must not turn a resolved id into an exception.
        try:
            _logout(host, port, sid, 'SynologyDrive')
        except requests.exceptions.RequestException as e:
            current_app.logger.warning(f'Drive logout failed after resolving {folder_path!r}: {e}')


def build_drive_folder_url(folder_path):
    """Drive web deep-link for a folder path (e.g. '/Projects/2026/Client/Job'),
    or None if it can't be resolved. Used by every "open NAS folder" link."""
    file_id = resolve_drive_file_id(folder_path)
    if not file_id:
        return None
    base = (current_app.config.get('NAS_WEB_URL') or
            f"https://{current_app.config.get('NAS_HOST', '')}")
    return f'{base.rstrip("/")}/drive/#file_id={file_id}'
