# Local-disk cache for Draft-stage submission files. Files sit here until
# Submit to Client, when the caller names each file in the zip and calls
# build_zip_bytes() to get one archive for nas.upload_app_file().
#
# Not built on zip_utils.build_zip(): that writes to a swept temp folder and
# returns a download link; here we need the zip bytes to upload ourselves.

import os
import io
import re
import zipfile
from flask import current_app

# Never swept on a schedule (a draft can sit for days); callers clear it via
# clear_submission_cache once files are on the NAS or the draft is discarded.
CACHE_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'submission_drafts')


def _sanitize(filename):
    """Strip characters that aren't safe in a filesystem path."""
    return re.sub(r'[\\/:*?"<>|]', '', filename).strip()


def _draft_folder(project_id, submission_id):
    """The folder a given submission's cached files live in."""
    return os.path.join(CACHE_ROOT, str(project_id), str(submission_id))


def _resolve_cache_path(stored):
    """Re-root a stored cache path onto this machine's CACHE_ROOT.
    Stored paths are absolute from whichever host wrote them; the part after
    'submission_drafts/' is portable. Returned unchanged if the marker is absent."""
    if not stored:
        return stored
    marker = 'submission_drafts/'
    idx = stored.replace('\\', '/').find(marker)
    if idx == -1:
        return stored
    rel = stored.replace('\\', '/')[idx + len(marker):]
    return os.path.join(CACHE_ROOT, *rel.split('/'))


def cache_submission_file(project_id, submission_id, file_bytes, original_filename):
    """Write an uploaded file into the draft's cache folder and return its
    path, which callers store on ProjectSubmissionFile.local_cache_path."""
    folder = _draft_folder(project_id, submission_id)
    os.makedirs(folder, exist_ok=True)

    safe_name = _sanitize(original_filename)
    local_path = os.path.join(folder, safe_name)

    with open(local_path, 'wb') as f:
        f.write(file_bytes)

    return local_path


def delete_cached_file(local_cache_path):
    """Delete one cached file. Safe if it's already gone; never raises."""
    path = _resolve_cache_path(local_cache_path)
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except OSError as e:
            current_app.logger.warning(
                f'Could not delete cached submission file {path}: {e}'
            )


def clear_submission_cache(project_id, submission_id):
    """Remove a submission's whole draft folder. Safe if it's empty or missing."""
    folder = _draft_folder(project_id, submission_id)
    if not os.path.isdir(folder):
        return
    for fname in os.listdir(folder):
        fpath = os.path.join(folder, fname)
        if os.path.isfile(fpath):
            os.remove(fpath)
    try:
        os.rmdir(folder)
    except OSError:
        # A concurrent write may have landed after listdir; the next clear gets it.
        pass


def build_zip_bytes(entries):
    """Build an in-memory zip from cached files and return its bytes.
    `entries` is a list of {'local_cache_path', 'arcname'}; the caller picks
    each arcname (the name inside the zip)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for entry in entries:
            with open(_resolve_cache_path(entry['local_cache_path']), 'rb') as f:
                zf.writestr(entry['arcname'], f.read())
    return buffer.getvalue()