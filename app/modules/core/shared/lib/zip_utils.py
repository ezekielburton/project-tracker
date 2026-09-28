# Build a zip, serve it once, then delete it. Callers pass (arcname, bytes)
# pairs to build_zip() and link the returned zip_id to
# /api/zip-download/<zip_id> (core/shared/routes/api.py). Callers fetch the
# file bytes themselves.

import os
import time
import unicodedata
import uuid
import zipfile
from urllib.parse import quote
from flask import Response

ZIP_TEMP_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp_zips')

# How long an unclaimed zip sits before it is swept away.
ZIP_MAX_AGE_SECONDS = 60 * 60  # 1 hour

# Size of each piece streamed to the browser.
ZIP_CHUNK_SIZE = 64 * 1024


def _remove_quietly(*paths):
    """Delete files, skipping ones already gone or still locked (Windows).
    Anything skipped is caught by the hourly sweep."""
    for p in paths:
        try:
            os.remove(p)
        except OSError:
            pass


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
            _remove_quietly(fpath)


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


def _stream_then_delete(zip_path, name_path):
    """Yield the zip in chunks, then delete it and its sidecar. The file is
    closed before the delete, which Windows requires. Runs when the download
    finishes or the client disconnects."""
    try:
        with open(zip_path, 'rb') as f:
            while True:
                chunk = f.read(ZIP_CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk
    finally:
        _remove_quietly(zip_path, name_path)


def _attachment_names(download_name):
    """Content-Disposition filename params. Non-ASCII names (e.g. Arabic
    customer names) get an ASCII fallback plus a UTF-8 filename*, the same
    as Flask's send_file."""
    try:
        download_name.encode('ascii')
        return {'filename': download_name}
    except UnicodeEncodeError:
        simple = unicodedata.normalize('NFKD', download_name)
        simple = simple.encode('ascii', 'ignore').decode('ascii')
        quoted = quote(download_name, safe="!#$&+-.^_`|~")
        return {'filename': simple, 'filename*': f"UTF-8''{quoted}"}


def serve_zip(zip_id):
    """
    Stream a built zip, then delete it (and its .name sidecar). Returns None
    for an unknown, used or expired zip_id; the caller turns that into a 404.
    """
    zip_path = os.path.join(ZIP_TEMP_FOLDER, f'{zip_id}.zip')
    name_path = zip_path + '.name'
    if not os.path.exists(zip_path):
        return None

    download_name = 'download.zip'
    if os.path.exists(name_path):
        with open(name_path, 'r', encoding='utf-8') as f:
            download_name = f.read().strip()

    response = Response(
        _stream_then_delete(zip_path, name_path),
        mimetype='application/zip',
        direct_passthrough=True,
    )
    response.headers.set('Content-Disposition', 'attachment', **_attachment_names(download_name))
    response.content_length = os.path.getsize(zip_path)
    return response
