"""Unit tests for the shared profile-picture save/delete helper."""
import io
import os
from werkzeug.datastructures import FileStorage
from app.modules.core.shared.lib.profilepic import save_profile_pic, delete_profile_pic


def _fs(name, data=b'x'):
    return FileStorage(stream=io.BytesIO(data), filename=name)


def test_save_accepts_image(tmp_path):
    fn = save_profile_pic(_fs('pic.PNG'), str(tmp_path))
    assert fn and fn.endswith('.png')
    assert os.path.exists(os.path.join(str(tmp_path), fn))


def test_save_rejects_non_image(tmp_path):
    assert save_profile_pic(_fs('doc.txt'), str(tmp_path)) is None
    assert os.listdir(str(tmp_path)) == []


def test_save_rejects_empty(tmp_path):
    assert save_profile_pic(_fs(''), str(tmp_path)) is None
    assert save_profile_pic(None, str(tmp_path)) is None


def test_delete_removes_file(tmp_path):
    p = os.path.join(str(tmp_path), 'gone.png')
    with open(p, 'wb') as f:
        f.write(b'x')
    delete_profile_pic(str(tmp_path), 'gone.png')
    assert not os.path.exists(p)


def test_delete_missing_is_safe(tmp_path):
    delete_profile_pic(str(tmp_path), None)
    delete_profile_pic(str(tmp_path), 'nope.png')
