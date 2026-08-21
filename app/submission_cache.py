# app/submission_cache.py
#
# Local-disk cache for Submissions Draft-stage files (M3 Step 4 overlay
# content build). While a submission is in Draft, uploaded files sit here
# instead of going straight to the NAS — see ProjectSubmissionFile.storage_
# location in app/models/__init__.py for the full reasoning. At Submit to
# Client, the caller (the submit-to-client route) reads every cached file
# for a submission, decides the in-zip name for each (this module doesn't
# know about canonical naming/revision labels — that's project/submission
# context the caller already has), and calls build_zip_bytes() to get back
# one archive ready to hand to app.nas.upload_app_file().
#
# Deliberately NOT built on top of app/zip_utils.py's build_zip() — that
# utility writes to a 1-hour-swept temp folder and hands back a one-time
# download link, which fits "Download All" but not this: we need the zip
# BYTES in hand immediately, to upload to the NAS ourselves, never to serve
# a download link for it.

import os
import io
import re
import zipfile
from flask import current_app

# Where draft-stage files live while a submission is being worked on.
# NOT swept on any schedule — a draft can sit for days. Cleared explicitly
# by the caller (via clear_submission_cache) once a submission's files are
# safely zipped and uploaded to the NAS, or if a draft is discarded.
CACHE_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'submission_drafts')


def _sanitize(filename):
    """Strip characters that aren't safe in a filesystem path. Same
    character set projects_submission.py's own _sanitize() strips from
    canonical submission names — kept local rather than shared, matching
    this codebase's existing convention of small per-file _sanitize()
    helpers rather than one shared util."""
    return re.sub(r'[\\/:*?"<>|]', '', filename).strip()


def _draft_folder(project_id, submission_id):
    """The folder a given submission's cached files live in."""
    return os.path.join(CACHE_ROOT, str(project_id), str(submission_id))


def cache_submission_file(project_id, submission_id, file_bytes, original_filename):
    """
    Write an uploaded file's bytes into the draft's local cache folder.

    Returns the local disk path — callers store this on
    ProjectSubmissionFile.local_cache_path so it can be read back later
    (for preview/download while still in Draft) or picked up by
    build_zip_bytes() at Submit to Client.
    """
    folder = _draft_folder(project_id, submission_id)
    os.makedirs(folder, exist_ok=True)

    safe_name = _sanitize(original_filename)
    local_path = os.path.join(folder, safe_name)

    with open(local_path, 'wb') as f:
        f.write(file_bytes)

    return local_path


def delete_cached_file(local_cache_path):
    """Delete one cached file. Safe to call if it's already gone (e.g. the
    whole draft was cleared out from under it) — never raises."""
    if local_cache_path and os.path.isfile(local_cache_path):
        try:
            os.remove(local_cache_path)
        except OSError as e:
            current_app.logger.warning(
                f'Could not delete cached submission file {local_cache_path}: {e}'
            )


def clear_submission_cache(project_id, submission_id):
    """Remove a submission's entire draft folder — called once its files
    are safely zipped and uploaded to the NAS (Submit to Client), or when
    a draft is explicitly discarded. Safe to call on an already-empty or
    never-created folder."""
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
        # Not empty for some reason (e.g. a concurrent write landed after
        # the listdir above) — leave it; next clear will catch it.
        pass


def build_zip_bytes(entries):
    """
    Build a zip archive in memory from a list of cached files.

    Args:
        entries: list of dicts, each {'local_cache_path': str, 'arcname': str}.
            arcname is the filename this file should have INSIDE the zip —
            the caller decides this (the canonical auto-name for whichever
            file is flagged is_main_deck, the file's own original_filename
            for everything else). This module has no opinion on naming.

    Returns:
        In-memory zip bytes, ready to hand to app.nas.upload_app_file().
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for entry in entries:
            with open(entry['local_cache_path'], 'rb') as f:
                zf.writestr(entry['arcname'], f.read())
    return buffer.getvalue()