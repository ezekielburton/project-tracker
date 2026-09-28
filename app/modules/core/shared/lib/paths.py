"""Filesystem locations shared across modules."""
import os
from flask import current_app


def template_upload_folder():
    """Absolute path to app/file_templates/, where C&CM file templates (per-store
    .ai files) are stored. Shared by the file-templates routes and the admin
    upload route."""
    return os.path.join(current_app.root_path, 'file_templates')
