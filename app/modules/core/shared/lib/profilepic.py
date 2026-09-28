"""
Save/delete for profile images (avatars and banners), shared by the profile
module and the admin panel. Only the file extension is checked server-side.
"""
import os
import uuid

ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
# Absolute (app/static/...) so saves don't depend on the process's working directory.
_STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'static'))
AVATAR_FOLDER = os.path.join(_STATIC_DIR, 'avatars')
BANNER_FOLDER = os.path.join(_STATIC_DIR, 'banners')


def save_profile_pic(file, folder):
    """Save an uploaded image to `folder` under a random name. Returns the
    stored filename, or None if missing or not an allowed extension."""
    if not file or file.filename == '':
        return None

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        return None

    stored_filename = f'{uuid.uuid4().hex[:8]}.{ext}'
    os.makedirs(folder, exist_ok=True)
    file.save(os.path.join(folder, stored_filename))
    return stored_filename


def delete_profile_pic(folder, filename):
    """Remove a previously stored image so replacements don't orphan files."""
    if not filename:
        return
    path = os.path.join(folder, filename)
    if os.path.exists(path):
        os.remove(path)
