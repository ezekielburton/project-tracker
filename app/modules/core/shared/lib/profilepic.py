"""
Shared save/delete for profile images (avatars and banners). Lives here so the
profile module and the admin panel both set images through the same validated
path. The browser sends a cropped, compressed JPEG, but we always re-validate
server-side — never trust what the client claims to have sent.
"""
import os
import uuid

ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
AVATAR_FOLDER = os.path.join('app', 'static', 'avatars')
BANNER_FOLDER = os.path.join('app', 'static', 'banners')


def save_profile_pic(file, folder):
    """Save an uploaded image to `folder` under a uuid name.
    Returns the stored filename, or None if missing / not an allowed type."""
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
