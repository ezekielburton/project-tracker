"""
Attachment paths (readable, no escaping the entry's folder) and allowed file types.
"""
from app.modules.hse.lib import files


class Entry:
    def __init__(self, register, ref):
        self.register = register
        self.ref = ref


def test_the_path_is_readable_for_someone_browsing_the_drive():
    entry = Entry('incidents', 'INC-0031')
    assert files.folder_for(entry) == '/HSE/Incident & near miss/INC-0031'


def test_an_unknown_register_still_gets_a_folder():
    """An undeclared register falls back to its key as the folder name."""
    assert files.folder_for(Entry('retired_thing', 'OLD-0001')) \
        == '/HSE/retired_thing/OLD-0001'


def test_a_filename_cannot_climb_out_of_the_folder():
    entry = Entry('incidents', 'INC-0031')
    path = files.path_for(entry, '../../etc/passwd')
    assert path.startswith('/HSE/Incident & near miss/INC-0031/')
    assert '..' not in path


def test_a_ref_with_separators_cannot_reshape_the_path():
    path = files.folder_for(Entry('incidents', '../../../root'))
    assert path.count('/') == 3, path


def test_allowed_types_are_what_a_compliance_record_carries():
    for name in ('hazard.jpg', 'certificate.PDF', 'report.docx', 'walkthrough.mp4'):
        assert files.is_allowed(name), name
    for name in ('payload.exe', 'macro.xlsm', 'script.sh', 'noextension'):
        assert not files.is_allowed(name), name


def test_extension_is_lowercased_and_safe_on_odd_names():
    assert files.extension('Photo.JPEG') == 'jpeg'
    assert files.extension('no-dot') == ''


def test_a_blank_segment_never_produces_a_double_slash():
    assert files.safe_segment('   ') == 'unnamed'
    assert files.safe_segment('...') == 'unnamed'
