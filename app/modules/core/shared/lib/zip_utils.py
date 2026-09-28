# Build a zip, serve it once, then delete it. Callers pass (arcname, bytes)
# pairs to build_zip() and link the returned zip_id to
# /api/zip-download/<zip_id> (core/shared/routes/api.py). Callers fetch the
# file bytes themselves.

import os
import time
import uuid
import zipfile
from flask import send_file, after_this_request

ZIP_TEMP_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp_zips')

# How long an unclaimed zip sits before it is swept away.
ZIP_MAX_AGE_SECONDS = 60 * 60  # 1 hour


def _sweep_stale_zips():
    """
    Delete temp files older than ZIP_MAX_AGE_SECONDS. Runs from build_zip()
    since the app has no task scheduler.
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
    Zip in-memory files into the temp folder and return an opaque zip_id for
    serve_zip(). `files` is (arcname, bytes) pairs; '/' in an arcname makes
    folders. `download_name` is the filename offered to the browser.
    """
    _sweep_stale_zips()

    os.makedirs(ZIP_TEMP_FOLDER, exist_ok=True)
    zip_id = uuid.uuid4().hex
    zip_path = os.path.join(ZIP_TEMP_FOLDER, f'{zip_id}.zip')

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for arcname, content in files:
            zf.writestr(arcname, content)

    # Sidecar file holds the download name, so no database table is needed.
    with open(zip_path + '.name', 'w', encoding='utf-8') as f:
        f.write(download_name)

    return zip_id


def serve_zip(zip_id):
    """
    Send a built zip and delete it (and its .name sidecar) after the
    response. Returns None for an unknown, used or expired zip_id; the
    caller turns that into a 404.
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