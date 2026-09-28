"""
NAS paths and the upload allowlist for HSE attachments. The bytes go
through core/shared's NAS service.
"""

import re

from app.modules.hse.lib.registers import register


# Everything this module writes lives under this folder.
HSE_NAS_ROOT = '/HSE'

# Photos, documents, spreadsheets and short videos. Kept narrow: this is a
# compliance record, not general file storage.
ALLOWED_EXTENSIONS = {
    'jpg', 'jpeg', 'png', 'heic', 'webp',
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'csv',
    'mp4', 'mov',
}

MAX_BYTES = 25 * 1024 * 1024  # 25 MB

# What the shared preview modal can render. Office files and video are
# download-only.
MIME_TYPES = {
    'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png',
    'heic': 'image/heic', 'webp': 'image/webp', 'pdf': 'application/pdf',
}
PREVIEWABLE = frozenset(MIME_TYPES)


def is_previewable(filename):
    return extension(filename) in PREVIEWABLE

# NAS paths are shared with humans browsing the drive, so keep them boring.
_UNSAFE = re.compile(r'[^A-Za-z0-9 ._&()-]+')


def extension(filename):
    """Lowercase extension, or '' when there isn't one."""
    return filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''


def is_allowed(filename):
    return extension(filename) in ALLOWED_EXTENSIONS


def safe_segment(value):
    """One path segment, stripped of anything that would confuse a file
    browser or the NAS API."""
    cleaned = _UNSAFE.sub('-', (value or '').strip())
    return cleaned.strip('-. ') or 'unnamed'


def folder_for(entry):
    """`/HSE/<register label>/<ref>`. The full path is stored on the
    attachment row, so relabelling a register does not orphan files."""
    reg = register(entry.register)
    label = reg.label if reg else entry.register
    return f'{HSE_NAS_ROOT}/{safe_segment(label)}/{safe_segment(entry.ref)}'


def path_for(entry, filename):
    return f'{folder_for(entry)}/{safe_segment(filename)}'
