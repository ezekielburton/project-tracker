"""Filesystem locations shared across modules."""
import os
from flask import current_app


def template_upload_folder():
    """Absolute path to the on-disk store of C&CM file-template files
    (per-store .ai design files), kept inside the app package at
    app/file_templates/. Anchored to the Flask application root so it
    resolves to the same folder no matter which module calls it.
    Both the file-templates browse/download routes and the admin upload
    route use this one definition."""
    return os.path.join(current_app.root_path, 'file_templates')
