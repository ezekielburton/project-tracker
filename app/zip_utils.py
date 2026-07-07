# app/zip_utils.py
#
# Shared "build a zip, serve it once, then clean up" utility. Any feature
# that needs a "Download All" button calls build_zip() with the files it
# wants zipped, gets back a zip_id, and hands that to the frontend as a
# download link pointing at /api/zip-download/<zip_id> (see api.py).
#
# Fetching the actual file bytes (from the NAS, local disk, wherever) is
# each caller's own responsibility — this module only knows how to zip
# bytes it's handed and serve the result once.

import os
import time
import uuid
import zipfile
from flask import send_file, after_this_request

ZIP_TEMP_FOLDER = os.path.join('app', 'temp_zips')

# How long an unclaimed zip is allowed to sit before it's swept away.
ZIP_MAX_AGE_SECONDS = 60 * 60  # 1 hour


def _sweep_stale_zips():
    """
    Deletes any zip (and its sidecar .name file) older than
    ZIP_MAX_AGE_SECONDS. Called at the start of build_zip() rather than
    from a background thread — there's no task scheduler in this stack,
    and this app's traffic is steady enough that "clean up old ones
    whenever someone builds a new one" keeps the temp folder bounded
    without needing a long-lived thread.
    """
    if not os.path.isdir(ZIP_TEMP_FOLDER):
        return
    now = time.time()
    for fname in os.listdir(ZIP_TEMP_FOLDER):
        fpath = os.path.join(ZIP_TEMP_FOLDER, fname)
        if os.path.isfile(fpath) and (now - os.path.getmtime(fpath)) > ZIP_MAX_AGE_SECONDS:
            os.remove(fpath)


def build_zip(files, download_name):
    """
    Builds a zip from in-memory file contents and stores it in the temp
    folder, ready for serve_zip() to send.

    Args:
        files: list of (arcname, bytes) tuples. arcname is the filename
            as it should appear INSIDE the zip — include '/' in it if you
            want a folder structure, e.g. 'UAE/Carrefour/logo.ai'.
        download_name: filename offered in the browser's save dialog,
            e.g. 'Summer 2026 - Reference Files.zip'.

    Returns:
        zip_id: opaque token — pass this to the frontend as
        /api/zip-download/<zip_id>.
    """
    _sweep_stale_zips()

    os.makedirs(ZIP_TEMP_FOLDER, exist_ok=True)
    zip_id = uuid.uuid4().hex
    zip_path = os.path.join(ZIP_TEMP_FOLDER, f'{zip_id}.zip')

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for arcname, content in files:
            zf.writestr(arcname, content)

    # Sidecar file remembers the friendly download name without needing
    # a database table just for that — simplest thing that works.
    with open(zip_path + '.name', 'w', encoding='utf-8') as f:
        f.write(download_name)

    return zip_id


def serve_zip(zip_id):
    """
    Serves a previously-built zip, then deletes it (and its .name
    sidecar) once the response has finished sending. Returns None if
    zip_id doesn't exist — the caller should turn that into a 404
    (covers both "never existed" and "already downloaded/expired").
    """
    zip_path = os.path.join(ZIP_TEMP_FOLDER, f'{zip_id}.zip')
    name_path = zip_path + '.name'
    if not os.path.exists(zip_path):
        return None

    download_name = 'download.zip'
    if os.path.exists(name_path):
        with open(name_path, 'r', encoding='utf-8') as f:
            download_name = f.read().strip()

    @after_this_request
    def _cleanup(response):
        for p in (zip_path, name_path):
            if os.path.exists(p):
                os.remove(p)
        return response

    return send_file(zip_path, as_attachment=True, download_name=download_name)