"""Profile image folders are absolute paths into the app package's static
folder, so saving works whatever the process's working directory is."""
import os

import app as app_package
from app.modules.core.shared.lib.profilepic import AVATAR_FOLDER, BANNER_FOLDER

_STATIC = os.path.join(os.path.dirname(os.path.abspath(app_package.__file__)), 'static')


def test_avatar_and_banner_folders_are_absolute_under_app_static():
    assert os.path.isabs(AVATAR_FOLDER) and os.path.isabs(BANNER_FOLDER)
    assert AVATAR_FOLDER == os.path.join(_STATIC, 'avatars')
    assert BANNER_FOLDER == os.path.join(_STATIC, 'banners')
