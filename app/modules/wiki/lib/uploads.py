"""Wiki uploads no article uses: finding them, and deleting them with their NAS backups."""
import os
import time
from collections import namedtuple

from flask import current_app

from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import WikiArticle
from app.modules.core.shared.services import nas

GRACE_SECONDS = 24 * 60 * 60
NAS_VIDEO_FOLDER = '/Admin/OVP/Wiki'

Upload = namedtuple('Upload', 'path name size is_video')


def upload_root():
    """Where wiki images live; videos sit in its videos/ folder. Tests point it elsewhere."""
    return (current_app.config.get('WIKI_UPLOAD_ROOT')
            or os.path.join(current_app.root_path, 'static', 'wiki-uploads'))


def _files(root):
    """Images directly in root and videos directly in root/videos. Never any deeper."""
    for folder, is_video in ((root, False), (os.path.join(root, 'videos'), True)):
        if not os.path.isdir(folder):
            continue
        for entry in os.scandir(folder):
            if entry.is_file():
                yield entry, is_video


def _stored_content():
    """Every copy of every article's content in one string: live, autosaved draft and legacy."""
    rows = db.session.query(WikiArticle.sections_json, WikiArticle.draft_sections_json,
                            WikiArticle.legacy_sections_json).all()
    return '\n'.join(part for row in rows for part in row if part)


def unused_uploads(now=None):
    """Files no article names anywhere, older than the grace period, so an upload
    still sitting in an unsaved editor tab is never caught."""
    now = now or time.time()
    used = _stored_content()
    unused = []
    for entry, is_video in _files(upload_root()):
        stat = entry.stat()
        if now - stat.st_mtime < GRACE_SECONDS or entry.name in used:
            continue
        unused.append(Upload(entry.path, entry.name, stat.st_size, is_video))
    return unused


def delete_unused():
    """Delete the unused files now and their NAS backups in the background. Returns how many went."""
    removed = []
    for upload in unused_uploads():
        try:
            os.remove(upload.path)
        except OSError as error:
            current_app.logger.warning(f'Wiki clean-up could not delete {upload.path}: {error}')
            continue
        removed.append(upload)

    videos = [upload.name for upload in removed if upload.is_video]
    if videos:
        app_obj = current_app._get_current_object()

        def _delete_backups():
            for name in videos:
                try:
                    nas.delete_app_file(f'{NAS_VIDEO_FOLDER}/{name}')
                except Exception as error:
                    app_obj.logger.warning(f'Wiki clean-up NAS delete failed for {name}: {error}')

        nas._run_in_background(app_obj, _delete_backups)
    return len(removed)
