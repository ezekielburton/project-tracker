import json
import time
import requests
import urllib3
from flask import current_app

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
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

def _get_session():
    """Login to Synology File Station API, return (sid, host, port)."""
    host = current_app.config['NAS_HOST']
    port = current_app.config['NAS_PORT']
    resp = requests.get(
        f'https://{host}:{port}/webapi/auth.cgi',
        verify=False,
        params={
            'api':     'SYNO.API.Auth',
            'version': '3',
            'method':  'login',
            'account': current_app.config['NAS_USERNAME'],
            'passwd':  current_app.config['NAS_PASSWORD'],
            'session': 'FileStation',
            'format':  'sid',
        },
        timeout=10
    )
    data = resp.json()
    if not data.get('success'):
        raise RuntimeError(f"NAS login failed: {data}")
    return data['data']['sid'], host, port

def _logout(host, port, sid):
    """Logout and invalidate the session token."""
    requests.get(
        f'https://{host}:{port}/webapi/auth.cgi',
        verify=False,
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
    resp = requests.get(
        f'https://{host}:{port}/webapi/entry.cgi',
        verify=False,
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
    requests.get(
        f'https://{host}:{port}/webapi/entry.cgi',
        verify=False,
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
                resp = requests.post(
                    f'https://{host}:{port}/webapi/entry.cgi',
                    verify=False,
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
                resp = requests.post(
                    f'https://{host}:{port}/webapi/entry.cgi',
                    verify=False,
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
        resp = requests.get(
            f'https://{host}:{port}/webapi/entry.cgi',
            verify=False,
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
            requests.get(
                f'https://{host}:{port}/webapi/entry.cgi',
                verify=False,
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
